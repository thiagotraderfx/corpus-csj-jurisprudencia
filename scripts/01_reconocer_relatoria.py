#!/usr/bin/env python3

import json
import re
import ssl
import sys
import hashlib

from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]

URL = (
    "https://consultajurisprudencial.ramajudicial.gov.co"
    "/WebRelatoria/csj/index.xhtml"
)

ROBOTS_URL = (
    "https://consultajurisprudencial.ramajudicial.gov.co/robots.txt"
)

TIMEOUT = 40


class PortalInspector(HTMLParser):

    def __init__(self):
        super().__init__()

        self.forms = []
        self.inputs = []
        self.selects = []
        self.buttons = []
        self.links = []
        self.scripts = []

        self.current_form = None
        self.current_select = None

    def handle_starttag(self, tag, attrs):

        a = dict(attrs)

        if tag == "form":

            self.current_form = {
                "id": a.get("id"),
                "name": a.get("name"),
                "action": a.get("action"),
                "method": a.get("method"),
                "enctype": a.get("enctype")
            }

            self.forms.append(self.current_form)

        elif tag == "input":

            item = {
                "type": a.get("type"),
                "id": a.get("id"),
                "name": a.get("name"),
                "value": a.get("value")
            }

            # No almacenar tokens de sesión.
            if item["name"] and "viewstate" in item["name"].lower():
                item["value"] = "[REDACTADO]"

            self.inputs.append(item)

        elif tag == "select":

            self.current_select = {
                "id": a.get("id"),
                "name": a.get("name"),
                "options": []
            }

            self.selects.append(self.current_select)

        elif tag == "option" and self.current_select is not None:

            self.current_select["options"].append({
                "value": a.get("value"),
                "selected": "selected" in a
            })

        elif tag == "button":

            self.buttons.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "type": a.get("type")
            })

        elif tag == "a":

            self.links.append({
                "href": a.get("href"),
                "title": a.get("title")
            })

        elif tag == "script":

            if a.get("src"):
                self.scripts.append(a["src"])

    def handle_endtag(self, tag):

        if tag == "form":
            self.current_form = None

        elif tag == "select":
            self.current_select = None


def fetch(url):

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 15) "
                "AppleWebKit/537.36 "
                "Chrome/131.0 Mobile Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            )
        }
    )

    context = ssl.create_default_context()

    with urlopen(
        request,
        timeout=TIMEOUT,
        context=context
    ) as response:

        body = response.read()

        return {
            "status": response.status,
            "headers": dict(response.headers.items()),
            "body": body,
            "final_url": response.geturl()
        }


