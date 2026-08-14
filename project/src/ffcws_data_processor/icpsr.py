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
MATERIAL_HARDSHIP_PAST_YEAR_COMPONENTS = (
    "p6j37",
    "p6j38",
    "p6j39",
    "p6j40",
    "p6j41",
    "p6j42",
    "p6j43",
    "p6j44",
    "p6j45",
    "p6j46",
    "p6j47",
)
MATERIAL_HARDSHIP_SINCE_LAST_VISIT_COMPONENTS = (
    "p6j48",
    "p6j49",
    "p6j50",
    "p6j51",
    "p6j52",
    "p6j53",
    "p6j54",
    "p6j55",
    "p6j56",
    "p6j57",
    "p6j58",
)
MATERIAL_HARDSHIP_COMPONENTS = (
    *MATERIAL_HARDSHIP_PAST_YEAR_COMPONENTS,
    *MATERIAL_HARDSHIP_SINCE_LAST_VISIT_COMPONENTS,
)


@dataclass(frozen=True)
class IcpsrSplits:
    """IDs and outcomes for the development pipeline and untouched lockbox."""

    train: pd.DataFrame
    development_test: pd.DataFrame
    locked_test: pd.DataFrame


@dataclass(frozen=True)
class HouseholdSplitAssignments:
    """A fixed three-way family assignment reused by every ICPSR outcome."""

    assignments: pd.DataFrame


@dataclass(frozen=True)
class MaterialHardshipDistributionTarget:
    """The pre-specified Challenge marginal-distribution target."""

    nonmissing_count: int
    mean: float
    standard_deviation: float
    denominator: int = 11
    mean_tolerance: float = 0.010
    standard_deviation_tolerance: float = 0.010
    minimum_acceptable_maximum_numerator: int = 8


@dataclass(frozen=True)
class MaterialHardshipCandidateValidation:
    """Auditable comparison of one reconstruction candidate with the target."""

    candidate: str
    nonmissing_count: int
    numerators: tuple[int, ...]
    minimum_numerator: int | None
    maximum_numerator: int | None
    mean: float | None
    standard_deviation: float | None
    passed: bool
    failures: tuple[str, ...]


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


def build_material_hardship_candidates(
    background: pd.DataFrame, *, id_column: str
) -> dict[str, pd.DataFrame]:
    """Reconstruct the two pre-specified complete-battery tie-break outcomes."""

    required = {id_column, *MATERIAL_HARDSHIP_COMPONENTS}
    missing = required - set(background.columns)
    if missing:
        raise KeyError(
            "ICPSR background is missing material-hardship component(s): "
            f"{sorted(missing)}"
        )
    def battery_score(components: tuple[str, ...]) -> tuple[pd.Series, pd.Series]:
        battery = background.loc[:, list(components)].apply(pd.to_numeric, errors="coerce")
        complete = battery.isin([1, 2]).all(axis=1)
        score = battery.eq(1).sum(axis=1).where(complete).astype(float) / len(components)
        return score, complete

    past_year, past_year_complete = battery_score(MATERIAL_HARDSHIP_PAST_YEAR_COMPONENTS)
    since_last_visit, since_last_visit_complete = battery_score(
        MATERIAL_HARDSHIP_SINCE_LAST_VISIT_COMPONENTS
    )
    candidates = {
        "past_year_preferred": pd.DataFrame(
            {
                id_column: background[id_column],
                "materialHardship": past_year.where(past_year_complete, since_last_visit),
            }
        ),
        "since_last_visit_preferred": pd.DataFrame(
            {
                id_column: background[id_column],
                "materialHardship": since_last_visit.where(
                    since_last_visit_complete, past_year
                ),
            }
        ),
    }
    for candidate, outcomes in candidates.items():
        ensure_unique_ids(outcomes, id_column, f"ICPSR materialHardship candidate {candidate}")
    return candidates


