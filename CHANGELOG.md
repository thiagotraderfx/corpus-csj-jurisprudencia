# Changelog

[Keep a Changelog](https://keepachangelog.com/es/1.0.0/) · [SemVer](https://semver.org/lang/es/).

## [Unreleased]
- Crawl incremental (0.6% → >5% cobertura)
- Clasificador `tema` propio (topic hit@5 53% → >80%)
- Eval alucinación LLM (~50 gold questions)
- Embeddings alternativos bge-m3, jina-v3

## [1.1.0] — 2026-11-07
- API REST 13 endpoints (FastAPI, Swagger /docs)
- RAG: rag_query.py, rag_ask.py
- Embeddings NVIDIA nemotron-3-embed-1b (2048d)
- Certificación 13/13 (v1.1.0-certified.json)
- DATA_QUALITY.md con limitaciones
- CI GitHub Actions (pytest)
- Aviso legal RAW visible en README
- Tests: 6/6 (4 en CI, 2 requieren assets)

## [1.0.0] — 2026-10-XX
- ETL inicial (crawler resumible, parser, build_md, chunks)
- ~200 docs base

[Unreleased]: https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/releases/tag/v1.1.0
[1.0.0]: https://github.com/thiagotraderfx/corpus-csj-jurisprudencia/releases/tag/v1.0.0

## [v1.1.6-cleanup] — 2026-11-10

### Limpieza técnica (fases L.0–L.5)
- Eliminados: 19 backups .bak/.BROKEN, 29 logs, 1 stale, 13 XML/HTML intermedios, 3 `__pycache__/`, faltan.txt, manifest.jsonl.bak
- Eliminados: 13 tarballs históricos del corpus (~1.4 GB)
- Creado respaldo completo en GH Releases: **corpus-v1.1.4-321docs** (321 docs, 312 MB)
- Proyecto reducido de 2.0 GB → 638 MB (−70 %)

### Corpus intacto
- `raw/`: 321 DOCX
- `md/`: 320 Markdown
- `manifest.jsonl`: 321 registros
- `chunks.jsonl`: 23.982 chunks

### Pendiente (no técnico)
- Q4: cotejo con Relatoría de los 10 casos especiales
- Q3: selección de 50 preguntas jurídicas
