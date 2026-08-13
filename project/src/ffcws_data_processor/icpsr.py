"""ICPSR-specific input, outcome, split, and metadata contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .common.schema import SourceSpec, numeric_values
from .common.validation import ensure_disjoint_ids, ensure_unique_ids


ICPSR_METADATA_ENCODING = "latin-1"
ICPSR_METADATA_COLUMNS = ("new_name", "old_name", "wave", "respondent")
PREDICTOR_WAVES = ("Baseline", "Year 1", "Year 3", "Year 5", "Year 9")
DISALLOWED_PREDICTOR_WAVES = ("Year 15", "Year 22")
GPA_COMPONENTS = ("k6b20a", "k6b20b", "k6b20c", "k6b20d")


@dataclass(frozen=True)
class IcpsrSplits:
    """IDs and outcomes for the development pipeline and untouched lockbox."""

    train: pd.DataFrame
    development_test: pd.DataFrame
    locked_test: pd.DataFrame


def normalize_columns_lower(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Lowercase source columns exactly once and reject case-fold collisions."""

    normalized = [str(column).lower() for column in frame.columns]
    duplicates = pd.Series(normalized).duplicated(keep=False)
    if bool(duplicates.any()):
        collisions = sorted(set(pd.Series(normalized)[duplicates].tolist()))
        raise ValueError(f"{label} has columns that collide after lowercasing: {collisions}")
    result = frame.copy()
    result.columns = normalized
    return result


def normalize_value_labels_lower(
    labels: Mapping[str, Mapping[object, str]]
) -> dict[str, dict[object, str]]:
    """Apply the same one-time column normalization to Stata value labels."""

    normalized: dict[str, dict[object, str]] = {}
    for column, mapping in labels.items():
        key = str(column).lower()
        if key in normalized:
            raise ValueError(f"Value-label columns collide after lowercasing: {key}")
        normalized[key] = dict(mapping)
    return normalized


def read_icpsr_metadata(path: Path) -> pd.DataFrame:
    """Read the official metadata using its documented latin-1 encoding."""

    metadata = pd.read_csv(
        path,
        encoding=ICPSR_METADATA_ENCODING,
        usecols=list(ICPSR_METADATA_COLUMNS),
    )
    missing = set(ICPSR_METADATA_COLUMNS) - set(metadata.columns)
    if missing:
        raise ValueError(f"ICPSR metadata is missing required columns: {sorted(missing)}")
    return metadata.loc[:, list(ICPSR_METADATA_COLUMNS)].copy()


def _unique_metadata_record(matches: pd.DataFrame) -> pd.Series | None:
    """Return one metadata record only when wave/respondent are unambiguous."""

    records = matches.loc[:, ["wave", "respondent"]].drop_duplicates()
    if len(records) != 1:
        return None
    return records.iloc[0]


def metadata_for_sources(
    metadata: pd.DataFrame, sources: Iterable[str]
) -> pd.DataFrame:
    """Attach official wave/respondent values to normalized raw source names."""

    normalized = metadata.copy()
    for column in ("new_name", "old_name"):
        normalized[column] = normalized[column].astype("string").str.strip().str.lower()
    rows: list[dict[str, object]] = []
    for source in sources:
        new_name_matches = normalized.loc[normalized["new_name"].eq(source)]
        record = _unique_metadata_record(new_name_matches)
        match_method = "new_name" if record is not None else None
        if record is None and new_name_matches.empty:
            old_name_matches = normalized.loc[normalized["old_name"].eq(source)]
            record = _unique_metadata_record(old_name_matches)
            match_method = "old_name" if record is not None else None
        rows.append(
            {
                "source_column": source,
                "wave": None if record is None or pd.isna(record["wave"]) else str(record["wave"]),
                "respondent": (
                    None
                    if record is None or pd.isna(record["respondent"])
                    else str(record["respondent"])
                ),
                "metadata_match": record is not None,
                "metadata_match_method": match_method,
            }
        )
    return pd.DataFrame(rows)


def regex_wave_number(source: str) -> int | None:
    """Return the legacy name-derived wave number for a diagnostic comparison."""

    import re

    match = re.match(r"^[A-Za-z]+(\d)", source)
    if match is None:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 5 else None


def wave_number(wave: object) -> int | None:
    return {
        "Baseline": 1,
        "Year 1": 2,
        "Year 3": 3,
        "Year 5": 4,
        "Year 9": 5,
    }.get(str(wave))


