"""Corpus CSJ — API REST v1.1.0

Endpoints:
    GET  /                       info del servicio
    GET  /health                 health check
    GET  /stats                  métricas del corpus
    POST /search                 retrieval puro
    POST /ask                    RAG completo
    POST /ask/stream             RAG streaming (SSE)
    GET  /providencias           listado paginado
    GET  /docs/{id}              documento MD completo
    GET  /chunks/{chunk_id}      chunk individual
    GET  /openapi.json           schema OpenAPI

Autenticación opcional: header X-API-Key (si API_KEY está en env).
"""
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api_index import get_index
from api_models import (
    AskRequest, AskResponse, ChunkResponse, DocumentResponse,
    HealthResponse, ListResponse, ProvidenciaSummary,
    SearchRequest, SearchResponse, SearchResult, StatsResponse,
)
from api_rag import RAGError, generate, retrieve

APP_VERSION = __import__("json").load(open("stats.json")).get("version", "1.1.5")
START_TS = time.time()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("csj.api")


# ─── Rate limiter simple en memoria ───
class RateLimiter:
    def __init__(self, max_req: int = 60, window: int = 60):
        self.max = max_req
        self.window = window
        self._hits = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._hits[key] = [t for t in self._hits[key] if now - t < self.window]
            if len(self._hits[key]) >= self.max:
                return False
            self._hits[key].append(now)
            return True


rate_limiter = RateLimiter(
    max_req=int(os.environ.get("RATE_LIMIT_MAX", "120")),
    window=int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
)


# ─── Auth opcional ───
REQUIRED_KEY = os.environ.get("API_KEY", "").strip()


def auth(x_api_key: Optional[str] = Header(None)):
    if not REQUIRED_KEY:
        return True
    if x_api_key != REQUIRED_KEY:
        raise HTTPException(status_code=401, detail="API key inválida")
    return True


