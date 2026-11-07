# Deuda técnica cerrada

## Fecha de cierre: 2026-11-06

### 1. Snapshot roto por archivos faltantes
- **Bug**: `tar czf ... failures.jsonl` fallaba si el archivo no existía
- **Fix**: placeholders creados al inicio (`touch`), tar incluye solo archivos existentes
- **Verificación**: snapshot extraído en /tmp y validado

### 2. Benchmark con metodología incorrecta
- **Deuda**: medía unicidad de metadata, no calidad de retrieval
- **Fix**: `benchmark_v2.py` con dos métodos:
  - `retrieval_sanity` (query = chunk del doc): mide identidad
  - `topic_retrieval` (query = tema único): mide cobertura, excluyendo duplicados
- **Verificación**: sanity debe ser ≥95%, topic ≥75%

### 3. Postproceso CJK integrado sin test
- **Deuda**: cambio en `rag_ask.py` sin prueba end-to-end
- **Fix**: `health_check.py` prueba `normalize_answer("【1】") → "[1]"`
- **Verificación**: check #9 del health

### 4. LLM `meta/llama-3.1-8b-instruct` retirado (410 Gone)
- **Bug**: modelo hardcodeado que ya no existe
- **Fix**: `get_available_models()` consulta `/v1/models` y filtra
- **Verificación**: check #8 del health

### 5. Headers/footers de DOCX no extraídos
- **No es bug**, es decisión de diseño
- **Justificación**: contienen radicado (redundante con metadatos) y "Página N" (no texto jurídico)
- **Estado**: `docx_full_extract.py` los detecta pero `build_md_full.py` solo los incluye si son semánticamente significativos

### 6. Duplicación de metadata en tutelas
- **No es bug**, es característica del corpus CSJ
- **Impacto**: retrieval por tema no puede distinguir 5+ tutelas con tema idéntico
- **Mitigación**: `benchmark_v2.py` excluye temas duplicados del test de topic retrieval
- **Uso real**: queries del usuario contienen detalles específicos, no solo el tema genérico

## Criterio de salud

El sistema se considera SANO si:
- `health_check.py` retorna exit 0
- `benchmark_v2.py` pasa ambos tests
- Snapshot se extrae y valida en directorio limpio

## Siguiente decisión

Una vez `health_check.py` OK:
- Si `retrieval_sanity ≥ 95%` y `topic_retrieval ≥ 75%`: escalar a 500-1000 docs
- Si no: investigar antes de escalar
