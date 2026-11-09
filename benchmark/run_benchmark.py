#!/usr/bin/env python3
"""Ejecuta el benchmark contra el sistema corriendo en localhost:8000.

Requiere:
- benchmark/data/preguntas.jsonl (escrito por el abogado)
- uvicorn api:app --host 127.0.0.1 --port 8000 (en otra terminal)
"""
import json, os, sys, time, requests
from datetime import datetime
from pathlib import Path

BENCH_DIR = Path(__file__).parent
PREGUNTAS = BENCH_DIR / "data" / "preguntas.jsonl"
RESULTS_DIR = BENCH_DIR / "results"
API_URL = os.environ.get("BENCH_API", "http://127.0.0.1:8000")


def cargar_preguntas():
    if not PREGUNTAS.exists():
        print(f"ERROR: {PREGUNTAS} no existe.")
        print(f"       Copia benchmark/data/preguntas_template.jsonl y escribe tus preguntas.")
        sys.exit(1)
    preguntas = []
    with open(PREGUNTAS) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                preguntas.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARN: JSON invalido en linea: {line[:80]}... ({e})")
    return preguntas


def run():
    preguntas = cargar_preguntas()
    if not preguntas:
        print("ERROR: No hay preguntas validas.")
        sys.exit(1)

    print(f"Preguntas cargadas: {len(preguntas)}")
    print(f"API: {API_URL}")

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"respuestas_{ts}.jsonl"

    with open(out, "w") as f:
        for i, p in enumerate(preguntas, 1):
            print(f"  [{i}/{len(preguntas)}] {p['id']}: {p['pregunta'][:60]}...", end=" ", flush=True)
            t0 = time.time()
            try:
                r = requests.post(
                    f"{API_URL}/ask/safe",
                    json={"query": p["pregunta"], "k": 5},
                    timeout=120,
                )
                r.raise_for_status()
                resp = r.json()
                resp["_bench"] = {
                    "id": p["id"],
                    "nivel": p.get("nivel"),
                    "tema": p.get("tema"),
                    "latency_s": round(time.time() - t0, 2),
                    "status": r.status_code,
                }
                f.write(json.dumps(resp, ensure_ascii=False) + "\n")
                print(f"OK ({resp['_bench']['latency_s']}s)")
            except Exception as e:
                print(f"FAIL {type(e).__name__}: {e}")
                f.write(json.dumps({"_bench": {"id": p["id"], "error": str(e)}}, ensure_ascii=False) + "\n")

    print(f"\nResultados: {out}")
    print(f"Siguiente: python3 benchmark/evaluate.py")


if __name__ == "__main__":
    run()
