# Eyes v4 — Deployment Plan

> **Status — May 2026.**
> * **Path C code is in `/app`** (Transformers + PEFT container, CPU-only,
>   int4-quantized, Eyes v4 LoRA mounted at `/adapter:ro`). The container
>   is unit-clean and produces stable health/predict/transcribe
>   responses. **Awaiting first-time roll-out to Hetzner CPX32.**
> * **Path B (Unsloth → GGUF) remains BLOCKED.** See
>   "Known issues — Path B status" below for the two unresolved
>   converter bugs. Don't plan around it landing soon.
> * **Production today.** `EYES_PROVIDER` override in Mongo is set to
>   `gemini` (Phase V3 retirement, May 2026). All Eyes calls go to
>   Gemini. Flipping to self-hosted Gemma-4 is a one-line override change
>   AFTER Phase 4 below passes.

---

## TL;DR — what's ready to ship

| Asset | Where it lives | Size |
| --- | --- | --- |
| Eyes v4 server runtime (Transformers + PEFT) | `/app/inference-server/eyes/main.py` | 21 KB |
| Eyes v4 container image recipe | `/app/inference-server/eyes/Dockerfile` | 3 KB |
| Pinned ML deps (incl. CPU torch, transformers 4.57+, quanto, peft) | `/app/inference-server/eyes/requirements.txt` | 2 KB |
| Trained Eyes v4 LoRA adapter | `/srv/AI-Stylist/eyes_v4_adapter/` (Hetzner) | 22 MB |
| Base model on HF Hub (gated) | `google/gemma-4-E2B-it` | 5 GB bf16 |
| Unsloth → GGUF Colab generator (back-out path, **blocked**) | `/app/scripts/build_eyes_unsloth_gguf_notebook.py` | 38 KB |
| Generated notebook from above | `/app/docs/notebooks/Eyes_v4_Unsloth_GGUF.ipynb` | 38 KB (**stale**: older than the generator; needs regen) |

---

## Architecture — what changed vs. v3

| Concern | v3 (May 2026) | **v4 (this rollout)** |
| --- | --- | --- |
| Inference engine | `llama-server` (compiled C++, GGUF) | `transformers` (PyTorch, native HF weights) |
| Quantization | GGUF Q4\_K\_M (mixed) | optimum-quanto **int4** weight-only |
| LoRA delivery | Merged into base, re-converted to GGUF | Live `/adapter` directory via `PeftModel` |
| Image input | OpenAI-style `image_url` content-part | Native `{"type":"image","image": PIL}` in chat template |
| Audio input | n/a (mmproj had no audio decoder mapping in GGUF) | **Native** via `POST /transcribe` (Gemma-4 audio tower) |
| Build toolchain in image | cmake, gcc/g++, curl/openssl headers | **None** — pure Python wheels |
| Resident memory (peak) | ~3.7 GB | ~3.1 GB |
| First-boot cold start | ~25 s | ~60–120 s (one-time HF download + bf16→int4 quantize) |
| Restart from warm cache | ~12 s | ~30 s |
| Backend client contract | `POST /predict` (custom JSON) | **UNCHANGED** — same `PredictIn` / `PredictOut` shape |

The backend's `garment_vision._call_gemma_space` needs **zero changes**.
Same goes for `eyes_override.py` (DB-backed runtime switch).

---

## Deployment runbook — first-time roll-out (Hetzner CPX32)

This walks the cold-path: there is NO running v4 container on the VPS
yet. After this completes you'll have v4 serving alongside the
production traffic, with a single Mongo flip away from being live.

Reference host (per `CONCRETE_FACTS.md`):

```
ssh root@178.104.114.210         # CPX32, 4 vCPU AMD, 8 GB RAM, no GPU
cd /srv/AI-Stylist/deploy        # working directory for all compose commands
```

### Phase 0 — Pre-flight (10 min)

Run all of these from the VPS. They're idempotent — safe to run again
if you're rolling back into the runbook mid-way.

**0.1 — Disk space.**

```bash
df -h /var/lib/docker /srv
```

Need at least **15 GB free** combined: ~5 GB for the Gemma-4 weight
cache (`HF_HOME` volume), ~3 GB for the new image, ~7 GB headroom for
Docker layer churn during build. If you're below that, the easiest
reclaim is to drop the retired v3 GGUFs out of the eyes-cache volume
(see "Cleanup" at the bottom).

**0.2 — Confirm the adapter is in place.**

