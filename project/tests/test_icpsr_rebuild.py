from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ffcws_data_processor.common.schema import SchemaConfig, build_shared_schema
from ffcws_data_processor.icpsr import (
    GPA_COMPONENTS,
    build_gpa_outcomes,
    metadata_for_sources,
    normalize_columns_lower,
    read_icpsr_metadata,
    split_icpsr_gpa,
    wave_diagnostics,
)
from ffcws_data_processor.landmarks import export_landmark_schemas
from ffcws_data_processor.pipeline import run_pipeline
from ffcws_data_processor.strategies.median_mode import encode_median_mode


def test_route_configs_keep_distinct_contract_versions() -> None:
    challenge = yaml.safe_load(
        (PROJECT_ROOT / "config" / "ffc.yaml").read_text(encoding="utf-8")
    )
    icpsr = yaml.safe_load(
        (PROJECT_ROOT / "config" / "ffc_icpsr.yaml").read_text(encoding="utf-8")
    )
    assert challenge["contract_version"] == "ffcws-adapter-v1"
    assert icpsr["contract_version"] == "ffcws-adapter-v2"


@pytest.mark.parametrize("columns", [["IDNUM", "M1A"], ["idnum", "m1a"]])
def test_icpsr_column_lowercasing_is_idempotent(columns: list[str]) -> None:
    frame = pd.DataFrame([[1, 2]], columns=columns)
    once = normalize_columns_lower(frame, label="synthetic")
    twice = normalize_columns_lower(once, label="synthetic")
    assert once.columns.tolist() == ["idnum", "m1a"]
    assert twice.equals(once)


@pytest.mark.parametrize("code", list(range(-18, -9)))
def test_icpsr_negative_codes_are_categories_or_missing_by_kind(code: int) -> None:
    ids = list(range(30))
    background = pd.DataFrame(
        {
            "idnum": ids,
            "category": [code, 0, 1] * 10,
            "continuous": [code, *range(1, 30)],
        }
    )
    schema = build_shared_schema(
        background,
        ids,
        value_labels={"category": {code: "substantive", 0: "zero", 1: "one"}},
        config=SchemaConfig(
            id_column="idnum",
            categorical_max_levels=3,
            continuous_negative_missing_threshold=-10,
        ),
    )
    category, continuous = schema.sources
    encoded = encode_median_mode(background, schema)
    assert category.status == "categorical"
    assert float(code) in category.levels
    assert encoded.features.loc[0, f"C_category__{code}__substantive"] == 1.0
    assert encoded.features[f"C_category__{code}__substantive"].dtype == np.dtype(float)
    assert continuous.status == "numeric"
    assert np.isnan(encoded.features.loc[0, "X_continuous"])
    assert encoded.features.loc[1, "X_continuous"] == 1.0
    assert encoded.features["X_continuous"].dtype == np.dtype(float)


@pytest.mark.parametrize("encoding", ["latin-1", "utf-8"])
def test_icpsr_metadata_encoding_is_explicit(tmp_path: Path, encoding: str) -> None:
    path = tmp_path / "metadata.csv"
    path.write_bytes(b"new_name,old_name,wave,respondent\nM1A,,Baseline,Interviewer\xe9\n")
    if encoding == "latin-1":
        frame = read_icpsr_metadata(path)
        assert frame.loc[0, "respondent"] == "Intervieweré"
    else:
        with pytest.raises(UnicodeDecodeError):
            pd.read_csv(path, encoding=encoding)


@pytest.mark.parametrize("source,wave", [("m1conflict", "Year 9"), ("k6b20a", "Year 15")])
def test_metadata_wave_overrides_regex_and_records_disagreement(source: str, wave: str) -> None:
    metadata = pd.DataFrame(
        {"new_name": [source], "old_name": [None], "wave": [wave], "respondent": ["Child"]}
    )
    assignment, mismatches = wave_diagnostics(metadata_for_sources(metadata, [source]))
    assert assignment.loc[0, "wave"] == wave
    if source == "m1conflict":
        assert mismatches["source_column"].tolist() == [source]


