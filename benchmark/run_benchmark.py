#!/usr/bin/env python3
"""Ejecuta benchmark contra uvicorn con run_id trazable."""
import hashlib, json, os, sys, time, requests
from datetime import datetime
from pathlib import Path

BENCH_DIR = Path(__file__).parent
RESULTS_DIR = BENCH_DIR / "results"
DEFAULT_API = "http://127.0.0.1:8803"
DEFAULT_INPUT = BENCH_DIR / "data" / "preguntas_demo.jsonl"


def cargar(path):
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try: out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARN: {e}")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--api", default=os.environ.get("BENCH_API", DEFAULT_API))
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} no existe"); sys.exit(1)

    preguntas = cargar(input_path)
    if not preguntas:
        print("ERROR: 0 preguntas"); sys.exit(1)

    # run_id = timestamp + hash(input) → trazabilidad exacta
    input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()[:12]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{input_hash}"

    RESULTS_DIR.mkdir(exist_ok=True)
    manifest_path = RESULTS_DIR / f"run_{run_id}.json"
    respuestas_path = RESULTS_DIR / f"respuestas_{run_id}.jsonl"

    # Escribir manifest ANTES de ejecutar (si falla, queda traza)
    manifest = {
        "run_id": run_id,
        "input_file": str(input_path.resolve()),
        "input_hash": input_hash,
        "api_url": args.api,
        "k": args.k,
        "started_at": datetime.now().isoformat(),
        "n_questions": len(preguntas),
        "status": "running",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"run_id: {run_id}")
    print(f"input:  {input_path.name} ({len(preguntas)} preguntas, hash={input_hash})")
    print(f"api:    {args.api}")
    print(f"out:    {respuestas_path.name}")

    ok_count, err_count = 0, 0
    with open(respuestas_path, "w") as f:
        for i, p in enumerate(preguntas, 1):
            pid = p.get("id", f"Q{i}")
            print(f"  [{i}/{len(preguntas)}] {pid}...", end=" ", flush=True)
            t0 = time.time()
            try:
                r = requests.post(f"{args.api}/ask/safe",
                    json={"query": p["pregunta"], "k": args.k}, timeout=120)
                r.raise_for_status()
                resp = r.json()
                resp["_bench"] = {
                    "id": pid, "nivel": p.get("nivel"), "tema": p.get("tema"),
                    "latency_s": round(time.time() - t0, 2),
                    "status": r.status_code,
                }
                f.write(json.dumps(resp, ensure_ascii=False) + "\n")
                ok_count += 1
                print(f"OK ({resp['_bench']['latency_s']}s)")
            except Exception as e:
                err_count += 1
                print(f"FAIL: {type(e).__name__}: {e}")
                f.write(json.dumps({
                    "_bench": {"id": pid, "error": str(e)},
                    "answer": "", "sources": [], "refused": None, "verified": None,
                }, ensure_ascii=False) + "\n")

    manifest["status"] = "completed"
    manifest["ended_at"] = datetime.now().isoformat()
    manifest["ok_count"] = ok_count
    manifest["err_count"] = err_count
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\n  Resultado: {ok_count} OK, {err_count} ERROR")
    print(f"  Manifest: {manifest_path.name}")
    print(f"  Respuestas: {respuestas_path.name}")
    print(f"\n  Evaluar: python3 benchmark/evaluate_v2.py --run-id {run_id}")


if __name__ == "__main__":
    main()
