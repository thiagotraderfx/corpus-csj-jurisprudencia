"""Embebe chunks.jsonl con NVIDIA NIM y guarda embeddings/passages.npy.

Uso:
    export NVIDIA_API_KEY="nvapi-..."
    python3 embed_with_nim.py [--model nvidia/nemotron-3-embed-1b]

Requiere: pip install requests numpy
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import numpy as np
    import requests
except ImportError:
    sys.exit("Falta: pip install requests numpy")

NIM_URL = os.environ.get("NIM_URL", "https://integrate.api.nvidia.com/v1/embeddings")


def embed(texts, api_key, model, input_type, batch=10, retries=3):
    vectors = []
    total = len(texts)
    for i in range(0, total, batch):
        chunk = texts[i:i + batch]
        for attempt in range(retries):
            try:
                r = requests.post(
                    NIM_URL,
                    headers={"Authorization": "Bearer " + api_key,
                             "Content-Type": "application/json"},
                    json={"input": chunk, "model": model,
                          "input_type": input_type,
                          "encoding_format": "float",
                          "truncate": "END"},
                    timeout=120,
                )
                r.raise_for_status()
                for item in r.json()["data"]:
                    vectors.append(item["embedding"])
                break
            except Exception as exc:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                print("  retry %d/%d en %ds: %s" % (attempt + 1, retries, wait, exc))
                time.sleep(wait)
        if (i // batch + 1) % 5 == 0:
            print("  %d/%d" % (min(i + len(chunk), total), total))
    return vectors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/nemotron-3-embed-1b")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        sys.exit("Falta NVIDIA_API_KEY en el entorno")

    root = Path(args.root).resolve()
    chunks_file = root / "chunks.jsonl"
    if not chunks_file.is_file():
        sys.exit("No existe " + str(chunks_file))

    chunks = [json.loads(l) for l in chunks_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not chunks:
        sys.exit("chunks.jsonl vacio")

    print("Modelo:    " + args.model)
    print("Chunks:    %d" % len(chunks))
    print("Endpoint:  " + NIM_URL)

    texts = [c["text"] for c in chunks]
    print("\nEmbebiendo...")
    t0 = time.time()
    vectors = embed(texts, api_key, args.model, "passage")
    elapsed = time.time() - t0

    arr = np.array(vectors, dtype=np.float32)
    out_dir = root / "embeddings"
    out_dir.mkdir(exist_ok=True)
    np.save(out_dir / "passages.npy", arr)

    ids = [{"chunk_id": c["chunk_id"], "providencia": c.get("providencia"),
            "section": c.get("section"), "md_url": c.get("md_url"),
            "raw_url": c.get("raw_url")} for c in chunks]
    (out_dir / "passages_ids.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ids) + "\n",
        encoding="utf-8")

    meta = {"model": args.model, "input_type": "passage",
            "dim": int(arr.shape[1]), "n_passages": int(arr.shape[0]),
            "elapsed_seconds": round(elapsed, 1),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n[OK] passages.npy: %s (%d bytes)" % (str(arr.shape), arr.nbytes))
    print("[OK] passages_ids: %d" % len(ids))
    print("[OK] meta.json:    %s" % meta)


if __name__ == "__main__":
    main()
