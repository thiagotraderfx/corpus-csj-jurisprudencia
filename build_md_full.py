"""Regenera .md usando docx_full_extract (defensivo: no pierde tablas)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from docx_full_extract import extract_full, KNOWN_SECTIONS


def _yaml_scalar(v):
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def frontmatter(record, formats_available):
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


def build_md(record, docx_path, formats_available):
    fm = frontmatter(record, formats_available)
    result = extract_full(docx_path)
    title = record.get("providencia") or record.get("id") or "Sin título"

    parts = [fm, "", f"# {title}", ""]
    for block in result["blocks"]:
        if block["level"]:
            parts.append(f"{'#' * block['level']} {block['text']}")
        else:
            parts.append(block["text"])
        parts.append("")

    # Apéndices (headers/footers solo si aportan — no "Página X")
    header_meaningful = [
        h for h in result["headers"]
        if not re.fullmatch(r"p[áa]gina\s+\d+(\s+de\s+\d+)?", h, re.I)
        and not h.isdigit()
    ]
    if header_meaningful or result["footnotes"] or result["endnotes"]:
        parts.append("---")
        parts.append("")
        parts.append("## Anexos del documento")
        parts.append("")
        if header_meaningful:
            parts.append("**Encabezado (header):** " + " / ".join(header_meaningful))
            parts.append("")
        for i, (fid, txt) in enumerate(result["footnotes"].items(), 1):
            parts.append(f"[^{i}]: {txt}")
        for i, (eid, txt) in enumerate(result["endnotes"].items(), 1):
            parts.append(f"[^{i}]: {txt}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
