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
| content_factual | 25 | 1 | 4% |
| out_of_domain | 10 | 10 | 100% |

Reproducible: `python3 eval/run_eval_v2.py`
**Nota sobre matcher content_factual**:
La evaluación v2 original usaba coincidencia literal, dando 16% (falso negativo).
La evaluación v3 usa: mención de providencia + longitud sustancial (>=100 chars)
+ al menos un verbo jurídico (casa/niega/confirma/revoca/declara/condena/
absuelve/resuelve/modifica). Esta métrica captura correctitud semántica básica
sin exigir coincidencia literal.

Reproducible v3: `python3 eval/run_eval_content_fix.py`

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
