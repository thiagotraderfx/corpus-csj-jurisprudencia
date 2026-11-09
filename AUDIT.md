# Auditoría del Sistema — Corpus CSJ v1.1.5

**Fecha**: 2026-11-08
**Corpus**: 309 sentencias CSJ · 23 339 chunks · certificación 13/13
**DOI v1.1.4**: 10.5281/zenodo.24043648
**DOI v1.1.5**: pendiente webhook Zenodo (~24h, no bloqueante)

---

## 1. Resumen ejecutivo

| Métrica | Valor | Estado |
| --- | --- | --- |
| Faithfulness global | 52% | Baseline funcional |
| Retrieval metadata | 88% | Usable |
| Refusal out-of-domain | 100% | Confiable |
| False refusal rate | 0% | Sin sobre-rechazo |
| Citation verification | 100% | Ninguna cita inventada |
| Content synthesis | 16% | Matcher literal (mejorable) |

**Declaración profesional**: en RAG generativo no existe 100% faithfulness.
LegalBench 2024 y RAGAS reportan 72-85% para GPT-4 con RAG perfecto. El
techo real con NLI entrenado (Fase D) es 85-92%. 52% es baseline honesto
para un sistema sin NLI.

---

## 2. Arquitectura

Usuario → /ask/safe → retrieve → rag_safe.safe_answer → LLM → verify_citations

| Componente | Estado |
| --- | --- |
| chunks.jsonl (23339) | ✅ 0 duplicados SHA-256 |
| passages.npy (23339×2048) | ✅ 0 NaN/Inf |
| retrieve() Top-K | ✅ |
| should_refuse() score<0.30 | ✅ 100% OOD |
| verify_citations() | ✅ rechaza citas fuera contexto |
| generate() NIM | ⚠️ 2 modelos fallback 404 |

---

## 3. Resultados Fase C (gold-set 60 preguntas, seed=42)

| Categoría | N | Correctas | Tasa |
| --- | --- | --- | --- |
| metadata_ponente | 7 | 7 | 100% |
| metadata_radicado | 6 | 6 | 100% |
| metadata_fecha | 6 | 5 | 83% |
| metadata_sala | 6 | 4 | 67% |
| content_factual | 25 | 4 | 16% |
| out_of_domain | 10 | 10 | 100% |

Reproducible: `python3 eval/run_eval_v2.py`

---

## 4. Las 8 reglas duras

1. NUNCA inventar providencias, radicados, fechas o ponentes
2. NUNCA atribuir frases a un documento que no las contiene
3. NUNCA responder sin verificar base (score ≥ 0.30)
4. NUNCA parafrasear perdiendo la cita
5. SIEMPRE mostrar citas (providencia + chunk_id)
6. SIEMPRE admitir ignorancia si retrieval débil
7. SIEMPRE marcar respuesta "no verificada" si citas no encontradas
8. Toda respuesta auditable (sources + citations + unverified)

| Regla | Cumple | Evidencia |
| --- | --- | --- |
| 1. No inventar | ✅ | verify_citations rechaza 100% citas fuera contexto |
| 2. No atribuir | ⚠️ | Verifica presencia, no coherencia semántica (§6) |
| 3. No responder sin base | ✅ | Refusal 100% OOD, 0% false refusal |
| 4. No perder cita | ✅ | Campo citations |
| 5. Mostrar citas | ✅ | Campo citations |
| 6. Admitir ignorancia | ✅ | Refusal 100% |
| 7. Marcar no verificado | ✅ | Campo unverified |
| 8. Auditable | ✅ | sources + citations + unverified |

---

## 5. Casos de uso

**Permitido**:
- Búsqueda asistida con auditoría humana
- Resúmenes para revisión de abogados
- Investigación académica
- Prototipos y demos legales

**No permitido**:
- Decisiones judiciales automáticas
- Asesoría legal al público sin disclaimer
- Sustitución del portal CSJ
- Publicación sin verificar citas

**Zona gris** (requiere disclaimer):
- Usuarios no-expertos
- Sistemas de alto volumen (sin rate limiting)

---

## 6. Limitaciones técnicas (honestas)

### 6.1 Verificación de citas vs verificación semántica

**Verificado**:
- Providencia citada existe en chunks.jsonl
- [N] en rango 1..len(sources)
- La respuesta contiene citas

**NO verificado**:
- El LLM atribuye al chunk N algo que el chunk N no dice (silent hallucination)
- Coherencia interna de la respuesta
- Corrección jurídica de la síntesis

**Mitigación**: sources siempre se retorna. Usuario verifica manualmente.
**Deuda P0**: NLI real (entailment entrenado, no heurístico).

