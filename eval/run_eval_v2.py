"""Evaluador v2: usa retrieve_boosted + métrica keyword-aware."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from api_index import get_index
from api_rag import generate, retrieve_boosted, _get_chat_defaults, _normalize_generate_out

GOLD = Path("eval/gold_questions_v2.jsonl")

def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))

def correct_metadata(expected, answer):
    if not expected or not answer:
        return False
    e = expected.lower().strip()
    a = answer.lower().strip()
    if e in a:
        return True
    e_t, a_t = toks(e), toks(a)
    if not e_t: return False
    return len(e_t & a_t) / len(e_t) >= 0.40

def correct_content_factual(keywords, answer):
    if not keywords or not answer:
        return False
    a = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in a)
    return hits >= max(1, len(keywords) // 2)

def main():
    print("═══ Fase C.2 — Eval con retrieve_boosted + content_factual ═══\n")
    gold = [json.loads(l) for l in GOLD.read_text().strip().split("\n") if l.strip()]
    print(f"  Gold: {len(gold)}")
    idx = get_index()
    dm, dt, dmax = _get_chat_defaults()

    results = []
    for i, q in enumerate(gold, 1):
        cat = q["category"]
        t0 = time.time()
        try:
            # Retrieval boosted
            raw = retrieve_boosted(idx, q["query"], k=5)
            chunks = raw[0] if isinstance(raw, tuple) else raw
            # Normalizar chunks
            chunks = [dict(c) if isinstance(c, dict) else {"text": str(c), "score": 0.0} for c in chunks]
            for c in chunks:
                c.setdefault("score", 0.0)
                for f in ("chunk_id","providencia","section","fecha","sala","text"):
                    c.setdefault(f, "")
            scores = [c.get("score", 0.0) for c in chunks]

            # Refusal check
            if cat == "out_of_domain":
                if not scores or max(scores) < 0.30:
                    results.append({"id": q["id"], "category": cat, "refused": True, "correct": True, "elapsed_ms": int((time.time()-t0)*1000)})
                    print(f"  [{i:2d}] {q['id']:4s} {cat:18s} refuse=True")
                    continue

            # Generar
            if max(scores) < 0.30:
                results.append({"id": q["id"], "category": cat, "refused": True, "correct": False, "elapsed_ms": int((time.time()-t0)*1000)})
                print(f"  [{i:2d}] {q['id']:4s} {cat:18s} refuse=True")
                continue

            out = generate(q["query"], chunks, dm if not q.get("model") else q["model"], dt, dmax)
            answer = _normalize_generate_out(out)
            elapsed = int((time.time()-t0)*1000)

            if cat == "out_of_domain":
                # No refused = incorrecto
                correct = False
            elif cat.startswith("metadata_"):
                correct = correct_metadata(q.get("expected_answer"), answer)
            elif cat == "content_factual":
                correct = correct_content_factual(q.get("expected_keywords"), answer)
            else:
                correct = False

            results.append({"id": q["id"], "category": cat, "query": q["query"],
                "answer": answer[:300], "refused": False, "correct": correct, "elapsed_ms": elapsed})
            mark = "✓" if correct else "✗"
            print(f"  [{i:2d}] {q['id']:4s} {cat:18s} {mark} conf={max(scores):.3f}")

        except Exception as e:
            results.append({"id": q["id"], "category": cat, "error": str(e)[:200], "correct": False, "refused": None, "elapsed_ms": int((time.time()-t0)*1000)})
            print(f"  [{i:2d}] {q['id']:4s} {cat:18s} ERROR: {e}")

    # Métricas
    in_dom = [x for x in results if x["category"] != "out_of_domain"]
    ood = [x for x in results if x["category"] == "out_of_domain"]
    ok_in = sum(1 for x in in_dom if x.get("correct"))
    refused_ood = sum(1 for x in ood if x.get("refused"))
    false_ref = sum(1 for x in in_dom if x.get("refused"))

    acc = ok_in / max(len(in_dom), 1)
    faith = ok_in / max(len(in_dom), 1)  # misma que acc en esta versión
    ref_acc = refused_ood / max(len(ood), 1)
    false_ref_rate = false_ref / max(len(in_dom), 1)

    from collections import defaultdict
    by = defaultdict(lambda: {"n":0,"ok":0,"refused":0})
    for x in results:
        by[x["category"]]["n"] += 1
        if x.get("correct"): by[x["category"]]["ok"] += 1
        if x.get("refused"): by[x["category"]]["refused"] += 1

    print(f"\n═══════════════════════════════════════════════════════")
    print(f"RESULTADOS v2 (retrieve_boosted + content_factual)")
    print(f"═══════════════════════════════════════════════════════")
    print(f"  Faithfulness:       {ok_in}/{len(in_dom)} = {acc*100:.1f}%")
    print(f"  Refusal accuracy:   {refused_ood}/{len(ood)} = {ref_acc*100:.1f}%")
    print(f"  False refusal rate: {false_ref}/{len(in_dom)} = {false_ref_rate*100:.1f}%")
    print(f"\n  Por categoría:")
    for cat, d in sorted(by.items()):
        rate = d["ok"]/d["n"] if d["n"] else 0
        marker = "✓" if rate >= 0.80 else "⚠" if rate >= 0.50 else "✗"
        print(f"    {marker} {cat:22s} {d['ok']:2d}/{d['n']:2d} = {rate*100:3.0f}%  refused={d['refused']}")

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metric_version": "v2-keyword+boosted",
        "n_questions": len(results),
        "n_in_domain": len(in_dom),
        "n_out_of_domain": len(ood),
        "metrics": {
            "faithfulness": round(acc, 4),
            "refusal_accuracy": round(ref_acc, 4),
            "false_refusal_rate": round(false_ref_rate, 4),
        },
        "by_category": {k: dict(v) for k, v in by.items()},
        "results": results,
    }
    Path("eval/EVAL_REPORT_v2.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    if acc >= 0.60:
        print(f"\n  ✓✓✓ Faithfulness {acc*100:.0f}% ≥ 60% — listo para AUDIT")
        sys.exit(0)
    elif acc >= 0.50:
        print(f"\n  ⚠ Faithfulness {acc*100:.0f}% (50-60%) — aceptable con deuda")
        sys.exit(0)
    else:
        print(f"\n  ✗ Faithfulness {acc*100:.0f}% <50% — investigar")
        sys.exit(1)

if __name__ == "__main__":
    main()
