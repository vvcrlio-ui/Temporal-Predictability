"""Orchestrate shared schema construction and strategy-specific outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from aleatoric_nk_grid.ingest import load_input
from aleatoric_nk_grid.validate_input import validate_input

from .common.io import (
    build_metadata,
    frame_hash,
    load_yaml,
    materialize_outcomes,
    read_stata_with_labels,
    stable_hash,
    write_frame,
    write_json,
)
from .common.manifests import (
    kept_source_order,
    source_manifest_frame,
    validate_feature_manifest,
)
from .common.schema import FFC_MISSING_CODES, SchemaConfig, build_shared_schema
from .common.validation import ensure_disjoint_ids, ensure_unique_ids
from .contract import enforce_outcome_train_category_coverage, write_engine_schema
from .icpsr import (
    DISALLOWED_PREDICTOR_WAVES,
    GPA_COMPONENTS,
    MATERIAL_HARDSHIP_COMPONENTS,
    MaterialHardshipDistributionTarget,
    build_gpa_outcomes,
    build_material_hardship_candidates,
    candidate_icpsr_predictor_sources,
    continuous_negative_code_summary,
    extend_icpsr_household_splits,
    metadata_for_sources,
    normalize_columns_lower,
    normalize_value_labels_lower,
    read_icpsr_metadata,
    select_validated_material_hardship_candidate,
    split_icpsr_gpa,
    split_outcome_by_household_assignment,
    wave_diagnostics,
)
from .landmarks import export_landmark_schemas
from .strategies import STRATEGIES


DEFAULT_OUTCOMES = (
    "gpa",
    "grit",
    "materialHardship",
    "eviction",
    "layoff",
    "jobTraining",
)
SUPPORTED_CONTRACT_VERSIONS = frozenset({"ffcws-adapter-v1", "ffcws-adapter-v2"})
CONTRACT_DATA_SOURCES = {
    "ffcws-adapter-v1": "challenge",
    "ffcws-adapter-v2": "icpsr",
}


def _resolve_path(value: str | Path, config_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (config_dir / path).resolve()


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Configuration requires a '{key}' mapping")
    return value


def _icpsr_split_config(document: dict[str, Any]) -> dict[str, float | int]:
    value = _required_mapping(document, "icpsr_split")
    required = {"seed", "train_fraction", "development_fraction", "locked_fraction"}
    missing = required - set(value)
    if missing:
        raise ValueError(f"ICPSR configuration is missing split settings: {sorted(missing)}")
    return {
        "seed": int(value["seed"]),
        "train_fraction": float(value["train_fraction"]),
        "development_fraction": float(value["development_fraction"]),
        "locked_fraction": float(value["locked_fraction"]),
    }


def _material_hardship_config(
    document: dict[str, Any]
) -> tuple[str, MaterialHardshipDistributionTarget]:
    value = _required_mapping(document, "material_hardship")
    target_document = _required_mapping(value, "distribution_target")
    required = {"selected_candidate", "nonmissing_count", "mean", "standard_deviation"}
    missing = required - {"selected_candidate", *target_document}
    if missing:
        raise ValueError(
            "Material-hardship configuration is missing required settings: "
            f"{sorted(missing)}"
        )
    return (
        str(value["selected_candidate"]),
        MaterialHardshipDistributionTarget(
            nonmissing_count=int(target_document["nonmissing_count"]),
            mean=float(target_document["mean"]),
            standard_deviation=float(target_document["standard_deviation"]),
            denominator=int(target_document.get("denominator", 11)),
            mean_tolerance=float(target_document.get("mean_tolerance", 0.010)),
            standard_deviation_tolerance=float(
                target_document.get("standard_deviation_tolerance", 0.010)
            ),
            minimum_acceptable_maximum_numerator=int(
                target_document.get("minimum_acceptable_maximum_numerator", 8)
            ),
        ),
    )


def _artifact_contract_version(provenance_path: Path) -> str | None:
    """Read the producer contract, including pre-marker artifact names."""

    if not provenance_path.is_file():
        return None
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid artifact provenance: {provenance_path}") from error
    version = provenance.get("contract_version")
    if version in SUPPORTED_CONTRACT_VERSIONS:
        return str(version)
    dataset = str(provenance.get("dataset", ""))
    if dataset.startswith("ffc_icpsr_"):
        return "ffcws-adapter-v2"
    if dataset.startswith("ffc_"):
        return "ffcws-adapter-v1"
    raise ValueError(
        "Cannot establish the contract version for existing artifact "
        f"{provenance_path}; migrate or remove it before rebuilding"
    )


def _assert_compatible_artifact_contract(
    *,
    ard_root: Path,
    datasets: Iterable[str],
    contract_version: str,
) -> None:
    """Reject writes that would put one contract inside another's artifact tree."""

    paths = [ard_root / dataset / "provenance.json" for dataset in datasets]
    paths.extend(parent / "provenance.json" for parent in (ard_root, *ard_root.parents))
    for provenance_path in paths:
        observed = _artifact_contract_version(provenance_path)
        if observed is not None and observed != contract_version:
            raise ValueError(
                "Refusing to mix FFCWS adapter artifact contracts: "
                f"requested {contract_version}, but {provenance_path.parent} "
                f"belongs to {observed}"
            )


