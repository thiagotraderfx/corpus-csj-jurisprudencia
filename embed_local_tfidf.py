"""TF-IDF completo: guarda vocab + idf para que queries funcionen."""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
CHUNKS = ROOT / "chunks.jsonl"
OUT = ROOT / "embeddings"
OUT.mkdir(exist_ok=True)

MAX_FEATURES = 2000
TOKEN_RE = re.compile(r"[a-záéíóúñü]{2,}")

def tokenize(t):
    return TOKEN_RE.findall(t.lower())

chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]
texts = [c["text"] for c in chunks]
tokenized = [tokenize(t) for t in texts]

global_counter = Counter()
for toks in tokenized:
    global_counter.update(set(toks))
vocab_list = [w for w, _ in global_counter.most_common(MAX_FEATURES)]
vocab = {w: i for i, w in enumerate(vocab_list)}

n_docs = len(texts)
df = Counter()
for toks in tokenized:
    for w in set(toks):
        if w in vocab:
            df[w] += 1
idf = {w: math.log((1 + n_docs) / (1 + df[w])) + 1 for w in vocab}

vectors = []
for toks in tokenized:
    vec = np.zeros(len(vocab), dtype=np.float32)
    tf = Counter(w for w in toks if w in vocab)
    for w, count in tf.items():
        vec[vocab[w]] = count * idf[w]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    vectors.append(vec)

arr = np.array(vectors, dtype=np.float32)
np.save(OUT / "passages.npy", arr)

ids = [
    {"chunk_id": c["chunk_id"], "providencia": c.get("providencia"),
     "section": c.get("section"), "md_url": c.get("md_url"),
     "raw_url": c.get("raw_url")}
    for c in chunks
]
(OUT / "passages_ids.jsonl").write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in ids) + "\n",
    encoding="utf-8")

meta = {
    "provider": "local_tfidf",
    "model": f"tfidf-{len(vocab)}",
    "dim": int(arr.shape[1]),
    "n_passages": int(arr.shape[0]),
    "vocab": vocab_list,
    "idf": idf,
    "tokenizer": "lowercase-[a-záéíóúñü]{2,}",
}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

print(f"[OK] TF-IDF persistido")
print(f"     matriz: {arr.shape} ({arr.nbytes:,} bytes)")
print(f"     vocab:  {len(vocab)} términos")
print(f"     idf:    guardado en meta.json")