```bash
ls -la /srv/AI-Stylist/eyes_v4_adapter/
#   expect: adapter_config.json + adapter_model.safetensors (~22 MB)

stat -c '%s' /srv/AI-Stylist/eyes_v4_adapter/adapter_model.safetensors
#   must be > 1 000 000 bytes.
#   If it's ≤ 40 bytes the file is an empty placeholder from a
#   half-completed download — re-pull the highest-step checkpoint from
#   Drive (the training Colab writes there).
```

**0.3 — HF token is set AND valid.**

```bash
grep -c '^EYES_HF_TOKEN=' /srv/AI-Stylist/deploy/.env
#   must print 1.

# Live-validate against the gated model:
source /srv/AI-Stylist/deploy/.env
curl -sf -I \
  -H "Authorization: Bearer $EYES_HF_TOKEN" \
  "https://huggingface.co/google/gemma-4-E2B-it/resolve/main/config.json" \
  | head -1
#   must print "HTTP/2 200" or "HTTP/1.1 200 OK".
#   "401" / "403" → the token isn't authorised for gemma-4. Visit
#   https://huggingface.co/google/gemma-4-E2B-it and accept the
#   license under the same HF account.
```

**0.4 — `EYES_API_TOKEN` is set.** This is the bearer the backend
sends on every `/predict` call. Reuse the existing one from v3 —
don't rotate it as part of this rollout (one fewer moving part).

```bash
grep -c '^EYES_API_TOKEN=' /srv/AI-Stylist/deploy/.env
#   must print 1.
```

**0.5 — Outbound network egress works.** First boot needs to download
~5 GB from `huggingface.co`. Behind some Hetzner DCs the DNS can be
quirky.

```bash
getent hosts huggingface.co
curl -sf -o /dev/null -w "%{http_code}\n" https://huggingface.co/api/models/google/gemma-4-E2B-it
#   200 → good. Anything else → fix the network first.
```

**0.6 — Sync the repo on the VPS to current `main`.** This is what
brings `/app/inference-server/eyes/*` onto the box.

```bash
cd /srv/AI-Stylist
git fetch --all
git pull --ff-only
# Sanity-check that main.py is the v4 version, not the v3 llama-server proxy:
grep -q 'DressApp Eyes v4 (transformers+peft)' inference-server/eyes/main.py \
  && echo "v4 main.py present" \
  || { echo "WRONG main.py — abort"; exit 1; }
```

### Phase 1 — Update `docker-compose.yml`

Patch the `eyes` service in `/srv/AI-Stylist/deploy/docker-compose.yml`
so it (a) mounts the adapter directory read-only, (b) sets the v4 env
contract, (c) drops the v3 env vars.

```yaml
services:
  eyes:
    # existing build / image stanza stays (re-built in Phase 2 below).
    # IMPORTANT — preserve `container_name: dressapp-eyes` and the
    # internal network alias so the backend's EYES_GEMMA_SPACE_URL
    # (http://eyes:7860) keeps resolving.
    volumes:
      - eyes-cache:/models                              # HF weights cache (UNCHANGED)
      - /srv/AI-Stylist/eyes_v4_adapter:/adapter:ro     # NEW for v4
    environment:
      EYES_BASE_MODEL: google/gemma-4-E2B-it
      EYES_ADAPTER_DIR: /adapter
      EYES_QUANT: int4
      EYES_COMPUTE_DTYPE: bfloat16
      EYES_HF_TOKEN: ${EYES_HF_TOKEN}
      EYES_API_TOKEN: ${EYES_API_TOKEN}
      EYES_MAX_NEW_TOKENS: 1024
      EYES_MAX_AUDIO_SECONDS: 30
      EYES_GENERATE_TIMEOUT_S: 180
      LOG_LEVEL: INFO
    # No longer read by main.py — safe to remove:
    #   EYES_MODEL_FILE, EYES_MMPROJ_FILE, EYES_MODEL_REPO,
    #   EYES_LLAMA_FLAGS, EYES_LORA_FILE
```

The HEALTHCHECK in the Dockerfile already allows up to **15 min cold
start** (`start-period: 900s`) so don't add a compose-level
healthcheck that would shorten it.

### Phase 2 — Build + boot

```bash
cd /srv/AI-Stylist/deploy

# Stop the v3 container (or whichever is running today). This is the
# only step that interrupts Eyes — but since the Mongo override is
# currently "gemini", backend traffic doesn't notice.
docker compose stop eyes
docker compose rm -f eyes

# Build the v4 image. --no-cache is mandatory the first time because
# Docker doesn't know main.py changed (different base layers).
# Budget: ~6–10 min (torch CPU wheel download is the long pole).
docker compose build --no-cache eyes

# Boot it. Don't pass --force-recreate — the container was already
# removed above, so a plain `up -d` starts it fresh.
docker compose up -d eyes

# Tail logs through cold start. First boot downloads ~5 GB into the
# eyes-cache volume; budget ~10 min over a typical Hetzner link.
docker compose logs -f eyes
```

