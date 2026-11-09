# Benchmark de calidad — Corpus CSJ

Infraestructura para evaluar la calidad de las respuestas del sistema
con la participación de un abogado humano.

## Para el abogado

### Paso 1 — Escribir preguntas

Copiar la plantilla y editar:

    cp benchmark/data/preguntas_template.jsonl benchmark/data/preguntas.jsonl

Editar `benchmark/data/preguntas.jsonl` con 50 preguntas cubriendo:
- Tutela contra providencia (15)
- Casación civil (15)
- Casación laboral (10)
- Casación penal (10)

Criterios:
- Respondibles con el corpus actual (321 docs, 2021-2026)
- Respuesta verificable en las providencias
- Jurídicamente sustantivas (no metadata)
- Respuesta esperada concisa (2-4 oraciones)

### Paso 2 — Ejecutar

Terminal 1:
    uvicorn api:app --host 127.0.0.1 --port 8000

Terminal 2:
    python3 benchmark/run_benchmark.py

Genera `benchmark/results/respuestas_YYYYMMDD_HHMMSS.jsonl`.

### Paso 3 — Evaluar

    python3 benchmark/evaluate.py

Genera `benchmark/results/evaluacion_YYYYMMDD_HHMMSS.json` con métricas objetivas.

### Paso 4 — Revisión humana

El abogado revisa el reporte y ajusta clasificaciones.

## Métricas

- Precisión jurídica (LLM-as-judge 1-5): pendiente fase siguiente
- Citas verificadas (% verified=True): disponible hoy
- Cobertura (% no refused): disponible hoy
- Latencia avg y p95: disponible hoy

## Estado

- Infraestructura: lista
- Preguntas escritas: pendiente (requiere abogado)
- Ejecución: pendiente
- Revisión: pendiente
