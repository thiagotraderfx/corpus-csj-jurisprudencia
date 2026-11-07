import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_manifest_exists():
    assert (ROOT / "manifest.jsonl").is_file()


def test_chunks_exists():
    assert (ROOT / "chunks.jsonl").is_file()


def test_embeddings_consistent():
    meta = json.loads((ROOT / "embeddings" / "meta.json").read_text())
    arr = np.load(ROOT / "embeddings" / "passages.npy")
    assert arr.shape[0] == meta["n_passages"]
    assert arr.shape[1] == meta["dim"]


def test_all_chunks_in_index():
    chunk_ids = {json.loads(l)["chunk_id"]
                 for l in (ROOT / "chunks.jsonl").read_text().splitlines() if l.strip()}
    indexed_ids = {json.loads(l)["chunk_id"]
                   for l in (ROOT / "embeddings" / "passages_ids.jsonl").read_text().splitlines() if l.strip()}
    assert chunk_ids == indexed_ids


def test_no_duplicate_shas():
    records = [json.loads(l) for l in (ROOT / "manifest.jsonl").read_text().splitlines() if l.strip()]
    shas = [r["sha256"] for r in records]
    assert len(shas) == len(set(shas))


def test_postprocess_cjk():
    from postprocess import normalize_answer
    out = normalize_answer("fallo 【1】 y 【2】")
    assert "[" in out and "]" in out
    assert "【" not in out and "】" not in out
