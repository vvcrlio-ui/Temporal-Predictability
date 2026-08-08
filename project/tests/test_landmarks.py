from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ffcws_data_processor.landmarks import (
    LANDMARK_WAVE_LIMITS,
    derive_source_wave_labels,
    export_landmark_schemas,
    source_wave_numbers,
    unassigned_source_columns,
)


def _synthetic_manifest(source_columns: list[str]) -> pd.DataFrame:
    rows = []
    for source_order, source in enumerate(source_columns):
        rows.append(
            {
                "source_column": source,
                "feature_name": f"X_{source}",
                "kind": "X",
                "strategy": "median_mode",
                "keep": True,
                "reason": "kept",
                "source_order": source_order,
                "feature_order": 0,
                "unit_type": "continuous",
                "drop_first": False,
                "is_reference": False,
                "reference_level": None,
                "level_value": None,
                "ordinal_levels": None,
                "source_prior": None,
                "prevalence": None,
                "observed_variance": None,
                "mapping_id": "",
            }
        )
    return pd.DataFrame(rows)


def _write_synthetic_ard(dataset_dir: Path, manifest: pd.DataFrame) -> None:
    dataset_dir.mkdir(parents=True)
    manifest.to_csv(dataset_dir / "feature_manifest.csv", index=False)
    predictors = manifest["feature_name"].tolist()
    data = pd.DataFrame(
        {
            "challengeID": [1, 2, 3],
            "gpa": [2.0, 2.5, 3.0],
            **{feature: [0.0, 1.0, 2.0] for feature in predictors},
        }
    )
    test = data.assign(challengeID=[4, 5, 6])
    data.to_parquet(dataset_dir / "data.parquet", index=False)
    test.to_parquet(dataset_dir / "test.parquet", index=False)


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("m1birth_item", "出生"),
        ("p2one_year_item", "1 岁"),
        ("hv3three_year_item", "3 岁"),
        ("f4five_year_item", "5 岁"),
        ("t5nine_year_item", "9 岁"),
    ],
)
def test_derive_source_wave_labels_maps_each_supported_collection_wave(
    source: str, label: str
) -> None:
    assert derive_source_wave_labels([source]) == {source: label}


def test_derive_source_wave_labels_keeps_unassigned_sources_separate() -> None:
    sources = ["m1birth", "innatsm", "p2one_year", "legacy", "z6future"]

    assert derive_source_wave_labels(sources) == {
        "m1birth": "出生",
        "p2one_year": "1 岁",
    }
    assert unassigned_source_columns(sources) == ("innatsm", "legacy", "z6future")


def test_landmark_export_is_strictly_nested_and_excludes_future_sources(
    tmp_path: Path,
) -> None:
    sources = ["m1birth", "p2one_year", "hv3three_year", "f4five_year", "t5nine_year", "legacy"]
    dataset_dir = tmp_path / "ard" / "synthetic_gpa"
    manifest = _synthetic_manifest(sources)
    _write_synthetic_ard(dataset_dir, manifest)

    artifacts = export_landmark_schemas(
        dataset_dir=dataset_dir,
        schema_root=tmp_path / "schema",
        dataset="synthetic_gpa",
        outcome="gpa",
        id_column="challengeID",
    )

    assert pd.read_csv(artifacts.unassigned_sources_path)["source_column"].tolist() == [
        "legacy"
    ]
    wave_numbers = source_wave_numbers(sources)
    previous_predictors: set[str] | None = None
    for landmark, maximum_wave in LANDMARK_WAVE_LIMITS:
        schema_path = artifacts.schema_paths[landmark]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        predictors = set(schema["predictor_columns"])
        assert schema["dataset"] == f"synthetic_gpa_lm{landmark}"
        assert schema["split_mode"] == "external_test"
        assert (schema_path.parent / schema["table"]).resolve() == (
            dataset_dir / "data.parquet"
        ).resolve()
        assert (schema_path.parent / schema["test_table"]).resolve() == (
            dataset_dir / "test.parquet"
        ).resolve()
        assert not (artifacts.manifest_paths[landmark].parent / "data.parquet").exists()
        assert not (artifacts.manifest_paths[landmark].parent / "test.parquet").exists()

        landmark_manifest = pd.read_csv(artifacts.manifest_paths[landmark])
        for row in landmark_manifest.itertuples(index=False):
            assert wave_numbers[row.source_column] <= maximum_wave
        assert "X_legacy" not in predictors
        if previous_predictors is not None:
            assert previous_predictors < predictors
        previous_predictors = predictors


def test_landmark_export_rejects_an_input_without_strictly_growing_horizons(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "ard" / "missing_wave"
    _write_synthetic_ard(
        dataset_dir,
        _synthetic_manifest(["m1birth", "p2one_year", "hv3three_year", "t5nine_year"]),
    )

    with pytest.raises(ValueError, match="strictly nested"):
        export_landmark_schemas(
            dataset_dir=dataset_dir,
            schema_root=tmp_path / "schema",
            dataset="missing_wave",
            outcome="gpa",
            id_column="challengeID",
        )


REAL_DATASET_DIR = PROJECT_ROOT / "data" / "ard" / "ffc_median_mode_gpa"
_REAL_ARTIFACTS_PRESENT = all(
    (REAL_DATASET_DIR / name).is_file()
    for name in ("data.parquet", "test.parquet", "feature_manifest.csv")
)


@pytest.mark.skipif(
    not _REAL_ARTIFACTS_PRESENT,
    reason="Real FFCWS ARD artifacts are not available in this checkout.",
)
def test_real_ffcws_landmark_export_is_nested_and_has_no_future_wave_columns(
    tmp_path: Path,
) -> None:
    source_manifest = pd.read_csv(REAL_DATASET_DIR / "feature_manifest.csv")
    test_dataset_dir = tmp_path / "ard" / "ffc_median_mode_gpa"
    test_dataset_dir.mkdir(parents=True)
    source_manifest.to_csv(test_dataset_dir / "feature_manifest.csv", index=False)
    for table_name in ("data.parquet", "test.parquet"):
        (test_dataset_dir / table_name).symlink_to(REAL_DATASET_DIR / table_name)
    artifacts = export_landmark_schemas(
        dataset_dir=test_dataset_dir,
        schema_root=tmp_path / "schema",
        dataset="ffc_median_mode_gpa",
        outcome="gpa",
        id_column="challengeID",
    )

    source_by_feature = source_manifest.set_index("feature_name")["source_column"]
    source_waves = source_wave_numbers(source_manifest["source_column"])
    unassigned = set(unassigned_source_columns(source_manifest["source_column"]))
    previous_predictors: set[str] | None = None
    for landmark, maximum_wave in LANDMARK_WAVE_LIMITS:
        schema = json.loads(artifacts.schema_paths[landmark].read_text(encoding="utf-8"))
        predictors = set(schema["predictor_columns"])
        predictor_sources = {str(source_by_feature[feature]) for feature in predictors}
        assert not predictor_sources & unassigned
        assert all(source_waves[source] <= maximum_wave for source in predictor_sources)
        if previous_predictors is not None:
            assert previous_predictors < predictors
        previous_predictors = predictors
