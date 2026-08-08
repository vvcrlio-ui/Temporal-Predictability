"""Pre-flight check for the FFCWS Challenge input files.

Run from ``project/`` before ``python adapter.py``.  It verifies that the three
expected files exist, are readable, and look like the Fragile Families Challenge
release rather than the general FFCWS distribution.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

OUTCOMES = ("gpa", "grit", "materialHardship", "eviction", "layoff", "jobTraining")


def main() -> int:
    config = yaml.safe_load(Path("config/ffc.yaml").read_text())
    base = Path("config")
    problems: list[str] = []

    for key in ("background", "train", "test"):
        path = (base / config["paths"][key]).resolve()
        print(f"\n--- {key}: {path}")
        if not path.exists():
            problems.append(f"{key} 缺失: {path}")
            print("   ✗ 文件不存在")
            continue
        size_mb = path.stat().st_size / 1_048_576
        print(f"   大小 {size_mb:.1f} MB")
        try:
            if path.suffix == ".dta":
                frame = pd.read_stata(path, convert_categoricals=False)
            else:
                frame = pd.read_csv(path)
        except Exception as error:  # noqa: BLE001 - report, do not crash
            problems.append(f"{key} 读取失败: {error}")
            print(f"   ✗ 读取失败: {error}")
            continue
        print(f"   形状 {frame.shape[0]} 行 × {frame.shape[1]} 列")

        id_column = config["id_column"]
        if id_column not in frame.columns:
            problems.append(f"{key} 缺少 ID 列 {id_column!r}")
            print(f"   ✗ 没有 {id_column} 列 —— 很可能下错了数据集")
        else:
            print(f"   ✓ 有 {id_column}")

        if key in ("train", "test"):
            missing = [name for name in OUTCOMES if name not in frame.columns]
            if missing:
                problems.append(f"{key} 缺少结果变量: {missing}")
                print(f"   ✗ 缺少结果变量 {missing}")
            else:
                print(f"   ✓ 六个结果变量齐全")

    print("\n" + "=" * 60)
    if problems:
        print("检查未通过:")
        for problem in problems:
            print(f"  - {problem}")
        print("\n请确认下载的是 Fragile Families Challenge 数据集")
        print("(带官方 train/test 切分),不是 ICPSR 31622 通用发布版。")
        return 1
    print("检查通过,可以运行:  ../.venv/bin/python adapter.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
