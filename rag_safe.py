"""Capa de seguridad anti-alucinación sobre rag_ask.py / api_rag.py."""
import json
import re
from pathlib import Path

_CHUNKS_CACHE = None
_PROV_PATTERN = r'\b([A-Z]{2,4}\d{1,6}-\d{4})\b'
_BRACKET_PATTERN = r'\[(\d+)\]'


def _load_valid_providencias():
    global _CHUNKS_CACHE
    if _CHUNKS_CACHE is None:
        provs = set()
        for line in Path("chunks.jsonl").read_text().strip().split("\n"):
            if line.strip():
                try:
                    c = json.loads(line)
                    p = c.get("providencia")
                    if p:
                        provs.add(p)
                except json.JSONDecodeError:
                    pass
        _CHUNKS_CACHE = provs
    return _CHUNKS_CACHE


def should_refuse(scores, threshold=0.30):
    """True si el retrieval es demasiado débil para responder con base."""
    if not scores:
        return True
    return max(scores) < threshold


def verify_citations(answer, context_chunks, strict=True):
    """
    Verifica citas en DOS formatos:
      - [N]: numérico (usado por generate())
      - SC1234-2024: providencia

    Retorna (verified: bool, unverified_list: list).
    """
    if not context_chunks:
        return (False, ["(empty context)"])

    n_chunks = len(context_chunks)
    unverified = []

    # Formato 1: [N] citations (rango válido: 1..n_chunks)
    bracket_nums = [int(n) for n in re.findall(_BRACKET_PATTERN, answer)]
    for n in bracket_nums:
        if n < 1 or n > n_chunks:
            unverified.append("[%d] out of range (max=%d)" % (n, n_chunks))

    # Formato 2: providencias SC1234-2024
    prov_citations = list(set(re.findall(_PROV_PATTERN, answer)))
    context_provs = {c.get("providencia") for c in context_chunks if c.get("providencia")}
    for prov in prov_citations:
        if prov not in context_provs:
            unverified.append(prov)

    # Sin citas de ningún formato
    if not bracket_nums and not prov_citations:
        return (not strict, ["(no citations found)"])

    return (len(unverified) == 0, unverified)


def safe_answer(question, context_chunks, scores, llm_call,
                refusal_threshold=0.30, strict_citations=True):
    """
    Pipeline: refusal + generación + verificación de citas.
    Retorna dict con answer, refused, verified, confidence, citations, unverified, reason.
    """
    max_score = max(scores) if scores else 0.0

    if should_refuse(scores, refusal_threshold):
        return {
            "answer": (
                "La evidencia recuperada para esta consulta es insuficiente para "
                "una respuesta con respaldo verificable. Para obtener resultados "
                "precisos, considere:\n"
                "  - Incluir el identificador de la providencia o el radicado.\n"
                "  - Acotar el aspecto jurídico específico de la consulta.\n"
                "  - Indicar el año o período de interés.\n\n"
                "También puede consultar directamente el portal oficial de la "
                "Corte Suprema de Justicia de Colombia."
            ),
            "refused": True,
            "verified": None,
            "confidence": max_score,
            "citations": [],
            "unverified": [],
            "reason": "retrieval_weak: max=%.3f < %.2f" % (max_score, refusal_threshold),
        }

    try:
        raw_answer = llm_call(question, context_chunks)
    except Exception as e:
        err_msg = str(e).strip() or type(e).__name__
        return {
            "answer": "Error al generar respuesta.",
            "refused": True,
            "verified": None,
            "confidence": max_score,
            "citations": [],
            "unverified": [],
            "reason": "llm_error: %s: %s" % (type(e).__name__, err_msg[:200]),
        }

    verified, unverified = verify_citations(raw_answer, context_chunks, strict_citations)
    cited = list(set(re.findall(_PROV_PATTERN, raw_answer)))
    valid_citations = [c for c in cited if c not in unverified]

    result = {
        "answer": raw_answer,
        "refused": False,
        "verified": verified,
        "confidence": max_score,
        "citations": valid_citations,
        "unverified": unverified,
    }

    if not verified:
        result["reason"] = "Citas no verificables: %s" % ", ".join(unverified)

    return result


if __name__ == "__main__":
    print("═══ Smoke test rag_safe ═══")
    provs = _load_valid_providencias()
    print("  Providencias válidas: %d" % len(provs))
    print("  Refusal [0.1]: %s" % should_refuse([0.1]))
    print("  Refusal [0.5]: %s" % should_refuse([0.5]))

    chunks = [{"providencia": "SC1234-2024"}, {"providencia": "SP5678-2023"}]

    print("  Cita buena [1]:      %s" % (verify_citations("Ver [1].", chunks),))
    print("  Cita mala [99]:      %s" % (verify_citations("Ver [99].", chunks),))
    print("  Cita buena prov:     %s" % (verify_citations("Según SC1234-2024.", chunks),))
    print("  Cita mala prov:      %s" % (verify_citations("Según SC9999-2030.", chunks),))
    print("  ✓ rag_safe.py OK")
