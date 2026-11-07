"""Singleton index loader con lock para thread safety."""
import json
import threading
from pathlib import Path
from typing import Optional

import numpy as np


class Index:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._loaded = False
        self.passages: Optional[np.ndarray] = None
        self.ids: list = []
        self.meta: dict = {}
        self.chunks: dict = {}
        self.chunks_by_id: dict = {}
        self.docs: dict = {}
        self.docs_list: list = []

    def load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            emb = self.root / "embeddings"
            self.meta = json.loads((emb / "meta.json").read_text(encoding="utf-8"))
            self.passages = np.load(emb / "passages.npy")
            self.ids = [
                json.loads(l) for l in
                (emb / "passages_ids.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()
            ]
            for line in (self.root / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                self.chunks_by_id[c["chunk_id"]] = c
            for line in (self.root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                rk = r["row_key"]
                if rk not in self.docs:
                    self.docs[rk] = r
                if r.get("ext") == "docx":
                    self.docs_list.append(r)
            self._loaded = True

    @property
    def n_chunks(self):
        return len(self.ids)

    @property
    def n_docs(self):
        return len(self.docs_list)

    def find_doc(self, key: str) -> Optional[dict]:
        """Busca por providencia o por row_key (id)."""
        for r in self.docs_list:
            if r.get("providencia") == key or r.get("id") == key or r.get("row_key") == key:
                return r
        return None

    def stats(self) -> dict:
        from collections import Counter
        import re
        tipos, salas, years = Counter(), Counter(), Counter()
        for r in self.docs_list:
            prov = r.get("providencia") or ""
            if prov.startswith("A"):
                tipos["auto"] += 1
            elif prov.startswith("S"):
                tipos["sentencia"] += 1
            if len(prov) > 1:
                sala = {"C": "civil", "L": "laboral", "P": "penal", "E": "especial", "T": "tutela"}.get(prov[1])
                if sala:
                    salas[sala] += 1
            m = re.search(r"/(\d{4})$", r.get("fecha") or "")
            if m:
                years[m.group(1)] += 1

        raw_bytes = sum(
            (self.root / r["raw_path"]).stat().st_size
            for r in self.docs_list
            if r.get("raw_path") and (self.root / r["raw_path"]).is_file()
        )
        md_files = sum(
            1 for r in self.docs_list
            if r.get("md_path") and (self.root / r["md_path"]).is_file()
        )
        shas = [r.get("sha256") for r in self.docs_list]
        duplicates = len(shas) - len(set(shas))

        bench = {}
        bench_file = self.root / "benchmark_report_v2.json"
        if bench_file.is_file():
            b = json.loads(bench_file.read_text(encoding="utf-8"))
            bench = {
                "sanity_hit_at_5": b.get("retrieval_sanity", {}).get("hit@k"),
                "sanity_mrr": b.get("retrieval_sanity", {}).get("mrr"),
                "topic_hit_at_5": b.get("topic_retrieval", {}).get("hit@k"),
                "topic_mrr": b.get("topic_retrieval", {}).get("mrr"),
            }

        return {
            "version": "1.1.0",
            "docs": len(self.docs_list),
            "chunks": self.n_chunks,
            "tipos": dict(tipos),
            "salas": dict(salas),
            "years": dict(sorted(years.items())),
            "embeddings": {
                "provider": self.meta.get("provider"),
                "model": self.meta.get("model"),
                "dim": self.meta.get("dim"),
            },
            "benchmark": bench,
            "raw_bytes": raw_bytes,
            "md_files": md_files,
            "duplicates_sha256": duplicates,
        }


_singleton: Optional[Index] = None


def get_index() -> Index:
    global _singleton
    if _singleton is None:
        root = Path(__file__).parent
        _singleton = Index(root)
        _singleton.load()
    return _singleton
