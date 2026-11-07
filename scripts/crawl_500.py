#!/usr/bin/env python3
"""Crawl estratificado 500 sentencias con checkpoint.

Crawler subyacente: m062_crawler_byid.py (dedup vía row_key + SHA-256).
Uso:
    python3 scripts/crawl_500.py --dry-run
    python3 scripts/crawl_500.py
    python3 scripts/crawl_500.py --resume
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "crawl_plan_500.json"
CHECKPOINT = ROOT / "crawl_500.checkpoint.json"
LOG = ROOT / "crawl_500.log"


def log_event(event):
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_checkpoint():
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {"started_at": datetime.now(timezone.utc).isoformat(), "cells": {}}


def save_checkpoint(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    CHECKPOINT.write_text(json.dumps(state, indent=2))


def run_cell(year, sala, count, delay):
    cmd = [
        sys.executable, str(ROOT / "m062_crawler_byid.py"),
        "--type", "sentencia",
        "--year", str(year),
        "--sala", sala,
        "--max-docs", str(count),
        "--delay", str(delay),
        "--format", "word",
    ]
    log_event({"event": "cell_start", "year": year, "sala": sala, "count": count})
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
    elapsed = time.time() - t0
    log_event({
        "event": "cell_end", "year": year, "sala": sala,
        "rc": r.returncode, "elapsed_s": round(elapsed, 1),
        "stdout_tail": r.stdout[-1500:],
        "stderr_tail": r.stderr[-500:] if r.stderr else "",
    })
    return r.returncode, elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-2026", action="store_true")
    args = ap.parse_args()

    plan = json.loads(PLAN.read_text())
    plan.pop("_meta", None)
    cells = {k: v for k, v in plan.items() if isinstance(v, int) and v > 0}
    if args.skip_2026:
        cells = {k: v for k, v in cells.items() if not k.startswith("2026__")}

    state = load_checkpoint() if args.resume else {
        "started_at": datetime.now(timezone.utc).isoformat(), "cells": {}
    }

    total_target = sum(cells.values())
    total_done = sum(state["cells"].get(k, {}).get("crawled", 0) for k in cells)

    print("═" * 60)
    print(f"crawl_500.py — {len(cells)} celdas")
    print(f"  Target:   {total_target}  |  Ya: {total_done}  |  Faltan: {total_target - total_done}")
    print(f"  Modo:     {'DRY-RUN' if args.dry_run else 'REAL'}  |  Resume: {args.resume}")
    print("═" * 60)

    priority = {"penal": 0, "laboral": 1, "civil": 2, "especial": 3}
    ordered = sorted(cells.items(), key=lambda kv: (priority.get(kv[0].split("__")[1], 9), kv[0]))

    for key, target in ordered:
        year, sala = key.split("__")
        done = state["cells"].get(key, {}).get("crawled", 0)
        need = target - done
        if need <= 0:
            print(f"  ✓ {key}: completo ({done}/{target})")
            continue
        print(f"\n  → {key}: {done}/{target}, faltan {need}")
        if args.dry_run:
            print(f"    [DRY] m062_crawler_byid.py --year {year} --sala {sala} --max-docs {need}")
            log_event({"event": "dry_run", "key": key, "need": need})
            continue
        rc, elapsed = run_cell(year, sala, need, args.delay)
        if rc == 0:
            state["cells"][key] = {"crawled": target, "status": "ok", "elapsed_s": round(elapsed, 1)}
            print(f"    ✓ OK ({elapsed:.0f}s)")
        else:
            state["cells"][key] = {"crawled": done, "status": f"fail_rc_{rc}", "elapsed_s": round(elapsed, 1)}
            print(f"    ✗ falló rc={rc}")
        save_checkpoint(state)
        time.sleep(5)

    done_total = sum(state["cells"].get(k, {}).get("crawled", 0) for k in cells)
    print(f"\n{'═' * 60}\nResumen: {done_total}/{total_target}\nCheckpoint: {CHECKPOINT}")


if __name__ == "__main__":
    main()
