# Eyes v4 — Deployment Plan

> **Status (continuation, 2026):** **Path C is live in /app.** Eyes v4
> ships via the rewritten `inference-server/eyes/` container running
> `transformers + peft` directly (no llama.cpp). The trained v4 LoRA
> adapter is the on-disk artefact at `/srv/AI-Stylist/eyes_v4_adapter/`
> on Hetzner and is volume-mounted into the container at `/adapter:ro`.
> v3 GGUFs are retired; Gemini stays as the DB-override fallback.

---

## TL;DR — what shipped this session

| Asset | Where it lives | Size |
| --- | --- | --- |
| Eyes v4 server runtime (Transformers + PEFT) | `/app/inference-server/eyes/main.py` | 21 KB |
| Eyes v4 container image recipe | `/app/inference-server/eyes/Dockerfile` | 3 KB |
| Pinned ML deps | `/app/inference-server/eyes/requirements.txt` | 2 KB |
| Trained Eyes v4 LoRA adapter | `/srv/AI-Stylist/eyes_v4_adapter/` (Hetzner) | 22 MB |
| Base model on HF Hub (gated) | `google/gemma-4-E2B-it` | 5 GB bf16 |
| Unsloth → GGUF Colab generator (back-out path) | `/app/scripts/build_eyes_unsloth_gguf_notebook.py` | TBD (Phase V4.4) |

---

## Architecture — what changed vs. v3

| Concern | v3 (May 2026) | v4 (this session) |
| --- | --- | --- |
| Inference engine | `llama-server` (compiled C++, GGUF) | `transformers` (PyTorch, native HF weights) |
| Quantization | GGUF Q4_K_M (mixed) | optimum-quanto **int4** weight-only |
| LoRA delivery | Merged into base, re-converted to GGUF | Live `/adapter` directory via `PeftModel` |
| Image input | OpenAI-style `image_url` content-part | Native `{"type":"image","image": PIL}` in chat template |
| Audio input | n/a (mmproj had no audio decoder mapping in GGUF) | **Native** via `POST /transcribe` |
| Resident memory | ~3.7 GB peak | ~3.1 GB peak |
| First-boot cold start | ~25 s | ~60-120 s (one-time HF download + bf16→int4 quantize) |
| Restart from warm cache | ~12 s | ~30 s |
| Backend client contract | `POST /predict` (custom JSON) | **UNCHANGED** — same `PredictIn`/`PredictOut` shape |

The backend's `garment_vision._call_gemma_space` needs **zero changes**.

---

## Deployment runbook (Hetzner CPX32)

This is the cookbook to flip production from "Gemini fallback" back to
"self-hosted Gemma-4 v4" once you've validated v4 in staging.

### Pre-flight

1. **Confirm the adapter is in place on Hetzner**:
   ```bash
   ls -la /srv/AI-Stylist/eyes_v4_adapter/
   # Expect adapter_config.json + adapter_model.safetensors (22 MB).
   stat -c '%s' /srv/AI-Stylist/eyes_v4_adapter/adapter_model.safetensors
   # Must be > 1 000 000 bytes. If it's 40 bytes, the file is empty —
   # re-download from the highest-step checkpoint in Drive.
   ```

2. **Confirm `EYES_HF_TOKEN` is set** in `/srv/AI-Stylist/deploy/.env`.
   The base model is gated; the container needs a token with access to
   `google/gemma-4-E2B-it`.

3. **Stop the old eyes container**:
   ```bash
   cd /srv/AI-Stylist
   docker compose -f deploy/docker-compose.yml stop eyes
   ```

### Wire the volume mount

Append to the `eyes` service in `deploy/docker-compose.yml`:

```yaml
services:
  eyes:
    # ... existing build / image / port config ...
    volumes:
      - eyes-cache:/models                       # HF weights cache (unchanged)
      - /srv/AI-Stylist/eyes_v4_adapter:/adapter:ro   # NEW for v4
    environment:
      EYES_BASE_MODEL: google/gemma-4-E2B-it
      EYES_ADAPTER_DIR: /adapter
      EYES_QUANT: int4
      EYES_COMPUTE_DTYPE: bfloat16
      EYES_HF_TOKEN: ${EYES_HF_TOKEN}
      EYES_API_TOKEN: ${EYES_API_TOKEN}
      LOG_LEVEL: INFO
```

The old `EYES_MODEL_FILE` / `EYES_MMPROJ_FILE` / `EYES_MODEL_REPO`
variables are no longer read; remove them or leave them as dead env
(the container silently ignores unknown vars).

### Build + boot the new image

```bash
docker compose -f deploy/docker-compose.yml build --no-cache eyes
docker compose -f deploy/docker-compose.yml up -d --force-recreate eyes

# Tail the logs through cold start. First boot downloads ~5 GB of
# Gemma-4 weights into the HF cache volume; budget ~10 min over a
# typical Hetzner link.
docker compose -f deploy/docker-compose.yml logs -f eyes
```

You should see, in order:
```
INFO dressapp-eyes: DressApp Eyes v4 (transformers+peft) starting up
INFO dressapp-eyes: loading base model google/gemma-4-E2B-it ...
... (download progress)
INFO dressapp-eyes: base model loaded in 94.3s
INFO dressapp-eyes: attaching LoRA adapter from /adapter
INFO dressapp-eyes: LoRA adapter attached in 1.8s
INFO dressapp-eyes: READY — base=google/gemma-4-E2B-it adapter=True vision=True audio=True quant=int4 dtype=bfloat16 rss=1854 MB
```

