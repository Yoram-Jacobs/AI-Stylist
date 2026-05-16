# Notebook patch — export the missing mmproj for Phase 2

Add the cells below to **`Copy of Eyes_merge_gguf.ipynb`**, AFTER the
existing GGUF conversion + quantisation cells (so they run against the
same `MERGED_DIR` / `GGUF_DIR` already on disk) and BEFORE the final
upload cell that pushes everything to the GGUF repo.

## Why this is needed

The current notebook calls `convert_hf_to_gguf.py` once — that script
writes the *language* tensors only. Gemma-4 E2B's vision_tower lives
in a separate sub-module of the merged HF model and is dropped
from the default GGUF output. To enable image input via
`llama-cpp-python` / `llama.cpp`, you need a **second** conversion
run with `--mmproj`, which extracts only the vision encoder + the
projection layer that maps SigLIP embeddings into the LLM's
embedding space. The resulting file is much smaller (≈500 MB at F16)
because it skips the LLM weights entirely.

Note: your LoRA fine-tune was text-only — the merge log warns
*"Found missing adapter keys for `vision_tower.*` and `audio_tower.*`"*.
That's expected and harmless. The merged model still contains the
**unmodified base** Gemma-4 E2B vision tower, which is exactly what
we want to export.

## Cell A — markdown header

```
## 5b · Export multimodal projector (mmproj) for Phase 2 vision
```

## Cell B — code

```python
import os, time

# llama.cpp must already be cloned / built by the cell that produced
# phase6-f16.gguf. Re-discover its path so this cell stands alone.
LLAMA_CPP_DIR = "/content/llama.cpp"
assert os.path.isdir(LLAMA_CPP_DIR), (
    f"Expected llama.cpp at {LLAMA_CPP_DIR}. Re-run the conversion cell first."
)

MMPROJ_OUT = f"{GGUF_DIR}/mmproj-Gemma4E2B-f16.gguf"

t0 = time.time()
print("Exporting vision_tower + projector to mmproj GGUF...")

# `--mmproj` flips convert_hf_to_gguf.py into projector-export mode.
# It reads the same merged model dir, but writes ONLY the vision
# encoder + projection layer to a separate GGUF. F16 is the right
# trade-off for a vision encoder — it's tiny relative to the LLM and
# Q4 hurts vision quality more than it helps file size.
!python {LLAMA_CPP_DIR}/convert_hf_to_gguf.py \
    {MERGED_DIR} \
    --outfile {MMPROJ_OUT} \
    --outtype f16 \
    --mmproj

assert os.path.isfile(MMPROJ_OUT), (
    f"convert_hf_to_gguf.py did not produce {MMPROJ_OUT}. "
    "If you see 'Architecture gemma4 has no vision/audio tower' the"
    " merged model is not multimodal — re-run cell 2 (Merge LoRA)"
    " using AutoModelForImageTextToText, not AutoModelForCausalLM."
)
print(f"mmproj written in {time.time()-t0:.1f}s")
!ls -lh {MMPROJ_OUT}
```

## Cell C — push the mmproj alongside the existing GGUFs

Extend (or duplicate) your existing upload cell to push the new file:

```python
from huggingface_hub import HfApi
api = HfApi(token=HF_TOKEN)

api.upload_file(
    path_or_fileobj=MMPROJ_OUT,
    path_in_repo="mmproj-Gemma4E2B-f16.gguf",
    repo_id=REPO_GGUF,           # "Yoram-Jacobs/dressapp-eyes-gguf"
    repo_type="model",
    token=HF_TOKEN,
)
print("Pushed mmproj to", REPO_GGUF)
```

## After you've pushed it

In the HF Space (`Yoram-Jacobs/dressapp-eyes-gguf`), open `Dockerfile`
and:

* Uncomment the **Phase 2: vision projector** `RUN` block (the
  `hf_hub_download` for `mmproj-Gemma4E2B-f16.gguf`).
* Uncomment the `ENV LLAMA_MMPROJ_PATH=/models/mmproj-Gemma4E2B-f16.gguf`
  line directly below it.

Commit → the Space rebuilds → `/healthz` will report
`vision_enabled: true` → `/predict` calls with `image_b64` start
producing real garment analyses.
