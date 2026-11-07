"""Crawler CSJ con búsqueda por ID — inmune al desfase de páginas.

Cada descarga comienza con search(idInput=<id>), que devuelve exactamente
1 fila, garantizando que la selección y el trigger apuntan al documento
correcto sin depender del estado de paginación.

Uso:
    python3 m062_crawler_byid.py --type sentencia --year 2024 --max-docs 30
    python3 m062_crawler_byid.py --type auto --year 2026 --dry-run
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
UA = "Mozilla/5.0 (compatible; CSJ-Crawler/0.5; +research)"
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
MD_DIR = ROOT / "md"
MANIFEST = ROOT / "manifest.jsonl"
FAILS = ROOT / "failures.jsonl"
sys.path.insert(0, str(ROOT))

from parser import parse_rows
from manifest_utils import load_all, save_all, sha256_file
from build_md_full import build_md


SALA_LETTERS = {"C": "civil", "L": "laboral", "P": "penal", "E": "especial", "T": "tutela"}

def classify_providencia(prov):
    if not prov:
        return ("unknown", None)
    p = prov.strip().upper()
    tipo = {"A": "auto", "S": "sentencia"}.get(p[0], "unknown")
    sala = SALA_LETTERS.get(p[1]) if len(p) > 1 else None
    return (tipo, sala)


def extract_year(fecha):
    if not fecha:
        return None
    m = re.search(r"/(\d{4})$", fecha.strip())
    return int(m.group(1)) if m else None


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

    def search(self, tema="", id_filter="", fecha_ini="", fecha_fin="", options1="0"):
        payload = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "searchForm:searchButton",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render":
                "resultForm:jurisTable resultForm:pagText2 resultForm:selectAllButton",
            "searchForm:searchButton": "",
            "searchForm": "searchForm",
            "searchForm:temaInput": tema,
            "searchForm:idInput": id_filter,
            "searchForm:options1": options1,
            "javax.faces.ViewState": self.vs,
        }
        if fecha_ini:
            payload["searchForm:fechaIniCal"] = fecha_ini
        if fecha_fin:
            payload["searchForm:fechaFinCal"] = fecha_fin

        _, sb = self.ajax_post(payload)
        vs_ok = _extract_vs(sb) is not None
        print(f"  [search] {len(sb)} bytes  vs={'ok' if vs_ok else 'MISSING'}")
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
    return None


def _safe_filename(row, ext):
    prov = row.get("providencia") or row["row_key"]
    prov = re.sub(r"[^\w\-\. ]+", "_", prov).strip()
    rad = row.get("radicado") or ""
    rad = re.sub(r"[^\w\-]", "_", rad)
    return f"{prov} ({rad}).{ext}" if rad else f"{prov}.{ext}"


def download_by_id(sess, doc_id, fmt, search_id):
    """Descarga un doc por ID. Sesión se navega a 1 resultado único."""
    src = "resultForm:j_idt293" if fmt == "word" else "resultForm:j_idt295"

    # 1. Fresh search by ID → 1 result
    table = sess.search(id_filter=doc_id)
    rows = parse_rows(table)
    if not rows:
        raise RuntimeError(f"search(idInput={doc_id}) devolvió 0 filas")
    if len(rows) > 1:
        raise RuntimeError(f"search(idInput={doc_id}) devolvió {len(rows)} filas (ambiguo)")
    row = rows[0]
    rk = row["row_key"]
    time.sleep(0.2)

    # 2. Select
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
    time.sleep(0.2)

    # 3. Trigger
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
        raise RuntimeError("sin window.open en trigger")
    time.sleep(0.2)

    # 4. GET binario con backoff
    for attempt in range(3):
        resp, data = sess.get(url)
        status = resp.status  # urllib: HTTPResponse.status (int)
        if status < 500 and status != 429:
            break
        wait = 2 ** (attempt + 1)
        print(f"    retry {attempt+1}/3 en {wait}s (HTTP {status})")
        time.sleep(wait)
    else:
        raise RuntimeError(f"GET binario falló tras 3 intentos: HTTP {status}")
    ext = _classify_binary(data, resp.headers.get("Content-Type", ""))
    if not ext:
        raise RuntimeError(f"magic inválido: {data[:8]!r}")

    filename = _safe_filename(row, ext)
    year = extract_year(row.get("fecha"))
    raw_sub = RAW_DIR / (str(year) if year else "unknown")
    raw_sub.mkdir(parents=True, exist_ok=True)
    path = raw_sub / filename
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()

    return {
        **{k: v for k, v in row.items() if k != "row_key"},
        "row_key": rk,
        "ext": ext,
        "raw_path": str(path.relative_to(ROOT)),
        "url_original": url,
        "content_type": resp.headers.get("Content-Type", ""),
        "size": len(data),
        "sha256": sha,
        "searched_with": search_id,
        "acquired_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metadata_sources": ["table"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=30)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--format", choices=["word", "pdf"], default="word")
    ap.add_argument("--type", choices=["sentencia", "auto", "both"], default="sentencia")
    ap.add_argument("--sala", choices=["civil", "laboral", "penal", "especial", "all"], default="all")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--search-tema", default="contrato")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fecha_ini = f"01/01/{args.year}" if args.year else ""
    fecha_fin = f"31/12/{args.year}" if args.year else ""

    print("=" * 78)
    print("M062 — CRAWLER POR ID (inmune a desfase de página)")
    print("=" * 78)
    print(f"  Tipo:     {args.type}")
    print(f"  Sala:     {args.sala} (filtro client-side)")
    print(f"  Año:      {args.year or 'todos'}")
    print(f"  Formato:  {args.format}")
    print(f"  Max:      {args.max_docs}")
    print(f"  Dry-run:  {args.dry_run}\n")

    existing = load_all(MANIFEST)
    done_rks = {r["row_key"] for r in existing}
    print(f"Manifest: {len(existing)} registros / {len(done_rks)} docs únicos\n")

    sess = Session()
    sess.bootstrap()
    print("Bootstrap OK\n")

    # ── 1. Recolectar IDs de candidatos (paginar solo para enlistar) ──
    search_id = f"search_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    table = sess.search(tema=args.search_tema, fecha_ini=fecha_ini, fecha_fin=fecha_fin)
    rows = parse_rows(table)

    candidates = []
    stats = {"sentencia": 0, "auto": 0, "unknown": 0}
    sala_stats = {}
    seen_ids = set()

    for page_num in range(1, 10001):
        for row in rows:
            doc_id = row.get("id")
            tipo, sala = classify_providencia(row.get("providencia"))
            stats[tipo] = stats.get(tipo, 0) + 1
            sala_stats[sala or "unknown"] = sala_stats.get(sala or "unknown", 0) + 1

            if not doc_id or doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            if args.type != "both" and tipo != args.type:
                continue
            if args.sala != "all" and sala != args.sala:
                continue
            if args.year and extract_year(row.get("fecha")) != args.year:
                continue
            if row["row_key"] in done_rks:
                continue
            candidates.append({"id": doc_id, "prov": row.get("providencia"),
                               "tipo": tipo, "sala": sala, "fecha": row.get("fecha")})

            if len(candidates) >= args.max_docs:
                break
        if len(candidates) >= args.max_docs:
            break
        try:
            table = sess.next_page()
            rows = parse_rows(table)
            if not rows:
                break
            if page_num % 10 == 0:
                print(f"  [enum] page {page_num}: {len(candidates)}/{args.max_docs} candidatos", flush=True)
        except Exception:
            break

    print(f"  [enum] DONE: {len(candidates)} candidatos en {page_num} páginas", flush=True)
    print(f"Clasificación vista: {stats}")
    print(f"Salas vistas:        {sala_stats}")
    print(f"Candidatos finales:  {len(candidates)}\n")

    if args.dry_run:
        print("[DRY-RUN] Primeros candidatos:")
        for c in candidates[:args.max_docs]:
            print(f"  id={c['id']:10}  {c['prov']:15}  {c['tipo']:10}/{c['sala'] or '?':8}  {c['fecha']}")
        return

    # ── 2. Descarga cada candidato con sesión fresca + búsqueda por ID ──
    count = 0
    t0 = time.time()
    for i, cand in enumerate(candidates, 1):
        if count >= args.max_docs:
            break
        doc_id = cand["id"]
        print(f"[{i}/{len(candidates)}] id={doc_id}  {cand['prov']}  {cand['tipo']}/{cand['sala']}  {cand['fecha']}")

        try:
            # Sesión fresca por cada descarga
            sess = Session()
            sess.bootstrap()

            manifest = download_by_id(sess, doc_id, args.format, search_id)

            # Verificación anti-duplicado
            existing_shas = {r.get("sha256") for r in load_all(MANIFEST)}
            if manifest["sha256"] in existing_shas:
                print(f"    DUP  sha={manifest['sha256'][:12]}… ya existe, saltando")
                continue

            with MANIFEST.open("a", encoding="utf-8") as f:
                f.write(json.dumps(manifest, ensure_ascii=False) + "\n")
            print(f"    OK   {manifest['size']:>10,} B  sha={manifest['sha256'][:12]}…")
            count += 1
        except Exception as exc:
            print(f"    FAIL {type(exc).__name__}: {exc}")
            with FAILS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": doc_id, "providencia": cand["prov"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }, ensure_ascii=False) + "\n")

        time.sleep(args.delay)

    # ── 3. Generar .md de nuevos docs ──
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
        except Exception as exc:
            print(f"  FAIL {rk}: {exc}")

    save_all(MANIFEST, records)

    print(f"\n{'='*78}")
    print("RESUMEN")
    print(f"{'='*78}")
    print(f"  Descargados: {count} nuevos")
    print(f"  MD:          {md_count} nuevos")
    print(f"  Tiempo:      {time.time() - t0:.1f}s")
    print(f"  Manifest:    {len(load_all(MANIFEST))} registros")

    # Reporte de duplicados (nunca debería haberlos)
    all_recs = load_all(MANIFEST)
    shas = {}
    for r in all_recs:
        sha = r.get("sha256")
        shas.setdefault(sha, []).append(r.get("providencia"))
    dups = {k: v for k, v in shas.items() if len(v) > 1}
    if dups:
        print(f"\n[ALERTA] Duplicados detectados: {dups}")
    else:
        print(f"\n[OK] Sin duplicados SHA-256")


if __name__ == "__main__":
    main()
