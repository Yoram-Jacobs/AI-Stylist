# Eyes v4 — Deployment Plan

> **Status (May 2026):** Eyes v4 LoRA training is complete; **deployment
> is blocked on upstream Gemma-4 LoRA → GGUF conversion support** in
> `llama.cpp`. Production currently runs `EYES_PROVIDER=gemini`
> (Gemini-2.5-Flash via the Emergent LLM key). The trained v4 adapter
> is preserved as a durable artefact and can be deployed in ~2 hours
> once the blocker clears.

This document records what we have, why we're not deploying it yet,
and the three concrete paths to actually ship it once we are. Future
you (or the next agent) reads this first.

---

## TL;DR

| Asset | Where it lives | Size |
| --- | --- | --- |
| Trained Eyes v4 LoRA | `/srv/AI-Stylist/eyes_v4_adapter/` (Hetzner) **and** Drive `Eyes_v4_run/checkpoint-N/` | 22 MB |
| Notebook that produced it | `/app/docs/notebooks/Eyes_FineTune_v4_Gemma4.ipynb` | 64 KB |
| Generator for that notebook | `/app/scripts/build_eyes_finetune_v4_notebook.py` | 65 KB |
| Base model on HF Hub | `google/gemma-4-E2B-it` (gated) | 5 GB bf16 |
| Pre-converted base GGUF | `ggml-org/gemma-4-E2B-it-GGUF` (`gemma-4-E2B-it-Q8_0.gguf`) | 4.97 GB |
| Pre-converted mmproj GGUF | `ggml-org/gemma-4-E2B-it-GGUF` (`mmproj-gemma-4-E2B-it-Q8_0.gguf`) | 532 MB |

---

## Why production isn't using Eyes v4 right now

Three things have to be true to deploy it through the existing
`inference-server/eyes` (llama.cpp + GGUF) pipeline:

1. ✅ A working **Gemma-4 base GGUF**. Solved — pre-converted by
   `ggml-org` and downloadable via `hf_hub_download`.
2. ✅ A working **Gemma-4 mmproj GGUF**. Same.
3. ❌ A working **Eyes v4 LoRA GGUF** (or a merged Eyes v4 base GGUF).
   **This is the blocker.**

