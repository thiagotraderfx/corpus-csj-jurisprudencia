"""Tests de la API con TestClient (sin red, sin LLM).

Requieren `embeddings/passages.npy` porque `api.py` carga stats/embeddings
al startup. En CI (sin release assets) el módulo entero se skipea.
"""
import pytest
from pathlib import Path as _Path

_ASSETS_OK = (_Path(__file__).resolve().parent.parent / "embeddings" / "passages.npy").exists()
pytestmark = pytest.mark.skipif(
    not _ASSETS_OK,
    reason="requiere passages.npy (gh release download v1.1.0)",
)

import os
from fastapi.testclient import TestClient

os.environ.pop("API_KEY", None)

from api import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    d = r.json()
    assert "version" in d
    assert d["version"].startswith("1.1")


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("ok", "degraded")
    assert "checks" in d


def test_stats():
    r = client.get("/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["docs"] > 0
    assert d["chunks"] > 0
    assert d["duplicates_sha256"] == 0


def test_list_providencias():
    r = client.get("/providencias?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert d["limit"] == 5
    assert len(d["results"]) <= 5


def test_list_filter_sala():
    r = client.get("/providencias?sala=civil&limit=10")
    assert r.status_code == 200
    for item in r.json()["results"]:
        prov = item["providencia"]
        assert len(prov) > 1 and prov[1] == "C"


def test_get_doc_not_found():
    r = client.get("/docs/INVALID-XXXX")
    assert r.status_code == 404


def test_get_chunk_not_found():
    r = client.get("/chunks/INVALID-XXXX")
    assert r.status_code == 404


def test_openapi():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    d = r.json()
    assert "paths" in d
    assert "/search" in d["paths"]
    assert "/ask" in d["paths"]
    assert "/docs/{doc_id}" in d["paths"]
