"""Extractor de metadatos desde el encabezado de un DOCX CSJ.

No infiere: extrae del texto literal del documento.
Campos garantizables desde DOCX:
  - providencia  (regex AC\\d{4}-\\d{4} o SC\\d{4}-\\d{4})
  - radicado     (regex 5-2-2-3-4-5-2)
  - fecha        (regex DD/MM/YYYY o "veintisiete (27) de octubre de ...")
  - tipo         (AUTO / SENTENCIA — del propio texto)
  - sala         (SALA DE CASACIÓN ... / SALA PLENA — encabezado)
"""
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    parts = []
    for p in root.findall(".//w:p", NS):
        t = "".join(x.text or "" for x in p.findall(".//w:t", NS))
        if t.strip():
            parts.append(t.strip())
    return "\n".join(parts)


def extract(path):
    text = docx_text(path)
    head = text[:2000]  # solo el encabezado — sin inferencias sobre el cuerpo

    m_prov = re.search(r"\b([A-Z]{2}\d{4}-\d{4})\b", head)
    m_rad = re.search(r"\b(\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2})\b", head)
    m_fecha_iso = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", head)
    m_tipo = re.search(r"\b(AUTO|SENTENCIA)\b", head)
    m_sala = re.search(
        r"\b(SALA DE CASACI[ÓO]N [A-ZÁÉÍÓÚ]+|SALA PLENA)\b", head
    )

    return {
        "providencia": m_prov.group(1) if m_prov else None,
        "radicado": m_rad.group(1) if m_rad else None,
        "fecha": m_fecha_iso.group(1) if m_fecha_iso else None,
        "tipo": m_tipo.group(1) if m_tipo else None,
        "sala": m_sala.group(1) if m_sala else None,
        "text_length": len(text),
    }
