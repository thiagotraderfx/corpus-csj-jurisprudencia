"""Health check completo: integridad + retrieval + LLM + postproceso."""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path.cwd()
EMB = ROOT / "embeddings"
FAILS = []


def check(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
        FAILS.append((name, str(exc)))


print("=" * 72)
print("HEALTH CHECK")
print("=" * 72)

# 1. Manifest
def _manifest():
    recs = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text().splitlines() if l.strip()]
    assert len(recs) > 0, "manifest vacío"
    globals()["_recs"] = recs
check("Manifest carga y no vacío", _manifest)

# 2. RAW files + hashes
def _raw():
    recs = globals()["_recs"]
    for r in recs:
        p = ROOT / r["raw_path"]
        assert p.is_file(), f"falta {p}"
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        assert h == r["sha256"], f"hash mismatch {r['providencia']}"
check("RAW files existen + SHA-256 coincide", _raw)

# 3. MD files
def _md():
    recs = globals()["_recs"]
    missing = [r for r in recs if r.get("ext") == "docx" and
               not (ROOT / (r.get("md_path") or "")).is_file()]
    assert not missing, f"{len(missing)} MD faltantes"
check("MD files existen", _md)

# 4. Chunks
def _chunks():
    lines = (ROOT/"chunks.jsonl").read_text().splitlines()
    assert len(lines) > 0, "chunks vacío"
    for line in lines:
        c = json.loads(line)
        assert c.get("chunk_id"), "chunk sin id"
        assert len(c.get("text", "")) > 0, "chunk sin texto"
check("Chunks JSON válido", _chunks)

# 5. Embeddings matrix
def _emb():
    arr = np.load(EMB / "passages.npy")
    meta = json.loads((EMB/"meta.json").read_text())
    assert arr.shape[0] == meta["n_passages"], "shape rows"
    assert arr.shape[1] == meta["dim"], "shape cols"
    assert arr.dtype == np.float32, "dtype"
    # Verificar normalización (vectores unitarios)
    norms = np.linalg.norm(arr[:10], axis=1)
    assert all(0.95 < n < 1.05 for n in norms), f"normas: {norms[:5]}"
check("Embeddings matrix válida y normalizada", _emb)

# 6. IDs alineados con chunks
def _ids():
    ids = [json.loads(l) for l in (EMB/"passages_ids.jsonl").read_text().splitlines() if l.strip()]
    meta = json.loads((EMB/"meta.json").read_text())
    assert len(ids) == meta["n_passages"], "count mismatch"
    # Verificar que todos los chunk_id existen
    chunk_ids = {json.loads(l)["chunk_id"] for l in (ROOT/"chunks.jsonl").read_text().splitlines() if l.strip()}
    missing = [i["chunk_id"] for i in ids if i["chunk_id"] not in chunk_ids]
    assert not missing, f"{len(missing)} ids huérfanos"
check("IDs alineados con chunks", _ids)

# 7. Retrieval end-to-end
def _retrieval():
    from embedding_client import EmbeddingClient
    meta = json.loads((EMB/"meta.json").read_text())
    arr = np.load(EMB / "passages.npy")
    client = EmbeddingClient(EMB / "meta.json")
    qv = client.embed("test")[0]
    assert qv.shape[0] == meta["dim"], f"dim {qv.shape[0]} != {meta['dim']}"
    scores = arr @ qv
    assert len(scores) == meta["n_passages"]
check("Retrieval end-to-end (embed + cosine)", _retrieval)

# 8. LLM disponible
def _llm():
    from rag_ask import get_available_models, CHAT_FALLBACKS
    api_key = os.environ.get("NVIDIA_API_KEY")
    avail = get_available_models(api_key)
    assert len(avail) > 0, "ningún modelo chat disponible"
    globals()["_avail_models"] = avail
check("Modelos chat disponibles", _llm)

# 9. Postproceso CJK → ASCII
def _post():
    from postprocess import normalize_answer
    test = "El fallo 【1】 cita 【2】【3】 y concluye."
    out = normalize_answer(test)
    assert "【" not in out and "】" not in out, f"quedan CJK: {out}"
    assert "[1]" in out and "[2]" in out, f"no convirtió: {out}"
check("Postproceso CJK → ASCII", _post)

# ─── Veredicto ───
print()
print("=" * 72)
if FAILS:
    print(f"HEALTH: {len(FAILS)} FALLOS")
    print("=" * 72)
    for name, err in FAILS:
        print(f"  ✗ {name}\n    {err}")
    sys.exit(1)
else:
    print("HEALTH: OK — sistema listo para escalar")
    print("=" * 72)
    print(f"  Modelos chat disponibles: {len(globals().get('_avail_models', []))}")
    for m in globals().get('_avail_models', [])[:3]:
        print(f"    - {m}")
