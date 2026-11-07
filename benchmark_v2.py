"""Benchmark del retrieval con DOS metodologías:

  A) retrieval_sanity: query = chunk de texto del doc
     Mide si el embedding preserva identidad del documento.
     Esperado: >=95%

  B) topic_retrieval: query = tema del doc
     Mide cobertura por tema. Problema: docs con tema idéntico
     son indistinguibles. Se reportan misses explicados.
     Esperado: 70-85% (limitado por duplicación de metadata)
"""
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import requests

ROOT = Path.cwd()
EMB = ROOT / "embeddings"
NIM = "https://integrate.api.nvidia.com/v1/embeddings"
TOP_K = 5
SEED = 42

api_key = os.environ.get("NVIDIA_API_KEY")
if not api_key:
    sys.exit("Falta NVIDIA_API_KEY")

meta = json.loads((EMB / "meta.json").read_text(encoding="utf-8"))
arr = np.load(EMB / "passages.npy")
ids = [json.loads(l) for l in (EMB / "passages_ids.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunks = {c["chunk_id"]: c for c in
          (json.loads(l) for l in (ROOT / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
records = [json.loads(l) for l in (ROOT / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


from embedding_client import EmbeddingClient
_embed_client = EmbeddingClient(EMB / "meta.json")

def embed_batch(texts):
    return _embed_client.embed(texts, batch_size=10)


def run_benchmark(queries, label):
    """queries: [{q, expected_prov}]. Devuelve dict de métricas."""
    hits, precs, rrs, misses = [], [], [], []
    BATCH = 10
    for start in range(0, len(queries), BATCH):
        batch = queries[start:start + BATCH]
        vecs = embed_batch([q["q"] for q in batch])
        for q, qv in zip(batch, vecs):
            scores = arr @ qv
            top_idx = np.argsort(scores)[-TOP_K:][::-1]
            top_provs = [ids[j]["providencia"] for j in top_idx]
            hit_pos = [p for p, prov in enumerate(top_provs, 1) if prov == q["expected"]]
            n_hits = sum(1 for p in top_provs if p == q["expected"])
            hits.append(1 if hit_pos else 0)
            precs.append(n_hits / TOP_K)
            rrs.append(1 / hit_pos[0] if hit_pos else 0)
            if not hit_pos:
                misses.append({"expected": q["expected"], "got": top_provs[:3]})
        if (start // BATCH + 1) % 5 == 0:
            print(f"  {label}: {min(start+BATCH, len(queries))}/{len(queries)}")

    return {
        "label": label,
        "n": len(queries),
        "hit@k": sum(hits) / len(hits),
        "precision@k": sum(precs) / len(precs),
        "mrr": sum(rrs) / len(rrs),
        "misses": misses[:10],
    }


print("=" * 72)
print("BENCHMARK V2")
print("=" * 72)

# ─── Método A: retrieval sanity (query = chunk text) ───
print("\n[A] Retrieval sanity (query = chunk del propio doc)")
random.seed(SEED)
docs_with_chunks = {}
for cid, c in chunks.items():
    prov = c.get("providencia")
    if prov and len(c.get("text", "")) > 300:
        docs_with_chunks.setdefault(prov, []).append(cid)

sanity_queries = []
for prov, cids in docs_with_chunks.items():
    cid = random.choice(cids)
    txt = chunks[cid]["text"]
    # Tomar primeros 300-500 chars del chunk (informativos, no metadata)
    q = txt[:400].strip()
    if len(q) >= 100:
        sanity_queries.append({"q": q, "expected": prov})

print(f"    Queries: {len(sanity_queries)}")
report_a = run_benchmark(sanity_queries, "sanity")

# ─── Método B: topic retrieval (query = tema, con dedup awareness) ───
print("\n[B] Topic retrieval (query = tema, advirtiendo duplicados)")
tema_count = Counter()
for rec in records:
    if rec.get("ext") == "docx" and rec.get("tema"):
        tema_count[rec["tema"][:150].strip()] += 1

topic_queries = []
duplicated = 0
for rec in records:
    if rec.get("ext") != "docx":
        continue
    tema = (rec.get("tema") or "")[:150].strip()
    if len(tema) < 20:
        continue
    # Solo incluir temas únicos (1 doc por tema) para benchmark limpio
    if tema_count[tema] == 1:
        topic_queries.append({"q": tema, "expected": rec["providencia"]})
    else:
        duplicated += 1

# Filtrar near-duplicates: temas con >80% de tokens compartidos
import re as _re
def _tokens(t): return set(_re.findall(r"[a-záéíóúñü]{3,}", (t or "").lower()))

kept_topics = []
near_dup = 0
for q in topic_queries:
    q_toks = _tokens(q["q"])
    is_dup = False
    for k in kept_topics:
        k_toks = _tokens(k["q"])
        if not q_toks or not k_toks: continue
        jaccard = len(q_toks & k_toks) / len(q_toks | k_toks)
        if jaccard > 0.80:
            is_dup = True
            break
    if is_dup:
        near_dup += 1
    else:
        kept_topics.append(q)

print(f"    Queries originales: {len(topic_queries)}")
print(f"    Excluidos near-dupes: {near_dup}")
print(f"    Queries finales: {len(kept_topics)}")
report_b = run_benchmark(kept_topics, "topic")

# ─── Reporte final ───
print("\n" + "=" * 72)
print("RESULTADOS")
print("=" * 72)
for r in (report_a, report_b):
    print(f"\n  {r['label'].upper()} ({r['n']} queries)")
    print(f"    hit@{TOP_K}:       {r['hit@k']*100:.1f}%")
    print(f"    precision@{TOP_K}: {r['precision@k']*100:.1f}%")
    print(f"    MRR:          {r['mrr']:.3f}")
    if r['misses']:
        print(f"    Misses: {len(r['misses'])}")

final = {
    "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    "corpus": {"n_docs": len(docs_with_chunks), "n_chunks": len(chunks)},
    "retrieval_sanity": report_a,
    "topic_retrieval": report_b,
}
(ROOT / "benchmark_report_v2.json").write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Reporte: benchmark_report_v2.json")

# ─── Criterio de salud ───
print("\n" + "=" * 72)
print("VEREDICTO")
print("=" * 72)
ok_sanity = report_a["hit@k"] >= 0.95
ok_topic = report_b["hit@k"] >= 0.75
print(f"  Retrieval sanity >= 95%:  {'✓ PASS' if ok_sanity else '✗ FAIL'} ({report_a['hit@k']*100:.1f}%)")
print(f"  Topic retrieval >= 75%:   {'✓ PASS' if ok_topic else '✗ FAIL'} ({report_b['hit@k']*100:.1f}%)")
sys.exit(0 if (ok_sanity and ok_topic) else 1)
