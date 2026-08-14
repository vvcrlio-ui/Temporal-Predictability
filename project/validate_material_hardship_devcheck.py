"""Automated, value-blind gate for the materialHardship development sweep.

This program is the only reader of ``outputs/hardship_devcheck``.  It may
inspect performance columns to check the preregistered file contract, but it
only emits booleans and structural counts.  It never prints a performance
value or a development-row prediction.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


RESULT_KEY = ["model", "seed", "draw", "N", "K"]
PREDICTION_KEY = [*RESULT_KEY, "row_id"]
PERFORMANCE_VALUE_PATTERN = re.compile(
    r"(?ix)(?:"
    r"(?:r2_test|rmse|mse|mae|r_sl|\\br\\s*\\([^)]*\\))"
    r"\\s*(?:=|:|为|是)\\s*[-+]?(?:\\d|\\.\\d)"
    r"|(?:开发半|development)[^\\n]{0,160}?"
    r"(?:r2_test|rmse|mse|mae|r_sl|\\br\\s*\\([^)]*\\))[^\\n]{0,60}?"
    r"[-+]?(?:\\d+\\.\\d+|\\.\\d+)"
    r")"
)


@dataclass(frozen=True)
class GateResult:
    all_expected_results_present: bool
    result_rows_complete: bool
    result_keys_unique: bool
    result_statuses_ok: bool
    prediction_files_complete: bool
    prediction_coverage_complete: bool
    prediction_keys_unique: bool
    predictions_complete: bool
    mse_consistent: bool
    report_has_no_development_performance_values: bool
    expected_result_rows: int
    observed_result_rows: int
    expected_prediction_repeat_cells: int
    observed_prediction_repeat_cells: int
    failed_checks: int

    @property
    def passed(self) -> bool:
        return self.failed_checks == 0

    def to_dict(self) -> dict[str, bool | int]:
        return {
            "passed": self.passed,
            "all_expected_results_present": self.all_expected_results_present,
            "result_rows_complete": self.result_rows_complete,
            "result_keys_unique": self.result_keys_unique,
            "result_statuses_ok": self.result_statuses_ok,
            "prediction_files_complete": self.prediction_files_complete,
            "prediction_coverage_complete": self.prediction_coverage_complete,
            "prediction_keys_unique": self.prediction_keys_unique,
            "predictions_complete": self.predictions_complete,
            "mse_consistent": self.mse_consistent,
            "report_has_no_development_performance_values": (
                self.report_has_no_development_performance_values
            ),
            "expected_result_rows": self.expected_result_rows,
            "observed_result_rows": self.observed_result_rows,
            "expected_prediction_repeat_cells": self.expected_prediction_repeat_cells,
            "observed_prediction_repeat_cells": self.observed_prediction_repeat_cells,
            "failed_checks": self.failed_checks,
        }


def _resolve_project_path(path: str, project_root: Path) -> Path:
    resolved = (project_root / path).resolve()
    if project_root not in resolved.parents and resolved != project_root:
        raise ValueError("Panel output resolves outside the project directory")
    return resolved


def _result_path(output_path: Path) -> Path | None:
    candidates = sorted(output_path.parent.glob(f"{output_path.stem}_*.csv"))
    return candidates[0] if len(candidates) == 1 else None


def _expected_result_rows(panel: dict[str, Any]) -> int:
    return (
        len(panel["models"])
        * int(panel["n_seeds"])
        * int(panel["n_draws"])
        * len(panel["n_grid"])
        * len(panel["k_grid"])
    )


def _expected_test_ids(schema_path: Path) -> set[Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    test_path = (schema_path.parent / schema["test_table"]).resolve()
    return set(pd.read_parquet(test_path, columns=[schema["id_column"]])[schema["id_column"]])


def _is_isolated_output(output_path: Path, dev_root: Path) -> bool:
    try:
        output_path.relative_to(dev_root)
    except ValueError:
        return False
    return True


def evaluate_gate(manifest_path: Path, report_path: Path, project_root: Path) -> GateResult:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    dev_root = (project_root / "outputs" / "hardship_devcheck").resolve()
    panels = manifest.get("panels", [])
    if not panels:
        raise ValueError("Development manifest has no panels")

    expected_rows = 0
    observed_rows = 0
    expected_prediction_repeat_cells = 0
    observed_prediction_repeat_cells = 0
    all_expected_results_present = True
    result_rows_complete = True
    result_keys_unique = True
    result_statuses_ok = True
    prediction_files_complete = True
    prediction_coverage_complete = True
    prediction_keys_unique = True
    predictions_complete = True
    mse_consistent = True

    for panel in panels:
        output_path = _resolve_project_path(str(panel["out"]), project_root)
        if not _is_isolated_output(output_path, dev_root):
            raise ValueError("Development panel output is not inside hardship_devcheck")
        expected_rows += _expected_result_rows(panel)
        result_path = _result_path(output_path)
        if result_path is None:
            all_expected_results_present = False
            result_rows_complete = False
            result_keys_unique = False
            result_statuses_ok = False
            prediction_files_complete = False
            prediction_coverage_complete = False
            prediction_keys_unique = False
            predictions_complete = False
            mse_consistent = False
            continue

        result = pd.read_csv(result_path)
        observed_rows += len(result)
        result_rows_complete &= len(result) == _expected_result_rows(panel)
        result_keys_unique &= not result.duplicated(RESULT_KEY).any()
        result_statuses_ok &= result["status"].eq("ok").all()

        prediction_path = result_path.with_suffix(".predictions.parquet")
        if not prediction_path.is_file():
            prediction_files_complete = False
            prediction_coverage_complete = False
            prediction_keys_unique = False
            predictions_complete = False
            mse_consistent = False
            continue

        predictions = pd.read_parquet(prediction_path)
        expected_ids = _expected_test_ids(_resolve_project_path(str(panel["schema"]), project_root))
        for cell in panel.get("prediction_export_cells", []):
            subset = predictions.loc[
                (predictions["model"] == cell["model"])
                & (predictions["N"] == cell["N"])
                & (predictions["K"] == cell["K"])
            ]
            expected_prediction_repeat_cells += int(panel["n_seeds"]) * int(panel["n_draws"])
            for _, repeat in subset.groupby(["seed", "draw"], sort=False):
                observed_prediction_repeat_cells += 1
                prediction_coverage_complete &= set(repeat["row_id"]) == expected_ids
                predictions_complete &= not repeat[["y_true", "y_pred"]].isna().any().any()
                prediction_keys_unique &= not repeat.duplicated(PREDICTION_KEY).any()
                matching_result = result.loc[
                    (result["model"] == cell["model"])
                    & (result["N"] == cell["N"])
                    & (result["K"] == cell["K"])
                    & (result["seed"] == repeat.iloc[0]["seed"])
                    & (result["draw"] == repeat.iloc[0]["draw"])
                ]
                if len(matching_result) != 1:
                    mse_consistent = False
                    continue
                mse = float(np.mean((repeat["y_true"] - repeat["y_pred"]) ** 2))
                rmse_squared = float(matching_result.iloc[0]["rmse"]) ** 2
                mse_consistent &= bool(
                    np.isfinite(mse)
                    and np.isfinite(rmse_squared)
                    and (
                        abs(mse - rmse_squared) < 1e-12
                        if rmse_squared == 0.0
                        else abs(mse / rmse_squared - 1.0) < 1e-9
                    )
                )

    prediction_coverage_complete &= (
        observed_prediction_repeat_cells == expected_prediction_repeat_cells
    )
    report_has_no_development_performance_values = not bool(
        PERFORMANCE_VALUE_PATTERN.search(report_path.read_text(encoding="utf-8"))
    )
    checks = [
        all_expected_results_present,
        result_rows_complete,
        result_keys_unique,
        result_statuses_ok,
        prediction_files_complete,
        prediction_coverage_complete,
        prediction_keys_unique,
        predictions_complete,
        mse_consistent,
        report_has_no_development_performance_values,
    ]
    return GateResult(
        all_expected_results_present=all_expected_results_present,
        result_rows_complete=result_rows_complete,
        result_keys_unique=result_keys_unique,
        result_statuses_ok=result_statuses_ok,
        prediction_files_complete=prediction_files_complete,
        prediction_coverage_complete=prediction_coverage_complete,
        prediction_keys_unique=prediction_keys_unique,
        predictions_complete=predictions_complete,
        mse_consistent=mse_consistent,
        report_has_no_development_performance_values=report_has_no_development_performance_values,
        expected_result_rows=expected_rows,
        observed_result_rows=observed_rows,
        expected_prediction_repeat_cells=expected_prediction_repeat_cells,
        observed_prediction_repeat_cells=observed_prediction_repeat_cells,
        failed_checks=sum(not check for check in checks),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    result = evaluate_gate(
        Path(args.manifest).resolve(),
        Path(args.report).resolve(),
        Path(args.project_root).resolve(),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
