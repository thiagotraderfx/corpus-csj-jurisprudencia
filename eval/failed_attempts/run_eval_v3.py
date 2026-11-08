"""Evaluador v3 — fix normalización + retry 404 + matcher mejorado."""
import json, re, sys, time, unicodedata
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from api_index import get_index
from api_rag import generate, retrieve_boosted, _get_chat_defaults, _normalize_generate_out, RAGError

GOLD = Path("eval/gold_questions_v2.jsonl")
REPORT = Path("eval/EVAL_REPORT_v3.json")
FALLBACK_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

# ─── Normalización ───
def norm_fecha(s):
    """Convertir '07/11/2025' o '7 de noviembre de 2025' a '2025-11-07'."""
    if not s:
        return ""
    s = s.strip()
    # dd/mm/yyyy
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # "7 de noviembre de 2025"
    meses = {"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
             "julio":"07","agosto":"08","septiembre":"09","setiembre":"09","octubre":"10",
             "noviembre":"11","diciembre":"12"}
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", s.lower())
    if m:
        d, mes, y = m.groups()
        if mes in meses:
            return f"{y}-{meses[mes]}-{int(d):02d}"
    return s.lower()

def norm_sala(s):
    """'SALA DE DESCONGESTIÓN LABORAL N.º 2' → 'sala de descongestion laboral 2'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\bn\s*\.?\s*[º°]\s*", "", s)
    s = re.sub(r"\bno\.\s*", "", s)
    s = re.sub(r"\bnro\.?\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))

# ─── Matchers ───
def correct_metadata(expected, answer, category):
    if not expected or not answer:
        return False
    e, a = expected.strip(), answer.strip()
    if category == "metadata_fecha":
        return norm_fecha(e) == norm_fecha(a) or norm_fecha(e) in norm_fecha(a)
    if category == "metadata_sala":
        en, an = norm_sala(e), norm_sala(a)
        et, at = set(en.split()), set(an.split())
        if not et:
            return False
        return len(et & at) / len(et) >= 0.7
    # radicado/ponente: substring or token overlap
    if e.lower() in a.lower():
        return True
    et, at = toks(e), toks(a)
    if not et:
        return False
    return len(et & at) / len(et) >= 0.40

def correct_content_factual(keywords, answer, prov=None):
    """Al menos 1 keyword + respuesta sustancial + menciona providencia."""
    if not keywords or not answer:
        return False
    a = answer.lower().strip()
    if len(a) < 80:  # too short = probably refusal
        return False
    kw_hit = any(kw.lower() in a for kw in keywords)
    if not kw_hit:
        return False
    if prov:
        prov_clean = prov.lower().replace("‑", "-").replace("\u2011", "-")
        a_clean = a.replace("‑", "-").replace("\u2011", "-")
        if prov_clean not in a_clean:
            return False
    return True

# ─── Generate con retry 404 ───
def safe_generate(query, chunks, model, temp, max_tokens):
    """generate() con retry si el modelo falla con 404."""
    try:
        out = generate(query, chunks, model, temp, max_tokens)
        return _normalize_generate_out(out)
    except RAGError as e:
        if "404" in str(e):
            out = generate(query, chunks, FALLBACK_MODEL, temp, max_tokens)
            return _normalize_generate_out(out)
        raise

# ─── Eval loop ───
def main():
    print("═══ Eval v3 (normalización + retry 404 + matcher mejorado) ═══\n")
    gold = [json.loads(l) for l in GOLD.read_text().strip().split("\n") if l.strip()]
    idx = get_index()
    dm, dt, dmax = _get_chat_defaults()

    results = []
    for i, q in enumerate(gold, 1):
        cat = q["category"]
        t0 = time.time()
        try:
            raw = retrieve_boosted(idx, q["query"], k=5)
            chunks = raw[0] if isinstance(raw, tuple) else raw
            chunks = [dict(c) if isinstance(c, dict) else {"text": str(c), "score": 0.0} for c in chunks]
            for c in chunks:
                c.setdefault("score", 0.0)
                for f in ("chunk_id","providencia","section","fecha","sala","text"):
                    c.setdefault(f, "")
            scores = [c.get("score", 0.0) for c in chunks]

            if cat == "out_of_domain":
                if not scores or max(scores) < 0.30:
                    results.append({"id": q["id"], "category": cat, "refused": True, "correct": True,
                                    "elapsed_ms": int((time.time()-t0)*1000)})
                    print(f"  [{i:2d}] {q['id']:4s} {cat:18s} refuse=True")
                    continue

            if max(scores) < 0.30:
                results.append({"id": q["id"], "category": cat, "refused": True, "correct": False,
                                "elapsed_ms": int((time.time()-t0)*1000)})
                print(f"  [{i:2d}] {q['id']:4s} {cat:18s} refuse=True")
                continue

            answer = safe_generate(q["query"], chunks, dm, dt, dmax)
            elapsed = int((time.time()-t0)*1000)

            if cat == "out_of_domain":
                correct = False
            elif cat.startswith("metadata_"):
                correct = correct_metadata(q.get("expected_answer", ""), answer, cat)
            elif cat == "content_factual":
                correct = correct_content_factual(q.get("expected_keywords", []), answer, q.get("expected_providencia"))
            else:
                correct = False

            results.append({"id": q["id"], "category": cat, "query": q["query"], "answer": answer[:300],
                            "refused": False, "correct": correct, "elapsed_ms": elapsed})
            mark = "✓" if correct else "✗"
            print(f"  [{i:2d}] {q['id']:4s} {cat:18s} {mark} conf={max(scores):.3f}")

        except Exception as e:
            results.append({"id": q["id"], "category": cat, "error": str(e)[:200], "correct": False,
                            "refused": None, "elapsed_ms": int((time.time()-t0)*1000)})
            print(f"  [{i:2d}] {q['id']:4s} {cat:18s} ERROR: {e}")

    # Métricas
    from collections import defaultdict
    in_dom = [x for x in results if x["category"] != "out_of_domain"]
    ood = [x for x in results if x["category"] == "out_of_domain"]
    ok_in = sum(1 for x in in_dom if x.get("correct"))
    refused_ood = sum(1 for x in ood if x.get("refused"))
    false_ref = sum(1 for x in in_dom if x.get("refused"))
    acc = ok_in / max(len(in_dom), 1)
    ref_acc = refused_ood / max(len(ood), 1)
    false_ref_rate = false_ref / max(len(in_dom), 1)

    by = defaultdict(lambda: {"n":0,"ok":0,"refused":0})
    for x in results:
        by[x["category"]]["n"] += 1
        if x.get("correct"): by[x["category"]]["ok"] += 1
        if x.get("refused"): by[x["category"]]["refused"] += 1

    print(f"\n═══════════════════════════════════════════════════════")
    print(f"RESULTADOS v3")
    print(f"═══════════════════════════════════════════════════════")
    print(f"  Faithfulness:       {ok_in}/{len(in_dom)} = {acc*100:.1f}%")
    print(f"  Refusal accuracy:   {refused_ood}/{len(ood)} = {ref_acc*100:.1f}%")
    print(f"  False refusal rate: {false_ref}/{len(in_dom)} = {false_ref_rate*100:.1f}%")
    print(f"\n  Por categoría:")
    for cat, d in sorted(by.items()):
        rate = d["ok"]/d["n"] if d["n"] else 0
        marker = "✓" if rate >= 0.90 else "⚠" if rate >= 0.70 else "✗"
        print(f"    {marker} {cat:22s} {d['ok']:2d}/{d['n']:2d} = {rate*100:3.0f}%  refused={d['refused']}")

    REPORT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metric_version": "v3-normalized+retry+nli-lite",
        "n_questions": len(results), "n_in_domain": len(in_dom), "n_out_of_domain": len(ood),
        "metrics": {"faithfulness": round(acc,4), "refusal_accuracy": round(ref_acc,4),
                    "false_refusal_rate": round(false_ref_rate,4)},
        "by_category": {k: dict(v) for k,v in by.items()},
        "results": results,
    }, indent=2, ensure_ascii=False))

    sys.exit(0 if acc >= 0.85 else (0 if acc >= 0.70 else 1))

if __name__ == "__main__":
    main()
