"""Corre gold-set contra generate_safe y mide faithfulness."""
import json
import sys
import time
from pathlib import Path

# Cargar corpus primero
sys.path.insert(0, str(Path.cwd()))

from api_index import get_index
from api_rag import generate_safe

GOLD = Path("eval/gold_questions.jsonl")
REPORT_JSON = Path("eval/EVAL_REPORT.json")
REPORT_MD = Path("eval/EVAL_REPORT.md")


def is_answer_correct(predicted, expected):
    """Verifica si la respuesta esperada está contenida en la predicción."""
    if not predicted or not expected:
        return False
    p = predicted.lower().replace("\n", " ").strip()
    e = expected.lower().replace("\n", " ").strip()
    if not e:
        return False
    # Match exacto del expected como substring
    if e in p:
        return True
    # Match semántico básico: al menos 80% de palabras del expected en predicted
    e_words = set(w for w in e.split() if len(w) > 3)
    if not e_words:
        return e in p
    p_words = set(p.split())
    overlap = len(e_words & p_words) / len(e_words)
    return overlap >= 0.8


def eval_question(idx, q, index, verbose=True):
    """Evalúa una pregunta. Retorna dict con resultado."""
    qid = q["id"]
    query = q["query"]
    cat = q["category"]

    if verbose:
        print(f"  [{idx:2d}] {qid} ({cat}): {query[:60]}...")

    t0 = time.time()
    try:
        result = generate_safe(query, index, k=5)
    except Exception as e:
        return {
            "id": qid, "category": cat, "error": "%s: %s" % (type(e).__name__, e),
            "correct": False, "refused": None, "has_citations": False,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    elapsed = int((time.time() - t0) * 1000)
    answer = result.get("answer", "")
    refused = result.get("refused", False)
    verified = result.get("verified")
    citations = result.get("citations", []) or []
    confidence = result.get("confidence", 0.0)
    expected = q.get("expected_answer")

    if cat == "out_of_domain":
        # OOD debe ser rechazado
        correct = bool(refused)
        has_cit = False
    else:
        # In-domain debe ser respondido Y correcto
        if refused:
            correct = False
        else:
            correct = is_answer_correct(answer, expected)
        has_cit = bool(verified) and len(citations) > 0

    return {
        "id": qid,
        "category": cat,
        "query": query,
        "answer": answer[:300],
        "expected": (expected or "")[:200] if expected else None,
        "refused": bool(refused),
        "verified": verified,
        "has_citations": has_cit,
        "confidence": round(confidence, 4),
        "correct": bool(correct),
        "elapsed_ms": elapsed,
    }


def main():
    print("═══ Fase C — Evaluación de faithfulness ═══")
    print()

    gold = [json.loads(l) for l in GOLD.read_text().strip().split("\n") if l.strip()]
    print(f"  Gold questions: {len(gold)}")

    print("  Cargando índice...")
    index = get_index()
    print("  ✓ Índice cargado")
    print()

    results = []
    for i, q in enumerate(gold, 1):
        results.append(eval_question(i, q, index, verbose=True))

    # ─── Calcular métricas ───
    in_dom = [r for r in results if r["category"] != "out_of_domain"]
    ood = [r for r in results if r["category"] == "out_of_domain"]

    in_dom_ok = [r for r in in_dom if r["correct"] and not r.get("error")]
    in_dom_refused = [r for r in in_dom if r.get("refused")]
    in_dom_cited = [r for r in in_dom if r.get("has_citations")]
    ood_refused = [r for r in ood if r.get("refused")]

    answer_acc = len(in_dom_ok) / max(len(in_dom), 1)
    cit_acc = len(in_dom_cited) / max(len(in_dom), 1)
    refusal_acc = len(ood_refused) / max(len(ood), 1)
    false_refusal = len(in_dom_refused) / max(len(in_dom), 1)

    # Faithfulness = (answer_correct AND has_citation) / in_domain
    faithful = [r for r in in_dom if r["correct"] and r.get("has_citations")]
    faithfulness = len(faithful) / max(len(in_dom), 1)

    # Por categoría
    by_cat = {}
    for r in results:
        c = r["category"]
        by_cat.setdefault(c, {"n": 0, "correct": 0, "refused": 0})
        by_cat[c]["n"] += 1
        if r.get("correct"):
            by_cat[c]["correct"] += 1
        if r.get("refused"):
            by_cat[c]["refused"] += 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_questions": len(results),
        "n_in_domain": len(in_dom),
        "n_out_of_domain": len(ood),
        "metrics": {
            "answer_accuracy": round(answer_acc, 4),
            "citation_accuracy": round(cit_acc, 4),
            "faithfulness": round(faithfulness, 4),
            "refusal_accuracy": round(refusal_acc, 4),
            "false_refusal_rate": round(false_refusal, 4),
        },
        "by_category": by_cat,
        "results": results,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # ─── Reporte markdown ───
    md = []
    md.append("# Evaluación de Faithfulness — Corpus CSJ\n\n")
    md.append(f"**Generado**: {report['generated_at']}\n\n")
    md.append(f"**Preguntas**: {len(results)} ({len(in_dom)} in-domain + {len(ood)} out-of-domain)\n\n")
    md.append("## Métricas principales\n\n")
    md.append("| Métrica | Valor | Interpretación |\n")
    md.append("| --- | --- | --- |\n")
    md.append(f"| **Faithfulness** | {faithfulness*100:.1f}% | % de in-domain con respuesta correcta Y citas verificadas |\n")
    md.append(f"| Answer accuracy | {answer_acc*100:.1f}% | % con contenido esperado en la respuesta |\n")
    md.append(f"| Citation accuracy | {cit_acc*100:.1f}% | % con al menos una cita válida |\n")
    md.append(f"| Refusal accuracy | {refusal_acc*100:.1f}% | % de out-of-domain correctamente rechazadas |\n")
    md.append(f"| False refusal rate | {false_refusal*100:.1f}% | % de in-domain rechazadas por error |\n")
    md.append("\n## Por categoría\n\n")
    md.append("| Categoría | N | Correctas | Tasa |\n")
    md.append("| --- | --- | --- | --- |\n")
    for cat in sorted(by_cat.keys()):
        d = by_cat[cat]
        rate = d["correct"] / d["n"] if d["n"] else 0
        md.append(f"| {cat} | {d['n']} | {d['correct']} | {rate*100:.1f}% |\n")

    md.append("\n## Metodología\n\n")
    md.append("- **Gold-set generado determinista** (seed=42) desde `chunks.jsonl`\n")
    md.append("- **25 preguntas de metadata**: radicado, ponente, fecha, sala (verificables objetivamente)\n")
    md.append("- **25 preguntas de contenido**: extracto literal de RESUELVE/CONSIDERACIONES (>500 chars)\n")
    md.append("- **10 preguntas out-of-domain**: temas totalmente ajenos (recetas, deportes, etc.)\n")
    md.append("- **Correctitud**: expected_answer aparece como substring (o 80% overlap de palabras)\n")
    md.append("- **Faithfulness**: respuesta correcta Y al menos 1 cita verificada por `rag_safe.verify_citations`\n")
    md.append("\n## Limitaciones\n\n")
    md.append("- Preguntas auto-generadas, no validadas por humano. Baseline objetivo, no ideal.\n")
    md.append("- Content questions usan extracto literal: miden retrieval, no razonamiento.\n")
    md.append("- Faithfulness mide citas verificables, no coherencia interna del LLM.\n")

    REPORT_MD.write_text("".join(md))

    print()
    print("═══════════════════════════════════════════════════════")
    print("RESULTADOS")
    print("═══════════════════════════════════════════════════════")
    print(f"  Faithfulness:       {faithfulness*100:.1f}%")
    print(f"  Answer accuracy:    {answer_acc*100:.1f}%")
    print(f"  Citation accuracy:  {cit_acc*100:.1f}%")
    print(f"  Refusal accuracy:   {refusal_acc*100:.1f}%")
    print(f"  False refusal rate: {false_refusal*100:.1f}%")
    print()
    print(f"  Reporte JSON: {REPORT_JSON}")
    print(f"  Reporte MD:   {REPORT_MD}")
    print()

    # Guardar contadores globales para uso posterior
    Path("eval/_last_metrics.json").write_text(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
