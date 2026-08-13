#!/usr/bin/env python3
"""Measure the four real-ARD ICPSR grid probes required before a formal run."""

from __future__ import annotations

import argparse
import json
import resource
import signal
import sys
import time
from pathlib import Path

import yaml
from aleatoric_nk_grid.run_panels import resolve_panel
from aleatoric_nk_grid.nk_grid import run_nk_grid


PROJECT_ROOT = Path(__file__).resolve().parent
MODELS = ("super_learner", "ridge", "random_forest", "lightgbm")
PROBES = (
    ("probe_1", 0, 1843, 526),
    ("probe_2", 9, 300, 5851),
    ("probe_3", 9, 1843, 300),
    ("probe_4", 9, 1843, 5851),
)


def peak_rss_gb() -> float:
    """Peak RSS of this process. Darwin reports bytes, Linux kilobytes."""

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024**3 if sys.platform == "darwin" else peak / 1024**2


def children_peak_rss_gb() -> float:
    """Peak RSS reported for completed child processes, in GB."""

    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return peak / 1024**3 if sys.platform == "darwin" else peak / 1024**2


class CalibrationTimeout:
    """Interrupt one fit at the remaining calibration-budget deadline."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._previous_handler: object | None = None

    def __enter__(self) -> None:
        def expire(_signum: int, _frame: object) -> None:
            raise TimeoutError(f"fit exceeded the {self.seconds:.1f}-second calibration limit")

        self._previous_handler = signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if self._previous_handler is not None:
            signal.signal(signal.SIGALRM, self._previous_handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-timeout-seconds", type=float, default=1800)
    parser.add_argument("--per-model-timeout-seconds", type=float, default=1800)
    parser.add_argument(
        "--out", type=Path, default=PROJECT_ROOT / "outputs" / "icpsr_grid_calibration.json"
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    deadline = time.monotonic() + args.total_timeout_seconds
    args.out.write_text(json.dumps({"probes": rows}, indent=2) + "\n", encoding="utf-8")
    for probe, landmark, n_value, k_value in PROBES:
        schema = PROJECT_ROOT / "schema" / f"ffc_icpsr_median_mode_gpa_lm{landmark}.json"
        for model in MODELS:
            stem = f"{probe}_{model}"
            manifest_path = args.out.parent / f"{stem}.yaml"
            output_path = args.out.parent / f"{stem}.csv"
            manifest_path.write_text(
                yaml.safe_dump(
                    {
                        "preset": "timing_full",
                        "experiment_id": "ffcws-icpsr-grid-calibration-v1",
                        "data_version": "ffcws-icpsr-ard-v2",
                        "model_spec_version": "nkgrid-models-v1",
                        "panels": [{
                            "name": stem,
                            "schema": str(schema),
                            "model_params": str(PROJECT_ROOT / "model_params.yaml"),
                            "outcome": "gpa",
                            "models": [model],
                            "n_seeds": 1,
                            "n_draws": 1,
                            "n_grid": [n_value],
                            "k_grid": [k_value],
                            "n_jobs": 1,
                            "out": str(output_path),
                        }],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            started = time.monotonic()
            before_gb = peak_rss_gb()
            before_children_gb = children_peak_rss_gb()
            remaining_seconds = deadline - started
            try:
                if remaining_seconds <= 0:
                    raise TimeoutError("the overall calibration budget was exhausted")
                _name, config = resolve_panel(
                    yaml.safe_load(manifest_path.read_text(encoding="utf-8"))["panels"][0],
                    manifest_path.parent,
                )
                with CalibrationTimeout(
                    min(args.per_model_timeout_seconds, remaining_seconds)
                ):
                    run_nk_grid(config, allow_large_run=True)
                after_gb = peak_rss_gb()
                after_children_gb = children_peak_rss_gb()
                rows.append({
                    "probe": probe, "landmark": landmark, "N": n_value, "K": k_value,
                    "model": model, "wall_seconds": time.monotonic() - started,
                    "rss_delta_gb": after_gb - before_gb, "peak_rss_gb": after_gb,
                    "children_rss_delta_gb": after_children_gb - before_children_gb,
                    "children_peak_rss_gb": after_children_gb,
                    "status": "ok",
                })
            except TimeoutError:
                rows.append({
                    "probe": probe, "landmark": landmark, "N": n_value, "K": k_value,
                    "model": model, "wall_seconds": time.monotonic() - started,
                    "rss_delta_gb": None, "peak_rss_gb": peak_rss_gb(),
                    "children_rss_delta_gb": None,
                    "children_peak_rss_gb": children_peak_rss_gb(), "status": "timeout",
                })
            except Exception as exc:  # record a failed real probe rather than inventing a cost
                rows.append({
                    "probe": probe, "landmark": landmark, "N": n_value, "K": k_value,
                    "model": model, "wall_seconds": time.monotonic() - started,
                    "rss_delta_gb": None, "peak_rss_gb": peak_rss_gb(),
                    "children_rss_delta_gb": None,
                    "children_peak_rss_gb": children_peak_rss_gb(),
                    "status": "error", "error_type": type(exc).__name__,
                })
            args.out.write_text(json.dumps({"probes": rows}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