@pytest.mark.parametrize(
    ("grades", "expected"),
    [
        ((1, 2, 3, 4), 2.5),
        ((4, 4, 4, 4), 1.0),
        ((1, 1, 1, 1), 4.0),
        ((1, 2, 5, 4), np.nan),
        ((1, 2, 7, 4), np.nan),
        ((1, 2, -1, 4), np.nan),
    ],
)
def test_gpa_rebuild_requires_four_valid_reverse_coded_subjects(
    grades: tuple[int, int, int, int], expected: float
) -> None:
    frame = pd.DataFrame({"idnum": [1], **dict(zip(GPA_COMPONENTS, [[value] for value in grades]))})
    observed = build_gpa_outcomes(frame, id_column="idnum").loc[0, "gpa"]
    if np.isnan(expected):
        assert np.isnan(observed)
    else:
        assert observed == expected


@pytest.mark.parametrize("seed", [17, 18])
def test_icpsr_split_is_reproducible_disjoint_and_complete(seed: int) -> None:
    outcomes = pd.DataFrame({"idnum": range(40), "gpa": np.linspace(1.0, 4.0, 40)})
    first = split_icpsr_gpa(
        outcomes,
        id_column="idnum",
        seed=seed,
        train_fraction=0.65,
        development_fraction=0.175,
        locked_fraction=0.175,
    )
    second = split_icpsr_gpa(
        outcomes,
        id_column="idnum",
        seed=seed,
        train_fraction=0.65,
        development_fraction=0.175,
        locked_fraction=0.175,
    )
    assert first.train.equals(second.train)
    all_ids = set(first.train.idnum) | set(first.development_test.idnum) | set(first.locked_test.idnum)
    assert all_ids == set(outcomes.idnum)
    assert not set(first.train.idnum) & set(first.development_test.idnum)
    assert not set(first.train.idnum) & set(first.locked_test.idnum)
    assert not set(first.development_test.idnum) & set(first.locked_test.idnum)


def _write_synthetic_icpsr_inputs(root: Path) -> tuple[Path, Path]:
    """Create the minimum five-wave ICPSR input required by the adapter."""

    rows = 60
    ids = list(range(900_000, 900_000 + rows))
    background = pd.DataFrame(
        {
            "IDNUM": ids,
            **{
                component.upper(): [1 + ((index + offset) % 4) for index in range(rows)]
                for offset, component in enumerate(GPA_COMPONENTS)
            },
            "M1A": [index % 2 for index in range(rows)],
            "P2A": [index % 2 for index in range(rows)],
            "P3A": [index % 2 for index in range(rows)],
            "P4A": [index % 2 for index in range(rows)],
            "P5A": [index % 2 for index in range(rows)],
        }
    )
    background_path = root / "icpsr.dta"
    background.to_stata(background_path, write_index=False)
    metadata_path = root / "metadata.csv"
    pd.DataFrame(
        {
            "new_name": [*GPA_COMPONENTS, "m1a", "p2a", "p3a", "p4a", "p5a"],
            "old_name": [None] * 9,
            "wave": ["Year 15"] * 4 + ["Baseline", "Year 1", "Year 3", "Year 5", "Year 9"],
            "respondent": ["Child"] * 9,
        }
    ).to_csv(metadata_path, index=False, encoding="latin-1")
    return background_path, metadata_path


