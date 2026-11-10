# Protocolo para el conjunto de evaluación (50 preguntas)

Este documento define el procedimiento para construir un conjunto de
evaluación jurídicamente defendible del corpus CSJ.

Advertencia: el harness está funcional pero los 4 smoke tests actuales
NO son el benchmark. El benchmark real es lo que usted va a construir.

---

## Paso 0 — Antes de escribir la primera pregunta

Verificar el estado del sistema:

    cd ~/corpus_corte_suprema
    source ~/.csj_keys
    sha256sum -c INTEGRITY.sha256
    python3 certify_v1_1.py 2>&1 | grep Estado

Los tres comandos deben dar: 3/3 OK, CERTIFIED.

Si alguno falla, DETENERSE y reportar antes de continuar.

---

## Paso 1 — Verificar qué providencias están en el corpus

El corpus tiene 321 sentencias de la Corte Suprema de Justicia de Colombia
(Civil, Penal, Laboral, Tutela), 2021-2026. NO incluye Corte Constitucional.

Para verificar si una providencia está indexada:

    python3 -c "import json; provs={json.loads(l)['providencia'] for l in open('chunks.jsonl') if l.strip()}; print('SC1234-2024' in provs)"

Reemplazar 'SC1234-2024' por el identificador a verificar.

Regla estricta: si una providencia NO está en chunks.jsonl, NO puede ser
fuente esperada de una pregunta. El sistema no puede recuperar lo que no
está indexado. Marcar esas preguntas como "no evaluables con este corpus"
o descartarlas.

Para ver cobertura por sala y año:

    curl -s http://127.0.0.1:8000/coverage | python3 -m json.tool

---

## Paso 2 — Estructura de cada pregunta

Cada pregunta es un objeto JSON en una línea de benchmark/data/preguntas.jsonl.

Campos obligatorios:

    id                   string único, ej: P001
    pregunta             string, problema jurídico concreto
    respuesta_esperada   string, 2-6 oraciones con fundamento normativo y jurisprudencial
    fuentes_esperadas    array de objetos {tipo, identificador}
                         tipo = "norma" | "jurisprudencia" | "jurisprudencia_externa"
                         identificador = ej: "LEY_906_2004_ART_381" o "SC3075-2024"
    criterios_obligatorios  array de strings (qué DEBE contener la respuesta)
    errores_criticos     array de strings (qué NO debe aparecer)
    nivel                "facil" | "medio" | "dificil" | "forense"
    tema                 string
    jurisdiccion         "ordinaria" | "constitucional"
    especialidad         "penal" | "civil" | "laboral" | "tutela"
    tipo_razonamiento    "conocimiento_normativo" | "interpretacion"
                         | "analisis_jurisprudencial" | "diferenciacion_instituciones"
                         | "reconstruccion_argumentativa"
    notas                criterios adicionales de aceptación

---

## Paso 3 — Criterios de calidad

Bien escrita:
- Problema jurídico real que un abogado en ejercicio plantearía
- Respuesta verificable en providencias del corpus
- Criterios objetivos de evaluación (no "la respuesta debe ser buena")
- Errores críticos identificables (ej: "invertir la carga de la prueba")

Mal escrita:
- Pregunta capciosa o artificial
- Respuesta que requiere información fuera del corpus
- Criterios subjetivos sin anclaje jurídico
- Sin fuente esperada verificada

Ejemplo bien escrito (con campos completos):

    {"id":"P001","pregunta":"¿Cuáles son los elementos esenciales del contrato de trabajo y qué efecto produce la presunción del artículo 24 del Código Sustantivo del Trabajo?","respuesta_esperada":"De conformidad con el artículo 23 del Código Sustantivo del Trabajo son elementos esenciales: prestación personal del servicio, subordinación o dependencia y salario. Adicionalmente el artículo 24 establece que toda relación de trabajo personal se presume regida por un contrato de trabajo, presunción que admite prueba en contrario. La subordinación es el elemento diferenciador frente a otras modalidades contractuales.","fuentes_esperadas":[{"tipo":"norma","identificador":"CST_ART_23"},{"tipo":"norma","identificador":"CST_ART_24"}],"criterios_obligatorios":["Enumerar los 3 elementos del art 23","Mencionar la presunción del art 24","Identificar la subordinación como elemento diferenciador"],"errores_criticos":["Omitir el art 24","Confundir elementos del contrato con los de la relación laboral"],"nivel":"medio","tema":"derecho laboral","jurisdiccion":"ordinaria","especialidad":"laboral","tipo_razonamiento":"conocimiento_normativo","notas":"Verificar que mencione los 3 elementos y la presunción."}

