"""Crawler controlado CSJ — descarga N documentos con reanudación.

Uso:
    python3 m060_crawler.py                        # 20 docs, Word, 2s delay
    python3 m060_crawler.py --max-docs 50
    python3 m060_crawler.py --format both          # Word + PDF
    python3 m060_crawler.py --dry-run              # ver qué haría
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
UA = "Mozilla/5.0 (compatible; CSJ-Crawler/0.3; +research)"
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw" / "2026"
MD_DIR = ROOT / "md" / "2026"
MANIFEST = ROOT / "manifest.jsonl"
FAILS = ROOT / "failures.jsonl"
RAW_DIR.mkdir(parents=True, exist_ok=True)
MD_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))
from parser import parse_rows
from manifest_utils import load_all, save_all, sha256_file
from build_md_full import build_md


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
            "Origin": ORIGIN,
            "Referer": BASE,
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
        return self.vs

    def search(self, tema, sala_checkbox, sala_value, options1="0"):
        _, sb = self.ajax_post({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "searchForm:searchButton",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render":
                "resultForm:jurisTable resultForm:pagText2 resultForm:selectAllButton",
            "searchForm:searchButton": "",
            "searchForm": "searchForm",
            "searchForm:temaInput": tema,
            sala_checkbox: sala_value,
            "searchForm:options1": options1,
            "javax.faces.ViewState": self.vs,
        })
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


def _classify(data, ctype):
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


def download_one(sess, row, fmt, search_id):
    """Descarga un documento. Devuelve manifest dict o lanza excepción."""
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
    ext = _classify(data, ctype)
    if not ext:
        raise RuntimeError(f"magic inválido: {data[:8]!r}")

    filename = _safe_filename(row, ext)
    path = RAW_DIR / filename
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
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=20)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--format", choices=["word", "pdf", "both"], default="word")
    ap.add_argument("--search-tema", default="contrato")
    ap.add_argument("--search-sala", default="scivil",
                    choices=["scivil", "slaboral", "spenal", "splena"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    SALAS = {
        "scivil": ("searchForm:scivil:0", "SALA DE CASACIÓN CIVIL"),
        "slaboral": ("searchForm:slaboral:4", "SALA DE CASACIÓN LABORAL"),
        "spenal": ("searchForm:spenal:2", "Sala de Casación Penal"),
        "splena": ("searchForm:splena:0", "SALA PLENA"),
    }
    sala_checkbox, sala_value = SALAS[args.search_sala]
    formats = ["word"] if args.format == "word" else (
              ["pdf"] if args.format == "pdf" else ["word", "pdf"])

    print("=" * 72)
    print("M060 — CRAWLER CONTROLADO")
    print("=" * 72)
    print(f"  Tema:       {args.search_tema}")
    print(f"  Sala:       {args.search_sala} ({sala_value})")
    print(f"  Formatos:   {formats}")
    print(f"  Max docs:   {args.max_docs}")
    print(f"  Delay:      {args.delay}s")
    print(f"  Dry run:    {args.dry_run}")
    print()

    # Load manifest → done_set
    existing = load_all(MANIFEST)
    done = {(r["row_key"], r.get("ext")) for r in existing}
    print(f"Manifest previo: {len(existing)} registros")
    print(f"Docs únicos ya descargados: {len({r['row_key'] for r in existing})}")
    print()

    sess = Session()
    sess.bootstrap()
    print(f"Bootstrap OK (vs={sess.vs[:20]}…)")

    search_id = f"search_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    print(f"Search: {search_id}")

    table = sess.search(args.search_tema, sala_checkbox, sala_value)
    rows = parse_rows(table)
    print(f"Fila inicial: {rows[0]['row_key'] if rows else '(vacía)'}\n")

    if args.dry_run:
        print("[DRY-RUN] Los siguientes serían descargados:")
        shown = 0
        while shown < args.max_docs and rows:
            for row in rows:
                if (row["row_key"], "docx") in done and (row["row_key"], "pdf") in done:
                    continue
                print(f"  row_key={row['row_key']}  providencia={row.get('providencia')}")
                shown += 1
                if shown >= args.max_docs:
                    break
            if shown >= args.max_docs:
                break
            table = sess.next_page()
            rows = parse_rows(table)
        print(f"\nTotal mostrados: {shown}")
        return

    count = 0
    t0 = time.time()
    while count < args.max_docs:
        rows = parse_rows(table)
        if not rows:
            print("Sin más filas — fin de resultados")
            break

        row = rows[0]
        rk = row["row_key"]

        # ¿Ya tenemos ambos formatos solicitados?
        missing = [f for f in formats if (rk, f) not in done]
        if not missing:
            print(f"  [SKIP] {rk} ya en manifest ({formats})")
            table = sess.next_page()
            time.sleep(args.delay / 2)
            continue

        print(f"[{count+1}/{args.max_docs}] {rk}  prov={row.get('providencia')}")
        for fmt in missing:
            try:
                manifest = download_one(sess, row, fmt, search_id)
                _append_jsonl(MANIFEST, manifest)
                done.add((rk, manifest["ext"]))
                print(f"    OK {fmt}: {manifest['size']:,} B  {manifest['sha256'][:12]}…")
                count += 1
            except Exception as exc:
                print(f"    FAIL {fmt}: {type(exc).__name__}: {exc}")
                _append_jsonl(FAILS, {
                    "row_key": rk,
                    "format": fmt,
                    "error": f"{type(exc).__name__}: {exc}",
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                # re-bootstrap para recuperar sesión
                try:
                    sess.bootstrap()
                    table = sess.search(args.search_tema, sala_checkbox, sala_value)
                except Exception:
                    pass
                break

        if count >= args.max_docs:
            break

        table = sess.next_page()
        time.sleep(args.delay)

    # Generar .md para nuevos docs
    print("\nGenerando .md para docs nuevos…")
    records = load_all(MANIFEST)
    by_rk = {}
    for r in records:
        rk = r["row_key"]
        by_rk.setdefault(rk, {})[r.get("ext")] = r

    md_count = 0
    for rk, exts in by_rk.items():
        if "docx" not in exts:
            continue
        rec = exts["docx"]
        if rec.get("md_path") and (ROOT / rec["md_path"]).is_file():
            continue
        prov = rec.get("providencia") or rk
        md_path = MD_DIR / f"{prov}.md"
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
    print()
    print("=" * 72)
    print("M060 — RESUMEN")
    print("=" * 72)
    print(f"  Descargados:   {count}")
    print(f"  MD generados:  {md_count}")
    print(f"  Tiempo:        {elapsed:.1f}s")
    print(f"  Manifest:      {len(load_all(MANIFEST))} registros totales")
    print()
    print("Siguiente: re-chunk + re-embed")
    print("  python3 build_chunks_all.py")
    print("  python3 embed_unified.py")


if __name__ == "__main__":
    main()
