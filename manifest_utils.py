"""Utilidades de I/O idempotente para manifest.jsonl."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def load_all(path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_all(path, records):
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_key(record):
    return (str(record.get("row_key", "")), str(record.get("ext", "")))


def merge_metadata(record, meta):
    """Actualiza el registro con metadatos no vacíos. Devuelve True si cambió."""
    field_map = [
        ("id", "id"),
        ("sala", "sala"),
        ("radicado", "radicado"),
        ("providencia", "providencia"),
        ("clase", "clase"),
        ("tipo", "tipo"),
        ("fecha", "fecha"),
        ("ponente", "ponente"),
        ("tema", "tema"),
        ("fuente_formal", "fuente_formal"),
    ]
    changed = False
    for meta_field, record_field in field_map:
        new_value = meta.get(meta_field)
        if new_value and record.get(record_field) != new_value:
            record[record_field] = new_value
            changed = True
    if changed:
        record["backfilled_at"] = (
            datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
    return changed


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
