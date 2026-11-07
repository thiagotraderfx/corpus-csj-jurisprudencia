# Corpus CSJ — Corte Suprema de Justicia de Colombia

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24043648.svg)](https://doi.org/10.5281/zenodo.24043648)


[![Tests](https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/actions/workflows/test.yml/badge.svg)](https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/thiagotraderfx/corpus-csj-jurisprudencia)](https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/releases)
[![License](https://img.shields.io/badge/license-MIT%20%2B%20CC%20BY%204.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)


ETL reproducible de jurisprudencia de la Corte Suprema de Justicia de
Colombia, con API REST y RAG listo para consulta.

> **Aviso legal.** Este repositorio redistribuye providencias públicas descargadas del portal `consultajurisprudencial.ramajudicial.gov.co`. No reclama derechos sobre los documentos originales (ver [LICENSE](LICENSE)). Si usted es titular de derechos y desea el retiro de algún contenido, abra un issue y se atenderá a la brevedad.

## Estado (v1.1.4 — CERTIFIED 13/13)

| Componente | Valor |
| --- | --- |
| Documentos RAW | 201 archivos |
| Markdown | 201 |
| Chunks | 10,991 |
| Embeddings | NVIDIA `nemotron-3-embed-1b` (2048d) |
| **Sanity hit@5** | **99.50%** (n=201) |
| Sanity precision@5 | 57.71% |
| Sanity MRR | 0.978 |
| **Topic hit@5** | **72.34%** (n=141) |
| Topic precision@5 | 35.60% |
| Topic MRR | 0.616 |
| API REST | 13 endpoints |
| Tests | 14/14 local · 4+10 skip en CI |
| Certificación | 13/13 → `v1.1.0-certified.json` |

Distribución por año: 2022 (50), 2023 (25), 2024 (97), 2025 (27), 2026 (3).

## Inicio rápido

```bash
git clone https://github.com/thiagotraderfx/corpus-csj-jurisprudencia.git
cd corpus-csj-jurisprudencia

# Assets (raw + embeddings) — descargar del release
gh release download v1.1.0 --pattern 'corpus_csj_*_v1.1.0.tar.gz'
sha256sum -c SHA256SUMS
tar xzf corpus_csj_raw_v1.1.0.tar.gz
tar xzf corpus_csj_embeddings_v1.1.0.tar.gz

# Configurar key
cat > ~/.csj_keys <<'KEYS'
export NVIDIA_API_KEY="nvapi-TU_KEY"
KEYS
chmod 600 ~/.csj_keys
source ~/.csj_keys

pip install -r requirements.txt

python3 health_check.py
python3 certify_v1_1.py

python3 rag_query.py "responsabilidad civil contractual"
python3 rag_ask.py "¿Cuál es el precedente sobre responsabilidad civil contractual?"
./run_api.sh    # http://localhost:8000/docs
```

## API (13 endpoints)

Swagger en `/docs`. Ejemplos:

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query":"responsabilidad civil","k":5,"year":2024}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"¿Cuál es el precedente sobre responsabilidad civil contractual?"}'
```

## Limitaciones documentadas

- **Cobertura parcial**: 202 docs del universo estimado de ~32 899.
- **Topic retrieval limitado**: el portal CSJ publica el mismo `tema` para docenas de docs distintos. Sanity (retrieval por contenido) es 99.5%. Ver `DATA_QUALITY.md`.
- **Metadata parcial**: 110 docs sin `fuente_formal`, 8 sin `sala` (derivada en M004), 1 sin `tema` (AC6987-2026).
- **Sin evaluación de respuestas LLM**: medimos retrieval, no alucinación.

## Estructura

```
.
├── api*.py                     FastAPI (endpoints, índice, RAG)
├── m062_crawler_byid.py        Crawler resumible
├── m063_rebuild_chunks_only.py Re-chunk sin re-embed
├── re_embed_nvidia.py          Re-embed NVIDIA con checkpoint
├── rag_query.py, rag_ask.py    CLI retrieval / RAG
├── embed_local_tfidf.py        Fallback offline (TF-IDF, sin API key)
├── embed_unified.py            NVIDIA → OpenRouter → TF-IDF
├── embed_with_nim.py           Wrapper NVIDIA NIM
├── legacy/                     m060, m061, docx_extract (histórico)
├── scripts/                    sanitize_har, 01_reconocer_relatoria
├── reports/                    Provenance del scoping del crawl
├── embedding_client.py         Cliente unificado
├── benchmark_v2.py             Sanity + topic retrieval
├── certify_v1_1.py             Certificación 13 checks
├── tests/                      pytest (14 tests)
├── md/YYYY/*.md                201 markdowns
├── chunks/YYYY/*.jsonl         Chunks por año
├── chunks.jsonl                10 991 chunks
├── manifest.jsonl              Provenance SHA-256
├── DATA_QUALITY.md             Gaps y limitaciones documentados
└── v1.1.0-certified.json       Certificado machine-readable
```

**Release assets** (no en git): `corpus_csj_raw_v1.1.0.tar.gz`,
`corpus_csj_embeddings_v1.1.0.tar.gz`, `corpus_csj_v1.1.0_FULL.tar.gz`,
`SHA256SUMS`.

## Reproducibilidad

```bash
python3 m062_crawler_byid.py --type sentencia --year 2024 --max-docs 100
python3 m063_rebuild_chunks_only.py
python3 re_embed_nvidia.py
python3 certify_v1_1.py
```

## Licencia

Ver [LICENSE](LICENSE). Código MIT, datos derivados CC BY 4.0, RAW sin
licencia declarada (atribución a la CSJ).

## Descargo

Herramienta de investigación. No sustituye la consulta de las providencias
en el portal oficial de la CSJ.
