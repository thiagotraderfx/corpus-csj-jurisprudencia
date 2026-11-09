"""Lógica RAG: retrieval + generación con fallback de modelos."""
import os
import re
import time
from typing import Optional

import numpy as np
import requests

from embedding_client import EmbeddingClient
from postprocess import normalize_answer
from api_index import Index

NIM_CHAT = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODELS = "https://integrate.api.nvidia.com/v1/models"

CHAT_FALLBACKS = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "mistralai/mistral-large-2-instruct",
    "nv-mistralai/mistral-nemo-12b-instruct",
]


class RAGError(Exception):
    pass


def _get_api_key():
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RAGError("Falta NVIDIA_API_KEY")
    return key


def _available_models(api_key: str) -> list:
    try:
        r = requests.get(NIM_MODELS, headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if r.status_code != 200:
            return CHAT_FALLBACKS
        avail = {m.get("id") for m in r.json().get("data", [])}
        filtered = [m for m in CHAT_FALLBACKS if m in avail]
        return filtered if filtered else CHAT_FALLBACKS
    except Exception:
        return CHAT_FALLBACKS


def retrieve(index: Index, query: str, k: int = 5,
             sala: Optional[str] = None,
             tipo: Optional[str] = None,
             year: Optional[int] = None) -> tuple:
    """Retorna (results, latency_ms). Aplica filtros opcionales."""
    t0 = time.time()
    try:
        client = EmbeddingClient(index.root / "embeddings" / "meta.json")
        qv = client.embed(query)[0]
    except Exception as exc:
        raise RAGError(f"Error embebiendo query: {type(exc).__name__}: {exc}")
    scores = index.passages @ qv

    # Filtrar por metadata antes de top-k
    mask = np.ones(len(index.ids), dtype=bool)
    if sala or tipo or year:
        for i, item in enumerate(index.ids):
            c = index.chunks_by_id.get(item["chunk_id"])
            if not c:
                mask[i] = False
                continue
            if sala and (c.get("sala") or "").lower().find(sala.lower()) < 0:
                mask[i] = False
            if tipo and (c.get("tipo") or "").lower() != tipo.lower():
                mask[i] = False
            if year and not (c.get("fecha") or "").endswith(f"/{year}"):
                mask[i] = False

    masked_scores = np.where(mask, scores, -np.inf)
    top_idx = np.argsort(masked_scores)[-k:][::-1]
    top_idx = [i for i in top_idx if masked_scores[i] > -np.inf]

    results = []
    for i in top_idx:
        item = index.ids[i]
        c = index.chunks_by_id.get(item["chunk_id"], {})
        results.append({
            "chunk_id": item["chunk_id"],
            "providencia": item.get("providencia") or "",
            "section": item.get("section") or "",
            "score": float(scores[i]),
            "md_url": item.get("md_url") or "",
            "raw_url": item.get("raw_url"),
            "text": c.get("text", ""),
            "radicado": c.get("radicado"),
            "fecha": c.get("fecha"),
            "sala": c.get("sala"),
            "ponente": c.get("ponente"),
            "tipo": c.get("tipo"),
        })

    latency_ms = int((time.time() - t0) * 1000)
    return results, latency_ms


def generate(query: str, sources: list, model: Optional[str],
             temperature: float, max_tokens: int) -> tuple:
    """Retorna (answer, model_used, provider)."""
    api_key = _get_api_key()

    context = "\n\n".join(
        f"[{i+1}] {s['providencia']} — {s['section']} ({s.get('fecha') or '?'}, {s.get('sala') or '?'})\n{s['text']}"
        for i, s in enumerate(sources)
    )

    system = (
        "Eres un asistente especializado EXCLUSIVAMENTE en jurisprudencia de la "
        "Corte Suprema de Justicia de Colombia (salas Civil, Penal, Laboral y "
        "Tutelas).\n\n"
        "Reglas estrictas:\n"
        "1. Si la consulta NO corresponde al ámbito jurídico colombiano "
        "(recetas, deportes, ciencia general, entretenimiento, cultura, etc.), "
        "responde EXACTAMENTE con: 'Este servicio atiende exclusivamente "
        "consultas sobre jurisprudencia de la Corte Suprema de Justicia de "
        "Colombia. La consulta planteada no corresponde a ese ámbito y no puede "
        "ser atendida. Para otras materias, consulte las fuentes especializadas "
        "correspondientes.'\n"
        "2. Si la consulta SÍ es jurídica pero el contexto no contiene "
        "información aplicable, responde: 'No se encontró jurisprudencia "
        "aplicable en el acervo actual para esta consulta. Se recomienda "
        "precisar la consulta indicando providencia, radicado, año o aspecto "
        "jurídico específico, o consultar directamente el portal oficial de la "
        "Corte Suprema de Justicia de Colombia.'\n"
        "3. NUNCA uses las palabras 'corpus', 'base de datos', 'memoria', "
        "'índice', 'acervo interno', 'sistema', 'modelo', 'algoritmo', ni "
        "jerga técnica interna. El usuario solo debe conocer el servicio y "
        "su ámbito de aplicación.\n"
        "4. Basa tu respuesta EXCLUSIVAMENTE en el contexto provisto.\n"
        "5. Cita con [N] donde N corresponde al fragmento del contexto. Usa "
        "exclusivamente corchetes ASCII [N] (nunca caracteres CJK).\n"
        "6. NUNCA inventes providencias, radicados, fechas ni nombres de "
        "ponentes.\n"
        "7. Responde en español, con lenguaje jurídico preciso y profesional."
    )
    user = f"Contexto:\n{context}\n\nPregunta: {query}\n\nRespuesta:"

    candidates = [model] if model else _available_models(api_key)
    if not candidates:
        raise RAGError("No hay modelos chat disponibles")

    if not sources:
        raise RAGError("No hay fuentes para generar respuesta")

    last_error = None
    for cand in candidates:
        try:
            r = requests.post(
                NIM_CHAT,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": cand,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=90,
            )
            if r.status_code in (404, 410):
                last_error = f"{cand}: HTTP {r.status_code}"
                continue
            r.raise_for_status()

            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                last_error = f"{cand}: respuesta sin choices"
                continue
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            finish = choices[0].get("finish_reason", "?")

            if not text or not str(text).strip():
                last_error = f"{cand}: content vacío (finish_reason={finish})"
                continue

            normalized = normalize_answer(text)
            if not normalized or not normalized.strip():
                last_error = f"{cand}: postproceso dejó vacío"
                continue

            tokens = (data.get("usage") or {}).get("total_tokens")
            return normalized, cand, "nvidia", tokens
        except Exception as exc:
            last_error = f"{cand}: {type(exc).__name__}: {exc}"
            continue

    raise RAGError(f"Ningún modelo chat respondió. Último: {last_error}")






# ═══════════════════════════════════════════════════════════════
# WRAPPER ANTI-ALUCINACIÓN (Fase A.2) — v2
# No modifica generate() ni retrieve(). Solo envuelve su salida.
# retrieve() → (list[dict], meta) — parseamos ambos.
# generate(query, sources, model=None) — api_key se lee del env.
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# WRAPPER ANTI-ALUCINACIÓN (Fase A.2) — v3
# Adapta args de generate() con inspect.signature, normaliza
# retorno tuple/dict/str. No modifica generate() ni retrieve().
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# WRAPPER ANTI-ALUCINACIÓN — v4
# Usa AskRequest defaults exactamente como api.py.
# ═══════════════════════════════════════════════════════════════

def _unpack_retrieve(raw):
    """retrieve() → (list[dict], meta). Devuelve list[dict] normalizada."""
    if isinstance(raw, tuple) and len(raw) == 2:
        chunks = raw[0]
    elif isinstance(raw, list):
        chunks = raw
    else:
        chunks = []
    if not isinstance(chunks, list):
        chunks = list(chunks)
    out = []
    for c in chunks:
        d = dict(c) if isinstance(c, dict) else {"text": str(c), "score": 0.0}
        for f in ("chunk_id", "providencia", "section", "fecha", "sala", "text"):
            d.setdefault(f, "")
        d.setdefault("score", 0.0)
        try:
            d["score"] = float(d["score"])
        except (TypeError, ValueError):
            d["score"] = 0.0
        out.append(d)
    return out


def _normalize_generate_out(out):
    if isinstance(out, tuple):
        out = out[0] if out else ""
    if isinstance(out, dict):
        out = out.get("answer", out.get("text", str(out)))
    return str(out) if out is not None else ""


def _get_chat_defaults():
    """Lee defaults del modelo AskRequest (Pydantic), igual que api.py."""
    try:
        from api_models import AskRequest
        r = AskRequest(query="x")
        return r.model, r.temperature, r.max_tokens
    except Exception:
        return "auto", 0.2, 1024


def generate_safe(query, index, k=5, model=None, refusal_threshold=0.30):
    """Versión blindada de generate() con defaults de AskRequest."""
    from rag_safe import safe_answer, should_refuse

    raw = retrieve(index, query, k=k)
    sources = _unpack_retrieve(raw)

    if not sources:
        return {
            "answer": ("La evidencia recuperada para esta consulta es insuficiente para "
                       "una respuesta con respaldo verificable. Para obtener resultados "
                       "precisos, considere:\n"
                       "  - Incluir el identificador de la providencia o el radicado.\n"
                       "  - Acotar el aspecto jurídico específico de la consulta.\n"
                       "  - Indicar el año o período de interés.\n\n"
                       "También puede consultar directamente el portal oficial de la "
                       "Corte Suprema de Justicia de Colombia."),
            "sources": [], "refused": True, "verified": None,
            "confidence": 0.0, "citations": [], "unverified": [],
            "reason": "no_retrieval_results",
        }

    scores = [s["score"] for s in sources]

    if should_refuse(scores, refusal_threshold):
        return {
            "answer": ("La evidencia recuperada para esta consulta es insuficiente para "
                       "una respuesta con respaldo verificable. Para obtener resultados "
                       "precisos, considere:\n"
                       "  - Incluir el identificador de la providencia o el radicado.\n"
                       "  - Acotar el aspecto jurídico específico de la consulta.\n"
                       "  - Indicar el año o período de interés.\n\n"
                       "También puede consultar directamente el portal oficial de la "
                       "Corte Suprema de Justicia de Colombia."),
            "sources": sources, "refused": True, "verified": None,
            "confidence": max(scores), "citations": [], "unverified": [],
            "reason": "retrieval_weak: max=%.3f < %.2f" % (max(scores), refusal_threshold),
        }

    default_model, default_temp, default_max = _get_chat_defaults()

    def _llm_call(q, _ctx):
        mdl = model if model is not None else default_model
        out = generate(q, sources, mdl, default_temp, default_max)
        return _normalize_generate_out(out)

    result = safe_answer(
        question=query,
        context_chunks=sources,
        scores=scores,
        llm_call=_llm_call,
        refusal_threshold=refusal_threshold,
    )
    result["sources"] = sources
    return result


# ═══════════════════════════════════════════════════════════════
# retrieve_boosted — si la query menciona una providencia, prioriza
# los chunks INTRO de esa providencia (donde vive la metadata).
# ═══════════════════════════════════════════════════════════════
def retrieve_boosted(index, query, k=5):
    """Retrieve con boost cuando la query menciona una providencia específica."""
    import re
    raw = retrieve(index, query, k=k)
    chunks = _unpack_retrieve(raw)

    # Detectar si la query menciona una providencia
    prov_match = re.search(r'\b([A-Z]{2,4}\d{1,6}-\d{4})\b', query)
    if not prov_match:
        return raw

    target = prov_match.group(1)

    # Buscar chunks de esa providencia directamente en el índice
    try:
        all_chunks = index.chunks if hasattr(index, "chunks") else []
    except Exception:
        all_chunks = []

    if not all_chunks:
        return raw

    target_chunks = [
        c for c in all_chunks
        if c.get("providencia") == target
    ]

    if not target_chunks:
        return raw

    # Priorizar INTRO (metadata) y luego el resto de esa providencia
    intro = [c for c in target_chunks if c.get("section") == "INTRO"]
    otros = [c for c in target_chunks if c.get("section") != "INTRO"]

    boosted = intro + otros[:3]  # hasta 3 chunks de la providencia
    for c in boosted:
        c.setdefault("score", 0.6)  # score alto artificial

    # Deduplicar contra top-5 inicial por chunk_id
    seen = {c.get("chunk_id") for c in boosted}
    extra = [c for c in chunks if c.get("chunk_id") not in seen]

    final = boosted + extra[:max(0, k - len(boosted))]
    return (final, None)  # formato compatible con retrieve