---

## Paso 4 — Clasificación por dificultad

Distribución sugerida de 50 preguntas:

    facil    12  conocimiento normativo directo (artículos, elementos)
    medio    18  interpretación y aplicación (cómo se aplica una norma)
    dificil  15  análisis jurisprudencial (reglas decididas por la CSJ)
    forense   5  reconstrucción de argumentos, identificación de errores judiciales

Cobertura sugerida por sala (ajustar según disponibilidad real):

    Civil    15
    Laboral  12
    Penal    13
    Tutela   10

Consultar /coverage para verificar que la cobertura real del corpus
soporta la distribución elegida. Si hay gaps (ej: penal 2021-2023 escaso),
marcar esas preguntas como "no evaluables" o no incluirlas.

---

## Paso 5 — Ejecutar el benchmark

Con el sistema corriendo en otra terminal:

    uvicorn api:app --host 127.0.0.1 --port 8000

En la terminal de trabajo:

    python3 benchmark/run_benchmark.py --input benchmark/data/preguntas.jsonl

Esto produce dos archivos en benchmark/results/:
- run_<run_id>.json (manifest con hash del input)
- respuestas_<run_id>.jsonl (respuestas del sistema)

Anotar el run_id de la salida.

---

## Paso 6 — Evaluar

    python3 benchmark/evaluate_v2.py --run-id <run_id>

Esto produce evaluacion_<run_id>_<ts>.json con:
- Score por pregunta (5 dimensiones ponderadas)
- Verificación documental (verify_doc contra chunks.jsonl)
- Recall@5 / Precision@5 (si aplica)
- Flag revision_humana_requerida

---

## Paso 7 — Revisión humana obligatoria

Los scores del juez LLM son SEÑALES, no verdad jurídica.

Revisar manualmente cada caso marcado con revision_humana_requerida=true:

- confianza < 0.7 del juez
- citas_inventadas > 0 (verify_doc falló)
- veredicto = inaceptable
- error en evaluación

Para cada caso:
- ¿La respuesta es jurídicamente correcta?
- ¿Cita las providencias correctas?
- ¿Cumple los criterios obligatorios?
- ¿Incurre en algún error crítico?

Anotar el veredicto humano en el reporte. Si el humano y el juez discrepan,
el humano prevalece.

---

## Paso 8 — Reporte final

Documentar en benchmark/REPORTE_<run_id>.md:

- Número de preguntas evaluadas / no evaluables
- Score promedio del juez (con advertencia: LLM ≠ verdad)
- Tasa de citas inventadas (verify_doc)
- Casos con revisión humana requerida (cantidad y resultado)
- Diferencias entre juez LLM y revisión humana
- Recomendaciones para mejorar el corpus (gaps de cobertura detectados)

---

## Reglas duras

1. No escribir preguntas capciosas para inflar o hundir scores
2. Verificar fuentes_esperadas contra chunks.jsonl ANTES de escribir
3. Diferenciar "no evaluable por falta de fuente" de "el sistema falla"
4. Toda discrepancia juez/humano se documenta
5. Los resultados del juez NO reemplazan el juicio jurídico humano

---

## Contacto técnico

Si el harness falla:
- run_benchmark.py: revisar uvicorn activo en el puerto 8000
- evaluate_v2.py: revisar OPENROUTER_API_KEY en ~/.csj_keys
- Reportar con run_id exacto y error completo

Si el sistema falla:
- certify_v1_1.py debe dar CERTIFIED
- sha256sum -c INTEGRITY.sha256 debe dar OK
- Si algo falla, NO ejecutar benchmark hasta restaurar