def inspect():

    print("=" * 80)
    print("CORPUS CORTE SUPREMA")
    print("MÓDULO 01 — RECONOCIMIENTO DE RELATORÍA")
    print("=" * 80)

    result = {
        "project": "corpus_corte_suprema",
        "source": URL,
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "started",
        "findings": {},
        "errors": []
    }

    print("\n[1] CONEXIÓN CON LA FUENTE OFICIAL")

    try:

        response = fetch(URL)

    except Exception as exc:

        result["status"] = "connection_error"
        result["errors"].append(str(exc))

        print("[ERROR]", exc)

        save_report(result)
        return 2

    body = response["body"]

    charset = "utf-8"

    content_type = response["headers"].get(
        "Content-Type", ""
    )

    match = re.search(
        r"charset=([\w-]+)",
        content_type,
        re.I
    )

    if match:
        charset = match.group(1)

    html = body.decode(
        charset,
        errors="replace"
    )

    print("HTTP:", response["status"])
    print("Content-Type:", content_type)
    print("Bytes:", len(body))
    print("URL final:", response["final_url"])

    print("\n[2] HUELLA DE RESPUESTA")

    result["findings"]["http"] = {
        "status": response["status"],
        "content_type": content_type,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "final_url": response["final_url"]
    }

    print(
        "SHA256:",
        result["findings"]["http"]["sha256"]
    )

    print("\n[3] TECNOLOGÍAS DETECTADAS")

    technologies = {}

    patterns = {
        "JSF ViewState": r"javax\.faces\.ViewState",
        "Jakarta Faces": r"jakarta\.faces",
        "PrimeFaces": r"PrimeFaces",
        "Faces AJAX": r"faces\.ajax",
        "Partial Execute": r"javax\.faces\.partial\.execute",
        "Partial Render": r"javax\.faces\.partial\.render",
        "RichFaces": r"RichFaces",
        "OmniFaces": r"omnifaces",
        "XMLHttpRequest": r"XMLHttpRequest"
    }

    for name, pattern in patterns.items():

        count = len(
            re.findall(pattern, html, re.I)
        )

        technologies[name] = count

        print(f"{name}: {count}")

    result["findings"]["technologies"] = technologies

    print("\n[4] ESTRUCTURA DE FORMULARIOS")

    parser = PortalInspector()
    parser.feed(html)

    result["findings"]["forms"] = parser.forms

    for form in parser.forms:
        print(form)

    print("\n[5] CAMPOS DE ENTRADA")

    result["findings"]["inputs"] = parser.inputs

    for item in parser.inputs:
        print(item)

    print("\n[6] SELECTORES")

    result["findings"]["selects"] = parser.selects

    for item in parser.selects:

        print({
            "id": item["id"],
            "name": item["name"],
            "options_count": len(item["options"]),
            "options_sample": item["options"][:10]
        })

    print("\n[7] BOTONES")

    result["findings"]["buttons"] = parser.buttons

    for item in parser.buttons:
        print(item)

    print("\n[8] ENLACES")

    relevant_links = []

    for link in parser.links:

        href = link.get("href") or ""

        if any(
            term in href.lower()
            for term in (
                "descarga",
                "download",
                "document",
                "providencia",
                "sentencia",
                ".pdf",
                ".doc"
            )
        ):

            relevant_links.append({
                "href": urljoin(URL, href),
                "title": link.get("title")
            })

    result["findings"]["relevant_links"] = relevant_links

    for item in relevant_links[:30]:
        print(item)

    print("\n[9] JAVASCRIPT EXTERNO")

    scripts = [
        urljoin(URL, script)
        for script in parser.scripts
    ]

    result["findings"]["scripts"] = scripts

    for script in scripts:
        print(script)

    print("\n[10] INDICADORES DE AJAX Y ENDPOINTS")

    patterns = [
        r"PrimeFaces\.ab\s*\([^;]{0,800}",
        r"faces\.ajax\.request\s*\([^;]{0,800}",
        r"XMLHttpRequest",
        r"\.xhtml(?:\?[^'\"\s]*)?",
        r"javax\.faces\.partial\.execute",
        r"javax\.faces\.partial\.render"
    ]

    ajax = {}

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            re.I
        )

        ajax[pattern] = matches[:10]

        print("\n", pattern, ":", len(matches))

        for item in matches[:10]:
            print(" ", item[:500])

    result["findings"]["ajax"] = ajax

    print("\n[11] VIEWSTATE")

    viewstates = re.findall(
        r'<input[^>]+(?:javax\.faces\.ViewState|ViewState)[^>]*>',
        html,
        re.I
    )

    # Nunca conservar el contenido del token.
    result["findings"]["viewstate"] = {
        "present": bool(viewstates),
        "count": len(viewstates)
    }

    print("Presente:", bool(viewstates))
    print("Cantidad:", len(viewstates))

    print("\n[12] ROBOTS.TXT")

    try:

        robots = fetch(ROBOTS_URL)

        robots_text = robots["body"].decode(
            "utf-8",
            errors="replace"
        )

        result["findings"]["robots"] = {
            "status": robots["status"],
            "content": robots_text[:10000]
        }

        print("HTTP:", robots["status"])
        print(robots_text[:5000])

    except Exception as exc:

        result["findings"]["robots"] = {
            "error": str(exc)
        }

        print("[NO DISPONIBLE]", exc)

    result["status"] = "completed"

    save_report(result)

    print("\n" + "=" * 80)
    print("RECONOCIMIENTO COMPLETADO")
    print("PROYECTO:", ROOT)
    print("=" * 80)

    return 0


def save_report(data):

    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    destination = reports / (
        "relatoria_reconocimiento_" + stamp + ".json"
    )

    with destination.open(
        "x",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\nINFORME PERSISTIDO:")
    print(destination)


if __name__ == "__main__":

    sys.exit(inspect())
