"""Genera v1.0.0-certified.json con checks automáticos."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()

summary = json.loads((ROOT / "v1_summary.json").read_text(encoding="utf-8"))
bench = json.loads((ROOT / "benchmark_report_v2.json").read_text(encoding="utf-8"))

health_ok = False
if (ROOT / "health_final.log").is_file():
    health_ok = "HEALTH: OK" in (ROOT / "health_final.log").read_text(encoding="utf-8")

dups = summary.get("duplicates_sha256", 0)
checks = {
    "docs_count_100": summary["docs"] == 100,
    "chunks_gt_6000": summary["chunks"] > 6000,
    "duplicates_zero": dups == 0,
    "md_files_complete": summary["md_files"] in (100, 101),
    "sanity_hit_ge_95": (bench["retrieval_sanity"]["hit@k"] or 0) >= 0.95,
    "topic_hit_ge_75": (bench["topic_retrieval"]["hit@k"] or 0) >= 0.75,
    "health_ok": health_ok,
    "tests_present": (ROOT / "tests" / "test_corpus.py").is_file(),
    "incremental_present": (ROOT / "m062_rebuild_incremental.py").is_file(),
    "recovery_present": (ROOT / "RECOVERY.md").is_file(),
}

certified = all(checks.values())
cert = {
    "certificate_id": f"CSJ-v1.0.0-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    "version": "1.0.0",
    "certified": certified,
    "certified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "checks": checks,
    "summary": summary,
    "benchmark": {
        "sanity_hit_at_5": bench["retrieval_sanity"]["hit@k"],
        "sanity_mrr": bench["retrieval_sanity"]["mrr"],
        "topic_hit_at_5": bench["topic_retrieval"]["hit@k"],
        "topic_mrr": bench["topic_retrieval"]["mrr"],
    },
}
(ROOT / "v1.0.0-certified.json").write_text(
    json.dumps(cert, indent=2, ensure_ascii=False), encoding="utf-8")

print("=" * 60)
print(f"Certificado: {cert['certificate_id']}")
print(f"Estado:      {'CERTIFIED' if certified else 'PENDING'}")
print("=" * 60)
for k, v in checks.items():
    print(f"  {'OK ' if v else 'FAIL'} {k}")

if not certified:
    sys.exit(1)
