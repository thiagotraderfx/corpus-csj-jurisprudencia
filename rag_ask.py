"""RAG completo sobre el corpus CSJ: retrieval + generación con NIM.

Uso:
    python3 rag_ask.py "¿Cuál es el precedente sobre responsabilidad civil contractual?"
    python3 rag_ask.py "..." --top-k 8
    python3 rag_ask.py "..." --model meta/llama-3.1-8b-instruct
    python3 rag_ask.py "..." --no-llm   # solo retrieve (debug)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import requests
from postprocess import normalize_answer

EMB = Path(__file__).parent / "embeddings"
NIM_EMBED_URL = "https://integrate.api.nvidia.com/v1/embeddings"
NIM_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def load_index():
    meta = json.loads((EMB / "meta.json").read_text(encoding="utf-8"))
    arr = np.load(EMB / "passages.npy")
    ids = [json.loads(l) for l in (EMB / "passages_ids.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = {}
    chunks_file = Path(__file__).parent / "chunks.jsonl"
    if chunks_file.is_file():
        for line in chunks_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                chunks[c["chunk_id"]] = c
    return meta, arr, ids, chunks


def embed_query(q):
    from embedding_client import EmbeddingClient
    client = EmbeddingClient(EMB / "meta.json")
    return client.embed(q)[0]


CHAT_FALLBACKS = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",   # el que funciona hoy
    "nvidia/nemotron-3-super-120b-a12b",               # fallback por si habilitan
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "mistralai/mistral-large-2-instruct",
    "nv-mistralai/mistral-nemo-12b-instruct",
]

NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


def get_available_models(api_key):
    """Consulta /v1/models y devuelve los modelos de CHAT_FALLBACKS que existen.

    Si la consulta falla, devuelve la lista completa (fallback offline).
    """
    try:
        r = requests.get(
            NIM_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if r.status_code != 200:
            return CHAT_FALLBACKS
        available = {m.get("id") for m in r.json().get("data", [])}
        filtered = [m for m in CHAT_FALLBACKS if m in available]
        return filtered if filtered else CHAT_FALLBACKS
    except Exception:
        return CHAT_FALLBACKS


def _try_chat(model, system, user, api_key):
    """Intenta un modelo. Devuelve (texto, error_msg)."""
    r = requests.post(
        NIM_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
        },
        timeout=60,
    )
    if r.status_code in (404, 410):
        return None, f"{r.status_code} (no disponible)"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:120]}"
    return r.json()["choices"][0]["message"]["content"], None


def generate_answer(question, context_chunks, api_key, model):
    context = "\n\n".join(
        f"[{i+1}] {c['providencia']} — {c['section']} ({c['fecha']}, {c['sala']})\n{c['text']}"
        for i, c in enumerate(context_chunks)
    )
    system = (
        "Eres un asistente jurídico experto en jurisprudencia de la Corte Suprema "
        "de Justicia de Colombia. Responde la pregunta del usuario basándote "
        "EXCLUSIVAMENTE en el contexto provisto. Cita las fuentes con [N] cuando "
        "uses información de cada fragmento. Si el contexto no contiene la "
        "respuesta, di que no tienes evidencia suficiente en el corpus. "
        "Responde en español, con lenguaje jurídico preciso. "
        "Usa exclusivamente corchetes ASCII [N] para citar (nunca caracteres CJK 【】)."
    )
    user = f"Contexto:\n{context}\n\nPregunta: {question}\n\nRespuesta:"

    if model == "auto":
        candidates = get_available_models(api_key)
        if len(candidates) < len(CHAT_FALLBACKS):
            skipped = [m for m in CHAT_FALLBACKS if m not in candidates]
            if skipped:
                print(f"  (omitiendo modelos no disponibles: {len(skipped)})")
    else:
        candidates = [model]
    if not candidates:
        raise RuntimeError("Ningún modelo chat disponible en /v1/models")

    last_error = None
    for candidate in candidates:
        print(f"  Probando modelo: {candidate}…")
        try:
            text, err = _try_chat(candidate, system, user, api_key)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"    excepción: {last_error}")
            continue
        if text:
            print(f"    ✓ {candidate} respondió")
            return normalize_answer(text)
        print(f"    ✗ {err}")
        last_error = err

    raise RuntimeError(
        f"Ningún modelo chat funcionó. Último error: {last_error}\n"
        "Verifica modelos disponibles con:\n"
        "  curl -s -H \"Authorization: Bearer $NVIDIA_API_KEY\" \\\n"
        "    https://integrate.api.nvidia.com/v1/models | \\\n"
        "    python3 -c \"import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]\""
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--model", default="auto",
                    help="modelo chat. 'auto' prueba CHAT_FALLBACKS en orden")
    ap.add_argument("--no-llm", action="store_true",
                    help="solo retrieval, sin generación")
    args = ap.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        sys.exit("Falta NVIDIA_API_KEY (source ~/.csj_keys)")

    meta, arr, ids, chunks = load_index()
    print(f"Corpus:  {meta['n_passages']} chunks, {meta['dim']} dims, provider={meta['provider']}")
    print(f"Query:   {args.question!r}\n")

    q_vec = embed_query(args.question)
    scores = arr @ q_vec
    top_idx = np.argsort(scores)[-args.top_k:][::-1]

    retrieved = []
    for rank, i in enumerate(top_idx, 1):
        item = ids[i]
        score = float(scores[i])
        full = chunks.get(item["chunk_id"], {})
        retrieved.append({
            **item,
            "score": score,
            "text": full.get("text", ""),
            "fecha": full.get("fecha"),
            "sala": full.get("sala"),
            "radicado": full.get("radicado"),
        })
        print(f"  [{rank}] {score:.4f}  {item['providencia']}  [{item['section']}]")

    if args.no_llm:
        print("\n[--no-llm] Solo retrieval")
        return

    print(f"\nGenerando respuesta (modelo: {args.model})…\n")
    try:
        answer = generate_answer(args.question, retrieved, api_key, args.model)
    except Exception as exc:
        sys.exit(f"[FAIL] {type(exc).__name__}: {exc}")

    print("=" * 78)
    print("RESPUESTA")
    print("=" * 78)
    print(answer)
    print()
    print("=" * 78)
    print("FUENTES")
    print("=" * 78)
    for i, r in enumerate(retrieved, 1):
        print(f"[{i}] {r['providencia']} — {r['section']}")
        print(f"    Radicado: {r['radicado']}")
        print(f"    Fecha:    {r['fecha']}  Sala: {r['sala']}")
        print(f"    MD:       {r['md_url']}")
        print(f"    Score:    {r['score']:.4f}")


if __name__ == "__main__":
    main()
