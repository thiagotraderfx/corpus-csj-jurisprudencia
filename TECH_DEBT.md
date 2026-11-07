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
