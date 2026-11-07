"""Reconstruye chunks + embeddings desde el manifest actual."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
records = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
md_recs = [r for r in records if r.get("md_path") and (ROOT/r["md_path"]).is_file() and r.get("ext")=="docx"]

print(f"Documentos con MD: {len(md_recs)}")

MAX_CHARS, OVERLAP = 1200, 100
all_chunks = []
(ROOT/"chunks").mkdir(exist_ok=True)

for rec in md_recs:
    md = (ROOT / rec["md_path"]).read_text(encoding="utf-8")
    sections = re.split(r"(?m)^##\s+(.+)$", md)
    blocks = [("INTRO", sections[0])]
    for i in range(1, len(sections), 2):
        title = sections[i].replace("**","").strip() or "INTRO"
        blocks.append((title, sections[i+1] if i+1<len(sections) else ""))

    doc_chunks = []
    for sec, text in blocks:
        plain = re.sub(r"^#+\s*","",text,flags=re.M)
        plain = re.sub(r"\*\*\*?|\*","",plain)
        plain = re.sub(r"\\\*","*",plain)
        plain = re.sub(r"\n{3,}","\n\n",plain).strip()
        if len(plain) < 30: continue
        start = 0
        while start < len(plain):
            end = min(start+MAX_CHARS, len(plain))
            if end < len(plain):
                for sep in ["\n\n",". ","\n"]:
                    idx = plain.rfind(sep, start+400, end)
                    if idx > start:
                        end = idx+len(sep); break
            ct = plain[start:end].strip()
            if len(ct) >= 50:
                doc_chunks.append({
                    "chunk_id": f"{rec.get('providencia')}__{len(doc_chunks):03d}",
                    "doc_id": rec.get("id"), "providencia": rec.get("providencia"),
                    "radicado": rec.get("radicado"), "sala": rec.get("sala"),
                    "fecha": rec.get("fecha"), "ponente": rec.get("ponente"),
                    "tipo": rec.get("tipo"), "section": sec,
                    "text": ct, "char_start": start, "char_end": end,
                    "md_url": rec.get("md_path"), "raw_url": rec.get("raw_path"),
                    "source_url": rec.get("url_original"),
                })
            if end >= len(plain): break
            start = end - OVERLAP

    if doc_chunks:
        year = (rec.get("fecha") or "").split("/")[-1] or "unknown"
        out_dir = ROOT/"chunks"/year
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir/f"{rec.get('providencia')}.jsonl").write_text(
            "\n".join(json.dumps(c,ensure_ascii=False) for c in doc_chunks)+"\n", encoding="utf-8")
        all_chunks.extend(doc_chunks)

(ROOT/"chunks.jsonl").write_text(
    "\n".join(json.dumps(c,ensure_ascii=False) for c in all_chunks)+"\n", encoding="utf-8")
print(f"Chunks generados: {len(all_chunks)} de {len(md_recs)} docs")

# Re-embed
print("\nRe-embediendo con NVIDIA…")
subprocess.run([sys.executable, "embed_unified.py"], check=True)
