"""Export FFCWS wave-labelled landmark schemas from an existing ARD table."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from .common.io import write_frame
from .contract import write_engine_schema


WAVE_LABELS: Mapping[int, str] = {
    1: "出生",
    2: "1 岁",
    3: "3 岁",
    4: "5 岁",
    5: "9 岁",
}
"""FFCWS collection-wave labels, keyed by the source-name wave number."""

LANDMARK_WAVE_LIMITS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (3, 3),
    (5, 4),
    (9, 5),
)
"""(Observation-age landmark, maximum collection-wave number) pairs."""

_SOURCE_WAVE_RE = re.compile(r"^[A-Za-z]+(\d)")
_OFFICIAL_WAVE_NUMBERS: Mapping[str, int] = {
    "Baseline": 1,
    "Year 1": 2,
    "Year 3": 3,
    "Year 5": 4,
    "Year 9": 5,
}
_FORBIDDEN_OFFICIAL_WAVES = frozenset({"Year 15", "Year 22"})


@dataclass(frozen=True)
class LandmarkSchemaArtifacts:
    """Paths emitted for one GPA (or other outcome) landmark export."""

    source_wave_labels_path: Path
    unassigned_sources_path: Path
    schema_paths: Mapping[int, Path]
    manifest_paths: Mapping[int, Path]


def _ordered_unique(source_columns: Iterable[object]) -> tuple[str, ...]:
    sources: list[str] = []
    seen: set[str] = set()
    for value in source_columns:
        if not isinstance(value, str) or not value:
            raise ValueError("source_column values must be non-empty strings")
        if value not in seen:
            sources.append(value)
            seen.add(value)
    return tuple(sources)


def source_wave_numbers(source_columns: Iterable[object]) -> dict[str, int]:
    """Return supported collection-wave numbers parsed from FFCWS source names.

    A source is eligible only when the first digit immediately following its
    alphabetic prefix is one of the documented FFCWS collection waves.  Sources
    without such a number are deliberately omitted rather than guessed.
    """

    result: dict[str, int] = {}
    for source in _ordered_unique(source_columns):
        match = _SOURCE_WAVE_RE.match(source)
        if match is None:
            continue
        wave = int(match.group(1))
        if wave in WAVE_LABELS:
            result[source] = wave
    return result


def derive_source_wave_labels(source_columns: Iterable[object]) -> dict[str, str]:
    """Map each assigned source column to its FFCWS collection-wave label."""

    return {
        source: WAVE_LABELS[wave]
        for source, wave in source_wave_numbers(source_columns).items()
    }


def unassigned_source_columns(source_columns: Iterable[object]) -> tuple[str, ...]:
    """Return source columns that cannot be assigned to waves 1--5."""

    sources = _ordered_unique(source_columns)
    assigned = source_wave_numbers(sources)
    return tuple(source for source in sources if source not in assigned)


def _landmark_manifest(
    manifest: pd.DataFrame,
    source_waves: Mapping[str, int],
    *,
    maximum_wave: int,
) -> pd.DataFrame:
    included_sources = {
        source for source, wave in source_waves.items() if wave <= maximum_wave
    }
    return manifest.loc[manifest["source_column"].isin(included_sources)].copy()


def _keep_mask(values: pd.Series) -> pd.Series:
    return values.map(
        lambda value: (
            bool(value)
            if isinstance(value, bool)
            else str(value).strip().lower() == "true"
        )
    )


def _manifest_wave_numbers(manifest: pd.DataFrame) -> tuple[dict[str, int], tuple[str, ...]]:
    """Read metadata-backed wave assignments from an ICPSR feature manifest."""

    if "wave" not in manifest:
        raise ValueError("ICPSR landmark export requires a manifest 'wave' column")
    source_wave = (
        manifest.loc[:, ["source_column", "wave"]]
        .drop_duplicates()
        .groupby("source_column", sort=False)["wave"]
        .agg(lambda values: tuple(pd.unique(values.dropna())))
    )
    waves: dict[str, int] = {}
    unassigned: list[str] = []
    for source, values in source_wave.items():
        if len(values) != 1:
            unassigned.append(str(source))
            continue
        wave = str(values[0])
        number = _OFFICIAL_WAVE_NUMBERS.get(wave)
        if number is None:
            unassigned.append(str(source))
        else:
            waves[str(source)] = number
    return waves, tuple(unassigned)


def export_landmark_schemas(
    *,
    dataset_dir: Path,
    schema_root: Path,
    dataset: str,
    outcome: str,
    id_column: str,
    adapter_contract_version: str = "ffcws-adapter-v1",
    use_manifest_wave: bool = False,
    forbidden_source_columns: Iterable[str] = (),
) -> LandmarkSchemaArtifacts:
    """Write five nested schemas that reuse an existing external-test ARD pair.

    ``dataset_dir`` is the existing complete-outcome ARD directory.  The export
    only writes landmark manifests and provenance below it; all schemas point
    back to its single ``data.parquet`` and ``test.parquet`` files.
    """

    dataset_dir = Path(dataset_dir)
    schema_root = Path(schema_root)
    manifest_path = dataset_dir / "feature_manifest.csv"
    table_path = dataset_dir / "data.parquet"
    test_path = dataset_dir / "test.parquet"
    for required_path in (manifest_path, table_path, test_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"Required ARD artifact is missing: {required_path}")

    manifest = pd.read_csv(manifest_path)
    required_columns = {"source_column", "feature_name", "keep"}
    missing_columns = required_columns - set(manifest.columns)
    if missing_columns:
        raise ValueError(
            "Feature manifest is missing required columns: "
            f"{sorted(missing_columns)}"
        )
    sources = _ordered_unique(manifest["source_column"].tolist())
    if use_manifest_wave:
        source_waves, unassigned = _manifest_wave_numbers(manifest)
        source_labels = {
            source: WAVE_LABELS[wave] for source, wave in source_waves.items()
        }
        forbidden_waves = manifest.loc[
            manifest["wave"].isin(_FORBIDDEN_OFFICIAL_WAVES), "source_column"
        ].astype(str)
        forbidden_sources = set(forbidden_source_columns) | set(forbidden_waves)
    else:
        source_waves = source_wave_numbers(sources)
        source_labels = derive_source_wave_labels(sources)
        unassigned = unassigned_source_columns(sources)
        forbidden_sources = set(forbidden_source_columns)

    labels_path = dataset_dir / "source_wave_labels.csv"
    write_frame(
        labels_path,
        pd.DataFrame(
            [
                {
                    "source_column": source,
                    "wave_number": source_waves[source],
                    "wave_label": source_labels[source],
                }
                for source in sources
                if source in source_waves
            ]
        ),
    )
    unassigned_path = dataset_dir / "unassigned_sources.csv"
    write_frame(
        unassigned_path,
        pd.DataFrame(
            {
                "source_column": list(unassigned),
                "reason": "no_supported_wave_number_in_alphabetic_prefix",
            }
        ),
    )

    schema_paths: dict[int, Path] = {}
    landmark_manifests: dict[int, Path] = {}
    previous_predictors: set[str] | None = None
    for landmark, maximum_wave in LANDMARK_WAVE_LIMITS:
        landmark_dir = dataset_dir / "landmarks" / f"lm{landmark}"
        landmark_manifest = _landmark_manifest(
            manifest,
            source_waves,
            maximum_wave=maximum_wave,
        )
        output_manifest_path = landmark_dir / "feature_manifest.csv"
        write_frame(output_manifest_path, landmark_manifest)
        landmark_dataset = f"{dataset}_lm{landmark}"
        schema_path = write_engine_schema(
            schema_root=schema_root,
            dataset_dir=landmark_dir,
            dataset=landmark_dataset,
            outcome=outcome,
            table_path=table_path,
            test_path=test_path,
            manifest_path=output_manifest_path,
            manifest=landmark_manifest,
            id_column=id_column,
            adapter_contract_version=adapter_contract_version,
        )
        predictors = {
            str(value)
            for value in landmark_manifest.loc[
                _keep_mask(landmark_manifest["keep"]), "feature_name"
            ]
        }
        predictor_sources = set(
            landmark_manifest.loc[
                _keep_mask(landmark_manifest["keep"]), "source_column"
            ].astype(str)
        )
        leaked_sources = predictor_sources & forbidden_sources
        if leaked_sources:
            raise ValueError(
                "Landmark predictors contain forbidden outcome/future sources: "
                f"{sorted(leaked_sources)}"
            )
        future_sources = {
            source for source in predictor_sources if source_waves.get(source, 99) > maximum_wave
        }
        if future_sources:
            raise ValueError(
                f"Landmark {landmark} includes a future-wave source: {sorted(future_sources)}"
            )
        if previous_predictors is not None and not previous_predictors < predictors:
            raise ValueError(
                "Landmark predictor sets must be strictly nested; "
                f"landmark {landmark} did not add any predictor"
            )
        previous_predictors = predictors
        schema_paths[landmark] = schema_path
        landmark_manifests[landmark] = output_manifest_path

    return LandmarkSchemaArtifacts(
        source_wave_labels_path=labels_path,
        unassigned_sources_path=unassigned_path,
        schema_paths=schema_paths,
        manifest_paths=landmark_manifests,
    )
