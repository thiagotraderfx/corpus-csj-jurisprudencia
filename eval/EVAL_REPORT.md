# Evaluación de Faithfulness — Corpus CSJ

**Generado**: 2026-11-08T12:47:33
**Métrica**: v2-token-overlap

**Preguntas**: 60 (50 in-domain + 10 out-of-domain)

## Métricas

| Métrica | Valor |
| --- | --- |
| **Faithfulness** | 46.0% |
| Answer accuracy | 46.0% |
| Refusal accuracy | 100.0% |
| False refusal rate | 8.0% |

## Por categoría

| Categoría | N | Correctas | Tasa |
| --- | --- | --- | --- |
| content_excerpt | 25 | 2 | 8% |
| metadata_fecha | 6 | 5 | 83% |
| metadata_ponente | 7 | 7 | 100% |
| metadata_radicado | 6 | 6 | 100% |
| metadata_sala | 6 | 3 | 50% |
| out_of_domain | 10 | 10 | 100% |

## Metodología

- **v2 token-overlap**: tokens alfanuméricos lowercase
- **metadata_***: substring exacto OR ≥40% tokens
- **content_excerpt**: substring exacto OR ≥25% tokens
- **out_of_domain**: correcto si refused
- **Faithfulness**: correcto Y no rechazado

## Limitaciones

- Preguntas auto-generadas (seed=42), no human-validated
- Métricas v1 dieron 2% (artefacto de substring estricto)
