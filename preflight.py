"""Pre-flight antes del crawl."""
import sys
import time
import requests
from http.cookiejar import CookieJar
from urllib.request import Request, build_opener, HTTPCookieProcessor

UA = "Mozilla/5.0 (compatible; CSJ-Crawler/0.5; +research)"
URL = "https://consultajurisprudencial.ramajudicial.gov.co/WebRelatoria/csj/index.xhtml"

print("=== Test con UA del crawler ===")
r = requests.get(URL, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=15)
print(f"  Status: {r.status_code}  Latencia: {r.elapsed.total_seconds()*1000:.0f}ms  Bytes: {len(r.content)}")

if r.status_code == 403:
    print("  ⚠ 403 con UA crawler. Probando bootstrap con cookies...")
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    req = Request(URL, headers={"User-Agent": UA, "Accept": "text/html"})
    resp = opener.open(req, timeout=15)
    print(f"  Bootstrap directo: HTTP {resp.status}  Cookies: {len(jar)}")
    if resp.status == 200:
        print("  ✓ Portal accesible vía urllib")
        sys.exit(0)
    sys.exit(1)

if r.status_code != 200:
    sys.exit(f"Portal respondió {r.status_code}")

print("  ✓ Portal accesible con UA crawler")
sys.exit(0)