You should see, in order:

```
INFO dressapp-eyes: DressApp Eyes v4 (transformers+peft) starting up
INFO dressapp-eyes: loading base model google/gemma-4-E2B-it (dtype=torch.bfloat16, quant=int4, hf_token=set)
... (HF download progress; on first boot only)
INFO dressapp-eyes: base model loaded in 94.3s
INFO dressapp-eyes: attaching LoRA adapter from /adapter
INFO dressapp-eyes: LoRA adapter attached in 1.8s
INFO dressapp-eyes: READY — base=google/gemma-4-E2B-it adapter=True vision=True audio=True quant=int4 dtype=bfloat16 rss=1854 MB
```

The `READY` line is the gate. The four flags that must show `True`:

| Flag | If it's `False` |
| --- | --- |
| `adapter=True` | The `/adapter` mount is missing or empty. Re-check Phase 0.2. **Do not proceed** — you'd be serving the un-fine-tuned base model. |
| `vision=True` | `transformers` is too old or `AutoProcessor` couldn't load the image processor. Verify `pip show transformers` ≥ 4.57.1 inside the container. |
| `audio=True` | Same root cause; the audio tower's `feature_extractor` didn't come down with the processor. Less critical (vision is the main use case) but flag it. |
| `quant=int4` | optimum-quanto wasn't installed; the server transparently fell back to `bf16`. Memory will jump from ~3.1 GB → ~5.5 GB. Tight on CPX32 but survivable. |

### Phase 3 — Verify

**3.1 — Liveness.**

```bash
docker compose exec eyes \
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
```

**3.2 — Vision smoke test.** Pick any test image already on the VPS,
or scp one over:

```bash
source /srv/AI-Stylist/deploy/.env

B64=$(base64 -w 0 < /srv/AI-Stylist/test_images/sample_shirt.jpg)
docker compose exec eyes \
  curl -s -X POST http://localhost:7860/predict \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $EYES_API_TOKEN" \
    -d "$(jq -n --arg b64 "$B64" '{
          prompt: "Describe this garment in one short sentence.",
          image_b64: $b64,
          max_tokens: 80
        }')" | jq .
# Expected:
# {
#   "output": "A white cotton T-shirt with...",
#   "finish_reason": "stop",
#   "tokens_prompt": 1287,
#   "tokens_completion": 22,
#   "elapsed_ms": 31410,
#   "vision_used": true,
#   "vision_disabled": false
# }
```

On the CPX32 a vision predict completes in **30–60 s** — that's the
CPU-tax the user explicitly accepted. If `elapsed_ms` is > 120 000
you're swapping; check `docker compose exec eyes free -m` and confirm
nothing else on the VPS is eating RAM.

**3.3 — STT smoke test** (only meaningful if Phase V4.2 has wired the
backend to call this — see "Audio pipeline migration" below):

```bash
docker compose exec eyes \
  curl -s -X POST http://localhost:7860/transcribe \
    -H "Authorization: Bearer $EYES_API_TOKEN" \
    -F "file=@sample_voice.wav" \
    -F "language=English" | jq .
# Expected:
# {
#   "text": "I'd like to find a blazer to wear with my new jeans.",
#   "language": "English",
#   "duration_s": 4.2,
#   "elapsed_ms": 18430
# }
```

**3.4 — Round-trip from the backend container.** This is the test that
matters for production cut-over. It exercises the exact code path that
will fire once you flip the override.

```bash
docker compose exec backend python -c "
import asyncio
from app.services.garment_vision import _call_gemma_space
print(asyncio.run(_call_gemma_space(
    prompt='Quick health probe.',
    image_b64=None,
    timeout_s=120,
)))
"
```

Should return a `PredictOut`-shaped dict, not raise. If you get a
401, the backend's `EYES_API_TOKEN` doesn't match what the eyes
container sees — re-check Phase 0.4.

### Phase 4 — Flip the override (cut traffic over)

```bash
docker compose exec backend python -c "
import asyncio
from app.services.eyes_override import set_override
print(asyncio.run(set_override('gemma', by_email='ops@dressapp.co')))
"
```

The runtime override has a 5-second TTL cache, so new analyze calls
get routed to the self-hosted v4 within ~5 s. Watch the eyes logs
(`docker compose logs -f eyes`) for the first real production
`POST /predict` to confirm.

### Phase 5 — Rollback paths