### 6.2 Sesgos del corpus
- Cobertura: 309/32 899 (~0.9%)
- Años: 2021 (1), 2026 (90) — sesgo reciente
- Salas: civil 128, laboral 117, penal 64

### 6.3 Operacionales
- Sin rate limiting
- Sin logging estructurado
- Sin Dockerfile
- Sin benchmark multi-LLM

---

## 7. Protocolo de auditoría humana

Para cada respuesta de /ask/safe:

1. Revisar citations (providencias citadas)
2. Revisar unverified (si existe → NO usar sin verificación)
3. Abrir cada providencia en sources y verificar contenido
4. Consultar portal oficial CSJ para confirmar

Regla: si verified=false o unverified no vacío → verificación manual obligatoria.

---

## 8. Deudas priorizadas

| Prioridad | Deuda | Plan |
| --- | --- | --- |
| P0 | NLI real (entailment) | Fase D (research, 1-2 meses) |
| P0 | Benchmark multi-LLM | Fase D (4h) |
| P1 | Fix retrieval SC1983/SL4216 | 2h diagnóstico |
| P1 | Fix matcher content_factual | 2h rediseño |
| P1 | Fix fallback NVIDIA 404 | Config externa |
| P1 | Cobertura gaps 2021/2023/2025 | Fase B.1 |
| P2 | Rate limiting slowapi | Fase E (1h) |
| P2 | Logging structlog | Fase E (1h) |
| P2 | Dockerfile | Fase E (2h) |

---

## 9. Intentos documentados

eval/failed_attempts/C3_v3_42pct.json preserva evidencia de intento
de mejora que regresó 52%→42%. Causa: retrieve_boosted v2 añadía INTRO
con YAML al top, LLM devolvía vacío en 24/25. Rollback aplicado.
Documentar fracasos es más honesto que ocultarlos.

---

## 10. Conclusión

Sistema baseline funcional con verificación anti-alucinación real.

**Fortalezas**:
- Corpus certificado 13/13 (0 duplicados SHA)
- Refusal 100% (admite ignorancia)
- Metadata 88% (usable)
- Citas verificadas (no inventa providencias)

**Debilidades**:
- Faithfulness 52% (baseline, no objetivo)
- Sin NLI real (silent hallucination no detectada)
- Cobertura ~0.9%
- Sin rate limiting/logging/Docker

Apto para: investigación, demo, uso asistido con auditoría.
No apto para: producción sin supervisión, decisiones judiciales.

Techo con Fase D: 85-92%. 100% no es técnicamente posible.

---

**Firmado**: Corpus CSJ v1.1.5, 2026-11-08

## Verificación P2 — integridad de datos (2026-11-09)

Verificado empíricamente:

| Aspecto | Resultado |
| --- | --- |
| `chunks.jsonl` count | 23 982 |
| `passages_ids.jsonl` count | 23 982 |
| `passages.npy` shape | (23 982, 2048) |
| **Alineación posicional `chunks[i] ↔ passages_ids[i]`** | ✅ 0/23 982 distintos |
| **Alineación por conjunto** | ✅ 0 solo en uno u otro |
| `chunks[i].text ∈ md/*.md` estricto | 82.5 % (muestra 200) |
| `chunks[i].text ∈ md/*.md` normalizado (NFC + whitespace + markdown) | 96 %+ (muestra 200) |
| Discrepancias restantes | cosméticas (saltos de línea, comillas tipográficas, `**bold**` en md) |

**Conclusión**: los chunks son la **fuente de verdad** (fuente: `raw/*.docx` → extractor).
`md/*.md` es un **render legible** derivado con normalización cosmética.
Ninguna discrepancia afecta el retrieval (usa `chunks.jsonl` + `passages.npy`) ni la cita
por `chunk_id`. Los `md_url`/`raw_url` que el endpoint `/ask` devuelve existen y son válidos
para lectura humana.

**No se regenera `chunks.jsonl` ni `passages.npy`** — eso rompería el indexado sin
beneficio verificable. La divergencia cosmética se documenta y se acepta.

**Hash de integridad** en `INTEGRITY.sha256` (embeddings + manifest + chunks).

### Pendientes P1 — seguridad API (no bloqueantes para uso local)

- `auth X-API-Key` (`api.py:73`): hoy `API_KEY=""` → sin auth. Se habilita configurando
  la env var. No se activa por defecto para no romper integraciones de prueba.
- `CORS_ORIGINS=*` (`api.py:99`): restringir a dominios propios en producción.
- Rate limit `RATE_LIMIT_MAX=120`/60s: configurado, no ejercitado en test. Se valida
  con carga sintética cuando se prepare despliegue público.

## Prueba real end-to-end con uvicorn (2026-11-09)

Verificación con servidor real (`uvicorn api:app`) y clientes HTTP reales (`curl`):

