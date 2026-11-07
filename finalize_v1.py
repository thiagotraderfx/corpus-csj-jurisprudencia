import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
records = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunks = [json.loads(l) for l in (ROOT/"chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
meta = json.loads((ROOT/"embeddings"/"meta.json").read_text(encoding="utf-8"))
bench = json.loads((ROOT/"benchmark_report_v2.json").read_text(encoding="utf-8"))

docs = {}
for r in records:
    docs.setdefault(r["row_key"], r)

tipos = Counter()
salas = Counter()
years = Counter()
for r in docs.values():
    prov = r.get("providencia") or ""
    if prov.startswith("A"): tipos["auto"] += 1
    elif prov.startswith("S"): tipos["sentencia"] += 1
    if len(prov) > 1:
        sala = {"C":"civil","L":"laboral","P":"penal","E":"especial","T":"tutela"}.get(prov[1], "?")
        salas[sala] += 1
    m = re.search(r"/(\d{4})$", r.get("fecha") or "")
    if m: years[m.group(1)] += 1

raw_bytes = sum((ROOT/r["raw_path"]).stat().st_size for r in records if (ROOT/r["raw_path"]).is_file())
md_count = sum(1 for r in records if r.get("md_path") and (ROOT/r["md_path"]).is_file())

_shas = [r.get("sha256") for r in records]
_dup_count = len(_shas) - len(set(_shas))

summary = {
    "version": "1.0",
    "docs": len(docs),
    "chunks": len(chunks),
    "tipos": dict(tipos),
    "salas": dict(salas),
    "years": dict(sorted(years.items())),
    "raw_bytes": raw_bytes,
    "md_files": md_count,
    "duplicates_sha256": _dup_count,
    "embeddings": {"provider": meta["provider"], "model": meta["model"], "dim": meta["dim"]},
    "benchmark": {
        "sanity_hit@5": bench["retrieval_sanity"]["hit@k"],
        "sanity_mrr": bench["retrieval_sanity"]["mrr"],
        "topic_hit@5": bench["topic_retrieval"]["hit@k"],
        "topic_mrr": bench["topic_retrieval"]["mrr"],
    },
}
(ROOT/"v1_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
