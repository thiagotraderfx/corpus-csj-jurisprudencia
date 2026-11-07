"""Embeddings con fallback automático: NVIDIA → OpenRouter → local TF-IDF.

Uso:
    python3 embed_unified.py                    # auto (NVIDIA → OpenRouter → local)
    python3 embed_unified.py --provider nvidia
    python3 embed_unified.py --provider openrouter
    python3 embed_unified.py --provider local

Escribe:
    embeddings/passages.npy         matriz float32 (N × dim)
    embeddings/passages_ids.jsonl   {chunk_id, providencia, section, ...} por fila
    embeddings/meta.json            {provider, model, dim, n_passages, ...}
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    import requests
except ImportError:
    sys.exit("Falta: pip install requests numpy")

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/embeddings"
NVIDIA_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
NVIDIA_MODEL = "nvidia/nemotron-3-embed-1b"

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_MODELS = [
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
    "baai/bge-m3",
    "thenlper/gte-large",
    "nomic-ai/nomic-embed-text-v1.5",
]


# ============================================================
# 1. NVIDIA
# ============================================================
def try_nvidia(chunks):
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        return None, "NVIDIA_API_KEY no definida"

    # 1a. Listar modelos
    try:
        r = requests.get(
            NVIDIA_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if r.status_code == 401:
            return None, "NVIDIA: API key inválida (401 en /models)"
        if r.status_code != 200:
            return None, f"NVIDIA: GET /models → HTTP {r.status_code}"
    except Exception as exc:
        return None, f"NVIDIA: error de red en /models ({exc})"

    # 1b. Probar 1 embedding
    try:
        r = requests.post(
            NVIDIA_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": ["ping"],
                "model": NVIDIA_MODEL,
                "input_type": "passage",
                "encoding_format": "float",
                "truncate": "END",
            },
            timeout=30,
        )
    except Exception as exc:
        return None, f"NVIDIA: error de red en /embeddings ({exc})"

    if r.status_code == 403:
        return None, "NVIDIA: 403 — falta scope 'Public API Endpoints'"
    if r.status_code == 404:
        return None, f"NVIDIA: 404 — modelo '{NVIDIA_MODEL}' no disponible"
    if r.status_code != 200:
        return None, f"NVIDIA: HTTP {r.status_code} en /embeddings ({r.text[:80]})"

    # 1c. Embeber todos
    print(f"  [NVIDIA] OK, embebiendo {len(chunks)} chunks…")
    texts = [c["text"] for c in chunks]
    vectors = []
    batch = 10
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        r = requests.post(
            NVIDIA_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": chunk,
                "model": NVIDIA_MODEL,
                "input_type": "passage",
                "encoding_format": "float",
                "truncate": "END",
            },
            timeout=120,
        )
        r.raise_for_status()
        for item in r.json()["data"]:
            vectors.append(item["embedding"])
        print(f"    {min(i + len(chunk), len(texts))}/{len(texts)}")
    return (
        np.array(vectors, dtype=np.float32),
        {"provider": "nvidia", "model": NVIDIA_MODEL},
    )


# ============================================================
# 2. OpenRouter
# ============================================================
def try_openrouter(chunks):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None, "OPENROUTER_API_KEY no definida"

    texts = [c["text"] for c in chunks]

    for model in OPENROUTER_MODELS:
        print(f"  [OpenRouter] probando modelo '{model}'…")
        try:
            r = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": ["ping"], "model": model},
                timeout=30,
            )
        except Exception as exc:
            print(f"    error de red: {exc}")
            continue

        if r.status_code == 404:
            print(f"    404 — modelo no disponible en OpenRouter")
            continue
        if r.status_code == 403:
            print(f"    403 — modelo no permitido en tu cuenta")
            continue
        if r.status_code != 200:
            print(f"    HTTP {r.status_code}: {r.text[:120]}")
            continue

        print(f"    OK, embebiendo {len(texts)} chunks…")
        vectors = []
        batch = 10
        ok = True
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            try:
                r = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"input": chunk, "model": model},
                    timeout=120,
                )
                r.raise_for_status()
                for item in r.json()["data"]:
                    vectors.append(item["embedding"])
                print(f"    {min(i + len(chunk), len(texts))}/{len(texts)}")
            except Exception as exc:
                print(f"    fallo en batch {i}: {exc}")
                ok = False
                break

        if ok and len(vectors) == len(texts):
            return (
                np.array(vectors, dtype=np.float32),
                {"provider": "openrouter", "model": model},
            )

    return None, "OpenRouter: ningún modelo de embeddings disponible"


# ============================================================
# 3. Local TF-IDF (siempre funciona, offline)
# ============================================================
def try_local_tfidf(chunks, max_features=2000):
    print(f"  [Local] TF-IDF con vocabulario de {max_features} términos…")
    texts = [c["text"].lower() for c in chunks]

    # Tokenizar simple: palabras de 2+ chars
    import re
    def tokenize(t):
        return re.findall(r"[a-záéíóúñü]{2,}", t)

    tokenized = [tokenize(t) for t in texts]

    # Vocabulario global
    global_counter = Counter()
    for toks in tokenized:
        global_counter.update(set(toks))
    vocab = {w: i for i, (w, _) in enumerate(global_counter.most_common(max_features))}

    # TF-IDF manual
    n_docs = len(texts)
    df = Counter()
    for toks in tokenized:
        for w in set(toks):
            if w in vocab:
                df[w] += 1

    import math
    idf = {w: math.log((1 + n_docs) / (1 + df[w])) + 1 for w in vocab}

    vectors = []
    for toks in tokenized:
        vec = np.zeros(len(vocab), dtype=np.float32)
        tf = Counter(w for w in toks if w in vocab)
        for w, count in tf.items():
            idx = vocab[w]
            vec[idx] = count * idf[w]
        # Normalizar L2
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vectors.append(vec)

    return (
        np.array(vectors, dtype=np.float32),
        {"provider": "local_tfidf", "model": "tfidf-2000", "vocab_size": len(vocab)},
    )


# ============================================================
# Main
# ============================================================
def write_outputs(root, vectors, info, chunks):
    out_dir = root / "embeddings"
    out_dir.mkdir(exist_ok=True)
    np.save(out_dir / "passages.npy", vectors)

    ids = [
        {
            "chunk_id": c["chunk_id"],
            "providencia": c.get("providencia"),
            "section": c.get("section"),
            "md_url": c.get("md_url"),
            "raw_url": c.get("raw_url"),
        }
        for c in chunks
    ]
    (out_dir / "passages_ids.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ids) + "\n",
        encoding="utf-8",
    )

    meta = {
        **info,
        "dim": int(vectors.shape[1]),
        "n_passages": int(vectors.shape[0]),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--provider",
        choices=["auto", "nvidia", "openrouter", "local"],
        default="auto",
    )
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    chunks_file = root / "chunks.jsonl"
    if not chunks_file.is_file():
        sys.exit(f"No existe {chunks_file}")

    chunks = [
        json.loads(l)
        for l in chunks_file.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if not chunks:
        sys.exit("chunks.jsonl vacío")

    print(f"Chunks a embeber: {len(chunks)}")
    print(f"Provider:         {args.provider}\n")

    providers = {
        "nvidia": [("nvidia", try_nvidia)],
        "openrouter": [("openrouter", try_openrouter)],
        "local": [("local", lambda c: try_local_tfidf(c))],
        "auto": [
            ("nvidia", try_nvidia),
            ("openrouter", try_openrouter),
            ("local", lambda c: try_local_tfidf(c)),
        ],
    }[args.provider]

    vectors = None
    info = None
    for name, fn in providers:
        print(f"→ Probando {name}…")
        try:
            vecs, info_or_err = fn(chunks)
        except Exception as exc:
            print(f"  excepción: {exc}")
            continue

        if vecs is not None:
            vectors = vecs
            info = info_or_err
            print(f"  ✓ {name} exitoso")
            break
        else:
            print(f"  ✗ {info_or_err}")

    if vectors is None:
        sys.exit(
            "\n[FAIL] Ningún provider funcionó.\n"
            "  NVIDIA: verificar scope 'Public API Endpoints'\n"
            "  OpenRouter: verificar OPENROUTER_API_KEY y modelos disponibles\n"
            "  Local: verificar numpy instalado"
        )

    meta = write_outputs(root, vectors, info, chunks)

    print()
    print("=" * 72)
    print("RESULTADO")
    print("=" * 72)
    print(f"  provider: {meta['provider']}")
    print(f"  model:    {meta['model']}")
    print(f"  dim:      {meta['dim']}")
    print(f"  chunks:   {meta['n_passages']}")
    print(f"  matriz:   {vectors.shape}  ({vectors.nbytes:,} bytes)")
    print()
    print(f"  embeddings/passages.npy")
    print(f"  embeddings/passages_ids.jsonl")
    print(f"  embeddings/meta.json")
    print()
    print("RECORDATORIO: para consultas RAG usa el mismo provider+model.")
    print(f"  → {meta['provider']} / {meta['model']}")


if __name__ == "__main__":
    main()
