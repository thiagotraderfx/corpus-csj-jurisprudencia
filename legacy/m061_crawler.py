"""Crawler CSJ con clasificación por prefijo de providencia.

Uso:
    python3 m061_crawler.py --type sentencia --year 2024 --max-docs 30
    python3 m061_crawler.py --type auto --sala civil --year 2026
    python3 m061_crawler.py --type both --dry-run

Prefijos reconocidos:
    A + C = Auto Civil       S + C = Sentencia Civil
    A + L = Auto Laboral     S + L = Sentencia Laboral
    A + P = Auto Penal       S + P = Sentencia Penal
    A + E = Auto Especial    S + E = Sentencia Especial
"""
import argparse
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import (
    Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler,
)

BASE = "https://consultajurisprudencial.ramajudicial.gov.co/WebRelatoria/csj/index.xhtml"
ORIGIN = "https://consultajurisprudencial.ramajudicial.gov.co"
TIMEOUT = 30
UA = "Mozilla/5.0 (compatible; CSJ-Crawler/0.4; +research)"
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
MD_DIR = ROOT / "md"
MANIFEST = ROOT / "manifest.jsonl"
FAILS = ROOT / "failures.jsonl"
sys.path.insert(0, str(ROOT))

from parser import parse_rows
from manifest_utils import load_all, save_all, sha256_file
from build_md_full import build_md


# ══════════════════════════════════════════════════════════════
# Clasificación por prefijo
# ══════════════════════════════════════════════════════════════
SALA_LETTERS = {
    "C": "civil",
    "L": "laboral",
    "P": "penal",
    "E": "especial",
    "T": "tutela",
}

def classify_providencia(prov):
    """Devuelve (tipo, sala). tipo ∈ {auto, sentencia, unknown}."""
    if not prov:
        return ("unknown", None)
    p = prov.strip().upper()
    if len(p) < 2:
        return ("unknown", None)
    tipo_map = {"A": "auto", "S": "sentencia"}
    tipo = tipo_map.get(p[0], "unknown")
    sala = SALA_LETTERS.get(p[1])
    return (tipo, sala)


def extract_year(fecha):
    """Extrae año de DD/MM/YYYY."""
    if not fecha:
        return None
    m = re.search(r"/(\d{4})$", fecha.strip())
    return int(m.group(1)) if m else None


# ══════════════════════════════════════════════════════════════
# HTTP helpers
# ══════════════════════════════════════════════════════════════
class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlparse(req.full_url), urlparse(urljoin(req.full_url, newurl))
        op = old.port or (443 if old.scheme == "https" else 80)
        np = new.port or (443 if new.scheme == "https" else 80)
        if new.scheme != "https" or new.hostname != old.hostname or np != op:
            raise RuntimeError(f"redirect bloqueado: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Session:
    def __init__(self):
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar), SafeRedirect())
        self.vs = None

    def ajax_post(self, payload):
        headers = {
            "User-Agent": UA,
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": ORIGIN, "Referer": BASE,
        }
        req = Request(BASE, data=urlencode(payload).encode(),
                      headers=headers, method="POST")
        resp = self.opener.open(req, timeout=TIMEOUT)
        return resp, resp.read()

    def get(self, url):
        req = Request(url, headers={"User-Agent": UA, "Referer": BASE})
        resp = self.opener.open(req, timeout=TIMEOUT)
        return resp, resp.read()

    def bootstrap(self):
        _, body = self.get(BASE)
        self.vs = _extract_vs(body.decode("utf-8", errors="replace"))

    def search(self, tema, salas_checkbox, options1, fecha_ini, fecha_fin):
        payload = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "searchForm:searchButton",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render":
                "resultForm:jurisTable resultForm:pagText2 resultForm:selectAllButton",
            "searchForm:searchButton": "",
            "searchForm": "searchForm",
            "searchForm:temaInput": tema,
            "searchForm:options1": options1,
            "javax.faces.ViewState": self.vs,
        }
        for name, value in salas_checkbox.items():
            payload[name] = value
        if fecha_ini:
            payload["searchForm:fechaIniCal"] = fecha_ini
        if fecha_fin:
            payload["searchForm:fechaFinCal"] = fecha_fin

        _, sb = self.ajax_post(payload)
        self.vs = _extract_vs(sb)
        return _extract_update(sb, "resultForm:jurisTable") or ""

    def next_page(self):
        _, sb = self.ajax_post({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "resultForm:j_idt275",
            "javax.faces.partial.execute": "resultForm:j_idt275",
            "javax.faces.partial.render":
                "resultForm:jurisTable resultForm:pagText2",
            "resultForm:j_idt275": "resultForm:j_idt275",
            "resultForm": "resultForm",
            "javax.faces.ViewState": self.vs,
        })
        self.vs = _extract_vs(sb)
        return _extract_update(sb, "resultForm:jurisTable") or ""


