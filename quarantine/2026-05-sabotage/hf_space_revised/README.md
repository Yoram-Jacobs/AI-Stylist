---
title: DressApp Eyes
emoji: 👁️
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
short_description: Self-hosted Gemma-4 E2B for garment analysis (DressApp).
---

# DressApp Eyes (Phase 1 — text-only Q4_K_M)

FastAPI wrapper around a fine-tuned **Gemma-4 E2B** GGUF (Q4_K_M, ~3.4 GB),
served via `llama-cpp-python` on a Docker Space (free CPU Basic tier).

## Endpoints

* `GET /healthz` — 200 once the model is loaded.
* `POST /predict` — chat completion. Body shape:
  ```json
  {"prompt": "...", "system": "...", "max_tokens": 512,
   "temperature": 0.2, "json_mode": false,
   "image_b64": null}
  ```
  `image_b64` is accepted for forward-compat with Phase 2; ignored
  when no `mmproj-*.gguf` is configured (response carries
  `vision_disabled: true`).

## Build secret

The model repo `Yoram-Jacobs/dressapp-eyes-gguf` is private, so the
Dockerfile pulls the GGUF at build time using a BuildKit secret named
`EYES_HF_TOKEN`. Configure it in *Space Settings → Secrets* with
**Read** scope for that repo.

## Phase 2 (vision)

1. Run the `Export multimodal projector (mmproj)` cell at the bottom
   of `Eyes_merge_gguf.ipynb` to generate
   `mmproj-Gemma4E2B-f16.gguf` and push it to the model repo.
2. In this Space’s Dockerfile, uncomment the second `RUN` block
   (the mmproj download) and the `ENV LLAMA_MMPROJ_PATH=...` line.
3. Redeploy. `app.py` auto-detects, loads `Llava15ChatHandler`,
   and starts using `image_b64` for real vision — no backend
   changes required.
