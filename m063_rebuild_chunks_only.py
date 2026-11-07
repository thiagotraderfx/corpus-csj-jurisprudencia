"""Regenera chunks.jsonl desde todos los .md del manifest (sin embed)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
records = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

# Dedup por row_key, quedarse con el docx
by_rk = {}
for r in records:
    rk = r["row_key"]
    if rk not in by_rk or r.get("ext") == "docx":
        by_rk[rk] = r

md_recs = [r for r in by_rk.values()
           if r.get("md_path") and (ROOT/r["md_path"]).is_file() and r.get("ext") == "docx"]

print(f"  Documentos con MD: {len(md_recs)}")

MAX_CHARS, OVERLAP = 1200, 100
all_chunks = []
(ROOT/"chunks").mkdir(exist_ok=True)

for i, rec in enumerate(md_recs, 1):
    md = (ROOT / rec["md_path"]).read_text(encoding="utf-8")
    sections = re.split(r"(?m)^##\s+(.+)$", md)
    blocks = [("INTRO", sections[0])]
    for j in range(1, len(sections), 2):
        title = sections[j].replace("**","").strip() or "INTRO"
        blocks.append((title, sections[j+1] if j+1 < len(sections) else ""))

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
    if i % 50 == 0:
        print(f"    [{i}/{len(md_recs)}] {len(all_chunks)} chunks acumulados")

(ROOT/"chunks.jsonl").write_text(
    "\n".join(json.dumps(c,ensure_ascii=False) for c in all_chunks)+"\n", encoding="utf-8")
print(f"  ✓ chunks.jsonl: {len(all_chunks)} chunks de {len(md_recs)} docs")
