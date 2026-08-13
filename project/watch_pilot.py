"""Progress monitor for a running panel sweep.

Reads the run log and the output directory; makes no assumptions beyond the
engine's own log lines.  Safe to run repeatedly while the sweep is in flight.

    ../.venv/bin/python watch_pilot.py
    ../.venv/bin/python watch_pilot.py --log outputs/pilot.log
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

PANEL_START = re.compile(r"^\[nk_grid\] (\S+ \S+) panel (\S+) starting")
PANEL_DONE = re.compile(r"^\[nk_grid\] (\S+ \S+) panel (\S+) finished")
BATCH = re.compile(r"^\[nk_grid\] (\S+ \S+) batch (\d+)/(\d+) wrote checkpoint "
                   r"new_rows=(\d+) ok=(\d+) failed=(\d+) skipped=(\d+)")
TOTAL_JOBS = re.compile(r"jobs total=(\d+)")


def _fmt(minutes: float) -> str:
    if minutes < 60:
        return f"{minutes:.0f} 分钟"
    return f"{minutes / 60:.1f} 小时"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="outputs/pilot.log")
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--manifest", default="panels.landmark.pilot.yaml")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"找不到日志: {log_path}")
        return 1

    started: dict[str, dt.datetime] = {}
    finished: dict[str, dt.datetime] = {}
    batches: list[tuple[dt.datetime, str, int, int, int, int]] = []
    current = None
    jobs_total = None

    for line in log_path.read_text(errors="ignore").splitlines():
        if match := PANEL_START.match(line):
            current = match.group(2)
            started.setdefault(current, dt.datetime.fromisoformat(match.group(1)))
        elif match := PANEL_DONE.match(line):
            finished[match.group(2)] = dt.datetime.fromisoformat(match.group(1))
        elif match := TOTAL_JOBS.search(line):
            jobs_total = int(match.group(1))
        elif match := BATCH.match(line):
            batches.append((
                dt.datetime.fromisoformat(match.group(1)),
                current or "?",
                int(match.group(2)), int(match.group(3)),
                int(match.group(6)), int(match.group(7)),
            ))

    configured: list[str] = []
    manifest_path = Path(args.manifest)
    if manifest_path.exists():
        import yaml
        document = yaml.safe_load(manifest_path.read_text()) or {}
        configured = [panel["name"] for panel in document.get("panels", [])]

    if not started:
        print("日志里还没有 panel 开始的记录")
        return 0

    first = min(started.values())
    last = batches[-1][0] if batches else first
    elapsed = (last - first).total_seconds() / 60

    print(f"起始 {first:%m-%d %H:%M}   最近活动 {last:%m-%d %H:%M}   已用 {_fmt(elapsed)}")
    print()

    done_panels = len(finished)
    total_panels = len(configured) or len(started)
    print(f"档位进度  {done_panels}/{total_panels} 完成"
          f"（配置里共 {total_panels} 个，串行执行）")
    for name in configured or started:
        if name in finished:
            span = (finished[name] - started[name]).total_seconds() / 60
            print(f"  ✅ {name:<38} {_fmt(span)}")
        else:
            same = [b for b in batches if b[1] == name]
            if same:
                _, _, cur, total, _, _ = same[-1]
                span = (same[-1][0] - started[name]).total_seconds() / 60
                pct = cur / total
                eta = span / pct - span if pct > 0 else float("nan")
                print(f"  🔄 {name:<38} {cur}/{total} ({pct:.0%})"
                      f"  已用 {_fmt(span)}  本档剩余约 {_fmt(eta)}")
            elif name in started:
                print(f"  ⏳ {name:<38} 刚开始")
            else:
                print(f"  ⬜ {name:<38} 未开始")

    failed = sum(b[4] for b in batches)
    skipped = sum(b[5] for b in batches)
    print(f"\n失败 {failed}   跳过 {skipped}", end="")
    if failed:
        print("   ⚠️ 有失败 cell，跑完要查原因", end="")
    print()

    if done_panels and done_panels < total_panels:
        per_panel = sum(
            (finished[n] - started[n]).total_seconds() / 60 for n in finished
        ) / done_panels
        in_flight = [n for n in started if n not in finished]
        spent_now = sum(
            (batches[-1][0] - started[n]).total_seconds() / 60 for n in in_flight
        )
        remaining = (total_panels - done_panels) * per_panel - spent_now
        finish_at = last + dt.timedelta(minutes=remaining)
        print(f"按每档平均 {_fmt(per_panel)} 推算，全部剩余约 {_fmt(remaining)}"
              f"（预计 {finish_at:%m-%d %H:%M} 完成）")

    out_dir = Path(args.outputs)
    parts = list(out_dir.glob("*.prediction-parts/*.parquet"))
    finals = list(out_dir.glob("*.predictions.parquet"))
    print(f"\n预测导出  分片 {len(parts)} 个   已合并文件 {len(finals)} 个")
    if not parts and not finals and batches:
        print("  ⚠️ 已经跑了一些批次却还没有任何分片——白名单只覆盖 N=1165，")
        print("     而 N 是网格里最后才跑到的值，早期没有分片属于正常。")
    for path in sorted(finals):
        print(f"  {path.name}  {path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
