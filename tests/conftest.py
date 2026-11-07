"""Configuración compartida de tests.

En CI (GitHub Actions) no están los assets del release (raw/, passages.npy).
Los tests que dependen de ellos se marcan skip si los archivos no existen.
Localmente, tras `gh release download v1.1.0`, se ejecutan todos.
"""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
EMBEDDINGS_NPY = REPO_ROOT / "embeddings" / "passages.npy"

# Tests que requieren passages.npy (release asset, no en git)
_ASSET_DEPENDENT = {
    "test_embeddings_consistent",
    "test_all_chunks_in_index",
}

def pytest_collection_modifyitems(config, items):
    if EMBEDDINGS_NPY.exists():
        return
    skip = pytest.mark.skip(
        reason="requiere passages.npy (gh release download v1.1.0)"
    )
    for item in items:
        if item.name in _ASSET_DEPENDENT:
            item.add_marker(skip)
