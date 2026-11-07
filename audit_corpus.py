"""Auditoría del corpus actual (sin red)."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd()
records = [json.loads(l) for l in (ROOT/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunks = [json.loads(l) for l in (ROOT/"chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

print("=" * 78)
print("AUDITORÍA DEL CORPUS")
print("=" * 78)

# 1. Documentos
docs = {}
for r in records:
    rk = r["row_key"]
    docs.setdefault(rk, {"exts": set(), "meta": r})
    docs[rk]["exts"].add(r.get("ext"))

print(f"\n[1] Documentos únicos: {len(docs)}")
print(f"    Registros totales: {len(records)}")
print(f"    Formatos: {Counter(r.get('ext') for r in records)}")

# 2. Tipos y salas
tipos = Counter()
salas = Counter()
for d in docs.values():
    prov = d["meta"].get("providencia") or ""
    if prov.startswith("A"):
        tipos["auto"] += 1
    elif prov.startswith("S"):
        tipos["sentencia"] += 1
    else:
        tipos["desconocido"] += 1
    if len(prov) > 1:
        salas[{"C":"civil","L":"laboral","P":"penal","E":"especial","T":"tutela"}.get(prov[1], "?")] += 1

print(f"\n[2] Tipos: {dict(tipos)}")
print(f"    Salas: {dict(salas)}")

# 3. Años
years = Counter()
for d in docs.values():
    fecha = d["meta"].get("fecha") or ""
    m = re.search(r"/(\d{4})$", fecha)
    years[m.group(1) if m else "?"] += 1
print(f"\n[3] Años: {dict(sorted(years.items()))}")

# 4. Integridad MD
print(f"\n[4] Integridad de MD:")
md_ok = md_missing = md_small = 0
for d in docs.values():
    rec = d["meta"]
    md = rec.get("md_path")
    if not md:
        md_missing += 1
        continue
    p = ROOT / md
    if not p.is_file():
        md_missing += 1
        continue
    if p.stat().st_size < 1000:
        md_small += 1
    else:
        md_ok += 1
print(f"    OK:      {md_ok}")
print(f"    Falta:   {md_missing}")
print(f"    <1KB:    {md_small}")

# 5. Chunks por doc
chunks_by_doc = defaultdict(int)
chars_by_doc = defaultdict(int)
for c in chunks:
    chunks_by_doc[c.get("providencia")] += 1
    chars_by_doc[c.get("providencia")] += len(c.get("text", ""))

print(f"\n[5] Chunks por documento:")
for prov in sorted(chunks_by_doc):
    print(f"    {prov:20}  {chunks_by_doc[prov]:>4} chunks  {chars_by_doc[prov]:>8,} chars")

# 6. Secciones
sections = Counter(c.get("section") for c in chunks)
print(f"\n[6] Secciones: {dict(sections.most_common(10))}")

# 7. Calidad de chunks
empty = sum(1 for c in chunks if len(c.get("text","")) < 50)
short = sum(1 for c in chunks if 50 <= len(c.get("text","")) < 200)
normal = sum(1 for c in chunks if len(c.get("text","")) >= 200)
print(f"\n[7] Calidad chunks:")
print(f"    Vacíos (<50):   {empty}")
print(f"    Cortos (<200):  {short}")
print(f"    Normales:       {normal}")

# 8. Duplicados SHA
shas = defaultdict(list)
for r in records:
    shas[r.get("sha256")].append(r.get("providencia"))
dups = {k: v for k, v in shas.items() if len(v) > 1}
print(f"\n[8] Duplicados SHA-256: {len(dups)}")
if dups:
    for sha, provs in dups.items():
        print(f"    {sha[:12]}… → {provs}")

# 9. Espacio
raw_files = list((ROOT/"raw").rglob("*.*"))
raw_size = sum(f.stat().st_size for f in raw_files if f.is_file())
md_files = list((ROOT/"md").rglob("*.md"))
md_size = sum(f.stat().st_size for f in md_files)
emb = ROOT/"embeddings"/"passages.npy"
emb_size = emb.stat().st_size if emb.is_file() else 0
print(f"\n[9] Espacio:")
print(f"    RAW:  {len(raw_files):>3} archivos / {raw_size:>12,} B")
print(f"    MD:   {len(md_files):>3} archivos / {md_size:>12,} B")
print(f"    EMB:  {emb_size:>12,} B")

print("\n" + "=" * 78)
