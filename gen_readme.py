import json
from pathlib import Path

ROOT = Path.cwd()
records = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunks = [json.loads(l) for l in (ROOT/"chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
docs = len({r["row_key"] for r in records})
raw_bytes = sum((ROOT/r["raw_path"]).stat().st_size for r in records if (ROOT/r["raw_path"]).is_file())
md_files = sum(1 for r in records if r.get("md_path") and (ROOT/r["md_path"]).is_file())

md = (
    "# Corpus Corte Suprema de Justicia — Colombia\n\n"
    "ETL de jurisprudencia CSJ para ingestión en LLM/RAG.\n\n"
    "## Estado actual\n\n"
    f"- Documentos únicos:  {docs}\n"
    f"- Registros totales:  {len(records)}\n"
    f"- Chunks RAG:         {len(chunks)}\n"
    "- Embeddings:         NVIDIA `nemotron-3-embed-1b` (2048 dims)\n"
    f"- Tamaño RAW:         {raw_bytes:,} bytes\n"
    f"- Tamaño MD:          {md_files} archivos\n\n"
    "## Estructura\n\n"
    "```\n"
    "raw/YYYY/*.docx|pdf    Documentos originales (byte-exact, SHA-256)\n"
    "md/YYYY/*.md           Markdown con frontmatter YAML\n"
    "chunks/YYYY/*.jsonl    Chunks RAG por documento\n"
    "chunks.jsonl           Todos los chunks\n"
    "manifest.jsonl         Provenance por RAW\n"
    "embeddings/            passages.npy + passages_ids.jsonl + meta.json\n"
    "```\n\n"
    "## Uso\n\n"
    "```bash\n"
    "source ~/.csj_keys\n\n"
    "# Descargar más documentos\n"
    "python3 m062_crawler_byid.py --type sentencia --year 2024 --max-docs 30\n\n"
    "# Reconstruir índice\n"
    "python3 m062_rebuild.py\n\n"
    "# Consultar (devuelve top-K chunks)\n"
    'python3 rag_query.py "responsabilidad civil contractual"\n\n'
    "# RAG con respuesta LLM (siguiente fase)\n"
    'python3 rag_ask.py "responsabilidad civil contractual"\n'
    "```\n\n"
    "## Clasificación por prefijo\n\n"
    "`A`=auto, `S`=sentencia. `C`=civil, `L`=laboral, `P`=penal, `T`=tutela.\n\n"
    "Ejemplo: `SC2954-2024` = Sentencia Civil 2024.\n"
)
(ROOT/"README.md").write_text(md, encoding="utf-8")
print(f"README.md actualizado: {docs} docs, {len(chunks)} chunks")