**Instant: 100 % traffic back to Gemini.** No code change, no
restart, no downtime. The eyes container can keep running while you
debug it.

```bash
docker compose exec backend python -c "
import asyncio
from app.services.eyes_override import set_override
print(asyncio.run(set_override('gemini', by_email='ops@dressapp.co')))
"
```

**Heavier: revert the container itself.** Only needed if v4 has a
correctness bug AND you still need self-hosted (e.g., Gemini key is
out of quota). The git tag `eyes-v3-final` (if you cut one before
this roll-out) is the way back — `git checkout eyes-v3-final --
inference-server/eyes/` and rebuild. Pragmatically, the
`override: gemini` path is faster + safer in 99 % of incidents.

---

## Known issues / status of paths

### Path B (Unsloth → GGUF) — **BLOCKED**

The Colab notebook at `/app/docs/notebooks/Eyes_v4_Unsloth_GGUF.ipynb`
(generator at `/app/scripts/build_eyes_unsloth_gguf_notebook.py`) is
intentionally kept as the back-out plan, but currently does **not**
produce usable GGUFs. Two unresolved blockers as of this session:

1. **`KeyError: 'image_mean'`** inside Unsloth's patched
   `unsloth_convert_hf_to_gguf.py` (line ~2624) when the mmproj
   export tries to read SigLIP normalization stats. Gemma-4's
   `Gemma4ImageProcessor` doesn't serialise `image_mean` /
   `image_std` to `preprocessor_config.json` because the SigLIP tower
   bakes them into the model. The converter assumes they're always
   on disk and crashes if not. **Workaround sketched** in this
   session's chat history (inject SigLIP stats `[0.5, 0.5, 0.5]`
   into preprocessor_config + monkey-patch the converter) but not
   yet baked into the generator.
2. **`AssertionError: No main GGUF (non-mmproj) found in
   /content/eyes_v4_q4_k_m`** — Section 7's verify cell trips
   because either (a) `save_pretrained_gguf` failed silently on the
   main quantize step while still producing the mmproj, or (b) the
   file is written under a subdir not covered by the glob. **Status:
   diagnostic Colab snippet pending from the user** (`ls -la
   /content/eyes_v4_q4_k_m/` + a stderr capture of the last
   conversion subprocess).

**Also**: the notebook on disk (mtime 08:45) is **older than the
generator** (08:59). Anything we fix in the generator only lands after
`python3 /app/scripts/build_eyes_unsloth_gguf_notebook.py` is re-run
and the new `.ipynb` is committed.

There's a separate **audit document** in chat history with 7 P0/P1
issues in the generator (install command missing `--no-deps`,
`push_to_hub_gguf` passing tokenizer instead of full processor,
fragile `load_in_16bit=True` kwarg, telemetry stub missing reflective
fallback, etc.). Those are queued behind the two production blockers
above.

### Audio backend wiring — **pending V4.2**

The Eyes container ships `/transcribe` ready-to-use, but the backend
voice pipeline still calls Groq Whisper. The migration steps:

* Create `backend/app/services/eyes_audio.py` (sibling of
  `garment_vision.py`) that hits `POST /transcribe` on the eyes
  container with the same multipart upload shape Groq accepted.
* Replace the Whisper client import in `backend/app/services/logic.py`
  (or wherever `STT` is wired today; grep for `groq`) with the new
  helper.
* Drop `GROQ_API_KEY` from `.env` after a clean prod run.

This is **Phase V4.2** in `plan.md` — separate roll-out from this
container deployment.

### Frontend TTS migration — **pending V4.3**

Deepgram TTS is being retired in favour of native browser
`window.speechSynthesis` (web) + `@capacitor-community/text-to-speech`
(mobile). Gemma-4 has no audio decoder; the native browser/OS TTS is
both free and lower-latency. Tracked separately in `plan.md`.

---

## Path C vs A vs B — why we chose C

| Criterion | Path A (wait for upstream) | Path B (Unsloth GGUF) | **Path C (chosen)** |
| --- | --- | --- | --- |
| Ships today | ❌ | ⚠️ blocked (see above) | ✅ |
| Production latency | ~3 s | ~3 s | 30–60 s (CPU) |
| Quality after quantization | High (Q4\_K\_M) | High (Q4\_K\_M) | High (int4 quanto) |
| Code change required | None | None | This commit |
| Adapter handling | Runtime LoRA flag on llama-server | Merged + reconverted | Runtime `PeftModel` |
| Future-proof | ⚠️ depends on upstream merge | ⚠️ depends on Unsloth stability | ✅ pure HF stack |
| Memory on CPX32 | ~3.7 GB | ~3.7 GB | ~3.1 GB |