def _write_icpsr_config(root: Path, *, ard_root: Path | None = None) -> Path:
    background_path, metadata_path = _write_synthetic_icpsr_inputs(root)
    config_path = root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "contract_version": "ffcws-adapter-v2",
                "data_source": "icpsr",
                "split_mode": "external_test",
                "feature_universe_mode": "train_pool_screened",
                "paths": {
                    "background": str(background_path),
                    "metadata": str(metadata_path),
                    "output_root": str(root / "output"),
                    "ard_root": str(ard_root or root / "ard"),
                    "schema_root": str(root / "schema"),
                },
                "id_column": "IDNUM",
                "outcomes": ["gpa"],
                "strategies": ["median_mode"],
                "input_validation_mode": "schema_only",
                "missing_value_codes": list(range(-9, 0)),
                "schema": {"continuous_negative_missing_threshold": -10},
                "icpsr_split": {
                    "seed": 17,
                    "train_fraction": 0.65,
                    "development_fraction": 0.175,
                    "locked_fraction": 0.175,
                },
                "exchangeability_justification": "Synthetic ICPSR sources are exchangeable.",
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_icpsr_outputs_disclose_no_locked_test_statistic_count_or_id(tmp_path: Path) -> None:
    summary = run_pipeline(_write_icpsr_config(tmp_path))
    output_root = tmp_path / "output"
    ard_root = tmp_path / "ard"
    locked_ids = set(
        pd.read_parquet(
            tmp_path / "ard" / "ffc_icpsr_median_mode_gpa" / "locked_test.parquet"
        )["idnum"].astype(str)
    )
    assert summary["strategies"]["median_mode"]["engine_schemas"]
    provenance = json.loads(
        (tmp_path / "ard" / "ffc_icpsr_median_mode_gpa" / "provenance.json").read_text(
            encoding="utf-8"
        )
    )
    assert provenance["contract_version"] == "ffcws-adapter-v2"
    for root in (output_root, ard_root):
        for artifact in root.rglob("*"):
            if (
                artifact.name == "locked_test.parquet"
                or artifact.suffix not in {".csv", ".json"}
            ):
                continue
            content = artifact.read_text(encoding="utf-8")
            assert "locked" not in content.lower()
            assert not any(locked_id in content for locked_id in locked_ids)


def test_pipeline_rejects_v1_output_nested_in_v2_artifact_directory(tmp_path: Path) -> None:
    v2_dataset_dir = tmp_path / "ard" / "ffc_icpsr_median_mode_gpa"
    v2_dataset_dir.mkdir(parents=True)
    (v2_dataset_dir / "provenance.json").write_text(
        json.dumps({"dataset": "ffc_icpsr_median_mode_gpa", "contract_version": "ffcws-adapter-v2"}),
        encoding="utf-8",
    )
    config_path = tmp_path / "v1.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "contract_version": "ffcws-adapter-v1",
                "data_source": "challenge",
                "split_mode": "external_test",
                "feature_universe_mode": "train_pool_screened",
                "paths": {
                    "background": str(tmp_path / "unused.dta"),
                    "train": str(tmp_path / "unused-train.csv"),
                    "test": str(tmp_path / "unused-test.csv"),
                    "output_root": str(tmp_path / "output"),
                    "ard_root": str(v2_dataset_dir),
                },
                "outcomes": ["gpa"],
                "strategies": ["median_mode"],
                "missing_value_codes": list(range(-9, 0)),
                "exchangeability_justification": "Synthetic sources are exchangeable.",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mix FFCWS adapter artifact contracts"):
        run_pipeline(config_path)


def test_negative_threshold_is_applied_after_raw_type_classification() -> None:
    ids = list(range(16))
    background = pd.DataFrame({"idnum": ids, "boundary": [-10, *range(15)]})
    schema = build_shared_schema(
        background,
        ids,
        config=SchemaConfig(
            id_column="idnum",
            categorical_max_levels=15,
            continuous_negative_missing_threshold=-10,
        ),
    )
    source = schema.sources[0]
    assert source.distinct == 16
    assert source.status == "numeric"
    assert source.continuous_negative_missing_threshold == -10
    assert np.isnan(encode_median_mode(background, schema).features.loc[0, "X_boundary"])


