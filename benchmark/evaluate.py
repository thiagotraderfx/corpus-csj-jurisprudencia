#!/usr/bin/env python3
"""Evalua los resultados de benchmark/run_benchmark.py (metricas objetivas)."""
import json, sys
from datetime import datetime
from pathlib import Path

BENCH_DIR = Path(__file__).parent
PREGUNTAS = BENCH_DIR / "data" / "preguntas.jsonl"
RESULTS_DIR = BENCH_DIR / "results"


def ultimo_resultado():
    files = sorted(RESULTS_DIR.glob("respuestas_*.jsonl"))
    if not files:
        print(f"ERROR: No hay resultados. Ejecuta primero benchmark/run_benchmark.py")
        sys.exit(1)
    return files[-1]


def cargar_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def metricas(respuestas):
    total = len(respuestas)
    responded = sum(1 for r in respuestas if not r.get("refused"))
    refused = sum(1 for r in respuestas if r.get("refused"))
    verified = sum(1 for r in respuestas if r.get("verified") is True)
    cov_gap = sum(1 for r in respuestas if r.get("coverage_gap") is True)
    errors = sum(1 for r in respuestas if "_bench" in r and "error" in r["_bench"])

    latencies = [r["_bench"]["latency_s"] for r in respuestas
                 if "_bench" in r and "latency_s" in r["_bench"]]
    lat_avg = sum(latencies) / len(latencies) if latencies else 0
    lat_p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    return {
        "total": total,
        "responded": responded,
        "refused": refused,
        "verified": verified,
        "coverage_gap": cov_gap,
        "errors": errors,
        "coverage_rate": round(responded / total, 3) if total else 0,
        "verification_rate": round(verified / responded, 3) if responded else 0,
        "latency_avg_s": round(lat_avg, 2),
        "latency_p95_s": round(lat_p95, 2),
    }


def main():
    respuestas = cargar_jsonl(ultimo_resultado())
    print(f"Respuestas cargadas: {len(respuestas)}")

    m = metricas(respuestas)
    print("\nMetricas objetivas:")
    for k, v in m.items():
        print(f"  {k}: {v}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"evaluacion_{ts}.json"
    with open(out, "w") as f:
        json.dump({"metricas": m, "respuestas": respuestas}, f, ensure_ascii=False, indent=2)
    print(f"\nReporte: {out}")
    print(f"\nPendiente: LLM-as-judge (precision 1-5) requiere OPENROUTER_API_KEY.")


if __name__ == "__main__":
    main()
