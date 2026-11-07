"""Benchmark del retrieval usando los metadatos del corpus como ground truth.

Para cada documento, se genera una query desde su 'tema' y se verifica si
un chunk del MISMO documento aparece en el top-K. Esto no mide calidad del
LLM (eso es otro ejercicio), sino cobertura del índice de embeddings.

Métricas:
  precision@k  — fracción de top-k chunks que son del doc esperado
  hit@k        — al menos 1 chunk del doc esperado en top-k (binario)
  mrr          — mean reciprocal rank del primer hit
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path.cwd()
EMB = ROOT / "embeddings"
NIM_EMBED = "https://integrate.api.nvidia.com/v1/embeddings"
TOP_K = 5

meta = json.loads((EMB / "meta.json").read_text(encoding="utf-8"))
arr = np.load(EMB / "passages.npy")
ids = [json.loads(l) for l in (EMB / "passages_ids.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
records = [json.loads(l) for l in (ROOT / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

api_key = os.environ.get("NVIDIA_API_KEY")
if not api_key:
    sys.exit("Falta NVIDIA_API_KEY")


def embed(q):
    r = requests.post(NIM_EMBED,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": [q], "model": meta["model"], "input_type": "query",
              "encoding_format": "float", "truncate": "END"},
        timeout=30)
    r.raise_for_status()
    return np.array(r.json()["data"][0]["embedding"], dtype=np.float32)


# Construir queries desde metadatos
queries = []
for rec in records:
    if rec.get("ext") != "docx":
        continue
    tema = rec.get("tema")
    prov = rec.get("providencia")
    if not tema or not prov:
        continue
    # Query corta (primeras ~150 chars del tema)
    q = tema[:150].strip()
    if len(q) < 20:
        continue
    queries.append({"q": q, "expected": prov, "tema_full": tema[:100]})

print(f"Queries de benchmark: {len(queries)}")
print(f"Top-K: {TOP_K}\n")

precisions, hits, rrs = [], [], []
misses = []

for i, item in enumerate(queries, 1):
    q_vec = embed(item["q"])
    scores = arr @ q_vec
    top_idx = np.argsort(scores)[-TOP_K:][::-1]
    top_provs = [ids[j]["providencia"] for j in top_idx]

    hit_positions = [pos for pos, p in enumerate(top_provs, 1) if p == item["expected"]]
    hit = 1 if hit_positions else 0
    prec = hit_positions and (1 / len(hit_positions)) or 0
    # precision@k = (# hits) / k
    n_hits = sum(1 for p in top_provs if p == item["expected"])
    prec = n_hits / TOP_K
    rr = 1 / hit_positions[0] if hit_positions else 0

    hits.append(hit)
    precisions.append(prec)
    rrs.append(rr)
    if not hit:
        misses.append({"query": item["q"][:60], "expected": item["expected"], "got": top_provs[:3]})

    if i % 10 == 0:
        print(f"  {i}/{len(queries)}")

print()
print("=" * 72)
print("RESULTADOS BENCHMARK")
print("=" * 72)
print(f"  Queries:       {len(queries)}")
print(f"  hit@{TOP_K}:        {sum(hits)}/{len(hits)} = {100*sum(hits)/len(hits):.1f}%")
print(f"  precision@{TOP_K}:  {100*sum(precisions)/len(precisions):.1f}%")
print(f"  MRR:           {sum(rrs)/len(rrs):.3f}")
print()
if misses:
    print(f"  Misses ({len(misses)}):")
    for m in misses[:5]:
        print(f"    q={m['query']!r}")
        print(f"      esperado: {m['expected']}  obtenido: {m['got']}")

report = {
    "n_queries": len(queries),
    "top_k": TOP_K,
    "hit_at_k": round(sum(hits)/len(hits), 4),
    "precision_at_k": round(sum(precisions)/len(precisions), 4),
    "mrr": round(sum(rrs)/len(rrs), 4),
    "misses": misses,
}
(ROOT / "benchmark_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Reporte: benchmark_report.json")