def _extract_vs(text):
    try:
        tree = ET.fromstring(text)
        for upd in tree.iter("update"):
            if upd.get("id", "").endswith("ViewState:0"):
                return "".join(upd.itertext()).strip()
    except ET.ParseError:
        pass
    m = re.search(r'name=["\']javax\.faces\.ViewState["\'][^>]*value=["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _extract_update(xml_bytes, uid):
    try:
        tree = ET.fromstring(xml_bytes)
        for upd in tree.iter("update"):
            if upd.get("id") == uid:
                return "".join(upd.itertext())
    except ET.ParseError:
        pass
    return None


def _find_eval_url(xml_bytes):
    try:
        tree = ET.fromstring(xml_bytes)
        for ev in tree.iter("eval"):
            text = "".join(ev.itertext())
            m = re.search(r"window\.open\(\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return m.group(1)
    except ET.ParseError:
        pass
    return None


def _classify_binary(data, ctype):
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "docx"
    if data[:2] == b"\xD0\xCF":
        return "doc"
    if "pdf" in ctype.lower():
        return "pdf"
    if "officedocument" in ctype.lower():
        return "docx"
    if "msword" in ctype.lower():
        return "doc"
    return None


def _safe_filename(row, ext):
    prov = row.get("providencia") or row["row_key"]
    prov = re.sub(r"[^\w\-\. ]+", "_", prov).strip()
    rad = row.get("radicado") or ""
    rad = re.sub(r"[^\w\-]", "_", rad)
    return f"{prov} ({rad}).{ext}" if rad else f"{prov}.{ext}"


def _append_jsonl(path, obj):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def download_one(sess, row, fmt, search_id, sala_expected):
    src = "resultForm:j_idt293" if fmt == "word" else "resultForm:j_idt295"
    rk = row["row_key"]

    # select
    _, sb = sess.ajax_post({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "resultForm:jurisTable",
        "javax.faces.behavior.event": "rowSelectCheckbox",
        "javax.faces.partial.event": "rowSelectCheckbox",
        "javax.faces.partial.execute": "resultForm:jurisTable",
        "javax.faces.partial.render": "resultForm:jurisTable",
        "resultForm:jurisTable_rowKey": rk,
        "resultForm:jurisTable_selection": rk,
        "resultForm": "resultForm",
        "javax.faces.ViewState": sess.vs,
    })
    sess.vs = _extract_vs(sb)
    time.sleep(0.3)

    # trigger
    _, sb = sess.ajax_post({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": src,
        "javax.faces.partial.execute": src,
        "javax.faces.partial.render": "@none",
        src: src,
        "resultForm": "resultForm",
        "resultForm:jurisTable_checkbox": "false",
        "resultForm:jurisTable_selection": rk,
        "javax.faces.ViewState": sess.vs,
    })
    sess.vs = _extract_vs(sb)
    url = _find_eval_url(sb)
    if not url:
        raise RuntimeError("sin window.open en respuesta de descarga")
    time.sleep(0.3)

    # GET binary
    resp, data = sess.get(url)
    ctype = resp.headers.get("Content-Type", "")
    ext = _classify_binary(data, ctype)
    if not ext:
        raise RuntimeError(f"magic inválido: {data[:8]!r}")

    filename = _safe_filename(row, ext)
    year = extract_year(row.get("fecha"))
    raw_sub = RAW_DIR / (str(year) if year else "unknown")
    raw_sub.mkdir(parents=True, exist_ok=True)
    path = raw_sub / filename
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        **{k: v for k, v in row.items() if k != "row_key"},
        "row_key": rk,
        "ext": ext,
        "raw_path": str(path.relative_to(ROOT)),
        "url_original": url,
        "content_type": ctype,
        "size": len(data),
        "sha256": sha,
        "searched_with": search_id,
        "acquired_at": now,
        "metadata_sources": ["table"],
        "sala_expected": sala_expected,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=20)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--format", choices=["word", "pdf", "both"], default="word")
    ap.add_argument("--type", choices=["sentencia", "auto", "both"], default="sentencia")
    ap.add_argument("--sala", choices=["civil", "laboral", "penal", "especial", "all"],
                    default="all")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--search-tema", default="contrato")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Sala checkbox: solo por compatibilidad, no es fiable
    SALA_CHK = {
        "civil":    {"searchForm:scivil:0": "SALA DE CASACIÓN CIVIL"},
        "laboral":  {"searchForm:slaboral:4": "SALA DE CASACIÓN LABORAL"},
        "penal":    {"searchForm:spenal:2": "Sala de Casación Penal"},
        "especial": {"searchForm:spenal:0": "Sala Especial de Primera Instancia"},
        "all":      {},
    }
    salas_checkbox = SALA_CHK.get(args.sala, {})

    formats = (["word"] if args.format == "word"
               else ["pdf"] if args.format == "pdf"
               else ["word", "pdf"])
    fecha_ini = f"01/01/{args.year}" if args.year else ""
    fecha_fin = f"31/12/{args.year}" if args.year else ""

    print("=" * 78)
    print("M061 — CRAWLER CLASIFICADOR")
    print("=" * 78)
    print(f"  Tema:      {args.search_tema!r}")
    print(f"  Tipo:      {args.type}")
    print(f"  Sala:      {args.sala} (filtro client-side por prefijo)")
    print(f"  Año:       {args.year or 'todos'}")
    print(f"  Formatos:  {formats}")
    print(f"  Max docs:  {args.max_docs}")
    print(f"  Delay:     {args.delay}s")
    print(f"  Dry-run:   {args.dry_run}")
    print()

    existing = load_all(MANIFEST)
    done = {(r["row_key"], r.get("ext")) for r in existing}
    done_rks = {r["row_key"] for r in existing}
    print(f"Manifest: {len(existing)} registros / {len(done_rks)} docs únicos\n")

    sess = Session()
    sess.bootstrap()
    print(f"Bootstrap OK")

    search_id = f"search_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    table = sess.search(args.search_tema, salas_checkbox, "0", fecha_ini, fecha_fin)
    rows = parse_rows(table)
    print(f"Primera página: {len(rows)} filas\n")

    # Estadísticas de clasificación
    stats = {"sentencia": 0, "auto": 0, "unknown": 0}
    sala_stats = {}
    shown = 0
    candidates = []

    for _ in range(10000):  # hard cap
        for row in rows:
            tipo, sala = classify_providencia(row.get("providencia"))
            stats[tipo] = stats.get(tipo, 0) + 1
            sala_stats[sala or "unknown"] = sala_stats.get(sala or "unknown", 0) + 1

            # Filtros client-side
            if args.type != "both" and tipo != args.type:
                continue
            if args.sala != "all" and sala != args.sala:
                continue
            if args.year:
                y = extract_year(row.get("fecha"))
                if y != args.year:
                    continue
            if row["row_key"] in done_rks:
                continue
            candidates.append(row)
            shown += 1
            if shown >= args.max_docs * 3:  # margen para fallos
                break
        if shown >= args.max_docs * 3:
            break
        try:
            table = sess.next_page()
            rows = parse_rows(table)
            if not rows:
                break
        except Exception:
            break

    print(f"[DRY-RUN] Resumen de clasificación (primeros {sum(stats.values())}):")
    print(f"  Tipos:  {stats}")
    print(f"  Salas:  {sala_stats}")
    print(f"  Candidatos que cumplen filtros: {len(candidates)}\n")

    if args.dry_run:
        print("[DRY-RUN] Primeros candidatos que se descargarían:")
        for row in candidates[:args.max_docs]:
            tipo, sala = classify_providencia(row.get("providencia"))
            print(f"  {row.get('providencia'):15}  {tipo:10}  {sala or '?':8}  "
                  f"{row.get('fecha'):10}  {row['row_key']}")
        return

    # Descarga real
    count = 0
    t0 = time.time()
    for row in candidates:
        if count >= args.max_docs:
            break
        rk = row["row_key"]
        tipo, sala = classify_providencia(row.get("providencia"))
        print(f"[{count+1}/{args.max_docs}] {row.get('providencia')}  {tipo}/{sala}  {row.get('fecha')}")

        for fmt in formats:
            if (rk, fmt) in done:
                continue
            try:
                manifest = download_one(sess, row, fmt, search_id, sala)
                _append_jsonl(MANIFEST, manifest)
                done.add((rk, manifest["ext"]))
                print(f"    OK  {fmt:5}  {manifest['size']:>10,} B  sha={manifest['sha256'][:12]}…")
                count += 1
            except Exception as exc:
                print(f"    FAIL {fmt}: {type(exc).__name__}: {exc}")
                _append_jsonl(FAILS, {
                    "row_key": rk, "providencia": row.get("providencia"),
                    "format": fmt, "error": f"{type(exc).__name__}: {exc}",
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                try:
                    sess.bootstrap()
                except Exception:
                    pass
                break

        if count >= args.max_docs:
            break

    # Generar .md de nuevos docs
    print("\nGenerando .md…")
    records = load_all(MANIFEST)
    by_rk = {}
    for r in records:
        by_rk.setdefault(r["row_key"], {})[r.get("ext")] = r

    md_count = 0
    for rk, exts in by_rk.items():
        if "docx" not in exts:
            continue
        rec = exts["docx"]
        if rec.get("md_path") and (ROOT / rec["md_path"]).is_file():
            continue
        prov = rec.get("providencia") or rk
        year = extract_year(rec.get("fecha")) or "unknown"
        md_sub = MD_DIR / str(year)
        md_sub.mkdir(parents=True, exist_ok=True)
        md_path = md_sub / f"{prov}.md"
        try:
            md = build_md(rec, ROOT / rec["raw_path"], sorted(exts.keys()))
            md_path.write_text(md, encoding="utf-8")
            for r in records:
                if r["row_key"] == rk:
                    r["md_path"] = str(md_path.relative_to(ROOT))
                    r["md_size"] = md_path.stat().st_size
                    r["md_sha256"] = sha256_file(md_path)
            md_count += 1
            print(f"  {prov}.md  {md_path.stat().st_size:,} B")
        except Exception as exc:
            print(f"  FAIL {rk}: {exc}")

    save_all(MANIFEST, records)

    elapsed = time.time() - t0
    print("\n" + "=" * 78)
    print("M061 — RESUMEN")
    print("=" * 78)
    print(f"  Descargados:  {count}")
    print(f"  MD generados: {md_count}")
    print(f"  Tiempo:       {elapsed:.1f}s")
    print(f"  Manifest:     {len(load_all(MANIFEST))} registros")
    print()
    print("Siguiente: re-chunk + re-embed")
    print("  python3 m062_rebuild.py")


if __name__ == "__main__":
    main()