def wave_diagnostics(source_metadata: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return metadata-first assignment and every legacy-regex disagreement."""

    assigned = source_metadata.copy()
    assigned["metadata_wave_number"] = assigned["wave"].map(wave_number)
    assigned["regex_wave_number"] = assigned["source_column"].map(regex_wave_number)
    mismatch = assigned.loc[
        assigned["metadata_wave_number"].notna()
        & (assigned["metadata_wave_number"] != assigned["regex_wave_number"])
    ].copy()
    return assigned, mismatch


def build_gpa_outcomes(background: pd.DataFrame, *, id_column: str) -> pd.DataFrame:
    """Reconstruct Year-15 GPA from four complete, reverse-coded subjects."""

    required = {id_column, *GPA_COMPONENTS}
    missing = required - set(background.columns)
    if missing:
        raise KeyError(f"ICPSR background is missing GPA component(s): {sorted(missing)}")
    components = pd.DataFrame(
        {column: pd.to_numeric(background[column], errors="coerce") for column in GPA_COMPONENTS}
    )
    valid = components.where(components.isin([1, 2, 3, 4]))
    reversed_components = 5 - valid
    gpa = reversed_components.mean(axis=1).where(valid.notna().all(axis=1))
    outcomes = pd.DataFrame({id_column: background[id_column], "gpa": gpa.astype(float)})
    ensure_unique_ids(outcomes, id_column, "ICPSR GPA outcomes")
    return outcomes


def split_icpsr_gpa(
    outcomes: pd.DataFrame,
    *,
    id_column: str,
    seed: int,
    train_fraction: float,
    development_fraction: float,
    locked_fraction: float,
) -> IcpsrSplits:
    """Create a reproducible disjoint 65/17.5/17.5 analysis split.

    Counts use largest-remainder allocation so the configured proportions are
    respected as closely as integer row counts permit, with ties broken in the
    stable order train, development, locked.
    """

    fractions = np.array([train_fraction, development_fraction, locked_fraction])
    if not np.isclose(fractions.sum(), 1.0):
        raise ValueError("ICPSR split fractions must sum to 1")
    if bool((fractions <= 0).any()):
        raise ValueError("ICPSR split fractions must all be positive")
    analysis = outcomes.loc[outcomes["gpa"].notna(), [id_column, "gpa"]].copy()
    if analysis.empty:
        raise ValueError("ICPSR GPA reconstruction produced no valid analysis rows")
    ensure_unique_ids(analysis, id_column, "ICPSR analysis sample")
    raw_counts = len(analysis) * fractions
    counts = np.floor(raw_counts).astype(int)
    for index in np.argsort(-(raw_counts - counts), kind="stable")[: len(analysis) - counts.sum()]:
        counts[index] += 1
    permutation = np.random.default_rng(seed).permutation(len(analysis))
    shuffled = analysis.iloc[permutation].reset_index(drop=True)
    train_end = int(counts[0])
    development_end = train_end + int(counts[1])
    split = IcpsrSplits(
        train=shuffled.iloc[:train_end].reset_index(drop=True),
        development_test=shuffled.iloc[train_end:development_end].reset_index(drop=True),
        locked_test=shuffled.iloc[development_end:].reset_index(drop=True),
    )
    ensure_disjoint_ids(split.train, split.development_test, id_column=id_column)
    ensure_disjoint_ids(split.train, split.locked_test, id_column=id_column)
    ensure_disjoint_ids(split.development_test, split.locked_test, id_column=id_column)
    return split


def candidate_icpsr_predictor_sources(
    source_metadata: pd.DataFrame,
    *,
    outcome_sources: Iterable[str] = GPA_COMPONENTS,
) -> set[str]:
    """Select only official Baseline--Year 9 predictors, never outcomes."""

    forbidden = set(outcome_sources)
    return set(
        source_metadata.loc[
            source_metadata["wave"].isin(PREDICTOR_WAVES)
            & ~source_metadata["source_column"].isin(forbidden),
            "source_column",
        ].astype(str)
    )


def continuous_negative_code_summary(
    background: pd.DataFrame, sources: Iterable[SourceSpec]
) -> pd.DataFrame:
    """Quantify nonstandard negative values masked in continuous predictors."""

    rows: list[dict[str, object]] = []
    for source in sources:
        threshold = source.continuous_negative_missing_threshold
        if source.status != "numeric" or threshold is None:
            continue
        numeric, _raw, _blank, _coded = numeric_values(background[source.source_column])
        rows.append(
            {
                "source_column": source.source_column,
                "kind": "X",
                "threshold": threshold,
                "cells_masked": int((numeric <= threshold).sum()),
            }
        )
    return pd.DataFrame(rows, columns=["source_column", "kind", "threshold", "cells_masked"])
