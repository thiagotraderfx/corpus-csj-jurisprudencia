"""Genera gold-set determinista desde corpus.

50 preguntas in-domain (metadata + contenido) + 10 out-of-domain.
Cada respuesta esperada es verificable objetivamente contra chunks.jsonl.
"""
import json
import random
from pathlib import Path

random.seed(42)  # Determinista

# Cargar chunks
chunks = [json.loads(l) for l in Path("chunks.jsonl").read_text().strip().split("\n") if l.strip()]

# Agrupar por providencia
by_prov = {}
for c in chunks:
    prov = c.get("providencia")
    if prov:
        by_prov.setdefault(prov, []).append(c)

providencias = sorted(by_prov.keys())
print(f"  Providencias: {len(providencias)}")

# Seleccionar 25 providencias al azar (del total 309)
sample_provs = random.sample(providencias, min(25, len(providencias)))

questions = []
qid = 0

# ─── Bloque 1: Metadata questions (25) ───
for prov in sample_provs:
    c = by_prov[prov][0]  # primer chunk tiene la metadata
    qid += 1

    # Rotar entre 4 tipos de metadata
    t = qid % 4

    if t == 0:
        questions.append({
            "id": f"q{qid:03d}",
            "query": f"¿Cuál es el número de radicado de la providencia {prov}?",
            "expected_answer": str(c.get("radicado", "")).strip(),
            "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"),
            "category": "metadata_radicado",
            "level": "easy",
        })
    elif t == 1:
        questions.append({
            "id": f"q{qid:03d}",
            "query": f"¿Quién fue el ponente de la providencia {prov}?",
            "expected_answer": str(c.get("ponente", "")).strip(),
            "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"),
            "category": "metadata_ponente",
            "level": "easy",
        })
    elif t == 2:
        questions.append({
            "id": f"q{qid:03d}",
            "query": f"¿Cuál es la fecha de la providencia {prov}?",
            "expected_answer": str(c.get("fecha", "")).strip(),
            "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"),
            "category": "metadata_fecha",
            "level": "easy",
        })
    else:
        questions.append({
            "id": f"q{qid:03d}",
            "query": f"¿A qué sala pertenece la providencia {prov}?",
            "expected_answer": str(c.get("sala", "")).strip(),
            "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"),
            "category": "metadata_sala",
            "level": "easy",
        })

# ─── Bloque 2: Content questions (25) ───
# Seleccionar 25 chunks de RESUELVE o DECISIÓN con texto sustancial (>500 chars)
content_chunks = [c for c in chunks
                  if c.get("section", "").upper() in ("RESUELVE", "DECISIÓN", "DECISION", "CONSIDERACIONES")
                  and len(c.get("text", "")) > 500]

random.shuffle(content_chunks)
selected_content = content_chunks[:25]

for c in selected_content:
    qid += 1
    prov = c.get("providencia", "")
    section = c.get("section", "")
    text = c.get("text", "")

    # Extraer primer fragmento sustancial como "respuesta esperada"
    # Limpiar caracteres problemáticos
    excerpt = text.strip().replace("\n", " ")
    if len(excerpt) > 400:
        # Cortar en punto seguido de espacio
        cut = excerpt[:400].rfind(". ")
        if cut > 150:
            excerpt = excerpt[:cut+1]
        else:
            excerpt = excerpt[:350] + "..."

    questions.append({
        "id": f"q{qid:03d}",
        "query": f"¿Qué establece la providencia {prov} en su sección {section}?",
        "expected_answer": excerpt,
        "expected_providencia": prov,
        "expected_chunk_id": c.get("chunk_id"),
        "category": "content_excerpt",
        "level": "medium",
    })

# ─── Bloque 3: Out-of-domain (10) ───
ood = [
    ("¿Cuál es la receta de la torta de chocolate?", "receta de cocina"),
    ("¿Cómo se calcula el interés compuesto en criptomonedas?", "finanzas/cripto"),
    ("¿Quién ganó el mundial de fútbol 2022?", "deportes"),
    ("¿Cuál es la capital de Mongolia?", "geografía"),
    ("¿Cómo se instala Python en Ubuntu?", "informática"),
    ("¿Qué es la teoría de cuerdas?", "física teórica"),
    ("¿Cuántos huesos tiene el cuerpo humano?", "medicina/básica"),
    ("¿Cómo se hace pan de masa madre?", "panadería"),
    ("¿Cuál es la diferencia entre TCP y UDP?", "redes"),
    ("¿Qué fue la Revolución Industrial?", "historia"),
]

for query, topic in ood:
    qid += 1
    questions.append({
        "id": f"q{qid:03d}",
        "query": query,
        "expected_answer": None,  # Debe rechazar
        "expected_providencia": None,
        "expected_chunk_id": None,
        "category": "out_of_domain",
        "level": "easy",
        "ood_topic": topic,
    })

# Guardar
out = Path("eval/gold_questions.jsonl")
with out.open("w") as f:
    for q in questions:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")

in_dom = sum(1 for q in questions if q["category"] != "out_of_domain")
out_dom = len(questions) - in_dom
print(f"  ✓ {len(questions)} preguntas guardadas")
print(f"    In-domain:  {in_dom} ({len(sample_provs)} metadata + {len(selected_content)} content)")
print(f"    Out-of-domain: {out_dom}")
print(f"    Archivo: {out}")