User cited "Gemma-4 runs fluently on Raspberry Pi at Q4" — the int4
quanto footprint is the closest HF-native analogue to llama.cpp's
Q4\_K\_M, and the rest of the toolchain (no C++ build, no GGUF
conversion) is cleaner.

Path B remains scaffolded as a **future-flip option** — see the
notebook + generator under `/app/scripts/` and `/app/docs/notebooks/`.
If Unsloth's Gemma-4 multimodal GGUF export stabilises (and the two
issues above are resolved), the team can flip the container back to
the llama.cpp pipeline without touching the backend.

---

## Operational notes

### First-boot disk usage

The `eyes-cache` Docker volume balloons to ~5.5 GB after the
Gemma-4 weights download. The `/var/lib/docker/overlay2/` partition
that hosts it must therefore have room. If you're scraping for
space, `dressapp_eyes-cache` is the right thing to grow, not delete.

### What survives container recreations

* HF weights cache (`eyes-cache:/models`) — survives.
  `docker compose up -d --force-recreate eyes` does NOT re-download.
* LoRA adapter (`/srv/AI-Stylist/eyes_v4_adapter`) — survives.
  It's a bind mount, not a managed volume.
* Inside-container state (uvicorn workers, asyncio.Lock) — does NOT
  survive. That's by design; the model is reloaded into RAM on every
  restart (~30 s warm).

### Cleanup of retired v3 artefacts

```bash
# v3 GGUFs may still be on disk under the eyes-cache volume. After
# you confirm v4 is healthy, drop them to recover ~10 GB:
docker run --rm -v dressapp_eyes-cache:/models alpine \
  sh -c "find /models -name '*.gguf' -print -delete"

# v3 llama-server binary (if you mounted it as a sibling) — drop it:
ls /srv/AI-Stylist/eyes_v3_bin/ 2>/dev/null && rm -rf /srv/AI-Stylist/eyes_v3_bin
```

### Memory pressure watchdog

A single `/predict` call peaks at ~3 GB resident. Two concurrent
predicts WOULD double that, but they can't — `main.py` serialises
generate() calls via `asyncio.Lock` (single-flight). If you ever
see `resident_mb > 4000` on `/healthz`, something else on the box
is leaking; check `docker stats`.

### Logs

```bash
docker compose logs -f eyes        # follow live
docker compose logs --tail=200 eyes | grep -E '(READY|ERROR|FAIL)'
```

Useful greps:
* `READY —` — start-of-life one-shot.
* `predict failed` / `transcribe failed` — request-level errors.
* `generation exceeded` — `/predict` hit `EYES_GENERATE_TIMEOUT_S`.
  Usually means RAM pressure (swapping).

---

## Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-05-15 | Production runs `EYES_PROVIDER=gemini` (DB override), v3 GGUFs retired | v3 was built off a wrong-class merge; quality untrusted |
| 2026-05-15 | `local_eyes_runtime.py` in backend reverted | Wrong architectural layer — backend HTTP-calls a sidecar |
| 2026-05-15 | Eyes v4 deployment **deferred** | Blocked on upstream Gemma-4 LoRA → GGUF support |
| 2026 (this session, earlier) | **Path C selected and shipped to `/app`** | User accepts CPU latency on CPX32; cleanest production path today |
| 2026 (this session, earlier) | `dressapp-eyes` container engine: `llama-server` → `transformers + peft` | Sidesteps the GGUF blocker entirely |
| 2026 (this session, earlier) | Quantization: optimum-quanto int4 | Closest HF-native analogue to llama.cpp Q4\_K\_M on x86 CPU |
| 2026 (this session, earlier) | LoRA adapter delivery: volume mount `/adapter:ro` | No HF re-upload, no image rebake, instant swap |
| 2026 (this session, earlier) | STT supplier: Groq Whisper → Gemma-4 audio tower | Confirmed multimodal capability per `ai.google.dev/gemma/docs/capabilities/audio` |
| 2026 (this session, earlier) | TTS supplier: Deepgram → `window.speechSynthesis` | Gemma-4 has no audio decoder; native browser/OS TTS is faster and free |
| 2026 (this session, now) | Path B (Unsloth GGUF) **still BLOCKED** on `KeyError: 'image_mean'` + "no main GGUF" | Diagnostic snippet pending from user; workaround sketched but not landed in generator |
| 2026 (this session, now) | V4_DEPLOY runbook restructured into Phase 0–5 first-roll-out shape | User is about to do the cold deploy; the old "update existing" structure didn't fit |
