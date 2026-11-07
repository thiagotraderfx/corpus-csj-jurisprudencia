"""Parser de filas de la tabla de resultados CSJ.

Resuelve entidades HTML (&Uacute;, &Oacute;) y estructura <br>-separada.
"""
import html as html_module
import re

FIELDS = [
    "ID",
    "NÚMERO DE PROCESO",
    "NÚMERO DE PROVIDENCIA",
    "CLASE DE ACTUACIÓN",
    "TIPO DE PROVIDENCIA",
    "FECHA",
    "PONENTE",
    "TEMA",
    "FUENTE FORMAL",
]


def _normalize(inner_html):
    with_breaks = re.sub(r"<br\s*/?>", "\n", inner_html, flags=re.I)
    unescaped = html_module.unescape(with_breaks)
    plain = re.sub(r"<[^>]+>", "", unescaped)
    return [ln.strip() for ln in plain.split("\n") if ln.strip()]


def parse_descrip(inner_html):
    lines = _normalize(inner_html)
    result = {
        "sala": None,
        "id": None,
        "radicado": None,
        "providencia": None,
        "clase": None,
        "tipo": None,
        "fecha": None,
        "ponente": None,
        "tema": None,
        "fuente_formal": None,
    }
    if not lines:
        return result

    if lines[0].startswith("SALA"):
        result["sala"] = lines[0]
        lines = lines[1:]

    LABEL_MAP = {
        "ID": "id",
        "NÚMERO DE PROCESO": "radicado",
        "NÚMERO DE PROVIDENCIA": "providencia",
        "CLASE DE ACTUACIÓN": "clase",
        "TIPO DE PROVIDENCIA": "tipo",
        "FECHA": "fecha",
        "PONENTE": "ponente",
        "TEMA": "tema",
        "FUENTE FORMAL": "fuente_formal",
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        matched = False
        for label, key in LABEL_MAP.items():
            prefix = label + ":"
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if key == "tema":
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]
                        if any(next_line.startswith(l + ":") for l in LABEL_MAP):
                            break
                        value += " " + next_line
                        j += 1
                    i = j
                else:
                    i += 1
                result[key] = value.strip() or None
                matched = True
                break
        if not matched:
            i += 1
    return result


def parse_rows(table_html):
    rows = []
    for rk_match in re.finditer(
        r'<tr\b[^>]*data-rk=["\'](\d+)["\'][^>]*>',
        table_html,
    ):
        rk = rk_match.group(1)
        remainder = table_html[rk_match.end():]
        dm = re.search(
            r'id=["\']resultForm:jurisTable:\d+:descrip["\'][^>]*>(.*?)</span>',
            remainder,
            re.DOTALL,
        )
        if not dm:
            continue
        fields = parse_descrip(dm.group(1))
        fields["row_key"] = rk
        rows.append(fields)
    return rows
