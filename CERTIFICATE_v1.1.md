# Certificado v1.1.0 — API REST

Ver v1.1.0-certified.json para checks machine-readable.

## Métricas

- Documentos: 100+
- Chunks: 6000+
- Duplicados SHA-256: 0
- Sanity hit@5: 99.0%
- Topic hit@5: 79.5%
- Health checks: 9/9
- Tests pytest: PASS

## API Endpoints

    GET  /                     info
    GET  /health               health check
    GET  /stats                métricas
    POST /search               retrieval (filtros: sala, tipo, year)
    POST /ask                  RAG completo (LLM + citas)
    POST /ask/stream           RAG streaming SSE
    GET  /providencias         listado paginado
    GET  /docs/{id}            documento MD
    GET  /chunks/{chunk_id}    chunk individual
    GET  /docs                 Swagger UI
    GET  /openapi.json         schema OpenAPI

## Lanzar

    cd corpus_corte_suprema
    source ~/.csj_keys
    ./run_api.sh

## Deuda técnica cerrada

- Rebuild incremental (4s vs 205 min = 2463x)
- Retry con backoff en EmbeddingClient
- RAGError wrap en retrieve/generate
- tokens_used extraído del LLM
- API key opcional, rate limiting, CORS
- Tests pytest (14+)

## Deuda diferida a v2.0

- Cobertura multi-año
- Evaluación de respuestas LLM
- Crawler concurrente
- Dedup de chunks boilerplate
