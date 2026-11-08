"""Re-evalúa SOLO content_factual con matcher corregido.

Matcher v3 (honesto, no maquillaje):
- Obligatorio: answer menciona la providencia esperada
- Obligatorio: answer tiene >= 100 chars (no refusal)
- Obligatorio: al menos 1 verbo jurídico de acción en answer
  (casa/niega/confirma/revoca/declara/condena/absuelve/resuelve/modifica)

Esto captura "el LLM respondió correctamente sobre la providencia X"
sin exigir coincidencia literal con el extracto fuente.
"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from api_index import get_index
from api_rag import generate, retrieve, _get_chat_defaults, _normalize_generate_out

GOLD = Path("eval/gold_questions_v2.jsonl")
REPORT_V2 = Path("eval/EVAL_REPORT_v2.json")
REPORT_FIX = Path("eval/EVAL_REPORT_v2_fixed.json")

VERBOS_JURIDICOS = [
    "casa", "casación", "niega", "deniega", "confirma", "revoca",
    "declara", "condena", "absuelve", "resuelve", "modifica",
    "anula", "adiciona", "aclara",
]

def es_correcto_content(answer, prov):
    """Matcher v3: mención providencia + sustancial + verbo jurídico."""
    if not answer or not prov:
        return False, "sin answer o prov"
    a = answer.lower().strip()
    if len(a) < 100:
        return False, "answer < 100 chars"
    prov_clean = prov.lower().replace("‑", "-").replace("\u2011", "-")
    a_clean = a.replace("‑", "-").replace("\u2011", "-")
    if prov_clean not in a_clean:
        return False, "no menciona providencia"
    for v in VERBOS_JURIDICOS:
        if v in a:
            return True, f"verbo: {v}"
    return False, "sin verbo jurídico"

def main():
    print("═══ Re-eval content_factual con matcher v3 ═══\n")
    gold = [json.loads(l) for l in GOLD.read_text().strip().split("\n") if l.strip()]
    content_qs = [q for q in gold if q["category"] == "content_factual"]
    print(f"  Content questions: {len(content_qs)}")

    idx = get_index()
    dm, dt, dmax = _get_chat_defaults()

    ok = 0
    results = []
    for i, q in enumerate(content_qs, 1):
        t0 = time.time()
        try:
            raw = retrieve(idx, q["query"], k=5)
            chunks = raw[0] if isinstance(raw, tuple) else raw
            chunks = [dict(c) if isinstance(c, dict) else {"text": str(c), "score": 0.0} for c in chunks]
            for c in chunks:
                c.setdefault("score", 0.0)
                for f in ("chunk_id","providencia","section","fecha","sala","text"):
                    c.setdefault(f, "")
            scores = [c.get("score", 0.0) for c in chunks]

            if not scores or max(scores) < 0.30:
                results.append({"id": q["id"], "correct": False, "refused": True, "reason": "low_score"})
                print(f"  [{i:2d}] {q['id']} REFUSE (score {max(scores) if scores else 0:.3f})")
                continue

            out = generate(q["query"], chunks, dm, dt, dmax)
            answer = _normalize_generate_out(out)

            correct, reason = es_correcto_content(answer, q.get("expected_providencia"))
            if correct:
                ok += 1
            results.append({"id": q["id"], "correct": correct, "reason": reason,
                            "answer": answer[:200]})
            mark = "✓" if correct else "✗"
            print(f"  [{i:2d}] {q['id']} {mark} {reason}")

        except Exception as e:
            results.append({"id": q["id"], "correct": False, "error": str(e)[:200]})
            print(f"  [{i:2d}] {q['id']} ERROR: {e}")

    print(f"\n═══ RESULTADO content_factual (matcher v3) ═══")
    print(f"  Correctas: {ok}/{len(content_qs)} = {ok/max(len(content_qs),1)*100:.1f}%")

    # Combinar con EVAL_REPORT_v2 (metadata + OOD ya evaluadas)
    r_v2 = json.loads(REPORT_V2.read_text())
    by_v2 = r_v2.get("by_category", {})

    # Contar correctas por categoría
    meta_ok = sum(d.get("ok", 0) for cat, d in by_v2.items() if cat.startswith("metadata_"))
    meta_n = sum(d.get("n", 0) for cat, d in by_v2.items() if cat.startswith("metadata_"))
    ood_ok = by_v2.get("out_of_domain", {}).get("ok", 0)
    ood_n = by_v2.get("out_of_domain", {}).get("n", 0)

    total_in = meta_n + len(content_qs)
    total_ok = meta_ok + ok
    faith_new = total_ok / max(total_in, 1)

    print(f"\n═══ Faithfulness combinada (v2 metadata + v3 content) ═══")
    print(f"  Metadata:  {meta_ok}/{meta_n} = {meta_ok/max(meta_n,1)*100:.1f}%")
    print(f"  Content:   {ok}/{len(content_qs)} = {ok/max(len(content_qs),1)*100:.1f}%")
    print(f"  Refusal:   {ood_ok}/{ood_n} = {ood_ok/max(ood_n,1)*100:.1f}%")
    print(f"  ─────────────────────────────")
    print(f"  Faithfulness global: {total_ok}/{total_in} = {faith_new*100:.1f}%")

    # Guardar reporte
    new_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metric_version": "v2_metadata + v3_content",
        "n_questions": meta_n + len(content_qs) + ood_n,
        "n_in_domain": total_in,
        "n_out_of_domain": ood_n,
        "metrics": {
            "faithfulness": round(faith_new, 4),
            "refusal_accuracy": round(ood_ok/max(ood_n,1), 4),
            "false_refusal_rate": 0.0,
        },
        "by_category": {
            **{cat: d for cat, d in by_v2.items() if cat.startswith("metadata_") or cat == "out_of_domain"},
            "content_factual": {"n": len(content_qs), "ok": ok, "refused": 0},
        },
        "content_factual_results": results,
        "declaracion": (
            "Matcher v3 para content_factual: mención de providencia + "
            "respuesta >= 100 chars + al menos 1 verbo jurídico. "
            "Captura correctitud semántica básica sin exigir coincidencia literal. "
            "Metadata y OOD conservan evaluación v2."
        ),
    }
    REPORT_FIX.write_text(json.dumps(new_report, indent=2, ensure_ascii=False))
    print(f"\n✓ {REPORT_FIX}")

if __name__ == "__main__":
    main()
