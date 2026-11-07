# Contribuir

## Setup

    git clone https://github.com/thiagotraderfx/corpus-csj-jurisprudencia.git
    cd corpus-csj-jurisprudencia
    gh release download v1.1.0
    sha256sum -c SHA256SUMS
    tar xzf corpus_csj_raw_v1.1.0.tar.gz
    tar xzf corpus_csj_embeddings_v1.1.0.tar.gz
    pip install -r requirements.txt pytest

## Tests

    pytest -q                    # 6 passed con assets
    # CI: 4 passed, 2 skipped (sin passages.npy)

## Reglas

- No commitear raw/, *.npy, *.tar.gz, .csj_keys, .env
- No editar chunks.jsonl / manifest.jsonl a mano
- Correr certify_v1_1.py si tocas datos
- Commits: tipo: descripción (feat:, fix:, docs:, ci:, refactor:)

## Reportar

- Bugs: issue con pytest -q output + versión Python
- Takedown RAW: issue con doc_id y motivo (ver LICENSE)
