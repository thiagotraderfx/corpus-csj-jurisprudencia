# Certificado v1.0.0

Ver v1.0.0-certified.json para checks machine-readable.

## Métricas

| Métrica | Valor |
| --- | --- |
| Documentos | 100 |
| Chunks | 6 127 |
| Duplicados SHA-256 | 0 |
| Sanity hit@5 | 99.0% |
| Topic hit@5 | 79.2% |
| Health checks | 9/9 |

## Reproducible

    python3 finalize_v1.py
    python3 benchmark_v2.py
    python3 health_check.py
    python3 -m pytest tests/ -q
    python3 certify.py

## Deuda cerrada

- Rebuild incremental (m062_rebuild_incremental.py)
- RECOVERY.md
- Test suite (tests/)
- Certificación automática (certify.py)

## Deuda diferida a v2.0

- API REST (FastAPI)
- Evaluación de respuestas LLM
- Crawler concurrente
- Cobertura multi-año