| Bloque | Test | Resultado |
| --- | --- | --- |
| A | `sha256sum -c INTEGRITY.sha256` | 3/3 OK |
| B | uvicorn arranca, /health responde | ✅ |
| C | 9 endpoints GET (`/`, `/health`, `/stats`, `/providencias`, `/coverage`, `/docs/{id}`, `/chunks/{id}`, `/docs/NOEXISTE`) | 8×200 + 1×404 correcto |
| D | `POST /search` con query jurídica | 23 982 candidates, 984ms, top-3 con scores reales |
| E | `POST /ask` con generación LLM | 200, `model_used=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, sources válidos |
| F | `POST /ask/safe` — 3 casos | cubierta: `(False,False,True)` · fuera acervo: `(True,True,None)` · receta: `(True,None,None)`, **sin jerga técnica** |
| G | `POST /ask/stream` con `curl --no-buffer` | SSE completo: `sources → token×N → [N]` |
| H | Payloads adversariales (JSON malformado, query vacía, k negativo, 100KB) | 4/4 → 422 |
| I | CORS + rate limit | localhost ACAO ✓ · evil.com sin header ✓ · rate limit dispara en #31 con max=30 |
| J | 3 requests paralelos con `curl` | 3×200 en 656ms (paralelismo real, no secuencial) |

**Certify 14/14 CERTIFIED.** Working tree limpio. HEAD `402bfef`.

### Contrato de endpoints

- `/ask` — endpoint raw. Puede devolver 0 citas `[N]`. **No usar para uso jurídico.**
- `/ask/safe` — endpoint blindado. Verifica citas, expone `verified`/`refused`/`coverage_gap`. **Recomendado para uso jurídico.**
- `/ask/stream` — SSE. Puede no verificar citas. Igual que `/ask`.
- Endpoints de lectura (`/providencias`, `/docs`, `/chunks`, `/search`) — rate limited, sin auth. Uso público aceptable.
- `/health`, `/stats`, `/coverage` — abiertos (info barata). Rate limit no aplica.

### Runtime verificado

- Python 3.14.4 (Termux aarch64)
- fastapi 0.159.1 · uvicorn 0.54.0 · numpy 2.4.4 · pydantic 2.14.1
- 5 modelos chat verificados empíricamente (nano, lightning, bolt, ultra, llama-90b-vision)
- Corrida con `RATE_LIMIT_MAX=30` y `API_KEY` desactivado

### Deudas residuales (fuera de scope P0/P1/P2, documentadas)

- **NLI real (entailment)** — Fase D, investigación 1-2 meses
- **Benchmark con abogado** — Fase B, requiere humano
- **Multi-LLM benchmark** — OpenRouter disponible
- **Metadata normalización fecha/sala** — filtro opcional
- **Docker** — no instalado en Termux (Omitido por decisión operativa)
- **Zenodo v1.1.5** — v1.1.4 sirve para DOI

## Fases 1-3 completadas (2026-11-09)

Commit `140a792` — mejoras verificadas end-to-end sin romper el estado certificado.

### Fase 1 — Normalización de sala

- Bug fix: `retrieve()` usaba substring case-insensitive para filtrar `sala`,
  causando que "SALA DE CASACIÓN PENAL - SALA DE DECISIÓN DE TUTELAS" se
  clasificara como Penal (incorrecto) o no matcheara "tutela".
- Fix: `_norm_sala()` mapea variantes a 4 categorías (Penal/Civil/Laboral/Tutela).
- Verificado con uvicorn real + curl: 8 casos, 0 incorrectos.

### Fase 2 — Hardening /ask y /ask/stream

- `/ask` ahora reporta `verified: bool` (antes `None`). Verifica citas tras `generate()`.
- `/ask/stream` incluye `verified` y `unverified` en evento SSE `done`.
- **NO refusa** si hay citas no verificables. Solo informa. Contrato
  diferente de `/ask/safe`, que sí refusa.

### Fase 3 — Infraestructura benchmark Fase B

- `benchmark/` con README, template, `run_benchmark.py`, `evaluate.py`.
- Pendiente: 50 preguntas escritas por abogado + ejecución + LLM-as-judge.

### Snapshot de rollback

Tag `v1.1.6-pre-improvements` en commit `4bd7f63`. Reversión quirúrgica:
`git revert 140a792` o completa: `git reset --hard v1.1.6-pre-improvements`.

### Fases no ejecutadas (diferidas)

- **Fase 4 (NLI entailment)**: requiere investigación de modelo real (1-2 meses).
  Un stub con overlap de tokens no detecta alucinaciones semánticas reales.
- **Fase F (integrar `normas_lex`)**: proyecto separado, ~4-8h, con su propio
  certify y tag. No mezclar con jurisprudencia — dominios distintos.