def rate_check(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit excedido")


# ─── App ───
app = FastAPI(
    title="Corpus CSJ — Corte Suprema de Justicia de Colombia",
    description="API REST para consulta de jurisprudencia CSJ con RAG",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RAGError)
async def rag_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# ─── Endpoints ───
@app.get("/", tags=["info"])
def root():
    return {
        "service": "Corpus CSJ API",
        "version": APP_VERSION,
        "docs_endpoint": "/docs",
        "openapi": "/openapi.json",
        "uptime_seconds": int(time.time() - START_TS),
    }


@app.get("/health", response_model=HealthResponse, tags=["info"])
def health():
    idx = get_index()
    missing = []
    checks = {}

    def chk(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            missing.append(name)

    chk("index_loaded", idx._loaded)
    chk("passages_present", idx.passages is not None)
    chk("ids_consistent", idx.passages is not None and len(idx.ids) == idx.passages.shape[0])
    chk("chunks_available", len(idx.chunks_by_id) > 0)
    chk("docs_available", len(idx.docs_list) > 0)

    meta = idx.meta or {}
    chk("dim_matches", idx.passages is not None and idx.passages.shape[1] == meta.get("dim", -1))
    chk("nvidia_key", bool(os.environ.get("NVIDIA_API_KEY")))

    shas = [r.get("sha256") for r in idx.docs_list]
    chk("no_duplicates", len(shas) == len(set(shas)))

    return HealthResponse(
        status="ok" if not missing else "degraded",
        version=APP_VERSION,
        checks=checks,
        missing=missing,
    )


@app.get("/stats", response_model=StatsResponse, tags=["info"])
def stats():
    idx = get_index()
    return idx.stats()


@app.post("/search", response_model=SearchResponse, tags=["retrieval"],
          dependencies=[Depends(auth), Depends(rate_check)])
def search(req: SearchRequest):
    idx = get_index()
    results, latency_ms = retrieve(
        idx, req.query, k=req.k, sala=req.sala, tipo=req.tipo, year=req.year
    )
    return SearchResponse(
        query=req.query,
        k=req.k,
        total_candidates=idx.n_chunks,
        latency_ms=latency_ms,
        results=[SearchResult(**r) for r in results],
    )


@app.post("/ask", response_model=AskResponse, tags=["rag"],
          dependencies=[Depends(auth), Depends(rate_check)])
def ask(req: AskRequest):
    idx = get_index()
    t0 = time.time()
    try:
        results, _ = retrieve(idx, req.query, k=req.k)
        answer, model_used, provider, tokens_used = generate(
            req.query, results, req.model, req.temperature, req.max_tokens
        )
    except RAGError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return AskResponse(
        query=req.query,
        answer=answer,
        sources=[SearchResult(**r) for r in results],
        model_used=model_used,
        provider=provider,
        latency_ms=int((time.time() - t0) * 1000),
        tokens_used=tokens_used,
    )


@app.post("/ask/stream", tags=["rag"],
          dependencies=[Depends(auth), Depends(rate_check)])
def ask_stream(req: AskRequest):
    """Streaming SSE: emite chunks de la respuesta token por token."""
    idx = get_index()

    async def gen():
        try:
            results, _ = retrieve(idx, req.query, k=req.k)
            yield f"data: {json.dumps({'type': 'sources', 'results': results})}\n\n"
            answer, model_used, provider, _ = generate(
                req.query, results, req.model, req.temperature, req.max_tokens
            )
            # Stream caracteres en bloques de 40
            for i in range(0, len(answer), 40):
                yield f"data: {json.dumps({'type': 'token', 'text': answer[i:i+40]})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'model': model_used, 'provider': provider})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/providencias", response_model=ListResponse, tags=["docs"])
def list_providencias(
    sala: Optional[str] = None,
    tipo: Optional[str] = None,
    year: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
):
    idx = get_index()
    docs = idx.docs_list

    def match(r):
        prov = r.get("providencia") or ""
        if sala:
            cod_sala = {"civil": "C", "laboral": "L", "penal": "P", "especial": "E", "tutela": "T"}.get(sala.lower())
            if not cod_sala or len(prov) < 2 or prov[1] != cod_sala:
                return False
        if tipo:
            if tipo.lower() == "auto" and not prov.startswith("A"):
                return False
            if tipo.lower() == "sentencia" and not prov.startswith("S"):
                return False
        if year:
            if not (r.get("fecha") or "").endswith(f"/{year}"):
                return False
        if q:
            hay = f"{prov} {r.get('radicado') or ''} {r.get('tema') or ''} {r.get('ponente') or ''}".lower()
            if q.lower() not in hay:
                return False
        return True

    filtered = [r for r in docs if match(r)]
    total = len(filtered)
    start = (page - 1) * limit
    page_items = filtered[start:start + limit]

    results = [
        ProvidenciaSummary(
            providencia=r.get("providencia") or "",
            radicado=r.get("radicado"),
            fecha=r.get("fecha"),
            sala=r.get("sala"),
            ponente=r.get("ponente"),
            tipo=r.get("tipo"),
            md_path=r.get("md_path") or "",
        )
        for r in page_items
    ]
    return ListResponse(total=total, page=page, limit=limit, results=results)


@app.get("/docs/{doc_id}", response_model=DocumentResponse, tags=["docs"])
def get_doc(doc_id: str, include_content: bool = False):
    idx = get_index()
    rec = idx.find_doc(doc_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Documento no encontrado: {doc_id}")

    md_path = rec.get("md_path")
    content = None
    if include_content and md_path:
        p = idx.root / md_path
        if p.is_file():
            content = p.read_text(encoding="utf-8")

    return DocumentResponse(
        providencia=rec.get("providencia") or "",
        id=rec.get("id"),
        radicado=rec.get("radicado"),
        fecha=rec.get("fecha"),
        sala=rec.get("sala"),
        ponente=rec.get("ponente"),
        tipo=rec.get("tipo"),
        clase=rec.get("clase"),
        tema=rec.get("tema"),
        fuente_formal=rec.get("fuente_formal"),
        md_path=md_path or "",
        raw_path=rec.get("raw_path"),
        raw_sha256=rec.get("sha256"),
        source_url=rec.get("url_original"),
        md_content=content,
    )


@app.get("/chunks/{chunk_id}", response_model=ChunkResponse, tags=["docs"])
def get_chunk(chunk_id: str):
    idx = get_index()
    c = idx.chunks_by_id.get(chunk_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Chunk no encontrado: {chunk_id}")
    return ChunkResponse(**{k: c.get(k) for k in (
        "chunk_id", "providencia", "section", "text",
        "char_start", "char_end", "md_url", "raw_url",
    ) if k in c})


# ─── Entry point ───


# ═══════════════════════════════════════════════════════════════
# /coverage — reporte determinista de cobertura por sala y año
# ═══════════════════════════════════════════════════════════════
def _norm_sala_coverage(s: str) -> str:
    s = (s or "").upper()
    if "PENAL" in s and "TUTELA" not in s: return "Penal"
    if "TUTELA" in s or "DECISIÓN DE TUTELAS" in s: return "Tutela"
    if "CIVIL" in s: return "Civil"
    if "LABORAL" in s: return "Laboral"
    return "Otra"


@app.get("/coverage", tags=["info"],
         summary="Cobertura del acervo por sala y año (determinista)")
def coverage(
    sala: Optional[str] = None,
    year: Optional[int] = None,
    threshold: int = 5,
):
    """
    Reporte de cobertura del acervo, calculado directamente sobre manifest.

    - Sin filtros: matriz completa sala × año + gaps críticos (< threshold).
    - `sala` / `year`: filtra la respuesta a esa celda.
    - `threshold`: umbral bajo el cual una celda se reporta como gap (default 5).

    No usa LLM. Los números son verificables contra manifest.jsonl.
    """
    import json as _json
    matrix = {}
    total_por_sala = {}
    total_por_year = {}
    total = 0

    with open("manifest.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            d = _json.loads(line)
            s = _norm_sala_coverage(d.get("sala"))
            y_raw = d.get("year") or ((d.get("fecha") or "")[-4:])
            try:
                y = int(y_raw) if y_raw else None
            except ValueError:
                y = None
            total += 1
            total_por_sala[s] = total_por_sala.get(s, 0) + 1
            if y:
                total_por_year[y] = total_por_year.get(y, 0) + 1
                matrix.setdefault(s, {}).setdefault(str(y), 0)
                matrix[s][str(y)] += 1

    all_years = sorted({str(y) for row in matrix.values() for y in row},
                       reverse=True)

    # Filtros
    if sala:
        sala_norm = _norm_sala_coverage(sala)
        matrix = {sala_norm: matrix.get(sala_norm, {})}
        all_years_filtered = all_years
    else:
        all_years_filtered = all_years

    if year:
        y_str = str(year)
        matrix = {s: {y_str: row.get(y_str, 0)} for s, row in matrix.items()}
        all_years_filtered = [y_str]

    # Gaps críticos (< threshold)
    gaps = []
    for s, row in matrix.items():
        for y, n in row.items():
            if n < threshold:
                gaps.append({"sala": s, "year": y, "docs": n})

    # Recomendaciones (plantilla determinista, sin LLM)
    recos = []
    for g in sorted(gaps, key=lambda x: (x["docs"], x["sala"]))[:10]:
        if g["docs"] == 0:
            recos.append(
                f"Ingerir providencias de la sala {g['sala']} del año {g['year']} "
                f"(sin cobertura actual)."
            )
        else:
            recos.append(
                f"Ampliar cobertura de la sala {g['sala']} del año {g['year']} "
                f"({g['docs']} docs actuales, umbral {threshold})."
            )

    return {
        "total": total,
        "por_sala": total_por_sala,
        "por_year": {str(y): n for y, n in sorted(total_por_year.items(), reverse=True)},
        "matrix": matrix,
        "years": all_years_filtered,
        "threshold": threshold,
        "gaps_criticos": gaps,
        "recomendaciones_ingesta": recos,
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Corpus CSJ API v{APP_VERSION}")
    print(f"  http://{host}:{port}/")
    print(f"  Docs: http://{host}:{port}/docs")
    uvicorn.run("api:app", host=host, port=port, reload=False)


# ═══════════════════════════════════════════════════════════════
# ENDPOINT /ask/safe — blindado anti-alucinación (Fase A.3-bis)
# No modifica /ask. Endpoint independiente. Cero regresión.
# ═══════════════════════════════════════════════════════════════
@app.post("/ask/safe", response_model=AskResponse, tags=["rag"],
          summary="RAG blindado anti-alucinación (refusal + verificación de citas)")
def ask_safe(req: AskRequest):
    """
    /ask con blindaje:
    - Refusal si retrieval débil (max score < 0.30)
    - Verificación de citas [N] y de providencias
    - Campos extra: verified/refused/confidence/citations/unverified/reason
    """
    from rag_safe import should_refuse, safe_answer
    from api_rag import _unpack_retrieve, _get_chat_defaults, _normalize_generate_out

    t0 = time.time()
    idx = get_index()
    raw_results = retrieve(idx, req.query, req.k)

    sources_list = _unpack_retrieve(raw_results)
    raw_sources = raw_results[0] if isinstance(raw_results, tuple) else raw_results
    scores = [s.get("score", 0.0) for s in sources_list]

    if not sources_list:
        elapsed = int((time.time() - t0) * 1000)
        return AskResponse(
            query=req.query,
            answer=("La evidencia recuperada para esta consulta es insuficiente para "
                "una respuesta con respaldo verificable. Para obtener resultados "
                "precisos, considere:\n"
                "  - Incluir el identificador de la providencia o el radicado.\n"
                "  - Acotar el aspecto jurídico específico de la consulta.\n"
                "  - Indicar el año o período de interés.\n\n"
                "También puede consultar directamente el portal oficial de la "
                "Corte Suprema de Justicia de Colombia."),
            sources=raw_sources, model_used="n/a", provider="n/a",
            latency_ms=elapsed, tokens_used=0,
            verified=None, refused=True, confidence=0.0,
            citations=[], unverified=[], reason="no_retrieval_results",
        )

    if should_refuse(scores, 0.30):
        elapsed = int((time.time() - t0) * 1000)
        return AskResponse(
            query=req.query,
            answer=("La evidencia recuperada para esta consulta es insuficiente para "
                "una respuesta con respaldo verificable. Para obtener resultados "
                "precisos, considere:\n"
                "  - Incluir el identificador de la providencia o el radicado.\n"
                "  - Acotar el aspecto jurídico específico de la consulta.\n"
                "  - Indicar el año o período de interés.\n\n"
                "También puede consultar directamente el portal oficial de la "
                "Corte Suprema de Justicia de Colombia."),
            sources=raw_sources, model_used="n/a", provider="n/a",
            latency_ms=elapsed, tokens_used=0,
            verified=None, refused=True, confidence=float(max(scores)),
            citations=[], unverified=[],
            reason="retrieval_weak: max=%.3f < 0.30" % max(scores),
        )

    dm, _dt, _dmax = _get_chat_defaults()
    mdl = req.model if req.model is not None else dm
    meta = {"model": "n/a", "provider": "n/a", "tokens": 0}

    def _llm_call(q, _ctx):
        out = generate(q, raw_sources, mdl, req.temperature, req.max_tokens)
        if isinstance(out, tuple) and len(out) >= 4:
            meta["model"] = out[1]
            meta["provider"] = out[2]
            meta["tokens"] = out[3] or 0
            return str(out[0])
        return _normalize_generate_out(out)

    result = safe_answer(
        question=req.query,
        context_chunks=sources_list,
        scores=scores,
        llm_call=_llm_call,
        refusal_threshold=0.30,
    )

    elapsed = int((time.time() - t0) * 1000)
    _ans = result.get("answer", "")
    _refused = result.get("refused")
    _cov_gap = False
    # Si el LLM decidió no-responder (M2 template), refused=True (contrato honesto)
    if _refused is False and isinstance(_ans, str) and _ans.strip().startswith(
            "No se encontró jurisprudencia aplicable"):
        _refused = True
        _cov_gap = True
    # Fix: verified debe ser None si coverage_gap=True (no hay contenido que verificar)
    _verified = result.get("verified")
    if _cov_gap:
        _verified = None
    return AskResponse(
        query=req.query,
        answer=_ans,
        sources=raw_sources,
        model_used=meta["model"], provider=meta["provider"],
        latency_ms=elapsed, tokens_used=meta["tokens"],
        verified=_verified,
        refused=_refused,
        confidence=result.get("confidence"),
        citations=result.get("citations"),
        unverified=result.get("unverified"),
        reason=result.get("reason"),
        coverage_gap=_cov_gap,
    )

# Fase E: middleware (defensivo)
try:
    from middleware import apply_middleware
    _mw = apply_middleware(app)
except Exception as _e:
    import sys as _s
    print(f"[api] middleware skipped: {_e}", file=_s.stderr)
    _mw = {"limiter": None}
