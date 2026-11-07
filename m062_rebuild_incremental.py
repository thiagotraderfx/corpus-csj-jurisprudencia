"""Rebuild incremental: solo embebe chunks nuevos."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
EMB = ROOT / "embeddings"
META = EMB / "meta.json"
PASSAGES = EMB / "passages.npy"
IDS = EMB / "passages_ids.jsonl"
CHUNKS = ROOT / "chunks.jsonl"


def main():
    if not (META.is_file() and PASSAGES.is_file() and IDS.is_file()):
        print("[FULL] Índice no existe, rebuild completo")
        return subprocess.call([sys.executable, "m062_rebuild.py"])

    meta = json.loads(META.read_text(encoding="utf-8"))
    arr = np.load(PASSAGES)
    ids = [json.loads(l) for l in IDS.read_text(encoding="utf-8").splitlines() if l.strip()]
    indexed = {i["chunk_id"] for i in ids}

    all_chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    all_ids = {c["chunk_id"] for c in all_chunks}

    new_chunks = [c for c in all_chunks if c["chunk_id"] not in indexed]
    orphans = indexed - all_ids

    print(f"Corpus: {len(all_chunks)}  Indexados: {len(indexed)}  "
          f"Nuevos: {len(new_chunks)}  Huérfanos: {len(orphans)}")

    if not new_chunks and not orphans:
        print("Índice al día")
        return 0

    if orphans or len(new_chunks) > len(indexed) * 0.5:
        print("[FULL] Huérfanos o mayoría nuevos, rebuild completo")
        return subprocess.call([sys.executable, "m062_rebuild.py"])

    print(f"[INCREMENTAL] Embebiendo {len(new_chunks)} chunks nuevos")
    from embedding_client import EmbeddingClient
    client = EmbeddingClient(META)
    new_vecs = client.embed([c["text"] for c in new_chunks],
                            input_type="passage", batch_size=10)
    new_arr = np.array(new_vecs, dtype=np.float32)

    if new_arr.shape[1] != meta["dim"]:
        print("[FAIL] dim mismatch, rebuild completo")
        return subprocess.call([sys.executable, "m062_rebuild.py"])

    combined = np.vstack([arr, new_arr])
    combined_ids = ids + [
        {"chunk_id": c["chunk_id"], "providencia": c.get("providencia"),
         "section": c.get("section"), "md_url": c.get("md_url"),
         "raw_url": c.get("raw_url")}
        for c in new_chunks
    ]

    np.save(PASSAGES, combined)
    IDS.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in combined_ids) + "\n",
                   encoding="utf-8")
    meta["n_passages"] = int(combined.shape[0])
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"OK: {combined.shape}, añadidos: {len(new_chunks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
