"""DOCX → Markdown plano con secciones canónicas.

Cambio v3: SIN formato inline (**/*). El texto de Word fragmenta runs,
mezcla bold con italic, incluye asteriscos literales y usa bold con
espacios perimetrales — todo eso produce Markdown inválido que ningún
renderer interpreta. Para un corpus jurídico, el bold no aporta valor
de búsqueda. Prioridad: Markdown válido > fidelidad tipográfica.

Se conserva:
  - Frontmatter YAML con metadatos
  - H1 = providencia
  - H2 = secciones canónicas de la lista blanca (promoción explícita)
  - Texto íntegro párrafo a párrafo
  - Notas al pie como [^N]

Se aplica un saneamiento final defensivo: cualquier `*` o `**` residual
del texto se escapa como \\* para evitar que se interprete como formato.
"""
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = NS["w"]

KNOWN_SECTIONS = {
    "ANTECEDENTES", "ANTECEDENTE",
    "CONSIDERACIONES", "CONSIDERACIONES Y FUNDAMENTOS",
    "FUNDAMENTOS", "FUNDAMENTOS DE LA DECISIÓN",
    "RESUELVE", "RESOLUCIÓN", "DECISIÓN", "DECIDE",
    "PROBLEMA JURÍDICO", "PROBLEMA JURÍDICO PLANTEADO",
    "CONSIDERACIONES DE LA CORTE", "LA CORTE CONSIDERA",
}


def _paragraph_text(p):
    """Texto plano concatenado de todos los w:t del párrafo."""
    parts = []
    for t in p.findall(".//w:t", NS):
        parts.append(t.text or "")
    return "".join(parts)


def _paragraph_style(p):
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        return None
    pstyle = ppr.find("w:pStyle", NS)
    return pstyle.get(f"{{{W}}}val") if pstyle is not None else None


def _style_to_level(style):
    if not style:
        return None
    if style == "Title":
        return 1
    if style.startswith("Heading"):
        digits = re.findall(r"\d+", style)
        return min(int(digits[0]), 6) if digits else 2
    return None


def _section_level(plain):
    key = re.sub(r"\s+", " ", plain).strip().rstrip(":").upper()
    return 2 if key in KNOWN_SECTIONS else None


def _extract_footnotes(z):
    try:
        root = ET.fromstring(z.read("word/footnotes.xml"))
    except KeyError:
        return {}
    result = {}
    for fn in root.findall("w:footnote", NS):
        fid = fn.get(f"{{{W}}}id")
        if not fid or fid in ("0", "-1"):
            continue
        text = " ".join(
            "".join(t.text or "" for t in p.findall(".//w:t", NS))
            for p in fn.findall("w:p", NS)
        ).strip()
        if text:
            result[fid] = text
    return result


def _escape_md_literal(text):
    """Escapa asteriscos residuales para que no se interpreten como formato.

    Mantiene intacto cualquier asterisco si el usuario los quiere en el
    render. Es defendible: el contenido literal del DOCX tenía `*`, y en
    Markdown eso requiere escape.
    """
    return text.replace("*", "\\*")


def docx_blocks(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        footnotes = _extract_footnotes(z)

    body = doc.find("w:body", NS)
    if body is None:
        return []

    fn_index = {fid: i + 1 for i, fid in enumerate(footnotes)}

    blocks = []
    for p in body.findall("w:p", NS):
        plain = _paragraph_text(p).strip()
        if not plain:
            continue

        style = _paragraph_style(p)
        level = _style_to_level(style)
        if level is None:
            level = _section_level(plain)

        # Recolectar footnotes en el párrafo (marcadores [^N])
        refs = [
            r.get(f"{{{W}}}id")
            for r in p.findall(".//w:footnoteReference", NS)
        ]
        marker = "".join(f"[^{fn_index.get(fid, '?')}]" for fid in refs if fid)

        # Saneamiento: escapar asteriscos literales del texto
        safe_text = _escape_md_literal(plain)
        if marker:
            safe_text += marker

        blocks.append({"level": level, "text": safe_text})

    if footnotes:
        blocks.append({"level": None, "text": "---"})
        blocks.append({"level": None, "text": "**Notas al pie**"})
        for fid, text in footnotes.items():
            idx = fn_index.get(fid, "?")
            blocks.append({
                "level": None,
                "text": f"[^{idx}]: {_escape_md_literal(text)}",
            })

    return blocks


def docx_to_markdown(docx_path):
    out = []
    for b in docx_blocks(docx_path):
        if b["level"]:
            out.append(f"{'#' * b['level']} {b['text']}")
        else:
            out.append(b["text"])
    return "\n\n".join(out).strip() + "\n"


def _yaml_scalar(v):
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def frontmatter(record, formats_available=None):
    keys = [
        "id", "providencia", "radicado", "fecha", "sala",
        "ponente", "tipo", "clase", "tema", "fuente_formal",
        "content_type", "size", "sha256",
    ]
    lines = ["---"]
    for k in keys:
        v = record.get(k)
        if v is None or v == "":
            continue
        lines.append(f"{k}: {_yaml_scalar(v)}")
    url = record.get("url_original") or record.get("source_url")
    if url:
        lines.append(f'source_url: "{url}"')
    if formats_available:
        fmt = ", ".join(f'"{f}"' for f in formats_available)
        lines.append(f"formats_available: [{fmt}]")
    lines.append("---")
    return "\n".join(lines)


def build_md(record, docx_path, formats_available=None):
    fm = frontmatter(record, formats_available)
    body = docx_to_markdown(docx_path)
    title = record.get("providencia") or record.get("id") or "Sin título"

    # Si el primer bloque ya es el título, omitirlo
    blocks = body.split("\n\n")
    if blocks:
        first_clean = re.sub(r"^[#\s]+", "", blocks[0]).strip()
        if first_clean == str(title).strip() or \
           first_clean.startswith(str(title).strip()):
            blocks = blocks[1:]

    return f"{fm}\n\n# {title}\n\n" + "\n\n".join(blocks).strip() + "\n"
