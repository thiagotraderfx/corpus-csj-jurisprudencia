"""Análisis autónomo de cobertura del corpus y recomendaciones.

Detecta desbalances por (año, sala, tipo) y genera recomendaciones
justificadas sobre qué sentencias conviene agregar.

No alucina: cada recomendación se basa en un cálculo transparente
sobre los 309 docs actuales.
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

SALAS_NORM = {
    "CIVIL": "civil", "PENAL": "penal", "LABORAL": "laboral", "ESPECIAL": "especial"
}


def norm_sala(s):
    if not s:
        return "otra"
    s = s.upper()
    for k, v in SALAS_NORM.items():
        if k in s:
            return v
    return "otra"


def norm_tipo(t):
    if not t:
        return "?"
    t = t.upper()
    if t.startswith("SENTENCIA"):
        return "sentencia"
    if t.startswith("AUTO"):
        return "auto"
    return "?"


def analyze():
    docs = [json.loads(l) for l in Path("manifest.jsonl").read_text().strip().split("\n") if l.strip()]
    print("═══ Análisis de cobertura del corpus ═══")
    print("Total: %d docs\n" % len(docs))

    # Matriz año × sala
    matrix = Counter()
    for d in docs:
        if norm_tipo(d.get("tipo")) == "sentencia":
            matrix[(d.get("year"), norm_sala(d.get("sala")))] += 1

    years = sorted(set(y for y, _ in matrix.keys() if y), reverse=True)[:6]
    salas = ["civil", "laboral", "penal"]

    print("Matriz año × sala (solo sentencias):")
    print("  %-6s %8s %8s %8s %8s" % ("Año", "civil", "laboral", "penal", "total"))
    for y in years:
        row = [matrix.get((y, s), 0) for s in salas]
        print("  %-6s %8d %8d %8d %8d" % (y, row[0], row[1], row[2], sum(row)))

    print("\nTotales por sala:")
    by_sala = Counter()
    for d in docs:
        if norm_tipo(d.get("tipo")) == "sentencia":
            by_sala[norm_sala(d.get("sala"))] += 1
    for s, n in by_sala.most_common():
        print("  %-10s %d" % (s, n))

    # Detección de gaps
    print("\n═══ Gaps detectados (candidatos a crawlear) ═══\n")
    recommendations = []

    # Gap 1: años con poca cobertura
    for y in years:
        year_total = sum(matrix.get((y, s), 0) for s in salas)
        if year_total < 40:
            recommendations.append({
                "tipo": "año_bajo",
                "target": y,
                "actual": year_total,
                "razon": "Solo %d sentencias en %s. Bajo el umbral recomendado (40)." % (year_total, y),
                "prioridad": "ALTA" if year_total < 20 else "MEDIA",
            })

    # Gap 2: desbalance de salas
    total_sent = sum(by_sala.values())
    for s in salas:
        n = by_sala.get(s, 0)
        pct = 100 * n / total_sent if total_sent else 0
        if pct < 10:
            recommendations.append({
                "tipo": "sala_baja",
                "target": s,
                "actual": n,
                "pct": round(pct, 1),
                "razon": "Sala %s representa solo %.1f%% del corpus. Recomendado ≥15%%." % (s, pct),
                "prioridad": "ALTA" if pct < 5 else "MEDIA",
            })

    # Gap 3: combos año×sala vacíos o casi vacíos
    for y in years[:4]:  # últimos 4 años
        for s in salas:
            n = matrix.get((y, s), 0)
            if n < 5:
                recommendations.append({
                    "tipo": "combo_vacio",
                    "target": "%s_%s" % (y, s),
                    "actual": n,
                    "razon": "%s %d tiene %d sentencias. Se recomienda al menos 5 para representatividad." % (s, y, n),
                    "prioridad": "MEDIA",
                })

    if not recommendations:
        print("  ✓ Corpus balanceado, no se detectan gaps significativos.")
    else:
        for i, r in enumerate(recommendations, 1):
            print("  [%d] %s — %s" % (i, r["prioridad"], r["razon"]))
            print("      Acción: crawlear más '%s' (%s)" % (r["target"], r["tipo"]))
            print()

    # Guardar reporte
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_docs": len(docs),
        "total_sentencias": total_sent,
        "by_year": {str(y): sum(matrix.get((y, s), 0) for s in salas) for y in years},
        "by_sala": dict(by_sala),
        "matrix": {"%s_%s" % (y, s): matrix.get((y, s), 0) for y in years for s in salas},
        "recommendations": recommendations,
    }
    Path("COVERAGE_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n  ✓ Reporte guardado en COVERAGE_REPORT.json")

    # Generar MD
    md = ["# Reporte de Cobertura del Corpus CSJ\n",
          "**Generado**: %s\n" % report["generated_at"],
          "**Total docs**: %d (sentencias: %d)\n" % (len(docs), total_sent),
          "\n## Distribución por año\n"]
    for y in years:
        md.append("- %s: %d\n" % (y, report["by_year"][str(y)]))
    md.append("\n## Distribución por sala\n")
    for s, n in by_sala.most_common():
        md.append("- %s: %d\n" % (s, n))
    md.append("\n## Recomendaciones (%d)\n" % len(recommendations))
    for i, r in enumerate(recommendations, 1):
        md.append("\n### %d. [%s] %s\n" % (i, r["prioridad"], r["razon"]))
        md.append("**Acción**: crawlear más `%s`\n" % r["target"])
    Path("COVERAGE_REPORT.md").write_text("".join(md))
    print("  ✓ Reporte guardado en COVERAGE_REPORT.md")


if __name__ == "__main__":
    analyze()
