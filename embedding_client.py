"""Cliente de embeddings unificado.

Lee meta.json y despacha al provider correcto (nvidia / openrouter).
Todos los scripts (rag_query, rag_ask, benchmark, health_check) usan esto,
evitando URLs hardcodeadas que se rompen cuando el provider cambia.
"""
import json
import os
from pathlib import Path

import numpy as np
import requests

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/embeddings"
OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"


class EmbeddingClient:
    def __init__(self, meta_path=None):
        if meta_path is None:
            meta_path = Path(__file__).parent / "embeddings" / "meta.json"
        self.meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        self.provider = self.meta["provider"]
        self.model = self.meta["model"]
        self.dim = self.meta["dim"]

    def embed(self, texts, input_type="query", batch_size=10, max_retries=3):
        """textos: str | list[str]. Devuelve list[np.ndarray].
        Reintenta con backoff exponencial en errores transitorios (5xx, timeout).
        """
        if isinstance(texts, str):
            texts = [texts]
        all_vecs = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            all_vecs.extend(self._embed_with_retry(batch, input_type, max_retries))
        return all_vecs

    def _embed_with_retry(self, batch, input_type, max_retries):
        import time as _t
        last_exc = None
        for attempt in range(max_retries):
            try:
                if self.provider == "nvidia":
                    return self._nvidia(batch, input_type)
                elif self.provider == "openrouter":
                    return self._openrouter(batch)
                elif self.provider == "local_tfidf":
                    return self._local_tfidf(batch)
                else:
                    raise ValueError(f"provider desconocido: {self.provider}")
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status in (429, 502, 503, 504) and attempt < max_retries - 1:
                    _t.sleep(2 ** attempt)
                    last_exc = exc
                    continue
                raise
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt < max_retries - 1:
                    _t.sleep(2 ** attempt)
                    last_exc = exc
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("embed falló sin excepción registrada")

    def _nvidia(self, batch, input_type):
        key = os.environ.get("NVIDIA_API_KEY")
        if not key:
            raise RuntimeError("Falta NVIDIA_API_KEY")
        r = requests.post(
            NVIDIA_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"input": batch, "model": self.model,
                  "input_type": input_type,
                  "encoding_format": "float", "truncate": "END"},
            timeout=60,
        )
        r.raise_for_status()
        return [np.array(item["embedding"], dtype=np.float32)
                for item in r.json()["data"]]

    def _openrouter(self, batch):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("Falta OPENROUTER_API_KEY")
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"input": batch, "model": self.model},
            timeout=60,
        )
        r.raise_for_status()
        return [np.array(item["embedding"], dtype=np.float32)
                for item in r.json()["data"]]