`llama.cpp/convert_lora_to_gguf.py` doesn't yet have Gemma-4 in its
architecture map. We tried it on the trained adapter and it produced a
GGUF with `n_tensors = 0` — metadata only, no weights. The full-model
converter `convert_hf_to_gguf.py` similarly rejects
`Gemma4ForConditionalGeneration` ("Model `Gemma4Model` is not
supported"). PR is in flight; merge ETA unknown but likely days/weeks.

In the meantime the existing v3 GGUFs at
`Yoram-Jacobs/dressapp-eyes-gguf` are **suspect** — they were built off
a wrong-class merge (`Gemma3ForConditionalGeneration` instead of the
multimodal Gemma-4 head). Production therefore runs
`EYES_PROVIDER=gemini` until v4 is shippable.

---

## Three paths to actually ship Eyes v4

### Path A — Wait for upstream (recommended for now)

* **What**: Track [llama.cpp issue #22735](https://github.com/ggml-org/llama.cpp/issues/22735)
  and the related Gemma-4 LoRA-export PR. When it merges, rebuild the
  eyes container (`Dockerfile` already pulls `LLAMA_CPP_REF=master`),
  then run `convert_lora_to_gguf.py --base google/gemma-4-E2B-it
  --outfile Eyes_v4_lora.gguf eyes_v4_adapter/`.
* **Cost**: €0, ~30 min of work when the day comes.
* **When**: Probably 1-3 weeks based on PR velocity.
* **Resulting deploy shape**: Push `Eyes_v4_lora.gguf` + the pre-converted
  base + mmproj to `Yoram-Jacobs/dressapp-eyes-gguf`, update env:
  ```
  EYES_MODEL_FILE=gemma-4-E2B-it-Q8_0.gguf
  EYES_MMPROJ_FILE=mmproj-gemma-4-E2B-it-Q8_0.gguf
  EYES_LORA_FILE=Eyes_v4_lora.gguf
  ```
  Then add a `--lora /models/Eyes_v4_lora.gguf` flag to the
  `llama-server` invocation in `inference-server/eyes/main.py`.
  llama-server applies LoRA at runtime; no merge needed.

### Path B — Unsloth `save_pretrained_gguf` (today, GPU)

Unsloth has Gemma-4 conversion patches landed in their fork:
`model.save_pretrained_gguf(directory, tokenizer, quantization_method="q4_k_m")`
emits a merged Q4_K_M GGUF directly. Documented working as of May
2026.

* **Where to run**: Fresh Colab session (`import unsloth` BEFORE
  `transformers`/`peft`, otherwise their numpy ABI patch fights ours
  and the kernel needs a restart).
* **Inputs**: The 22 MB adapter from Drive's
  `Eyes_v4_run/checkpoint-N/`.
* **Outputs**: A **merged** Q4_K_M GGUF (~3 GB) plus mmproj.
* **Caveat**: Last attempt hit `RuntimeError: numpy was upgraded
  mid-session` because we'd already imported transformers earlier in
  the kernel. Must be the very first import in a clean session.
* **After**: Upload the produced GGUFs to
  `Yoram-Jacobs/dressapp-eyes-gguf`, bump `EYES_MODEL_FILE` /
  `EYES_MMPROJ_FILE` in `deploy/.env`, `docker compose up -d eyes`.
  No code changes.

### Path C — Pivot eyes container to transformers + PEFT

Replace the llama.cpp + GGUF approach with a Python inference server
that loads `google/gemma-4-E2B-it` via `AutoModelForMultimodalLM` and
applies the LoRA via `PeftModel.from_pretrained`. Sidesteps GGUF
entirely.

* **Cost**:
  * On the current CPX32 (8 GB CPU): bf16 won't fit; int8 via
    bitsandbytes is feasible (~3 GB weights) but ~30-60 s per call.
  * On a Hetzner GEX44 GPU sidecar (~€60/mo): 3-5 s per call, fits
    cleanly.
* **When to pick it**: If upstream Gemma-4 LoRA conversion takes longer
  than expected AND you can stomach the latency hit / cost.
* **Implementation seed**: A previous iteration of the backend wired
  this up at `/app/backend/app/services/local_eyes_runtime.py` (now
  reverted — see git history). That code is the right shape for a
  thin FastAPI proxy inside the eyes container; lift the `analyze`
  function and merge logic verbatim, swap the chat template + image
  flow for the existing `inference-server/eyes/main.py` HTTP contract.

---

## Recovering the adapter if `/srv/AI-Stylist/eyes_v4_adapter/` is wiped

The trainer auto-saved checkpoints every 200 steps to
`gdrive:/DressApp_Gemma4_E2B_Training/Eyes_v4_run/checkpoint-N/`.
Each checkpoint has its own `adapter_config.json` +
`adapter_model.safetensors`. The notebook's recovery cell walks them
newest-first looking for a non-empty `adapter_model.safetensors` (>1
KB), so even if the highest-step checkpoint is truncated, an earlier
one will work.

Steps:
1. Drive web UI → `My Drive/DressApp_Gemma4_E2B_Training/Eyes_v4_run/`.
2. Pick the highest-numbered `checkpoint-N` whose
   `adapter_model.safetensors` is many MB (right-click → Details).
3. Download the folder, extract, copy
   `adapter_config.json` + `adapter_model.safetensors` (and any
   `tokenizer*.json`) to `/srv/AI-Stylist/eyes_v4_adapter/` on
   Hetzner.

---

## Environment & code hooks already in place

* `inference-server/eyes/Dockerfile` builds `llama-server` from
  llama.cpp `master` — already supports Gemma-4 *inference*. No
  rebuild needed when we eventually drop in v4 GGUFs.
* `deploy/.env` reads:
  ```
  EYES_PROVIDER=gemma | gemini   # set to gemini for v4-pending fallback
  EYES_GEMMA_SPACE_URL=http://eyes:7860
  EYES_MODEL_FILE=…              # bumped to v4 once GGUF exists
  EYES_MMPROJ_FILE=…
  ```
* `backend/app/services/garment_vision.py` `_call_gemma_space` is the
  HTTP client that talks to `dressapp-eyes`. **Untouched** for v4 —
  the contract stays the same; we just swap the GGUF behind the
  llama-server.

---

## Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-05-15 | Production runs `EYES_PROVIDER=gemini`, not v3 GGUFs | v3 was built off a wrong-class merge (`Gemma3ForConditionalGeneration`); quality untrusted |
| 2026-05-15 | `local_eyes_runtime.py` in backend reverted | Wrong layer — backend HTTP-calls a sidecar, doesn't load models in-process |
| 2026-05-15 | Eyes v4 deployment deferred | Blocked on upstream Gemma-4 LoRA → GGUF support |
| TBD | Pick Path A / B / C | When latency, cost, or upstream merge tips the calculus |
