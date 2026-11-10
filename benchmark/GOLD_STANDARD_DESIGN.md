# Golden Standard v2 — diseño

Este documento define el schema y los criterios de evaluación del benchmark
del corpus CSJ. Sustituye al esquema plano del smoke test inicial.

## Distinción importante

- **Sistema** (`corpus_corte_suprema`): producto estatal de alta envergadura,
  RAG productivo, CERTIFIED 14/14, 321 sentencias reales.
- **Harness** (`benchmark/`): herramienta de medición. No es el sistema.
- **Smoke test** (4 preguntas demo): valida que el harness funciona.
- **Benchmark real** (50 preguntas del abogado): el instrumento de calidad.
- **Golden standard**: la referencia humana contra la cual se mide la IA.

## Schema JSONL v2

Cada línea de `preguntas.jsonl` es un objeto JSON con:

    {
      "id": "P001",
      "pregunta": "problema jurídico concreto",
      "respuesta_esperada": "respuesta jurídicamente fundamentada (2-6 oraciones)",
      "fuentes_esperadas": [
        {"tipo": "norma", "identificador": "LEY_906_2004_ART_381"},
        {"tipo": "jurisprudencia", "identificador": "SP298-2026", "radicado": "..."}
      ],
      "criterios_obligatorios": [
        "Identificar el estándar probatorio",
        "Explicar su aplicación al caso"
      ],
      "errores_criticos": [
        "Invertir la carga de la prueba",
        "Confundir certeza absoluta con duda razonable"
      ],
      "nivel": "facil|medio|dificil|forense",
      "tema": "string",
      "jurisdiccion": "ordinaria|constitucional|...",
      "especialidad": "penal|civil|laboral|tutela|...",
      "tipo_razonamiento": "conocimiento_normativo|interpretacion|analisis_jurisprudencial|diferenciacion_instituciones|reconstruccion_argumentativa",
      "notas": "criterios de aceptación del abogado"
    }

## 5 dimensiones de evaluación (LLM-as-judge)

| Dimensión | Qué verifica | Peso |
|-----------|--------------|------|
| Exactitud jurídica | La regla jurídica es correcta | 30% |
| Fundamentación normativa | Identifica las disposiciones aplicables | 15% |
| Fundamentación jurisprudencial | Cita providencias reales y pertinentes | 20% |
| Razonamiento | Aplica la regla al problema correctamente | 25% |
| Fidelidad documental | No inventa citas/radicados/reglas | 10% |

## 6 indicadores globales

| Indicador | Objetivo |
|-----------|----------|
| Recall@5 | La providencia pertinente está en top-5 |
| Precision@5 | Proporción de resultados pertinentes |
| Exactitud jurídica (1-5) | Corrección de la respuesta |
| Fidelidad de citas | Citas existen en la fuente |
| Cobertura normativa | Incorpora las disposiciones pertinentes |
| Alucinación jurisprudencial | Detecta providencias/radicados/reglas inventadas |

## Reglas del juez LLM

1. El juez NO tiene autoridad para convertir interpretaciones discutibles en verdad.
2. La calificación está subordinada a las fuentes verificables y criterios humanos.
3. Si el juez no puede decidir, retorna `confianza < 0.7` y se marca para revisión humana.
4. El juez DEBE estructurar su evaluación en JSON (no texto libre).

## Clasificación de preguntas por cobertura

El corpus puede no soportar todas las preguntas. Clasificamos en:

- **Cubierta**: el corpus tiene ≥5 docs con contenido temático pertinente.
- **Débil**: 1-4 docs, evaluación posible pero limitada.
- **Fuera de corpus**: 0 docs. Se marca para ingesta futura.

Solo las preguntas "cubierta" entran al benchmark principal. Las "débiles"
se evalúan pero con advertencia. Las "fuera" se entregan al operador como
candidatas a ingesta.
