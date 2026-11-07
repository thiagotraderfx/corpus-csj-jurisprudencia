# Recuperación — Corpus CSJ v1.0

## Restaurar desde snapshot

    tar xzf corpus_csj_v1.0_CERTIFIED_*.tar.gz -C /ruta/destino/
    cd /ruta/destino/
    python3 finalize_v1.py
    python3 benchmark_v2.py
    python3 health_check.py

## Regenerar embeddings

    source ~/.csj_keys
    python3 m062_rebuild.py

## Verificar integridad

    python3 audit_corpus.py
    python3 benchmark_v2.py
    python3 health_check.py
    python3 -m pytest tests/ -q

## Contenido del snapshot

- raw/            Documentos byte-exact (SHA-256 en manifest)
- md/             Markdown con frontmatter
- chunks/         Chunks por documento
- embeddings/     passages.npy + ids + meta.json
- manifest.jsonl  Provenance por RAW
- tests/          Suite pytest