def validate_material_hardship_candidate(
    outcomes: pd.DataFrame,
    *,
    candidate: str,
    target: MaterialHardshipDistributionTarget,
) -> MaterialHardshipCandidateValidation:
    """Validate an outcome reconstruction against the immutable M2 target."""

    if "materialHardship" not in outcomes:
        raise KeyError("Material-hardship candidate is missing the outcome column")
    observed = pd.to_numeric(outcomes["materialHardship"], errors="coerce").dropna()
    numerators = observed.mul(target.denominator)
    rounded = numerators.round()
    failures: list[str] = []
    if not np.allclose(numerators.to_numpy(), rounded.to_numpy(), atol=1e-12, rtol=0.0):
        failures.append(f"values are not integer multiples of 1/{target.denominator}")
    integer_numerators = tuple(sorted(set(rounded.astype(int).tolist())))
    maximum = max(integer_numerators) if integer_numerators else None
    minimum = min(integer_numerators) if integer_numerators else None
    if minimum is None or minimum < 0 or maximum is None or maximum > target.denominator:
        failures.append(
            "numerators must lie between 0 and the fixed denominator "
            f"{target.denominator}"
        )
    if maximum is None or maximum < target.minimum_acceptable_maximum_numerator:
        failures.append(
            f"maximum numerator is {maximum}, below the required "
            f"{target.minimum_acceptable_maximum_numerator}"
        )
    mean = float(observed.mean()) if not observed.empty else None
    standard_deviation = float(observed.std(ddof=1)) if len(observed) > 1 else None
    if mean is None or abs(mean - target.mean) > target.mean_tolerance:
        failures.append(
            f"mean is {mean}, outside {target.mean} +/- {target.mean_tolerance}"
        )
    if (
        standard_deviation is None
        or abs(standard_deviation - target.standard_deviation)
        > target.standard_deviation_tolerance
    ):
        failures.append(
            "standard deviation is "
            f"{standard_deviation}, outside {target.standard_deviation} +/- "
            f"{target.standard_deviation_tolerance}"
        )
    return MaterialHardshipCandidateValidation(
        candidate=candidate,
        nonmissing_count=int(len(observed)),
        numerators=integer_numerators,
        minimum_numerator=minimum,
        maximum_numerator=maximum,
        mean=mean,
        standard_deviation=standard_deviation,
        passed=not failures,
        failures=tuple(failures),
    )


def select_validated_material_hardship_candidate(
    candidates: Mapping[str, pd.DataFrame],
    *,
    selected_candidate: str,
    target: MaterialHardshipDistributionTarget,
) -> tuple[pd.DataFrame, tuple[MaterialHardshipCandidateValidation, ...]]:
    """Return the pre-specified tie-break candidate only when it passes M2."""

    if selected_candidate not in candidates:
        raise ValueError(
            "Configured material-hardship candidate is unavailable: "
            f"{selected_candidate}"
        )
    validations = tuple(
        validate_material_hardship_candidate(
            outcomes, candidate=candidate, target=target
        )
        for candidate, outcomes in candidates.items()
    )
    selected_validation = next(
        validation
        for validation in validations
        if validation.candidate == selected_candidate
    )
    if not selected_validation.passed:
        raise ValueError(
            "Material-hardship M2 distribution target did not match the pre-specified "
            f"candidate {selected_candidate!r}; analysis is blocked: "
            f"{'; '.join(selected_validation.failures)}"
        )
    return candidates[selected_candidate].copy(), validations


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


def _largest_remainder_counts(
    size: int, fractions: np.ndarray
) -> np.ndarray:
    """Allocate integer split counts with the established stable tie break."""

    raw_counts = size * fractions
    counts = np.floor(raw_counts).astype(int)
    for index in np.argsort(-(raw_counts - counts), kind="stable")[: size - counts.sum()]:
        counts[index] += 1
    return counts


