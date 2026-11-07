# Deuda técnica conocida (v1.1.0)

## Datos
- Cobertura 202/32899 (0.6%) → crawl incremental semanal
- Topic hit@5 53% → clasificador desde contenido (no desde portal)
- 110 docs sin `fuente_formal` → extracción desde docx/pdf
- 8 docs sin `sala` → derivada por radicado, verificar manual
- 1 doc sin `tema` (AC6987-2026) → asignación manual
- 986442 tiene docx+pdf → duplicado intencional, documentado

## Evaluación
- Sin eval de alucinación LLM → ~50 preguntas gold-standard
- Sin benchmark alt embeddings → bge-m3, jina-v3
- Topic eval depende del portal → re-anotar 50 docs

## Infraestructura
- Sin Dockerfile → añadir Dockerfile + compose
- Sin deploy API → Fly.io / Railway
- CI no corre `certify_v1_1.py` → job nocturno con secret
- Sin rate limiting → slowapi
- Sin logging estructurado → structlog + JSON lines

## Portabilidad
- Termux `gh`/Go requiere `$PREFIX/etc/resolv.conf` → ver RECOVERY.md
- `git add` silencioso con paths inexistentes → patrón `[ -e ]`
- Release no atómico → `--draft` + upload uno a uno

## Prioridad sugerida
1. Cobertura (6 meses)
2. Clasificador `tema` (2 semanas)
3. Eval alucinación (1 semana)
4. Dockerfile + deploy API (2 días)

## Descubierto 2026-11-07 (auditoría v1.1.4)

| Deuda | Impacto | Estado |
| --- | --- | --- |
| ~~`stats.json` era de 3 docs~~ | API servía métricas falsas | ✅ Resuelto (regenerado) |
| ~~`year` ausente en manifest~~ | Bloqueaba estratificación | ✅ Resuelto (derivado de `providencia`) |
| README decía topic hit@5 = ~53% (real 72.34%) | Deshonestidad técnica | ✅ Resuelto (corregido) |
| `certify_v1_1.py` llamaba `pytest tests/ test_api.py` | Path inexistente tras mover `test_api.py` | ✅ Resuelto (1 línea) |
| `api_stats_version` compara `== "1.1.0"` hardcoded | Fallará en v1.2.0 | ⏳ Actualizar a `startswith("1.")` |
| Topic hit@5 medido solo sobre 141/202 docs (70%) | Falta cobertura en 61 docs sin `tema` | ⏳ Documentado en DATA_QUALITY |
| Disco al 98% (1.2 GB libres) | Bloquea crawl 500 | ⏳ Pendiente limpieza |

## Incidente 2026-11-07 22:10 — Portal CSJ soft-block

**Síntoma**: tras 6+ bootstraps JSF en 90 min (test 2024, test 2023,
intento crawl, 2 dry-runs, comparativa de 5 temas), el portal
comenzó a devolver **1 sola fila** para cualquier query, sin importar
tema o año. Sin 429, sin captcha, sin 403.

**Evidencia**:
- 21:00 (2024 penal, mismo código, misma IP): 368 filas
- 22:10 (2022, cualquier tema): 1 fila
- `casación` para 2022 completo devolviendo 1 fila es imposible

**Diagnóstico**: soft-block del portal por número de sesiones JSF
desde la misma IP en ventana corta. Degrada respuestas en lugar de
bloquear explícitamente.

**Fix inmediato**: NO tocar el portal 90-120 min. El contador
server-side debe decaer.

**Patches pendientes** (para el reintento):
1. `m062_crawler_byid.py`: `--max-pages` arg (hoy es `range(1, 10001)` fijo)
2. `m062_crawler_byid.py`: default `--search-tema` de `"contrato"` → `""`
3. `scripts/crawl_500.py`: `--delay 3.0`, `sleep 60` entre celdas,
   pasar `--search-tema ""` explícito y `--max-pages 20`
4. Rotación de User-Agent en `Session.__init__`

**Frecuencia máxima segura**: 1 sesión cada 5 min, 30 docs/celda máximo.
