"""LLM-as-judge + verificación documental determinista.

SEPARACIÓN CRÍTICA:
- judge()       → evalúa 5 dimensiones con LLM (juicio semántico)
- verify_doc()  → verifica que las citas existan en chunks.jsonl (determinista)

El LLM NO es verdad jurídica. Es una señal que requiere revisión humana
cuando confianza < 0.7 o cuando verify_doc reporta citas inventadas.
"""
import json, os, time, requests
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini")
_CHUNKS_CACHE = None


def _load_corpus_provs():
    """Deterministic: todas las providencias en chunks.jsonl."""
    global _CHUNKS_CACHE
    if _CHUNKS_CACHE is None:
        provs = set()
        path = Path("chunks.jsonl")
        if path.exists():
            for line in path.read_text().splitlines():
                if not line.strip(): continue
                try:
                    c = json.loads(line)
                    p = c.get("providencia")
                    if p: provs.add(p)
                except json.JSONDecodeError: pass
        _CHUNKS_CACHE = provs
    return _CHUNKS_CACHE


def verify_doc(sources):
    """Verifica citas contra corpus. Deterministic. NO LLM."""
    corpus_provs = _load_corpus_provs()
    validas, inventadas = [], []
    for s in sources or []:
        p = s.get("providencia") or s.get("doc_id")
        if not p: continue
        (validas if p in corpus_provs else inventadas).append(p)
    return {
        "citas_validas": sorted(set(validas)),
        "citas_inventadas": sorted(set(inventadas)),
        "fidelidad_ok": len(inventadas) == 0,
        "method": "deterministic_corpus_check",
    }


SYSTEM_PROMPT = """Eres un evaluador jurídico experto del sistema de jurisprudencia
de la Corte Suprema de Justicia de Colombia. Evalúas respuestas de IA contra un
golden standard preparado por abogados expertos.

DEBES responder SIEMPRE en JSON válido, sin texto adicional, con este formato:
{
  "exactitud_juridica": {"score": 1-5, "razon": "..."},
  "fundamentacion_normativa": {"score": 1-5, "razon": "..."},
  "fundamentacion_jurisprudencial": {"score": 1-5, "razon": "..."},
  "razonamiento": {"score": 1-5, "razon": "..."},
  "fidelidad_documental": {"score": 1-5, "razon": "..."},
  "errores_criticos_presentes": [...],
  "criterios_cumplidos": [...],
  "veredicto_global": "aceptable|parcial|inaceptable",
  "confianza": 0.0-1.0,
  "comentario": "..."
}

Reglas:
- Si omite errores_criticos del golden → exactitud ≤ 3
- Si el juez no puede decidir con certeza → confianza < 0.7
- NO inventes criterios. Basate en el golden standard.
- Tu juicio NO es verdad jurídica definitiva. Es una señal para revisión humana.
"""


def _get_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k: raise RuntimeError("Falta OPENROUTER_API_KEY")
    return k


def judge(pregunta, respuesta_esperada, criterios_obligatorios, errores_criticos,
          respuesta_ia, fuentes_ia, max_retries=2):
    """Evalúa respuesta IA contra golden (5 dimensiones). Retorna dict JSON."""
    user = f"""GOLDEN STANDARD:
Pregunta: {pregunta}
Respuesta esperada: {respuesta_esperada}
Criterios obligatorios: {json.dumps(criterios_obligatorios, ensure_ascii=False)}
Errores críticos a detectar: {json.dumps(errores_criticos, ensure_ascii=False)}

RESPUESTA IA A EVALUAR:
{respuesta_ia}

Fuentes que la IA citó: {json.dumps(fuentes_ia, ensure_ascii=False)[:2000]}

Evalúa siguiendo el formato JSON indicado."""

    key = _get_key()
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(OPENROUTER_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": JUDGE_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1, "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                }, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt); continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"): content = content[4:]
                content = content.strip()
            return json.loads(content)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < max_retries:
                time.sleep(2); continue
            return {"error": last_err, "veredicto_global": "error_evaluacion", "confianza": 0.0}
    return {"error": last_err, "veredicto_global": "error_evaluacion", "confianza": 0.0}


def score_ponderado(ev):
    """Score 1-5 ponderado por 5 dimensiones."""
    if "error" in ev: return None
    try:
        return round(
            0.30 * ev["exactitud_juridica"]["score"]
            + 0.15 * ev["fundamentacion_normativa"]["score"]
            + 0.20 * ev["fundamentacion_jurisprudencial"]["score"]
            + 0.25 * ev["razonamiento"]["score"]
            + 0.10 * ev["fidelidad_documental"]["score"], 2)
    except (KeyError, TypeError): return None
