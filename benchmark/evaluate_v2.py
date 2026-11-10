"""Evaluación con validación estricta, métricas Recall@5/Precision@5 y flag de revisión humana."""
import json, sys
from datetime import datetime
from pathlib import Path
import argparse

BENCH_DIR = Path(__file__).parent
RESULTS_DIR = BENCH_DIR / "results"

from llm_judge import judge, verify_doc, score_ponderado, JUDGE_MODEL


def cargar_jsonl(path):
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out


def recall_precision_at_k(respuesta_ia, fuentes_esperadas, k=5):
    """Recall@k y Precision@k para fuentes tipo jurisprudencia."""
    expected = {f["identificador"] for f in fuentes_esperadas
                if f.get("tipo") == "jurisprudencia" and f.get("identificador")}
    if not expected:
        return None, None, "sin_fuentes_esperadas"

    top_k_provs = set()
    for s in (respuesta_ia.get("sources") or [])[:k]:
        p = s.get("providencia") or s.get("doc_id")
        if p: top_k_provs.add(p)

    hits = expected & top_k_provs
    recall = 1.0 if hits else 0.0  # cualquier fuente esperada recuperada
    precision = len(hits) / len(top_k_provs) if top_k_provs else 0.0
    return round(recall, 3), round(precision, 3), "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, help="run_id del manifest")
    args = ap.parse_args()

    manifest_path = RESULTS_DIR / f"run_{args.run_id}.json"
    respuestas_path = RESULTS_DIR / f"respuestas_{args.run_id}.jsonl"
    if not manifest_path.exists():
        print(f"ABORT: {manifest_path} no existe"); sys.exit(1)
    if not respuestas_path.exists():
        print(f"ABORT: {respuestas_path} no existe"); sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    preguntas = {p["id"]: p for p in cargar_jsonl(Path(manifest["input_file"]))}
    respuestas = cargar_jsonl(respuestas_path)

    # ─── Fix #2: Validación estricta de correspondencia ───
    if len(respuestas) != manifest["n_questions"]:
        print(f"ABORT: respuestas={len(respuestas)} != preguntas={manifest['n_questions']}")
        sys.exit(1)
    if len(preguntas) != len(respuestas):
        print(f"ABORT: input tiene {len(preguntas)} pero respuestas {len(respuestas)}")
        sys.exit(1)

    for r in respuestas:
        pid = r.get("_bench", {}).get("id")
        if pid not in preguntas:
            print(f"ABORT: respuesta con id={pid} no está en input"); sys.exit(1)
        if "error" in r.get("_bench", {}):
            print(f"  WARN: respuesta {pid} tiene error: {r['_bench']['error']}")

    print(f"run_id: {args.run_id}")
    print(f"preguntas: {len(preguntas)} · respuestas: {len(respuestas)} (validación OK)")
    print(f"juez: {JUDGE_MODEL}\n")

    evaluaciones = []
    for r in respuestas:
        pid = r["_bench"]["id"]
        p = preguntas[pid]
        print(f"  [{pid}] evaluando...", flush=True)

        # Evaluación semántica (LLM)
        ev = judge(
            pregunta=p["pregunta"],
            respuesta_esperada=p["respuesta_esperada"],
            criterios_obligatorios=p.get("criterios_obligatorios", []),
            errores_criticos=p.get("errores_criticos", []),
            respuesta_ia=r.get("answer", ""),
            fuentes_ia=r.get("sources", []),
        )

        # Fix #3: Verificación documental determinista
        doc_check = verify_doc(r.get("sources", []))

        # Fix #4: Recall@5 / Precision@5
        recall, precision, rp_reason = recall_precision_at_k(
            r, p.get("fuentes_esperadas", []), k=5)

        # E1: Flag de revisión humana
        confianza = ev.get("confianza", 0.0)
        revision_humana = (
            confianza < 0.7
            or not doc_check["fidelidad_ok"]
            or ev.get("veredicto_global") == "inaceptable"
            or "error" in ev
        )

        ev_full = {
            "_id": pid,
            "_nivel": p.get("nivel"),
            "_tema": p.get("tema"),
            "_verified": r.get("verified"),
            "_refused": r.get("refused"),
            "_latency_s": r["_bench"].get("latency_s"),
            "evaluacion_llm": ev,
            "verificacion_documental": doc_check,
            "recall_at_5": recall,
            "precision_at_5": precision,
            "recall_precision_reason": rp_reason,
            "score_ponderado": score_ponderado(ev),
            "revision_humana_requerida": revision_humana,
        }
        evaluaciones.append(ev_full)

        score_str = f"{ev_full['score_ponderado']}" if ev_full['score_ponderado'] is not None else "ERROR"
        rp_str = f"R@5={recall} P@5={precision}" if recall is not None else f"R/P={rp_reason}"
        rev_str = " ⚠REVISIÓN" if revision_humana else ""
        print(f"    score={score_str} {rp_str} veredicto={ev.get('veredicto_global')}{rev_str}")

    # ─── Agregados ───
    total = len(evaluaciones)
    scores = [e["score_ponderado"] for e in evaluaciones if e["score_ponderado"] is not None]
    verified = sum(1 for e in evaluaciones if e["_verified"] is True)
    refused = sum(1 for e in evaluaciones if e["_refused"] is True)
    revisar = sum(1 for e in evaluaciones if e["revision_humana_requerida"])
    con_citas_inv = sum(1 for e in evaluaciones
                        if not e["verificacion_documental"]["fidelidad_ok"])
    recalls = [e["recall_at_5"] for e in evaluaciones if e["recall_at_5"] is not None]
    precisions = [e["precision_at_5"] for e in evaluaciones if e["precision_at_5"] is not None]

    print("\n════════════════════════════════════════════════════════════")
    print("REPORTE GLOBAL (requiere revisión humana — LLM no es verdad jurídica)")
    print("════════════════════════════════════════════════════════════")
    print(f"  Total:               {total}")
    print(f"  Score promedio 1-5:  {round(sum(scores)/len(scores),2) if scores else 'N/A'}")
    print(f"  Score min/max:       {min(scores) if scores else 'N/A'} / {max(scores) if scores else 'N/A'}")
    print(f"  Verified (citas):    {verified}/{total}")
    print(f"  Refused:             {refused}/{total}")
    print(f"  Citas inventadas:    {con_citas_inv}/{total}")
    print(f"  Revisión humana:     {revisar}/{total} casos marcados")
    if recalls:
        print(f"  Recall@5 promedio:   {round(sum(recalls)/len(recalls),3)} ({len(recalls)} con fuentes esperadas)")
    else:
        print(f"  Recall@5:            N/A (ninguna pregunta define fuentes_esperadas)")
    if precisions:
        print(f"  Precision@5 prom.:   {round(sum(precisions)/len(precisions),3)}")
    else:
        print(f"  Precision@5:         N/A")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"evaluacion_{args.run_id}_{ts}.json"
    out.write_text(json.dumps({
        "run_id": args.run_id,
        "manifest": manifest,
        "juez_model": JUDGE_MODEL,
        "advertencia": "Puntuaciones son señales del LLM, NO verdad jurídica definitiva. Requiere revisión humana.",
        "agregados": {
            "total": total,
            "score_avg": round(sum(scores)/len(scores),2) if scores else None,
            "verified": verified, "refused": refused,
            "revision_humana": revisar, "citas_inventadas": con_citas_inv,
            "recall_at_5_avg": round(sum(recalls)/len(recalls),3) if recalls else None,
            "precision_at_5_avg": round(sum(precisions)/len(precisions),3) if precisions else None,
        },
        "evaluaciones": evaluaciones,
    }, indent=2, ensure_ascii=False))
    print(f"\n  Reporte: {out}")


if __name__ == "__main__":
    main()
