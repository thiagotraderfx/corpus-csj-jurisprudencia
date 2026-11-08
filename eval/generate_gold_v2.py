"""Gold-set v2: content_factual verificable + metadata mejorable."""
import json, random, re
from pathlib import Path

random.seed(42)

chunks = [json.loads(l) for l in Path("chunks.jsonl").read_text().strip().split("\n") if l.strip()]

by_prov = {}
for c in chunks:
    prov = c.get("providencia")
    if prov:
        by_prov.setdefault(prov, []).append(c)

providencias = sorted(by_prov.keys())
sample_provs = random.sample(providencias, min(25, len(providencias)))

questions = []
qid = 0

# Metadata (25) — misma lógica que v1
for prov in sample_provs:
    c = by_prov[prov][0]
    qid += 1
    t = qid % 4
    if t == 0:
        questions.append({"id": f"q{qid:03d}", "query": f"¿Cuál es el número de radicado de la providencia {prov}?",
            "expected_answer": str(c.get("radicado", "")).strip(), "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"), "category": "metadata_radicado", "level": "easy"})
    elif t == 1:
        questions.append({"id": f"q{qid:03d}", "query": f"¿Quién fue el ponente de la providencia {prov}?",
            "expected_answer": str(c.get("ponente", "")).strip(), "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"), "category": "metadata_ponente", "level": "easy"})
    elif t == 2:
        questions.append({"id": f"q{qid:03d}", "query": f"¿Cuál es la fecha de la providencia {prov}?",
            "expected_answer": str(c.get("fecha", "")).strip(), "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"), "category": "metadata_fecha", "level": "easy"})
    else:
        questions.append({"id": f"q{qid:03d}", "query": f"¿A qué sala pertenece la providencia {prov}?",
            "expected_answer": str(c.get("sala", "")).strip(), "expected_providencia": prov,
            "expected_chunk_id": c.get("chunk_id"), "category": "metadata_sala", "level": "easy"})

# Content_factual (25) — verificable semánticamente
content_chunks = [c for c in chunks
                  if c.get("section", "").upper() in ("RESUELVE", "DECISIÓN", "DECISION")
                  and len(c.get("text", "")) > 200]
random.shuffle(content_chunks)
selected_content = content_chunks[:25]

for c in selected_content:
    qid += 1
    prov = c.get("providencia", "")
    text = c.get("text", "").lower()

    # Derivar verificadores factuales (keywords que deben aparecer si responde)
    verificadores = []
    if "resuelve" in text or "resolución" in text: verificadores.append("resuelve")
    if "casa" in text: verificadores.append("casa")
    if "niega" in text or "no casar" in text: verificadores.append("niega")
    if "confirma" in text: verificadores.append("confirma")
    if "revoca" in text: verificadores.append("revoca")
    if "modifica" in text: verificadores.append("modifica")
    if "condena" in text: verificadores.append("condena")
    if "absuelve" in text: verificadores.append("absuelve")
    if "declara" in text: verificadores.append("declara")

    if not verificadores:
        # Fallback: usar 2-3 palabras clave largas del texto
        words = [w for w in text.split() if len(w) > 6][:3]
        verificadores = words if words else ["providencia"]

    questions.append({
        "id": f"q{qid:03d}",
        "query": f"¿Qué decide la Corte en la providencia {prov}?",
        "expected_answer": None,  # Verificable por keywords, no substring
        "expected_keywords": verificadores[:5],
        "expected_providencia": prov,
        "expected_chunk_id": c.get("chunk_id"),
        "category": "content_factual",
        "level": "medium",
    })

# Out-of-domain (10)
ood = [
    ("¿Cuál es la receta de la torta de chocolate?", "cocina"),
    ("¿Cómo se calcula el interés compuesto en criptomonedas?", "cripto"),
    ("¿Quién ganó el mundial de fútbol 2022?", "deportes"),
    ("¿Cuál es la capital de Mongolia?", "geografía"),
    ("¿Cómo se instala Python en Ubuntu?", "informática"),
    ("¿Qué es la teoría de cuerdas?", "física"),
    ("¿Cuántos huesos tiene el cuerpo humano?", "medicina"),
    ("¿Cómo se hace pan de masa madre?", "panadería"),
    ("¿Cuál es la diferencia entre TCP y UDP?", "redes"),
    ("¿Qué fue la Revolución Industrial?", "historia"),
]
for q, topic in ood:
    qid += 1
    questions.append({"id": f"q{qid:03d}", "query": q, "expected_answer": None,
        "expected_providencia": None, "expected_chunk_id": None,
        "category": "out_of_domain", "level": "easy", "ood_topic": topic})

out = Path("eval/gold_questions_v2.jsonl")
with out.open("w") as f:
    for q in questions:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")

print(f"  ✓ {len(questions)} preguntas v2")
print(f"    metadata: 25")
print(f"    content_factual: 25 (verificadores por keyword)")
print(f"    out_of_domain: 10")