@pytest.mark.parametrize("future_wave", ["Year 15", "Year 22"])
def test_metadata_landmarks_exclude_future_waves_and_outcome_sources(
    tmp_path: Path, future_wave: str
) -> None:
    dataset_dir = tmp_path / "ard"
    dataset_dir.mkdir()
    sources = ["m1a", "p2a", "p3a", "p4a", "p5a", "k6b20a", "future"]
    waves = ["Baseline", "Year 1", "Year 3", "Year 5", "Year 9", "Year 15", future_wave]
    manifest = pd.DataFrame(
        {
            "source_column": sources,
            "feature_name": [f"X_{source}" for source in sources],
            "kind": "X",
            "strategy": "median_mode",
            "keep": True,
            "reason": "kept",
            "source_order": range(len(sources)),
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
            "wave": waves,
            "respondent": "Mother",
        }
    )
    manifest.to_csv(dataset_dir / "feature_manifest.csv", index=False)
    table = pd.DataFrame({"idnum": [1, 2], "gpa": [2.0, 3.0], **{f"X_{s}": [0, 1] for s in sources}})
    table.to_parquet(dataset_dir / "data.parquet", index=False)
    table.assign(idnum=[3, 4]).to_parquet(dataset_dir / "test.parquet", index=False)
    artifacts = export_landmark_schemas(
        dataset_dir=dataset_dir,
        schema_root=tmp_path / "schema",
        dataset="icpsr",
        outcome="gpa",
        id_column="idnum",
        use_manifest_wave=True,
        forbidden_source_columns=GPA_COMPONENTS,
    )
    for path in artifacts.schema_paths.values():
        predictors = json.loads(path.read_text(encoding="utf-8"))["predictor_columns"]
        assert "X_k6b20a" not in predictors
        assert "X_future" not in predictors


REAL_BACKGROUND = PROJECT_ROOT / "data" / "private" / "ffcws_icpsr.dta"
REAL_METADATA = PROJECT_ROOT / "data" / "private" / "FFMetadata_v20_f.csv"
REAL_SCHEMA_ROOT = PROJECT_ROOT / "schema"


@pytest.mark.skipif(
    not (REAL_BACKGROUND.is_file() and REAL_METADATA.is_file()),
    reason="Authorized ICPSR source data and metadata are unavailable.",
)
def test_real_icpsr_inputs_expose_required_gpa_components_and_metadata() -> None:
    background = pd.read_stata(REAL_BACKGROUND, convert_categoricals=False)
    background = normalize_columns_lower(background, label="ICPSR background")
    assert {"idnum", *GPA_COMPONENTS}.issubset(background.columns)
    gpa = build_gpa_outcomes(background, id_column="idnum")["gpa"].dropna()
    assert set(gpa.unique()).issubset({value / 4 for value in range(4, 17)})
    assert gpa.min() >= 1.0 and gpa.max() <= 4.0
    assert read_icpsr_metadata(REAL_METADATA)["wave"].notna().any()


@pytest.mark.parametrize("landmark", [0, 1, 3, 5, 9])
@pytest.mark.skipif(
    not all(
        (REAL_SCHEMA_ROOT / f"ffc_icpsr_median_mode_gpa_lm{landmark}.json").is_file()
        for landmark in (0, 1, 3, 5, 9)
    ),
    reason="ICPSR landmark schemas have not been built.",
)
def test_real_icpsr_landmarks_are_nested_and_exclude_future_and_outcome_sources(
    landmark: int,
) -> None:
    current = json.loads(
        (REAL_SCHEMA_ROOT / f"ffc_icpsr_median_mode_gpa_lm{landmark}.json").read_text(
            encoding="utf-8"
        )
    )
    predictors = set(current["predictor_columns"])
    manifest = pd.read_csv(REAL_SCHEMA_ROOT / current["feature_manifest"])
    kept = manifest.loc[manifest["keep"].astype(bool)]
    assert not kept["wave"].isin(["Year 15", "Year 22"]).any()
    assert not kept["source_column"].isin(GPA_COMPONENTS).any()
    for prior in (0, 1, 3, 5, 9):
        if prior >= landmark:
            break
        previous = json.loads(
            (REAL_SCHEMA_ROOT / f"ffc_icpsr_median_mode_gpa_lm{prior}.json").read_text(
                encoding="utf-8"
            )
        )
        assert set(previous["predictor_columns"]) < predictors