If `adapter=False`, the `/adapter` volume mount is wrong — the
container is serving the BASE (un-fine-tuned) Gemma-4. Stop and fix
before flipping production traffic.

### Verify

```bash
# Liveness
curl -s http://localhost:7860/healthz | jq .
# {
#   "status": "ok",
#   "base_model": "google/gemma-4-E2B-it",
#   "adapter_loaded": true,
#   "vision_enabled": true,
#   "audio_enabled": true,
#   "quant_method": "int4",
#   "compute_dtype": "bfloat16",
#   "resident_mb": 1860,
#   "uptime_s": 47
# }

# Vision smoke test — pick any test image
B64=$(base64 -w 0 < /srv/AI-Stylist/test_images/sample_shirt.jpg)
curl -s -X POST http://localhost:7860/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EYES_API_TOKEN" \
  -d "$(jq -n --arg b64 "$B64" '{
        prompt: "Describe this garment in one short sentence.",
        image_b64: $b64,
        max_tokens: 80
      }')" | jq .

# STT smoke test — ~5 s wav
curl -s -X POST http://localhost:7860/transcribe \
  -H "Authorization: Bearer $EYES_API_TOKEN" \
  -F "file=@sample_voice.wav" \
  -F "language=English" | jq .
```

### Flip production to Gemma

```bash
# Run inside any backend container (or directly against Mongo Atlas)
# to switch the live override from "gemini" back to "gemma":
docker compose -f deploy/docker-compose.yml exec backend python -c \
  "import asyncio; from app.services.eyes_override import set_override; \
   print(asyncio.run(set_override('gemma', by_email='ops@dressapp.co')))"
```

The runtime override is read every 5 s; new analyze calls will be
served by the self-hosted v4 within seconds.

### Rollback (if Eyes v4 misbehaves)

```bash
# Instantly route 100% of traffic back to Gemini — no code change:
docker compose -f deploy/docker-compose.yml exec backend python -c \
  "import asyncio; from app.services.eyes_override import set_override; \
   print(asyncio.run(set_override('gemini', by_email='ops@dressapp.co')))"
```

This bypasses the eyes container entirely; you can leave the
misbehaving container running while you debug.

---

## Why we picked Path C over Path A (wait for upstream) / Path B (Unsloth GGUF)

| Criterion | Path A (wait) | Path B (Unsloth) | **Path C (chosen)** |
| --- | --- | --- | --- |
| Ships today | ❌ | ⚠️ GPU Colab required | ✅ |
| Production latency | ~3 s | ~3 s | 30–60 s (CPU) |
| Quality after quantization | High (Q4_K_M) | High (Q4_K_M) | High (int4 quanto) |
| Code change required | None | None | This commit |
| Adapter handling | Runtime LoRA flag on llama-server | Merged + reconverted | Runtime `PeftModel` |
| Future-proof | ⚠️ depends on upstream merge | ⚠️ depends on Unsloth stability | ✅ pure HF stack |
| Memory on CPX32 | ~3.7 GB | ~3.7 GB | ~3.1 GB |

The user explicitly accepted the CPU latency trade-off, citing
"Gemma-4 runs fluently on Raspberry Pi at Q4". That mental model holds:
optimum-quanto int4 weight-only is the closest HF-native analogue to
llama.cpp's Q4_K_M, with comparable footprint.

Path B (Unsloth) remains scaffolded as a **future-flip option** —
see `/app/scripts/build_eyes_unsloth_gguf_notebook.py` (Phase V4.4).
If Unsloth's Gemma-4 multimodal GGUF export stabilises, the team can
generate v4 GGUFs and revert the container to the previous llama.cpp
pipeline without touching the backend.

---

## Audio pipeline migration (Phase V4.2 + V4.3)

* **STT (Speech → Text)** — `POST /transcribe` on this container
  replaces Groq Whisper. Backend wiring is the next phase (V4.2):
  see `plan.md`.
* **TTS (Text → Speech)** — **Deepgram is retired**. Gemma-4 has no
  audio decoder. Frontend will use `window.speechSynthesis` (web)
  and `@capacitor-community/text-to-speech` (mobile via Capacitor)
  through a thin abstraction in `frontend/src/lib/tts.js`.
  See V4.3 in `plan.md`.

---

## Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-05-15 | Production runs `EYES_PROVIDER=gemini` (DB override), v3 GGUFs retired | v3 was built off a wrong-class merge; quality untrusted |
| 2026-05-15 | `local_eyes_runtime.py` in backend reverted | Wrong architectural layer — backend HTTP-calls a sidecar |
| 2026-05-15 | Eyes v4 deployment **deferred** | Blocked on upstream Gemma-4 LoRA → GGUF support |
| 2026 (this session) | **Path C selected and shipped** | User accepts CPU latency on CPX32; cleanest production path today |
| 2026 (this session) | `dressapp-eyes` container engine: `llama-server` → `transformers + peft` | Sidesteps the GGUF blocker entirely |
| 2026 (this session) | Quantization: optimum-quanto int4 | Closest HF-native analogue to llama.cpp Q4_K_M on x86 CPU |
| 2026 (this session) | LoRA adapter delivery: volume mount `/adapter:ro` | No HF re-upload, no image rebake, instant swap |
| 2026 (this session) | STT supplier: Groq Whisper → Gemma-4 audio tower | Confirmed multimodal capability per `ai.google.dev/gemma/docs/capabilities/audio` |
| 2026 (this session) | TTS supplier: Deepgram → `window.speechSynthesis` | Gemma-4 has no audio decoder; native browser/OS TTS is faster and free |
