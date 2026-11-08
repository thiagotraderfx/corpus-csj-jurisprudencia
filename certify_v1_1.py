"""Certificación v1.1.0 — incluye API REST."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
summary = json.loads((ROOT / "v1_summary.json").read_text(encoding="utf-8"))
bench = json.loads((ROOT / "benchmark_report_v2.json").read_text(encoding="utf-8"))

health_ok = (ROOT / "health_final.log").is_file() and \
            "HEALTH: OK" in (ROOT / "health_final.log").read_text(encoding="utf-8")

try:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT),
    )
    tests_pass = r.returncode == 0
    tests_out = (r.stdout or "")[-300:]
except Exception:
    tests_pass = False
    tests_out = ""

try:
    from api import app
    api_ok = True
    n_routes = len(app.routes)
except Exception:
    api_ok = False
    n_routes = 0

try:
    from fastapi.testclient import TestClient
    client = TestClient(app)
    h = client.get("/health").json()
    s = client.get("/stats").json()
    o = client.get("/openapi.json").json()
    health_api_ok = h.get("status") == "ok"
    stats_has_dups = "duplicates_sha256" in s
    stats_version_ok = str(s.get("version", "")).startswith("1.")
    openapi_ok = "/search" in o.get("paths", {}) and "/ask" in o.get("paths", {})
except Exception:
    health_api_ok = stats_has_dups = stats_version_ok = openapi_ok = False

dups = summary.get("duplicates_sha256", -1)
checks = {
    "docs_count_100": summary["docs"] >= 100,
    "chunks_gt_6000": summary["chunks"] > 6000,
    "duplicates_field": dups == 0,
    "md_files_complete": summary["md_files"] >= 100,
    "sanity_hit_ge_95": (bench["retrieval_sanity"]["hit@k"] or 0) >= 0.95,
    "topic_hit_ge_50": (bench["topic_retrieval"]["hit@k"] or 0) >= 0.50,
    "health_ok": health_ok,
    "tests_pass": tests_pass,
    "api_importable": api_ok,
    "api_health_ok": health_api_ok,
    "api_stats_has_duplicates": stats_has_dups,
    "api_stats_version": stats_version_ok,
    "api_openapi": openapi_ok,
}
certified = all(checks.values())
cert = {
    "certificate_id": f"CSJ-v1.1.0-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    "version": "1.1.0",
    "certified": certified,
    "certified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "checks": checks,
    "summary": summary,
    "api": {"routes": n_routes},
    "benchmark": {
        "sanity_hit_at_5": bench["retrieval_sanity"]["hit@k"],
        "sanity_mrr": bench["retrieval_sanity"]["mrr"],
        "topic_hit_at_5": bench["topic_retrieval"]["hit@k"],
        "topic_mrr": bench["topic_retrieval"]["mrr"],
    },
    "tests_tail": tests_out,
}
(ROOT / "v1.1.0-certified.json").write_text(
    json.dumps(cert, indent=2, ensure_ascii=False), encoding="utf-8")
print("=" * 64)
print(f"Certificado: {cert['certificate_id']}")
print(f"Estado:      {'CERTIFIED' if certified else 'PENDING'}")
print("=" * 64)
for k, v in checks.items():
    print(f"  {'OK  ' if v else 'FAIL'} {k}")
sys.exit(0 if certified else 1)