def extend_icpsr_household_splits(
    household_ids: pd.Series,
    gpa_outcomes: pd.DataFrame,
    *,
    id_column: str,
    seed: int,
    train_fraction: float,
    development_fraction: float,
    locked_fraction: float,
) -> HouseholdSplitAssignments:
    """Extend the established GPA split to all families without moving GPA IDs."""

    ids = pd.DataFrame({id_column: household_ids}).copy()
    ensure_unique_ids(ids, id_column, "ICPSR household universe")
    fractions = np.array([train_fraction, development_fraction, locked_fraction])
    if not np.isclose(fractions.sum(), 1.0) or bool((fractions <= 0).any()):
        raise ValueError("ICPSR split fractions must be positive and sum to 1")
    gpa_split = split_icpsr_gpa(
        gpa_outcomes,
        id_column=id_column,
        seed=seed,
        train_fraction=train_fraction,
        development_fraction=development_fraction,
        locked_fraction=locked_fraction,
    )
    parts = (
        ("train", gpa_split.train),
        ("development", gpa_split.development_test),
        ("locked", gpa_split.locked_test),
    )
    gpa_assignments = pd.concat(
        [
            frame.loc[:, [id_column]].assign(split=split_name)
            for split_name, frame in parts
        ],
        ignore_index=True,
    )
    desired_counts = _largest_remainder_counts(len(ids), fractions)
    gpa_counts = np.array([len(frame) for _name, frame in parts])
    additional_counts = desired_counts - gpa_counts
    if bool((additional_counts < 0).any()):
        raise ValueError("GPA split already exceeds an all-household split quota")
    additional_ids = ids.loc[
        ~ids[id_column].isin(gpa_assignments[id_column]), id_column
    ].to_numpy()
    permutation = np.random.default_rng(seed).permutation(len(additional_ids))
    shuffled_additional = additional_ids[permutation]
    additional_assignments = pd.DataFrame(
        {
            id_column: shuffled_additional,
            "split": np.repeat(
                np.array(["train", "development", "locked"]), additional_counts
            ),
        }
    )
    assignments = pd.concat([gpa_assignments, additional_assignments], ignore_index=True)
    ensure_unique_ids(assignments, id_column, "ICPSR household split assignments")
    if len(assignments) != len(ids) or set(assignments[id_column]) != set(ids[id_column]):
        raise AssertionError("Household split assignments are not a partition of all families")
    if not np.array_equal(
        assignments["split"].value_counts().reindex(["train", "development", "locked"]).to_numpy(),
        desired_counts,
    ):
        raise AssertionError("All-household split counts do not match the configured allocation")
    for split_name, frame in parts:
        expected_gpa_ids = set(frame[id_column])
        assigned_gpa_ids = set(
            assignments.loc[
                assignments["split"].eq(split_name)
                & assignments[id_column].isin(gpa_assignments[id_column]),
                id_column,
            ]
        )
        if assigned_gpa_ids != expected_gpa_ids:
            raise AssertionError(f"GPA {split_name} assignment changed during extension")
    return HouseholdSplitAssignments(assignments=assignments)


def split_outcome_by_household_assignment(
    outcomes: pd.DataFrame,
    assignments: HouseholdSplitAssignments,
    *,
    id_column: str,
    outcome: str,
) -> IcpsrSplits:
    """Intersect one valid outcome with the fixed whole-family split assignment."""

    required = {id_column, outcome}
    missing = required - set(outcomes.columns)
    if missing:
        raise KeyError(f"Outcome split is missing columns: {sorted(missing)}")
    valid = outcomes.loc[outcomes[outcome].notna(), [id_column, outcome]].copy()
    ensure_unique_ids(valid, id_column, f"ICPSR {outcome} analysis sample")
    assigned = valid.merge(
        assignments.assignments, on=id_column, how="left", validate="one_to_one"
    )
    if assigned["split"].isna().any():
        raise AssertionError("Valid outcome rows are missing a household split assignment")
    split_frames = {
        split_name: assigned.loc[assigned["split"].eq(split_name), [id_column, outcome]]
        .reset_index(drop=True)
        for split_name in ("train", "development", "locked")
    }
    return IcpsrSplits(
        train=split_frames["train"],
        development_test=split_frames["development"],
        locked_test=split_frames["locked"],
    )


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
