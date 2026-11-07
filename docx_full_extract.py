"""Extractor completo de DOCX CSJ.

Resuelve TODOS los tipos de contenido textual:
  - párrafos directos
  - tablas (con contenido de cada celda)
  - párrafos dentro de tablas
  - headers y footers (como apéndice)
  - endnotes
  - text boxes (w:txbxContent)
  - bold/italic restaurado sin asteriscos rotos

Orden preservado. Empty paragraphs colapsados. Cero omisiones.
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


# ---------- Runs y formato ----------
def _runs_raw(p):
    runs = []
    for r in p.findall("w:r", NS):
        rpr = r.find("w:rPr", NS)
        bold = italic = False
        if rpr is not None:
            bold = rpr.find("w:b", NS) is not None
            italic = rpr.find("w:i", NS) is not None
        text = "".join(t.text or "" for t in r.findall("w:t", NS))
        if text:
            runs.append((text, bold, italic))
    return runs


def _group_runs(runs):
    if not runs:
        return []
    merged = []
    cur_t, cur_b, cur_i = runs[0]
    for t, b, i in runs[1:]:
        if b == cur_b and i == cur_i:
            cur_t += t
        else:
            merged.append((cur_t, cur_b, cur_i))
            cur_t, cur_b, cur_i = t, b, i
    merged.append((cur_t, cur_b, cur_i))
    return merged


def _escape_stars(text):
    return text.replace("*", "\\*")


def _render_runs(runs):
    """Aplica bold/italic con espacios perimetrales movidos fuera."""
    escaped = [(_escape_stars(t), b, i) for t, b, i in runs]
    grouped = _group_runs(escaped)
    out = []
    for t, b, i in grouped:
        lead = len(t) - len(t.lstrip())
        trail = len(t) - len(t.rstrip())
        core = t.strip()
        if not core:
            out.append(t)
            continue
        prefix = " " * lead
        suffix = " " * trail
        if b and i:
            formatted = f"***{core}***"
        elif b:
            formatted = f"**{core}**"
        elif i:
            formatted = f"*{core}*"
        else:
            formatted = core
        out.append(f"{prefix}{formatted}{suffix}")
    return "".join(out)


def _plain(p):
    return "".join(t.text or "" for t in p.findall(".//w:t", NS)).strip()


def _style_level(p):
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        return None
    ps = ppr.find("w:pStyle", NS)
    if ps is None:
        return None
    style = ps.get(f"{{{W}}}val")
    if not style:
        return None
    if style == "Title":
        return 1
    if style.startswith("Heading"):
        d = re.findall(r"\d+", style)
        return min(int(d[0]), 6) if d else 2
    return None


def _whitelist_level(plain):
    key = re.sub(r"\s+", " ", plain).strip().rstrip(":").upper()
    return 2 if key in KNOWN_SECTIONS else None


# ---------- Bloques ----------
def _render_paragraph(p):
    runs = _runs_raw(p)
    plain = _plain(p)
    if not runs and not plain:
        return None
    level = _style_level(p) or _whitelist_level(plain)
    body = _render_runs(runs) if runs else _escape_stars(plain)

    # Text boxes dentro del párrafo: extracto al final con prefijo
    txbx_texts = []
    for txbx in p.findall(".//w:txbxContent", NS):
        t_plain = " ".join(
            _plain(pp) for pp in txbx.findall(".//w:p", NS) if _plain(pp)
        )
        if t_plain.strip():
            txbx_texts.append(_escape_stars(t_plain.strip()))

    if txbx_texts:
        body += "\n\n> [Texto flotante] " + " / ".join(txbx_texts)

    return {"level": level, "text": body.strip()}


def _render_table(tbl):
    """Renderiza una tabla DOCX como markdown."""
    rows = []
    for tr in tbl.findall(".//w:tr", NS):
        cells = []
        for tc in tr.findall(".//w:tc", NS):
            cell_parts = []
            for p in tc.findall(".//w:p", NS):
                ptext = _render_runs(_runs_raw(p))
                if ptext.strip():
                    cell_parts.append(ptext.strip())
            cells.append(" ".join(cell_parts))
        rows.append(cells)
    if not rows:
        return None
    # Markdown table
    ncols = max(len(r) for r in rows)
    padded = [r + [""] * (ncols - len(r)) for r in rows]
    header = "| " + " | ".join(padded[0]) + " |"
    sep = "|" + "|".join(["---"] * ncols) + "|"
    body = ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join([header, sep] + body)


def _iter_body_children(body):
    """Itera hijos de body preservando orden entre p y tbl."""
    for child in body:
        tag = child.tag.split("}")[-1]
        yield tag, child


# ---------- Foot/end/headers ----------
def _extract_notes(root_tag, z, key):
    try:
        root = ET.fromstring(z.read(f"word/{key}.xml"))
    except KeyError:
        return {}
    result = {}
    for fn in root.findall(f"w:{root_tag}", NS):
        fid = fn.get(f"{{{W}}}id")
        if not fid or fid in ("0", "-1"):
            continue
        text = " ".join(
            _plain(p) for p in fn.findall(".//w:p", NS) if _plain(p)
        )
        if text.strip():
            result[fid] = _escape_stars(text.strip())
    return result


def _extract_header_footer_text(z, kind):
    """kind: 'header' o 'footer'."""
    texts = []
    for name in z.namelist():
        if not name.startswith(f"word/{kind}"):
            continue
        if not name.endswith(".xml"):
            continue
        try:
            root = ET.fromstring(z.read(name))
        except Exception:
            continue
        content = " ".join(
            _plain(p) for p in root.findall(".//w:p", NS) if _plain(p)
        ).strip()
        if content and content not in texts:
            texts.append(content)
    return texts


# ---------- Extractor principal ----------
def extract_full(docx_path):
    """Devuelve dict con blocks, metadata de verificación y apéndices."""
    with zipfile.ZipFile(docx_path) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        footnotes = _extract_notes("footnote", z, "footnotes")
        endnotes = _extract_notes("endnote", z, "endnotes")
        headers = _extract_header_footer_text(z, "header")
        footers = _extract_header_footer_text(z, "footer")

    body = doc.find("w:body", NS)
    if body is None:
        return {"blocks": [], "stats": {}, "headers": [], "footers": [],
                "footnotes": {}, "endnotes": {}}

    blocks = []
    n_p = n_tbl = n_tbl_p = 0
    for tag, child in _iter_body_children(body):
        if tag == "p":
            b = _render_paragraph(child)
            n_p += 1
            if b:
                blocks.append(b)
        elif tag == "tbl":
            md_tbl = _render_table(child)
            n_tbl += 1
            n_tbl_p += len(child.findall(".//w:p", NS))
            if md_tbl:
                blocks.append({"level": None, "text": md_tbl})

    stats = {
        "paragraphs_direct": n_p,
        "tables": n_tbl,
        "table_paragraphs": n_tbl_p,
        "footnotes": len(footnotes),
        "endnotes": len(endnotes),
        "headers": len(headers),
        "footers": len(footers),
    }
    return {
        "blocks": blocks,
        "stats": stats,
        "headers": headers,
        "footers": footers,
        "footnotes": footnotes,
        "endnotes": endnotes,
    }
