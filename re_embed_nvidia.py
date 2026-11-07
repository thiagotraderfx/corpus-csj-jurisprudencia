"""Re-embed NVIDIA resumible por checkpoint."""
import json, os, sys, time
import numpy as np
import requests
from pathlib import Path

ROOT = Path.cwd()
EMB = ROOT / "embeddings"
CHUNKS = ROOT / "chunks.jsonl"
CKPT = EMB / "nvidia_ckpt.npy"
CKPT_IDS = EMB / "nvidia_ckpt_ids.jsonl"

API_KEY = os.environ.get("NVIDIA_API_KEY")
if not API_KEY:
    sys.exit("Falta NVIDIA_API_KEY")
URL = "https://integrate.api.nvidia.com/v1/embeddings"
MODEL = "nvidia/nemotron-3-embed-1b"
BATCH = 10

def embed_batch(batch, retries=5):
    for attempt in range(retries):
        try:
            r = requests.post(URL,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"input": batch, "model": MODEL, "input_type": "passage",
                      "encoding_format": "float", "truncate": "END"},
                timeout=120)
            r.raise_for_status()
            return [item["embedding"] for item in r.json()["data"]]
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"    retry {attempt+1}/{retries} en {wait}s: {type(exc).__name__}: {str(exc)[:80]}", flush=True)
            time.sleep(wait)

chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"Chunks: {len(chunks)}")

all_vecs, start_idx = [], 0
if CKPT.is_file() and CKPT_IDS.is_file():
    try:
        cv = list(np.load(CKPT))
        ci = [json.loads(l)["chunk_id"] for l in CKPT_IDS.read_text(encoding="utf-8").splitlines() if l.strip()]
        if [c["chunk_id"] for c in chunks[:len(ci)]] == ci:
            all_vecs, start_idx = cv, len(cv)
            print(f"Resume desde {start_idx}/{len(chunks)}")
        else:
            print("Checkpoint inválido, desde 0")
    except Exception as e:
        print(f"Checkpoint error: {e}")

t0 = time.time()
for i in range(start_idx, len(chunks), BATCH):
    bc = chunks[i:i+BATCH]
    try:
        all_vecs.extend(embed_batch([c["text"] for c in bc]))
    except Exception as exc:
        print(f"\n[FAIL] batch {i}: {type(exc).__name__}: {exc}")
        arr = np.array(all_vecs, dtype=np.float32)
        np.save(CKPT, arr)
        ids_ck = [{"chunk_id": c["chunk_id"]} for c in chunks[:len(all_vecs)]]
        CKPT_IDS.write_text("\n".join(json.dumps(x) for x in ids_ck) + "\n", encoding="utf-8")
        print(f"Checkpoint guardado: {arr.shape}")
        sys.exit(1)

    done = i + len(bc)
    if (i // BATCH) % 10 == 9:
        arr = np.array(all_vecs, dtype=np.float32)
        np.save(CKPT, arr)
        ids_ck = [{"chunk_id": c["chunk_id"]} for c in chunks[:len(all_vecs)]]
        CKPT_IDS.write_text("\n".join(json.dumps(x) for x in ids_ck) + "\n", encoding="utf-8")
        print(f"  {done}/{len(chunks)} ({done/len(chunks)*100:.1f}%)  {time.time()-t0:.0f}s", flush=True)

arr = np.array(all_vecs, dtype=np.float32)
np.save(EMB / "passages.npy", arr)
ids = [{"chunk_id": c["chunk_id"], "providencia": c.get("providencia"),
        "section": c.get("section"), "md_url": c.get("md_url"),
        "raw_url": c.get("raw_url")} for c in chunks]
(EMB / "passages_ids.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in ids) + "\n", encoding="utf-8")
meta = {"provider": "nvidia", "model": MODEL, "dim": int(arr.shape[1]),
        "n_passages": int(arr.shape[0]),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
(EMB / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
CKPT.unlink(missing_ok=True)
CKPT_IDS.unlink(missing_ok=True)
print(f"\nOK: {arr.shape} en {time.time()-t0:.0f}s")
