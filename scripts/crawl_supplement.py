#!/usr/bin/env python3
"""Crawl 20 docs suplementarios para llegar a 300."""
import argparse, json, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "taxonomy_v3_supplement.json"
CHECKPOINT = ROOT / "crawl_supplement.checkpoint.json"
LOG = ROOT / "crawl_supplement.log"


def log_event(event):
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_checkpoint():
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {"started_at": datetime.now(timezone.utc).isoformat(), "temas": {}}


def save_checkpoint(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    CHECKPOINT.write_text(json.dumps(state, indent=2))


def sala_to_crawler(sala):
    if sala.startswith("civil"): return "civil"
    if sala.startswith("laboral"): return "laboral"
    if sala.startswith("penal"): return "penal"
    return "all"


def run_tema(tema, faltan, delay, timeout_s=900):
    sala_crawler = sala_to_crawler(tema["sala"])
    cmd = [
        sys.executable, str(ROOT / "m062_crawler_byid.py"),
        "--type", "sentencia",
        "--search-tema", tema["consulta"],
        "--sala", sala_crawler,
        "--max-docs", str(faltan),
        "--delay", str(delay),
        "--format", "word",
    ]
    log_event({"event": "tema_start", "tema": tema["tema"], "faltan": faltan})
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout_s)
        elapsed = time.time() - t0
        m = re.search(r"Descargados:\s*(\d+)\s*nuevos", r.stdout)
        downloaded = int(m.group(1)) if m else 0
        log_event({"event": "tema_end", "tema": tema["tema"], "rc": r.returncode,
                   "downloaded": downloaded, "elapsed_s": round(elapsed, 1)})
        return downloaded, "ok" if r.returncode == 0 else "rc_%d" % r.returncode
    except subprocess.TimeoutExpired:
        log_event({"event": "tema_timeout", "tema": tema["tema"]})
        return 0, "timeout"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    taxonomy = json.loads(TAXONOMY.read_text())
    temas = taxonomy["temas"]
    total_target = sum(t["cuota"] for t in temas)

    state = load_checkpoint() if args.resume else {
        "started_at": datetime.now(timezone.utc).isoformat(), "temas": {}
    }
    done = sum(t.get("downloaded", 0) for t in state["temas"].values())

    print("=" * 62)
    print("crawl_supplement.py — %d temas · %d docs target" % (len(temas), total_target))
    print("  Ya hecho: %d | Faltan: %d" % (done, total_target - done))
    print("  Modo: %s" % ("DRY-RUN" if args.dry_run else "REAL"))
    print("=" * 62)

    for i, tema in enumerate(temas, 1):
        key = tema["tema"]
        cuota = tema["cuota"]
        t_state = state["temas"].get(key, {})
        downloaded = t_state.get("downloaded", 0)

        if downloaded >= cuota:
            print("[%2d/%d] OK %-38s (%d/%d)" % (i, len(temas), key, downloaded, cuota))
            continue

        faltan = cuota - downloaded
        print("")
        print("[%2d/%d] >> %-38s sala=%-10s falta=%d/%d" % (
            i, len(temas), key, sala_to_crawler(tema["sala"]), faltan, cuota
        ))
        print("         consulta: %r" % tema["consulta"])

        if args.dry_run:
            print("         [DRY] m062_crawler_byid.py --search-tema %r --sala %s --max-docs %d" % (
                tema["consulta"], sala_to_crawler(tema["sala"]), faltan))
            continue

        d_now, status = run_tema(tema, faltan, args.delay)
        state["temas"][key] = {
            "downloaded": downloaded + d_now,
            "status": "ok" if d_now > 0 else status,
        }
        save_checkpoint(state)

        if d_now > 0:
            print("         + %d docs nuevos" % d_now)
        else:
            print("         ! 0 docs (%s) — siguiendo" % status)

        time.sleep(3)

    print("")
    print("=" * 62)
    final_done = sum(t.get("downloaded", 0) for t in state["temas"].values())
    print("RESUMEN: %d/%d docs crawleados" % (final_done, total_target))
    print("=" * 62)


if __name__ == "__main__":
    main()
