import json, re, sys, hashlib, base64
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

def usage_and_exit(code=1):
    print()
    print("=" * 78)
    print("M036 — SANEADOR DE HAR CSJ")
    print("=" * 78)
    print()
    print("USO:")
    print("  python3 sanitize_har.py <archivo.har>")
    print()
    print("El archivo .har debe provenir de una captura manual en navegador.")
    print("Ver M036 §3.3 del protocolo: F12 → Network → Preserve log → Export HAR.")
    print()
    print("Este script NO captura tráfico. Solo sanea un HAR existente:")
    print("  - filtra entradas fuera del origen CSJ")
    print("  - redacta jsessionid y ViewState")
    print("  - elimina cookies y Authorization")
    print("  - produce .redacted.json y .summary.txt")
    print()
    sys.exit(code)

if len(sys.argv) != 2:
    usage_and_exit(1)

HAR_IN = Path(sys.argv[1])
if not HAR_IN.is_file():
    print(f"[ABORT] No existe: {HAR_IN.resolve()}")
    usage_and_exit(1)

CSJ_HOSTS = {
    "consultajurisprudencial.ramajudicial.gov.co",
    "www.ramajudicial.gov.co",
    "ramajudicial.gov.co",
}
KEEP_REQ = {"content-type", "accept", "x-requested-with", "faces-request", "user-agent"}
KEEP_RES = {"content-type", "content-disposition", "location"}

def redact_url(url):
    p = urlparse(url)
    q = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        if k.lower() in {"jsessionid", "token", "csrf"}:
            v = "[REDACTADO]"
        q.append((k, v))
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))

def redact_vs(text):
    if not text:
        return text
    text = re.sub(
        r"(?i)((?:javax|jakarta)\.faces\.ViewState[=:]\s*[\"']?)([^&\"'\s]+)",
        r"\1[REDACTADO]", text
    )
    return text

def body_summary(text, enc):
    if not text:
        return {"size": 0, "sha256": None, "preview": None, "is_binary": False}
    raw = base64.b64decode(text) if enc == "base64" else text.encode("utf-8", "replace")
    is_bin = any(b == 0 for b in raw[:512]) or sum(
        b < 9 or (13 < b < 32) for b in raw[:512]
    ) > 4
    preview = None
    if not is_bin and len(raw) <= 4000:
        preview = raw.decode("utf-8", "replace")
    return {
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "preview": preview,
        "is_binary": is_bin,
    }

try:
    har = json.loads(HAR_IN.read_text(encoding="utf-8"))
except Exception as exc:
    sys.exit(f"[ABORT] HAR ilegible: {exc}")

entries = har.get("log", {}).get("entries", [])
kept, lines = [], []
lines.append("=" * 78)
lines.append("CSJ — M036 — RESUMEN DE CAPTURA HAR (SANEADO)")
lines.append("=" * 78)
lines.append("")
lines.append(f"Entradas originales: {len(entries)}")

for idx, e in enumerate(entries, 1):
    req, res = e.get("request", {}), e.get("response", {})
    url = req.get("url", "")
    if (urlparse(url).hostname or "").lower() not in CSJ_HOSTS:
        continue
    method = req.get("method", "?")
    red_url = redact_url(url)
    req_h = {h["name"].lower(): h.get("value", "") for h in req.get("headers", [])
             if (h.get("name") or "").lower() in KEEP_REQ}
    post = (req.get("postData") or {}).get("text", "") if isinstance(req.get("postData"), dict) else ""
    post = redact_vs(post)
    res_h = {h["name"].lower(): h.get("value", "") for h in res.get("headers", [])
             if (h.get("name") or "").lower() in KEEP_RES}
    body = body_summary((res.get("content") or {}).get("text"),
                        (res.get("content") or {}).get("encoding"))
    kept.append({
        "entry": idx, "method": method, "url": red_url,
        "request_headers": req_h, "post_text_redacted": post,
        "response_status": res.get("status", 0),
        "response_headers": res_h, "response_body": body,
    })
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"ENTRADA {idx}: {method} {red_url}")
    lines.append(f"  Status: {res.get('status', 0)}")
    for k, v in req_h.items():
        lines.append(f"  Req[{k}]: {v}")
    if post:
        lines.append(f"  POST ({len(post)} chars, ViewState redactado):")
        for field in post.split("&"):
            lines.append(f"    {field}")
    for k, v in res_h.items():
        lines.append(f"  Res[{k}]: {v}")
    lines.append(f"  Body: {body['size']} bytes, sha256={body['sha256']}, binary={body['is_binary']}")
    if body["preview"]:
        for line in body["preview"].splitlines()[:20]:
            lines.append(f"    {line[:200]}")

lines.append("")
lines.append("=" * 78)
lines.append(f"FIN — {len(kept)} entradas conservadas")
lines.append("=" * 78)

summary_path = HAR_IN.with_suffix(".summary.txt")
summary_path.write_text("\n".join(lines), encoding="utf-8")

redacted_path = HAR_IN.with_suffix(".redacted.json")
redacted_path.write_text(json.dumps({
    "log": {
        "version": har.get("log", {}).get("version", "1.2"),
        "creator": {"name": "CSJ-M036-sanitizer", "version": "1.1"},
        "entries": kept,
    }
}, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n".join(lines))
print()
print(f"[OK] Saneado : {redacted_path}")
print(f"[OK] Resumen : {summary_path}")
print(f"[OK] Original conservado: {HAR_IN}")
