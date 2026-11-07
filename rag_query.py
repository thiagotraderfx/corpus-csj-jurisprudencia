"""Consulta de retrieval puro sobre el corpus CSJ."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from embedding_client import EmbeddingClient

ROOT = Path(__file__).parent
EMB = ROOT / "embeddings"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    meta = json.loads((EMB / "meta.json").read_text(encoding="utf-8"))
    arr = np.load(EMB / "passages.npy")
    ids = [json.loads(l) for l in (EMB / "passages_ids.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    print(f"Provider: {meta['provider']} / {meta['model']} / dim={meta['dim']}")
    print(f"Query:    {args.question!r}\n")

    client = EmbeddingClient(EMB / "meta.json")
    qv = client.embed(args.question)[0]
    scores = arr @ qv
    top_idx = np.argsort(scores)[-args.top_k:][::-1]

    print(f"Top-{args.top_k} chunks:\n")
    for rank, i in enumerate(top_idx, 1):
        item = ids[i]
        score = float(scores[i])
        print(f"  [{rank}] score={score:.4f}")
        print(f"      {item['providencia']}  [{item['section']}]")
        print(f"      {item['md_url']}")
        print(f"      chunk_id: {item['chunk_id']}")
        print()


if __name__ == "__main__":
    main()
