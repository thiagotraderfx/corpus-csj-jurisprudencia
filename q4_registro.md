# Q4 — Registro de Cotejo con la Relatoría de la CSJ

**Fecha de cotejo:** _____________________
**Abogado:** _____________________________
**T.P.:** ________________________________
**URL Relatoría:** https://consultajurisprudencial.ramajudicial.gov.co/

---

## Instrucciones

Para cada caso:
1. Abrir la Relatoría en el navegador
2. Buscar por el identificador de la providencia
3. Anotar los datos oficiales
4. Marcar la decisión: Aceptado / Aceptado con nota / Rechazado
5. Anotar observaciones si no es Aceptado

---

## Tabla de 10 casos

| # | Providencia | Grupo | Fecha corpus | Fecha Relatoría | Radicado corpus | Radicado Relatoría | Sala | Tipo | Decisión | Notas |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | STP17662-2024 | A | 2024-12-10 | | T 141675 | | | | | |
| 2 | SL913-2026 | A | 2026-07-29 | | 05045310500220210029401 | | | | | |
| 3 | SL3434-2024 | B | 2024-12-16 | | 97084 | | | | | |
| 4 | STC16024-2024 | B | 2024-11-28 | | T 1500122130002024-00192-01 | | | | | |
| 5 | STC16132-2022 | B | 2022-12-01 | | T 1100122030002022-02323-01 | | | | | |
| 6 | SC056-2026 | B | 2026-04-23 | | 7652-03-10-30-04-2016-00170-01 | | | | | |
| 7 | SC3972-2022 | C | 2022-12-15 | | 11001-31-03-035-2019-00014-01 | | | | | |
| 8 | STC16508-2022 | C | 2022-12-14 | | T 0500122130002022-00659-01 | | | | | |
| 9 | STL15987-2022 | C | 2022-12-07 | | T 100493 | | | | | |
| 10 | STP21582-2025 | D | 2024-12-16 | | T 151342 | | | | | |

---

## Notas específicas por caso

### 1. STP17662-2024 (Grupo A — errata en el documento)

El párrafo 5 del encabezado dice literalmente:
> `Bogotá, D.C., diez (10) de diez de dos mil veinticuatro (2024).`

El mes está escrito como **"diez"** (palabra) en lugar del nombre del mes. El manifest dice 2024-12-10 (diciembre), pero el DOCX no dice "diciembre" en ninguna parte.

**Al cotejar:** confirmar en la Relatoría cuál es la fecha oficial. Si es 2024-12-10, el manifest está bien y el DOCX tiene una errata de redacción.

---

### 2. SL913-2026 (Grupo A — fecha sí extraíble, parser no la vio)

El párrafo 5 del encabezado dice:
> `Nuquí, Chocó, veintinueve (29) de julio de dos mil veintiséis (2026)`

La fecha es perfectamente legible: 29 de julio de 2026, **coincide con el manifest**. El parser buscaba solo párrafos que empiezan con "Bogotá", por eso no la extrajo.

**Al cotejar:** confirmar en la Relatoría. Si coincide (esperado), este caso puede pasar a Q2 directamente sin observación.

---

### 3. SL3434-2024 (Grupo B — fecha discrepante)

- Manifest: 2024-12-16
- DOCX (Bogotá): 2024-12-10
- Diferencia: 6 días, manifest posterior

**Al cotejar:** verificar cuál fecha publica la CSJ. Es probable que el manifest tenga la fecha de publicación y el DOCX la de sesión/firma.

---

### 4. STC16024-2024 (Grupo B — fecha discrepante)

- Manifest: 2024-11-28
- DOCX (Bogotá): 2024-11-24
- Diferencia: 4 días, manifest posterior

**Al cotejar:** igual que el caso 3.

---

### 5. STC16132-2022 (Grupo B — fecha discrepante)

- Manifest: 2022-12-01
- DOCX (Bogotá): 2022-12-02
- Diferencia: 1 día, manifest anterior

**Al cotejar:** verificar cuál es la oficial.

---

### 6. SC056-2026 (Grupo B — Bogotá vs sesión)

- Manifest: 2026-04-23 (Bogotá)
- DOCX (sesión): 2026-01-29
- Diferencia: 84 días

**Al cotejar:** lo más probable es que la fecha oficial sea la de Bogotá (2026-04-23), y el 29 de enero sea la fecha de sesión de aprobación. Confirmar.

---

### 7. SC3972-2022 (Grupo C — radicado discrepante)

- Manifest: `11001-31-03-035-2019-00014-01`
- DOCX: `11001-31-03-035-2019-00014-00`
- Diferencia: termina en `01` vs `00`

**Al cotejar:** el sufijo `-00` suele ser el proceso de primera instancia, `-01` de segunda. Verificar cuál publica la Relatoría como radicado principal.

---

### 8. STC16508-2022 (Grupo C — radicado discrepante)

- Manifest: `T 0500122130002022-00659-01` (tutela 2022)
- DOCX: `0500140030112019109100` (proceso civil 2019)

**Al cotejar:** el DOCX muestra el proceso de origen (2019), no la tutela (2022). Confirmar cuál publica la Relatoría.

---

### 9. STL15987-2022 (Grupo C — radicado discrepante)

- Manifest: `T 100493` (número interno CSJ)
- DOCX: `11001310301920210005101` (radicado completo)

**Al cotejar:** el manifest tiene el número interno del despacho, el DOCX el radicado completo del proceso. Confirmar cuál usa la Relatoría.

---

### 10. STP21582-2025 (Grupo D — contradicción interna)

El encabezado dice 16/12/2024, pero el cuerpo menciona:
- Fallo de tutela: 13 de agosto de 2025
- Confirmación de Tribunal: 28 de enero de 2025
- Reparto al despacho: acta del 10 de diciembre de 2025

**La fecha del encabezado (2024) es ANTERIOR a hechos que el propio documento narra (2025).**

**Al cotejar:** confirmar en la Relatoría la fecha real. Si la Relatoría dice 2025, el DOCX tiene errata en el encabezado. Si dice 2024, hay un problema mayor con el cuerpo del DOCX.

---

## Resumen final

| Decisión | Cantidad |
|---|---|
| Aceptado | _____ |
| Aceptado con nota | _____ |
| Rechazado | _____ |
| **Total** | **10** |

---

## Firma del abogado

Firma: ______________________________

Nombre: _____________________________

T.P.: _______________________________

Fecha: ______________________________

