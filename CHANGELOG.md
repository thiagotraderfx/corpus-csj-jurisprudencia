# Changelog

## v1.0 — 2026-11-06

### Añadido
- 100 documentos CSJ únicos (98 sentencias + 2 autos)
- 6 127 chunks con provenance
- Embeddings NVIDIA nemotron-3-embed-1b (2048d)
- embedding_client.py — cliente unificado NVIDIA/OpenRouter
- benchmark_v2.py — dos metodologías (sanity + topic)
- health_check.py — 9 checks end-to-end
- postprocess.py — normalización CJK a ASCII
- tests/ — suite pytest
- m062_rebuild_incremental.py — deuda #1 cerrada

### Corregido
- resp.status_code -> resp.status en crawler
- URLs hardcodeadas -> despacho dinámico vía embedding_client
- LLM retirado (410 Gone) -> fallback dinámico

### Métricas
- Sanity: 99.0% hit@5, MRR 0.976
- Topic: 79.2% hit@5, MRR 0.626
- Health: 9/9
- Duplicados SHA-256: 0
