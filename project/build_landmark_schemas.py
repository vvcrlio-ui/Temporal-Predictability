#!/usr/bin/env python3
"""Export nested FFCWS landmark schemas from the prepared GPA ARD table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ffcws_data_processor.landmarks import export_landmark_schemas


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Write nested FFCWS landmark schemas without copying ARD tables."
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ard" / "ffc_median_mode_gpa",
    )
    parser.add_argument(
        "--schema-root", type=Path, default=PROJECT_ROOT / "schema"
    )
    parser.add_argument("--dataset", default="ffc_median_mode_gpa")
    parser.add_argument("--outcome", default="gpa")
    parser.add_argument("--id-column", default="challengeID")
    args = parser.parse_args(argv)
    artifacts = export_landmark_schemas(
        dataset_dir=args.dataset_dir,
        schema_root=args.schema_root,
        dataset=args.dataset,
        outcome=args.outcome,
        id_column=args.id_column,
    )
    print(
        {
            "source_wave_labels": str(artifacts.source_wave_labels_path),
            "unassigned_sources": str(artifacts.unassigned_sources_path),
            "schemas": {key: str(value) for key, value in artifacts.schema_paths.items()},
        }
    )


if __name__ == "__main__":
    main()
