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

## Diagnóstico 2026-11-07 23:00 — Portal CSJ no soporta crawl masivo

**Diagnóstico ERRÓNEO previo**: se pensó que era soft-block por sesiones.
**Diagnóstico correcto**: el portal **funciona normalmente**, pero:

1. Devuelve **1 sola fila por página** (no configurable, paginator override rechazado con HTTP 500)
2. Para 2022 hay **30,198 documentos** totales (confirmado en HTML: `Resultado: 1 / 30198`)
3. Cada request AJAX tarda ~8s
4. Búsqueda por tema+año devuelve decenas de miles de resultados → imposible crawlear todos

**Cálculo del bloqueo**:
- Crawlear 37 penal 2022: paginar ~25,000 páginas × 8s = **55 horas por celda**
- 13 celdas pendientes del plan → **700+ horas (30 días sin parar)**

**Cómo se crawlearon los 202 docs originales**:
- No fue por búsqueda tema+año
- Fue por **`id_filter`** (búsqueda de ID específico, 1 doc por request directo, sin paginar)
- Acumulación de IDs durante semanas

**Modelo viable**:
- `crawl_by_ids.py` (por crear): busca IDs manualmente o desde semilla externa, crawlea por ID
- Ritmo realista: 20-50 docs/semana
- Objetivo 500 docs: **6-10 semanas**, no 5 días

**Cambios pendientes para crawler masivo** (si algún día el portal cambia):
1. `m062_crawler_byid.py`: `--max-pages` arg
2. `m062_crawler_byid.py`: default `--search-tema` de `"contrato"` → `""`
3. `scripts/crawl_500.py`: pasar `--search-tema ""` explícito, `--max-pages 20`
4. Filtro de sala server-side: investigar payload del navegador con DevTools (Opción C)

**Estado actual**: corpus 207 docs (212 con los 5 penales crawleados hoy), certificado 13/13, publicado con DOI. Aceptable para uso investigativo. Limitaciones documentadas honestamente.

## Fase B.1/B.2 — Descubierta 2026-11-08

- **re_embed_nvidia.py NO es incremental** cuando m063 regenera chunks
  - Checkpoint usa posiciones, no IDs
  - m063 cambia posiciones → checkpoint inválido → re-embed desde 0
  - Efecto: 12 docs nuevos → 45-90 min re-embed (era 5-10 min esperado)
  - Fix P2: checkpoint como dict {chunk_id: embedding}
  - Impacto: re-embeds futuros de 30 docs tomarán 40-60 min en vez de 5