def run_pipeline(
    config_path: Path,
    *,
    strategies: Iterable[str] | None = None,
    validation_models: Iterable[str] = ("ols",),
    min_n: int = 10,
    test_size: float = 0.3,
    seed: int = 12345,
) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    document = load_yaml(config_path)
    contract_version = str(document.get("contract_version", ""))
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ValueError("Unsupported FFCWS contract_version")
    if document.get("split_mode") != "external_test":
        raise ValueError("FFCWS contract requires split_mode=external_test")
    if document.get("feature_universe_mode") != "train_pool_screened":
        raise ValueError(
            "FFCWS contract requires feature_universe_mode=train_pool_screened"
        )
    if tuple(document.get("missing_value_codes", ())) != FFC_MISSING_CODES:
        raise ValueError(
            f"FFCWS contract missing_value_codes must be {list(FFC_MISSING_CODES)}"
        )
    justification = str(document.get("exchangeability_justification", "")).strip()
    if not justification:
        raise ValueError("FFCWS contract requires an exchangeability justification")
    paths = _required_mapping(document, "paths")
    schema_document = dict(document.get("schema") or {})
    id_column = str(document.get("id_column", "challengeID"))
    outcomes = [str(item) for item in document.get("outcomes", DEFAULT_OUTCOMES)]
    unknown_threshold = float(document.get("unknown_rate_threshold", 0.95))
    if not 0.0 <= unknown_threshold <= 1.0:
        raise ValueError("unknown_rate_threshold must be between 0 and 1")

    config_dir = config_path.parent
    background_path = _resolve_path(paths["background"], config_dir)
    output_root = _resolve_path(paths["output_root"], config_dir)
    ard_root = _resolve_path(paths.get("ard_root", output_root / "ard"), config_dir)
    schema_root = _resolve_path(
        paths.get("schema_root", output_root / "schemas"), config_dir
    )
    selected = list(strategies or document.get("strategies") or STRATEGIES)
    selected_validation_models = tuple(validation_models)
    if not selected_validation_models:
        raise ValueError("At least one validation model is required")
    unknown = [name for name in selected if name not in STRATEGIES]
    if unknown:
        raise ValueError(f"Unknown preprocessing strategy: {', '.join(unknown)}")
    input_validation_mode = str(document.get("input_validation_mode", "engine_models"))
    if input_validation_mode not in {"engine_models", "schema_only"}:
        raise ValueError(
            "input_validation_mode must be either 'engine_models' or 'schema_only'"
        )

    data_source = str(document.get("data_source", "challenge"))
    expected_data_source = CONTRACT_DATA_SOURCES[contract_version]
    if data_source != expected_data_source:
        raise ValueError(
            f"{contract_version} requires data_source={expected_data_source!r}, "
            f"not {data_source!r}"
        )
    datasets = [
        (
            f"ffc_icpsr_{strategy}_{outcome}"
            if data_source == "icpsr"
            else f"ffc_{strategy}_{outcome}"
        )
        for strategy in selected
        for outcome in outcomes
    ]
    _assert_compatible_artifact_contract(
        ard_root=ard_root,
        datasets=datasets,
        contract_version=contract_version,
    )
    background, value_labels = read_stata_with_labels(
        background_path, include_value_labels=data_source != "icpsr"
    )
    source_metadata: pd.DataFrame | None = None
    input_paths: dict[str, Path] = {"background": background_path}
    locked_split = None
    outcome_forbidden_sources: tuple[str, ...] = GPA_COMPONENTS
    material_hardship_validations = ()
    if data_source == "icpsr":
        background = normalize_columns_lower(background, label="ICPSR background")
        value_labels = normalize_value_labels_lower(value_labels)
        id_column = id_column.lower()
        metadata_path = _resolve_path(paths["metadata"], config_dir)
        metadata = read_icpsr_metadata(metadata_path)
        source_metadata = metadata_for_sources(
            metadata,
            [column for column in background.columns if column != id_column],
        )
        source_metadata, wave_mismatches = wave_diagnostics(source_metadata)
        gpa_outcomes = build_gpa_outcomes(background, id_column=id_column)
        split_config = _icpsr_split_config(document)
        if outcomes == ["gpa"]:
            splits = split_icpsr_gpa(gpa_outcomes, id_column=id_column, **split_config)
        elif outcomes == ["materialHardship"]:
            selected_candidate, target = _material_hardship_config(document)
            candidates = build_material_hardship_candidates(background, id_column=id_column)
            outcomes_frame, material_hardship_validations = (
                select_validated_material_hardship_candidate(
                    candidates,
                    selected_candidate=selected_candidate,
                    target=target,
                )
            )
            household_assignments = extend_icpsr_household_splits(
                background[id_column],
                gpa_outcomes,
                id_column=id_column,
                **split_config,
            )
            splits = split_outcome_by_household_assignment(
                outcomes_frame,
                household_assignments,
                id_column=id_column,
                outcome="materialHardship",
            )
            outcome_forbidden_sources = MATERIAL_HARDSHIP_COMPONENTS
        else:
            raise ValueError(
                "ICPSR configurations must build one outcome at a time; supported "
                "outcomes are ['gpa'] and ['materialHardship']"
            )
        train = splits.train
        test = splits.development_test
        locked_split = splits.locked_test
        candidate_sources = candidate_icpsr_predictor_sources(
            source_metadata, outcome_sources=outcome_forbidden_sources
        )
        input_paths["metadata"] = metadata_path
    else:
        train_path = _resolve_path(paths["train"], config_dir)
        test_path = _resolve_path(paths["test"], config_dir)
        train = pd.read_csv(train_path)
        test = pd.read_csv(test_path)
        candidate_sources = None
        input_paths.update({"train": train_path, "test": test_path})
    ensure_unique_ids(background, id_column, "background")
    ensure_unique_ids(train, id_column, "train")
    ensure_unique_ids(test, id_column, "test")
    ensure_disjoint_ids(train, test, id_column=id_column)

    schema_config = SchemaConfig(id_column=id_column, **schema_document)
    schema = build_shared_schema(
        background,
        train[id_column],
        value_labels=value_labels,
        config=schema_config,
        candidate_sources=candidate_sources,
    )
    source_manifest = source_manifest_frame(schema)
    output_root.mkdir(parents=True, exist_ok=True)
    if source_metadata is not None:
        source_manifest = source_manifest.merge(
            source_metadata.loc[:, ["source_column", "wave", "respondent"]],
            on="source_column",
            how="left",
            validate="one_to_one",
        )
        excluded_sources = source_metadata.loc[
            ~source_metadata["source_column"].isin(candidate_sources),
            ["source_column", "wave", "respondent", "metadata_match"],
        ].copy()
        excluded_sources["reason"] = "not_an_eligible_Baseline_to_Year_9_predictor"
        write_frame(output_root / "excluded_sources.csv", excluded_sources)
        unassigned_sources = source_metadata.loc[
            source_metadata["wave"].isna(),
            ["source_column", "metadata_match"],
        ].copy()
        unassigned_sources["reason"] = "no_official_metadata_wave"
        write_frame(output_root / "unassigned_sources.csv", unassigned_sources)
        write_frame(output_root / "metadata_regex_mismatches.csv", wave_mismatches)
        if material_hardship_validations:
            write_json(
                output_root / "material_hardship_candidate_validations.json",
                [
                    {
                        "candidate": validation.candidate,
                        "nonmissing_count": validation.nonmissing_count,
                        "numerators": list(validation.numerators),
                        "minimum_numerator": validation.minimum_numerator,
                        "maximum_numerator": validation.maximum_numerator,
                        "mean": validation.mean,
                        "standard_deviation": validation.standard_deviation,
                        "target_mean_tolerance": target.mean_tolerance,
                        "target_standard_deviation_tolerance": (
                            target.standard_deviation_tolerance
                        ),
                        "minimum_acceptable_maximum_numerator": (
                            target.minimum_acceptable_maximum_numerator
                        ),
                        "passed": validation.passed,
                        "failures": list(validation.failures),
                    }
                    for validation in material_hardship_validations
                ],
            )
    write_frame(output_root / "source_manifest.csv", source_manifest)
    write_json(output_root / "schema.json", schema.to_dict())

    # Schema inference needs every ICPSR candidate source, but encoding needs
    # only sources that survived the training-pool screen.  Releasing dropped
    # columns before materializing a 16k-feature table keeps the full-data
    # rebuild within the workspace memory budget without changing the schema.
    encoding_columns = [id_column, *[source.source_column for source in schema.eligible_sources]]
    background = background.loc[:, encoding_columns].copy()

    results = []
    for strategy in selected:
        result = STRATEGIES[strategy](
            background,
            schema,
            test_ids=test[id_column],
            unknown_rate_threshold=unknown_threshold,
        )
        validate_feature_manifest(
            result.features, result.feature_manifest, id_column=id_column
        )
        results.append(result)
    config_hash = stable_hash(document)
    run_summary: dict[str, Any] = {
        "schema_hash": schema.content_hash,
        "eligible_raw_source_count": len(schema.eligible_sources),
        "strategies": {},
    }

    for result in results:
        strategy_dir = output_root / result.strategy
        suffix = ".parquet"
        features_path = strategy_dir / f"features{suffix}"
        stale_features_path = strategy_dir / "features.csv"
        if stale_features_path.exists():
            stale_features_path.unlink()
        manifest_path = strategy_dir / "feature_manifest.csv"
        qa_path = strategy_dir / "qa_summary.json"
        write_frame(features_path, result.features)
        manifest_to_write = result.feature_manifest
        if source_metadata is not None:
            manifest_to_write = manifest_to_write.merge(
                source_metadata.loc[:, ["source_column", "wave", "respondent"]],
                on="source_column",
                how="left",
                validate="many_to_one",
            )
        write_frame(manifest_path, manifest_to_write)
        persisted_manifest = pd.read_csv(manifest_path)
        if result.ordinal_mappings:
            write_json(strategy_dir / "ordinal_mappings.json", result.ordinal_mappings)

        outcome_frames, outcome_summary = materialize_outcomes(
            result.features,
            train,
            test,
            outcomes=outcomes,
            id_column=id_column,
        )
        outcome_frames, outcome_category_coverage = (
            enforce_outcome_train_category_coverage(
                outcome_frames,
                persisted_manifest,
                unknown_rate_threshold=unknown_threshold,
            )
        )
        write_json(
            qa_path,
            {
                **result.qa,
                "outcome_category_coverage": (
                    outcome_category_coverage.to_dict(orient="records")
                ),
            },
        )
        write_frame(
            strategy_dir / "outcome_category_coverage.csv",
            outcome_category_coverage,
        )
        write_frame(strategy_dir / "outcome_summary.csv", outcome_summary)

        engine_schemas: dict[str, str] = {}
        for outcome in outcomes:
            dataset = (
                f"ffc_icpsr_{result.strategy}_{outcome}"
                if data_source == "icpsr"
                else f"ffc_{result.strategy}_{outcome}"
            )
            dataset_dir = ard_root / dataset
            train_ard = dataset_dir / f"data{suffix}"
            test_ard = dataset_dir / f"test{suffix}"
            for stale_name in ("data.csv", "test.csv"):
                stale_path = dataset_dir / stale_name
                if stale_path.exists():
                    stale_path.unlink()
            manifest_ard = dataset_dir / "feature_manifest.csv"
            write_frame(train_ard, outcome_frames[("train", outcome)])
            write_frame(test_ard, outcome_frames[("test", outcome)])
            if locked_split is not None:
                locked_ard = locked_split.merge(
                    result.features,
                    on=id_column,
                    how="left",
                    sort=False,
                    validate="one_to_one",
                )
                if locked_ard[result.features.columns].isna().all(axis=None):
                    raise ValueError("Locked ICPSR test rows failed to merge with features")
                write_frame(dataset_dir / "locked_test.parquet", locked_ard)
            write_frame(manifest_ard, persisted_manifest)
            schema_path = write_engine_schema(
                schema_root=schema_root,
                dataset_dir=dataset_dir,
                dataset=dataset,
                outcome=outcome,
                table_path=train_ard,
                test_path=test_ard,
                manifest_path=manifest_ard,
                manifest=persisted_manifest,
                id_column=id_column,
                adapter_contract_version=contract_version,
                feature_universe_stem=(
                    f"ffc_icpsr_{result.strategy}_{outcome}"
                    if data_source == "icpsr" and outcome != "gpa"
                    else f"ffc_icpsr_{result.strategy}"
                    if data_source == "icpsr"
                    else f"ffc_{result.strategy}"
                ),
            )
            loaded = load_input(schema_path, outcome)
            if loaded.train.empty or loaded.test.empty:
                raise ValueError("Engine input loader produced an empty train or test table")
            if input_validation_mode == "engine_models":
                validate_input(
                    loaded,
                    outcome,
                    models=selected_validation_models,
                    min_n=min_n,
                    test_size=test_size,
                    seed=seed,
                )
            engine_schemas[outcome] = str(schema_path)

            if data_source == "icpsr":
                landmark_artifacts = export_landmark_schemas(
                    dataset_dir=dataset_dir,
                    schema_root=schema_root,
                    dataset=dataset,
                    outcome=outcome,
                    id_column=id_column,
                    adapter_contract_version=contract_version,
                    use_manifest_wave=True,
                    forbidden_source_columns=outcome_forbidden_sources,
                )
                engine_schemas.update(
                    {
                        f"{outcome}_lm{landmark}": str(path)
                        for landmark, path in landmark_artifacts.schema_paths.items()
                    }
                )

        metadata = build_metadata(
            strategy=result.strategy,
            schema_hash=schema.content_hash,
            config_hash=config_hash,
            input_paths=input_paths,
            rows=len(result.features),
            columns=result.features.shape[1],
            content_identity={
                "features": frame_hash(result.features),
                "feature_manifest": frame_hash(persisted_manifest),
                "outcome_summary": frame_hash(outcome_summary),
                "outcome_category_coverage": frame_hash(
                    outcome_category_coverage
                ),
                "ordinal_mappings": stable_hash(result.ordinal_mappings),
            },
        )
        write_json(strategy_dir / "metadata.json", metadata)
        run_summary["strategies"][result.strategy] = {
            "features": str(features_path),
            "feature_manifest": str(manifest_path),
            "content_identity_hash": metadata["content_identity_hash"],
            "predictor_count": result.features.shape[1] - 1,
            "source_count": len(kept_source_order(persisted_manifest)),
            "engine_schemas": engine_schemas,
        }

    if source_metadata is not None:
        negative_summary = continuous_negative_code_summary(background, schema.sources)
        write_frame(output_root / "continuous_negative_code_summary.csv", negative_summary)
        disallowed_in_schema = source_manifest.loc[
            source_manifest["wave"].isin(DISALLOWED_PREDICTOR_WAVES), "source_column"
        ]
        if not disallowed_in_schema.empty:
            raise ValueError(
                "Year 15/22 sources entered the ICPSR predictor schema: "
                f"{disallowed_in_schema.tolist()[:5]}"
            )

    write_json(output_root / "run_summary.json", run_summary)
    return run_summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build leak-free FFC encoding strategies for NK Grid."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--strategy",
        nargs="+",
        choices=tuple(STRATEGIES),
        default=None,
        help="One or more strategies; defaults to the config list.",
    )
    parser.add_argument("--validation-model", nargs="+", default=["ols"])
    parser.add_argument("--min-n", type=int, default=10)
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args(argv)
    summary = run_pipeline(
        args.config,
        strategies=args.strategy,
        validation_models=args.validation_model,
        min_n=args.min_n,
        test_size=args.test_size,
        seed=args.seed,
    )
    print(summary)


if __name__ == "__main__":
    main(sys.argv[1:])
