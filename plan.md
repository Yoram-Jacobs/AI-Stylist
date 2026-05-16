# DressApp — Development Plan (Core-first) **UPDATED (Eyes v3 / Gemma 4 E2B self-host LIVE on production VPS)**

> 📌 **Last in-chat session — 14 May 2026.** See
> [`docs/SESSION_2026_05_14.md`](./docs/SESSION_2026_05_14.md) for the
> full patch-by-patch log. TL;DR shipped in that session:
>
> * **Qwen + HF runtime calls fully retired** from `/app/backend`
>   (DashScope, FLUX, HF Inference API). Stylist now goes
>   straight to Gemini 2.5 Pro; image edits go to Nano Banana.
> * **Closet UX restored**: optimistic-first delete; new item card
>   shows a thumbnail immediately (raw bbox crop, swapped to clean
>   cutout 5–10 s later via background `_run_background_matte`).
> * **`/analyze` latency cut ~40 %** (47 s → 29 s on a 2-garment
>   outfit) by deferring rembg matting to a `BackgroundTask`. Flag
>   `DEFER_REMBG_ON_ANALYZE` (default `true`) is the kill-switch.
> * **One-pass Eyes retired.** Three CCP-Ninja benchmark runs proved
>   Gemini-Flash returns ≤1 garment per call regardless of prompt.
>   Production uses SegFormer + per-crop Eyes only. `EYES_ONE_PASS`
>   env var is no longer read.
> * **SegFormer accessory recall lifted from 0 % → 50–100 %** for
>   sunglasses / belt / bag / hat / purse via per-category min-area
>   thresholds in `clothing_parser.py`.
> * **Open thread:** Gemma-3n fine-tuning Colab notebook is
>   scaffolded but the model-class question is unresolved — do NOT
>   run as-is; clarify the HF class with the user first.
> * **Hetzner deploy of these patches is NOT done** — the preview
>   pod has them; the production VPS does not.

## 1) Objectives

### ✅ Production stabilisation (dressapp.co) — **SHIPPED & VERIFIED**
- ✅ **Hetzner build fix**: pinned `protobuf==5.29.6` to resolve dependency conflict.
- ✅ Removed legacy post-analysis duplicate detection (`find_potential_duplicate`) to reduce ML spend.
- ✅ Atlas upgrade: production DB moved to **10GB Atlas M10**.
- ✅ Duplicate-system UX: pre-flight hash duplicate detection only; star auto-demotion when original deleted.

### ✅ UX polish (Wave 1) — **SHIPPED**
- ✅ Brand logo lockups (`BrandLogo.jsx`) added to Login + TopNav.
- ✅ Closet search bar polish:
  - debounced live search
  - clear button
  - active-state ring
- ✅ Category filter improvements:
  - case-insensitive
  - synonym mapping (e.g. `Footwear` → `shoes`)
- ✅ PWA/favicon/manifest icons wired.
- ✅ `CHANGELOG.md` drafted; guidance to tag `v1.0-stable`.

### ✅ Marketplace Wave 1 — **SHIPPED**
- ✅ Auto-retire linked marketplace listings when closet item is deleted.
- ✅ Auto-list closet items to marketplace when item `source` flips to **Shared**.
- ✅ Merchant card hydration on listing detail:
  - **PII-safe name fallback**: `display_name → company_name → first_name → (hide)`
  - location fallback: `listing.location → seller.home_location → seller.address`.
- ✅ Resend transactional email integration wired end-to-end.
  - Templates in `services/email_service.py`:
    - `sale_seller`, `sale_buyer`
    - `swap_request`, `swap_success`, `swap_denied`
    - `donation_both`
  - Sale emails triggered from PayPal capture flow.

### ✅ Marketplace Wave 2 — Swap + Donate pipelines (JWT-signed email actions) — **SHIPPED**
Wave 2 shipped the first complete “non-buy” marketplace transaction flows:
1. ✅ **Swap pipeline**: propose → email accept/deny (JWT-signed) → confirm receipt → complete.
2. ✅ **Donation pipeline (MVP)**: claim donation → donor accept/deny via JWT email → confirmation email.
3. ✅ **Transaction landing page**: minimal status UI after accept/deny clicks (auth-optional).
4. ✅ **Listing detail enrichment**: shows **size, description, condition** + mode-aware CTAs.

**Decisions implemented (locked):**
- ✅ **JWT action links** signed using `JWT_SECRET` with a dedicated `aud`.
- ✅ **Swap UX**: modal closet picker (single item offer).
- ✅ **Self actions**: hide Swap/Donate on own listings.

### ✅ Marketplace Wave 3 — Shipping Fee + Transactions UI + APP_PUBLIC_URL hygiene — **SHIPPED**
Wave 3 extended Marketplace beyond Wave 2 MVP with listing-level shipping, PayPal capture for donation shipping, and a polished transactions hub.

**Ethos enforcement (implemented):**
- ✅ **No handling fees for donations** (donations remain free; only optional shipping reimbursement).
- ✅ UI nudges local pickup and community connection:
  - “🌱 Prefer local pickup”
  - “Meet locally to skip the fee 🌱”

### ✅ Phase O — Stylist Provider Migration — Wave O.1 — **SHIPPED (v1.1.1 candidate)**
**Primary objective achieved:** The stylist “Brain” no longer relies on Google Gemini as the default provider.

- ✅ Primary stylist brain swapped from **Google Gemini 2.5 Pro** → **Alibaba Qwen-VL-Max-Latest** via DashScope (international endpoint).
- ✅ Provider abstraction introduced so future model swaps are config-driven (env var) rather than deep code surgery.
- ✅ End-to-end verified:
  - Qwen brain completion observed at ~**19.5s**
  - Full `/api/v1/stylist` call observed at ~**42s** total in preview environment

### ✅ Phase O — Wave O.3 — Eyes v3 (Gemma 4 E2B) Self-Host on Hetzner VPS — **SHIPPED & LIVE**
**Primary objective achieved:** Custom LoRA-fine-tuned Gemma 4 E2B vision model now serves AddItem garment analysis in production, replacing the managed-API dependency for the Eyes tier. **Gemini 2.5 Flash remains the safety fallback**.

**Pipeline (Colab notebook `docs/Eyes_v2_Merge_Quantize.ipynb`):**
- ✅ Diagnosed architecture mismatch (Gemma **4** E2B, not Gemma 3n): uses `Gemma4ClippableLinear` wrappers, tied embeddings, PLE lookup tables.
- ✅ Rewrote merge pipeline with dynamic unwrap/rewrap of `Gemma4ClippableLinear` for PEFT compatibility.
- ✅ Fixed `pillow` + `torchao` dependency conflicts blocking the Colab build.
- ✅ Two-pass `llama.cpp` conversion (F16 mmproj first, then LM).
- ✅ Mixed-precision quantization:
  - Body: **Q4_K_M**
  - Tied embeddings: **Q8_0**
  - Norms: **F32**
  - Vision/audio projector (mmproj): **F16**
- ✅ Final footprint: **~4.85 GB** total (3.9 GB LM + 940 MB mmproj).
- ✅ Validated inference in Colab: ~15 s cold, accurate **18-field JSON** garment schema.

**Backend changes:**
- ✅ `parse_eyes_response` patched to handle both object and array responses from the model (multi-garment inputs).

**Production VPS cutover (Hetzner CX32, 7.6 GB RAM):**
- ✅ Confirmed VPS architecture: backend talks to a separate `dressapp-eyes` Docker container (`http://eyes:7860`) which proxies to `llama-server` on `:8080` reading from volume `eyes-cache` mounted at `/var/lib/docker/volumes/dressapp_eyes-cache/_data`.
- ✅ Uploaded GGUFs into the Docker volume:
  - `Eyes_v3_Gemma4_E2B-Q4_K_M.gguf`
  - `Eyes_v3_Gemma4_E2B-mmproj-F16.gguf`
- ✅ Updated `deploy/.env`:
  - `EYES_MODEL_FILE=Eyes_v3_Gemma4_E2B-Q4_K_M.gguf`
  - `EYES_MMPROJ_FILE=Eyes_v3_Gemma4_E2B-mmproj-F16.gguf`
- ✅ **Fixed compose wiring**: added `EYES_MODEL_FILE: ${EYES_MODEL_FILE:-}` to `deploy/docker-compose.yml` so the container receives the correct LM filename (previously only mmproj was plumbed; LM defaulted to baked-in `phase6-Q4_K_M.gguf`).
- ✅ Recreated service correctly using **service name** `eyes` (not container name):
  - `docker compose -f deploy/docker-compose.yml up -d --force-recreate eyes`

**Live verification (from `dressapp-eyes` logs):**
- ✅ `general.architecture: gemma4`, `general.name: Eyes_v3_Gemma4_E2B_merged`
- ✅ Quantization mix loaded as designed: f32:263 · f16:1 · q8_0:2 · q4_K:251 · q6_K:24
- ✅ Memory fit: projected ~**3735 MiB** host usage vs **7745 MiB** available → ~**4 GB headroom**
- ✅ mmproj loaded (`projector: gemma4v`, `vision=True`)
- ✅ `/healthz` returns **200 OK**; `Application startup complete`

**Bugs found & fixed during cutover:**
- 🐛 Compose confusion: attempted `docker compose ... dressapp-eyes` (container name) but compose expects **service name** (`eyes`).
- 🐛 Missing LM env plumbing: `EYES_MODEL_FILE` wasn’t passed through compose; resulted in stale baked-in LM default.

**Post-cutover follow-ups (open):**
- ⏳ Real garment-photo smoke test through the live app (<30 s response, 18-field JSON, no Gemini fallback).
- ⏳ Rotate exposed secrets from deployment transcript: `EYES_HF_TOKEN`, `EYES_API_TOKEN`, `GEMINI_API_KEY`, `GOOGLE_OAUTH_CLIENT_SECRET`.
- ✅ ~~Remove dead code: `app/backend/app/services/eyes_local_gemma4.py` + dormant `EYES_GEMMA_BACKEND=local` branch in `garment_vision.py`.~~ — **DONE** (deleted file; stripped routing branch from `garment_vision.py` and diagnostics block from `admin.py`; backend restarted clean, lint passes).
- ⏳ After 24 h stable traffic: delete deprecated GGUFs from VPS volume (`phase6-Q4_K_M.gguf`, `mmproj-Gemma4E2B-f16.gguf`).
- ⏳ **(VPS action) Update `dressapp-eyes` proxy `main.py`** to forward two new payload fields to `llama-server`:
  - `response_format` / `json_schema` → grammar-constrained decoding to the `EYES_JSON_SCHEMA` (`oneOf` single object | array).
  - `enable_thinking` / `think` (default `false` from backend) → per-request reasoning toggle, overriding the container's launch defaults. AddItem stays `false`; future Brain experiments can flip `true` per request.
  Backend already sends both fields; proxy currently ignores them harmlessly.
- ✅ ~~Live `_extract_json` in `garment_vision.py` only parses objects.~~ — **DONE**
- ✅ ~~Output language fix.~~ — **DONE**

### ✅ Phase O.6 — Eyes Single-Pass architecture (SegFormer/rembg removed from hot path) — **SHIPPED BEHIND FLAG + VERIFIED SAFE**
**Primary objective achieved:** Single-pass Eyes flow is implemented and gated behind feature flag `EYES_ONE_PASS` to ensure **zero behavioral change** when `false`.

**What shipped (behind `EYES_ONE_PASS=false`):**
- ✅ Backend: `garment_vision.py` schema extended to include `region.bbox` bounding boxes.
- ✅ Backend: `analyze_outfit_one_pass` implemented; `/closet/analyze` branches on `settings.EYES_ONE_PASS`.
- ✅ Backend: `closet.py` defers `rembg` matting to a FastAPI `BackgroundTask` when `from_one_pass=True`.
- ✅ DB: `ClosetItem.clean_image_status` added (supports polling status: pending → done/failed).
- ✅ Frontend: `bestImageUrl` fallback resolver implemented (`thumbnail_data_url → reconstructed_image_url → clean_image_url → segmented_image_url → original_image_url`).
- ✅ Frontend: polling UI for `clean_image_status === 'pending'` with “Polishing photo…” badge.
- ✅ Frontend: new “Repair photo” CTA wired (Nano Banana reshoot endpoint `/closet/{id}/repair`).
- ✅ Deleted dead legacy Qwen-Eyes integration code to avoid confusion.
- ✅ Benchmark tooling: generated `/app/docs/notebooks/Eyes_OnePass_Benchmark.ipynb` + rollout runbook `docs/EYES_ONE_PASS_RUNBOOK.md`.

**Pre-deployment safety checklist (COMPLETE):**
- ✅ Renamed confusing legacy variables in `frontend/src/pages/ItemDetail.jsx`:
  - old: `repairing`/`repairProgress`/`onRepair` (actually background removal)
  - new: `cleaningBackground`/`cleanBackgroundProgress`/`onCleanBackground`
  - kept separate from Phase O.6 “Repair photo” state: `reshootingPhoto`/`onReshootPhoto`.
- ✅ Updated `deploy/.env.example` with documented block:
  - `EYES_ONE_PASS=false` (explicit default) + rollout gating notes.
- ✅ Automated testing agent run: **100% backend (9/9)** + **100% frontend (8/8)** with `deployment_readiness.ready_for_production=true`.
  - Only warning: pre-existing React hydration warning in Closet grid (nested `<a>`), unrelated to Phase O.6.

**Remaining gate (user-driven):**
- ⏳ Run Colab/Jupyter benchmark notebook to confirm bbox IoU accuracy before enabling the flag.

### ✅ Phase L — Localization Wave 3 — Manual UI wiring patches — **SHIPPED**
Closed the last 4 known gaps where translated strings already existed in every locale JSON but the React code was still rendering raw English. Documented originally in `/app/docs/code_fixes_needed.md`.

- ✅ **ListingDetail.jsx (1a–1d)** — Listing chips now wire through existing taxonomy keys.
- ✅ **Home.jsx (2a–2b)** — Trend-Scout chip + fallback cards localized.
- ✅ **SeoBase.jsx (3)** — Page title/meta tags switch language.
- ✅ **countries.js (4)** — Adopted `Intl.DisplayNames` for country names.

**Known pre-existing gap (out of scope here, flagged for later):**
- `public/index.html` ships a static `<meta name="description">` that react-helmet does not remove.

### ✅ SPA zero-delay navigation (Closet + Marketplace + Experts) — **SHIPPED & VERIFIED**
**Objective achieved:** Main directory pages no longer re-fetch/flash spinners on SPA back/forward navigation.

### ✅ Phase X — Chrome Extension (Shopping Assistant) — **SHIPPED IN REPO (manual Chrome E2E pending; backend verified)**
**Primary objective achieved:** A Manifest V3 Chrome extension exists end-to-end.

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 3 — Frontend V1 (React) **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 4 — Payments (PayPal) **(SHIPPED)**
Delivered previously; unchanged.

---

### Phase Z2 — Duplicate detection (pre-flight only) + cleanup **(SHIPPED)**
Delivered previously; unchanged.

---

### Marketplace Wave 1 — Auto-publish + Merchant Card + Email wiring **(SHIPPED)**
Delivered previously; unchanged.

---

### Marketplace Wave 2 — Swap + Donate + Email landing **(SHIPPED)**
Delivered previously; unchanged.

---

### Marketplace Wave 3 — Shipping Fee + Transactions polish **(SHIPPED)**
Delivered previously; unchanged.

---

### Phase O — Stylist provider migration (Gemini → Qwen → Gemma) — **IN PROGRESS**
Delivered previously; unchanged.

---

### Phase X — Chrome Extension — **SHIPPED / E2E pending**
Delivered previously; unchanged.

---

## 3) Next Actions (immediate)

> **Priority update (this session):** Phase V4.2 → V4.5 work is **PAUSED**
> in favour of Phase S (Stylist UX bugs). Resume V4.x after Phase S ships.

### P0 — Next wave candidates
1. **Phase S — Stylist UX Patch (image-aware picker + thumbnail floater + prompt fix)** — ship to preview, then redeploy the Emergent production pod.
2. **Deploy Phase O.6 safely (flag remains OFF):**
   - Push to Hetzner production with `EYES_ONE_PASS=false`.
   - Confirm the legacy hot path remains stable under real traffic.
3. **Phase X.6 E2E (Chrome):** manual validation of connect + overlay + chart extraction on each store.

### P1
4. Run Eyes One-Pass benchmark (user gate).
5. Extension QoL improvements (post-E2E).

### P2
6. Object storage migration (Mongo base64 bloat → R2/S3).

---

## 4) Success Criteria

(unchanged; Phase S adds its own success criteria below.)

---

# Phase V4 — Eyes v4 Production Deploy + Audio Migration (2026 continuation)

> **Status:** V4.1 complete in preview. **V4.2–V4.5 are paused** until
> Phase S ships (Stylist UX bugs). Do not proceed on V4.x until Phase S
> is marked shipped.

## V4 decisions (locked)

(unchanged; see previous section.)

---

## Phase V4.1 — Eyes inference server rewrite (Path C) **(✅ COMPLETE)**

(unchanged; implementation exists in `/app/inference-server/eyes/`.)

---

## Phase V4.2 — Backend STT migration **(PAUSED)**

---

## Phase V4.3 — Frontend TTS migration (Deepgram retirement) **(PAUSED)**

---

## Phase V4.4 — Unsloth → GGUF Colab notebook **(✅ COMPLETE)**

---

## Phase V4.5 — Docs + retirement notes **(PAUSED)**

---

# Phase S — Stylist UX Patch (image-aware picker + thumbnail floater + prompt fix)

> **Context:** User reports 3 UX bugs when asking the Stylist to complete
> an outfit from an uploaded photo. Both preview and Emergent prod pods
> are Gemini-routed, so the fix applies uniformly; user must redeploy
> to push preview fixes to production.

## Problems (P0/P1)

**Issue #1 (P0)** — Composer attachment picker is upload-only; users can’t pick from their existing closet.

**Issue #2 (P0)** — Uploaded photo is “totally ignored” by the Stylist.

**Issue #3 (P1)** — Thumbnail results in the chat are not interactive.

## Locked decisions (user)

- **1c:** Unified picker with **multi-select**: pick closet items + upload images in one flow.
- **3c:** **Side sheet** floater that slides in from the right; chat stays visible (no dimmed backdrop).
- **4b:** Image is **soft context**: Stylist may reference it when relevant, but is not required to anchor on it.

## Root cause analysis (Issue #2)

- Image bytes reach Gemini correctly end-to-end:
  `stylist.py` reads `image` UploadFile → bytes → `logic.get_styling_advice(image_bytes=...)` →
  `gemini_stylist.advise(image_base64=...)` → `UserMessage(file_contents=[ImageContent(...)])`.
- **Bug:** `SYSTEM_PROMPT` in `gemini_stylist.py` (1322 chars) contains **zero** references to images/photos/attachments.
  So Gemini receives the image without instruction to consider it.

**Fix:** conditionally append an image-aware addendum to the system prompt when an image is attached. Use permissive language (“may reference”) to honor soft-context decision (4b).

---

## Phase S1 — Stylist sees the photo (P0 / backend) **(✅ COMPLETE)**

### Implementation
- Patch `app/backend/app/services/gemini_stylist.py`:
  - Add `_IMAGE_CONTEXT_ADDENDUM` constant (4–6 lines):
    - Image is **optional context**
    - You **may** reference visible elements if relevant
    - Do **not** invent details; if uncertain, say so
  - In `advise()`: when `image_base64` is provided, append addendum to `sys_msg`.
  - Order: append **before** `_language_directive` so language directive remains last.
  - Add a one-line log breadcrumb confirming “image addendum applied”.

- Patch the Phase R multi-image path:
  - Grep for the stylist multi-image composer prompt builder (`/api/v1/stylist/compose-outfit` stack) and add the same addendum when images are present.

### Testing
- Unit test asserts addendum appears **IFF** `image_base64` is truthy.
- Ruff/lint passes on touched backend files.

---

## Phase S2 — Unified attachment picker with closet multi-select (P0 / frontend) **(✅ COMPLETE)**

### Implementation
- New component: `/app/frontend/src/components/stylist/AttachmentPicker.jsx`
  - Single paperclip trigger button in the composer row (replaces bare file input UI).
  - Opens a shadcn `Sheet` (bottom on mobile, side on desktop).
  - Two tabs: **Upload** / **From Closet**.
  - Upload tab: drag-and-drop + native multi-file input.
  - From-Closet tab:
    - grid from `closetStore` (already prewarmed)
    - search bar with debounce
    - multi-select with check overlay
    - selection count
  - Bottom action bar: Cancel + “Attach N”.
  - Returns selections to `Stylist.jsx` as an array of records:
    `{kind:'closet', id, name, image_url}`.

- Wire `Stylist.jsx`
  - Replace file input with `<AttachmentPicker>`.
  - Maintain a selection preview row for both uploaded images and closet picks.
  - On submit:
    - For closet picks: fetch each image URL → Blob → File, append to existing `FormData` as `images`.
    - This keeps the backend unchanged (MVP).
  - Add remove (X) per attachment.

### Test IDs (mandatory)
- `attachment-picker-trigger`, `attachment-picker-sheet`,
  `attachment-picker-tab-upload`, `attachment-picker-tab-closet`,
  `attachment-picker-search`, `attachment-picker-item-{id}`,
  `attachment-picker-confirm`, `attachment-picker-cancel`.

---

## Phase S3 — Side-sheet item floater on thumbnail click (P1 / frontend) **(✅ COMPLETE)**

### Implementation
- New component: `/app/frontend/src/components/stylist/ItemFloater.jsx`
  - Fixed-position right-edge panel (no backdrop dim).
  - Desktop width ~360px; mobile full-width.
  - Content:
    - large image
    - name + category badge
    - color swatch + name
    - condition pill
    - optional brand/description
    - primary “View full details” → `/closet/:id`
    - close (X)
  - Dismiss: X, ESC, click outside panel.
  - Animation: slide-in from right (200ms).
  - Accessibility: focus trap, restore focus.

- Wire call-sites (thumbnail click opens floater)
  - `OutfitRecommendationCard.jsx`
  - Inline closet suggestions in `Stylist.jsx` message stream
  - Inline closet suggestions in `OutfitCompletionSheet.jsx`

### Test IDs
- `item-floater-panel`, `item-floater-close`, `item-floater-view-details`, `item-floater-image`.

---

## Phase S4 — Smoke tests + lint (P0) **(✅ COMPLETE)**

- Backend:
  - Ruff lint
  - Pytest for prompt addendum
- Frontend:
  - build/compile check
  - Playwright (testing_agent) flow:
    - open stylist
    - attach via picker (1 closet item + 1 upload)
    - submit
    - verify response mentions that an image was received or shows image-aware reasoning (soft reference allowed)
    - click a thumbnail → floater opens → “View details” navigates

---

## Execution order

**S1 → S3 → S2 → S4**

Rationale:
- S1 is a surgical backend patch that immediately fixes the user’s mental model (“photo isn’t ignored”).
- S3 is shorter than S2 and yields a visible quality lift quickly.
- S2 is the largest (unified picker + multi-select) and lands after the photo bug is fixed.

---

## Out of scope (intentional)

- Multi-select Stylist response actions (e.g. “save this whole outfit”).
- Backend `closet_item_ids` form field to skip image round-trip (future optimisation).
- Reworking the entire composer layout — only the attachment entry point changes.

---

# Phase M12 — Matting hardening (May 2026 closet-test follow-up)

> **Context:** After Phase O.6 the SegFormer + rembg + `apply_alpha_intersection`
> triad was restored on the save flow. Live closet tests surfaced two
> remaining edge-case regressions: (a) low-contrast accessories (burgundy
> sneakers on cobblestone, dark belt on dark trousers) coming out as
> smeared blobs because SegFormer returned a patchy mask the dilation
> couldn't rescue, and (b) the Edit Item → "Clean background" CTA used a
> rembg-only path so users saw different cutouts on first save vs.
> CTA reruns of the same crop.

## ✅ Patch 12g — Mask "confidence" check (SHIPPED)

- File: `backend/app/services/clothing_parser.py::apply_alpha_intersection`.
- Behaviour: after the SegFormer mask is resized to the matted-PNG
  dimensions, compute `(mask > 127).mean()`. If coverage < **40 %** of
  the bbox, treat the mask as unreliable → return `None` → caller keeps
  the rembg-only output.
- Why 40 %: empirical sweet spot from May 2026 closet tests. Tops /
  bottoms / dresses score 60–95 % when SegFormer is confident; sunglasses
  / belts / bags / hats score 50–80 %; failure modes (low-contrast
  accessories) score 10–30 %. 40 % bisects the gap cleanly.
- Soft fallback (caller already handles `None`), so this never blocks
  rembg-only cutouts.
- Smoke-tested via `python -c` with synthetic 256×256 PNGs across four
  coverage regimes (10 %, 38.6 %, 41.5 %, 100 %) — bail/refine matches
  the threshold.

## ✅ Patch 12h — Triad parity in `/clean-background` (SHIPPED)

- File: `backend/app/api/v1/closet.py::clean_item_background`.
- Behaviour: the CTA now runs **SegFormer (best-effort) → rembg + CLIP
  guard → `apply_alpha_intersection`**, mirroring `_run_background_matte`.
  All three stages are independently soft — any failure falls back to
  rembg-only output.
- Adds `reconstruction_metadata.segformer_refined` (bool) so we can tell
  triad-refined CTA reruns apart from rembg-only fallbacks during triage.
- Lint clean (ruff), backend restarted cleanly, smoke import of the
  endpoint confirms `parse_garments` + `apply_alpha_intersection` are
  wired.

## Smoking gun for Issue 3 — "Analysis failed" on first upload

User DevTools screenshot this session proved:

```
POST /api/v1/closet/analyze → 502 Bad Gateway
```

Root cause: **Kubernetes ingress timeout (60 s) killing the connection
on first man-photo upload while SegFormer + rembg + CLIP load lazily.**
On retry the models are warm and the request completes inside the
timeout. So:

> **Issue 3 ≡ Task 2 (wall time)** — same root cause, same fix.

## ✅ Patch M13 — Cold-start model warmup (SHIPPED, resolves Issue 3 ≡ Task 2)

**Root cause confirmed by user DevTools last session:**
`POST /api/v1/closet/analyze` returning `502 Bad Gateway` on first
man-photo upload was a Kubernetes ingress 60 s timeout firing while
the three heavy CV models lazy-loaded serially on the request thread.

**Implementation:**
- New module `backend/app/services/warmup.py` with `warmup_models()`
  fire-and-forget entry point.
- Topology: **SegFormer → FashionCLIP (serial on transformers track),
  parallel with rembg (independent onnxruntime track).** A naïve
  3-way parallel `asyncio.gather` exposes a torch/accelerate race
  inside `transformers.from_pretrained` (concurrent threads observe
  a half-initialised meta-device model → `NotImplementedError:
  Cannot copy out of meta tensor`). Two-track sequencing is the
  resilient middle ground.
- Pre-imports the four needed transformers classes on the asyncio
  thread before the gather, so the lazy `__getattr__` runs once
  serially (avoids an earlier `ImportError` race we hit during M13.1).
- Fired from `server.py::on_startup` as `asyncio.create_task` — NEVER
  awaited inline so supervisor / k8s readiness probe still gets a
  ready response in <3 s.
- New config flag `WARMUP_MODELS_ON_STARTUP` in `config.py` (default
  `true` on full-ML deploys, `false` on `LIGHTWEIGHT_DEPLOY=true`).

**Bonus fix — M13.2:** `fashion_clip._load` now passes
`low_cpu_mem_usage=False` to `CLIPModel.from_pretrained` to bypass the
transformers 4.57 meta-device default. Without this fix the lazy
fallback on first user request would have ALSO raised the same
`NotImplementedError`, leaving the rembg CLIP faithfulness guard a
permanent no-op. Verified working in a fresh subprocess.

**Measured wall time on the dev pod (live `backend.err.log`):**
- SegFormer **0.68 s**, FashionCLIP **0.95 s**, rembg **0.59 s**
- Parallel wall **4.53 s** (vs. ~10-14 s serial cold-start cost)
- 3/3 ready, 0 failed, 0 skipped.

**Effect:** The first user upload after backend boot no longer pays
the cumulative model-init tax. /closet/analyze should comfortably
stay under the 60 s ingress ceiling, eliminating the "Analysis
failed → succeeds on retry" UX. Per-crop Gemini parallelism was
already in place (`asyncio.Semaphore(6)` inside
`garment_vision._analyse_crops`), so no change was needed there.

## ✅ Patch M14 — Defer Nano Banana reconstruction off the analyze hot path (SHIPPED)

**Diagnosis from live preview logs after M13:** Even with all three
models warm, `/closet/analyze` was still 33–60 s for a 4-item outfit
(timeline screenshots from user showed `/analyze` hanging 50–140 s →
502 Bad Gateway from the Kubernetes ingress 60 s ceiling).

`detect_items` (SegFormer) was fast (~5 s) and rembg matting was
already deferred (`DEFER_REMBG_ON_ANALYZE=true`). The remaining
consumer was **`should_reconstruct` firing inside
`_analyse_one_crop`** on every crop whose bbox touched a frame edge
(i.e. essentially every crop in a full-body outfit shot — tops touch
top, footwear touch bottom, etc.). Each fire ran a 20–40 s Gemini
image-generation call synchronously; the parallel `Semaphore(6)` was
bounded by the slowest single (analyze + reconstruct) chain → 30–60 s
critical path per request.

**Implementation (mirror of M8 `defer_matte`):**
- New config flag `DEFER_RECONSTRUCTION_ON_ANALYZE` (`config.py`),
  default `true` (env-overrideable to `false` for triage).
- `garment_vision._analyse_one_crop`: when flag is on and
  `should_reconstruct` fires, skip the inline `reconstruct()` call,
  set `reconstruction=None`, and surface
  `needs_reconstruction=True` + `reconstruction_reasons=[...]` on
  the returned dict.
- `closet.CreateItemIn`: two new optional fields
  (`needs_reconstruction: bool`, `reconstruction_reasons: list[str]`)
  so the frontend echoes the analyzer's flag back on save.
- `closet.py`: new `_run_background_reconstruction(item_id, crop_bytes,
  analysis, reasons)` task that runs `reconstruct()` and patches
  `reconstructed_image_url` + `reconstruction_metadata` (with
  `deferred=true` marker). Mirrors `_run_background_matte`
  bit-for-bit; all failures are soft.
- `closet.create_item`: queues the new BackgroundTask when
  `payload.needs_reconstruction and raw_bytes`.

**Expected /analyze wall time (4-item full-body outfit):**
- Before: 50–60 s (often 502)
- After: ~10–15 s (detect 5 s + parallel per-crop Gemini analyze 5–10 s)
- Reconstruction now lands seconds-to-minutes after save via
  BackgroundTask → `reconstructed_image_url` populates in the
  background and the next /closet read picks it up.

**Frontend handling:** the closet list already uses
`pick_source_data_url` priority chain
(`thumbnail_data_url → reconstructed_image_url → clean_image_url →
segmented_image_url → original_image_url`). When the reconstruction
lands, the cached thumbnail is invalidated (`$unset thumbnail_data_url`)
so the next read regenerates from the freshly reconstructed image.
No frontend change needed; the React store already polls deferred work.

## ✅ Patch M15 — Raise `_ANALYZE_LOCK` semaphore from 1 → 3 (SHIPPED)

**Diagnosis from live preview logs after M14:** Single-request
`/analyze` dropped from 50-60 s → **17-31 s** as designed. But user
DevTools screenshots still showed 502s on **bulk uploads** (multiple
photos at once). Root cause: a hard `asyncio.Semaphore(1)` lock
inside `closet.py` was serialising every `/analyze` call across the
whole process — so on 4-photo bulk upload, the 4th call waited
~70-90 s behind the queue and the Kubernetes ingress killed it with
a 502, even though the backend ultimately returned 200 OK seconds
later.

**The lock's original rationale was OBSOLETE:**
- It was added to prevent OOM from two concurrent `rembg` onnxruntime
  sessions on a 3 GB Hetzner box.
- Patch 8 (`DEFER_REMBG_ON_ANALYZE=true`) already removed rembg from
  the analyze hot path → it's a post-save BackgroundTask now.
- Patch M14 (`DEFER_RECONSTRUCTION_ON_ANALYZE=true`) just removed
  Nano Banana from the same hot path → also a post-save BackgroundTask.
- What remains inside `/analyze`: SegFormer (one short CPU spike,
  ~2-4 s) + Gemini API calls (network-bound, no local memory).
  Both safely parallelisable.

**Implementation:**
- New env var `ANALYZE_CONCURRENCY` (default `3`), read at module
  import time.
- `_ANALYZE_LOCK = asyncio.Semaphore(_ANALYZE_CONCURRENCY)`.
- All four existing `async with _ANALYZE_LOCK` call sites unchanged —
  they just block fewer requests now.

**Effect on bulk uploads:**
- Before: 4 photos × 25 s serial = 100 s → 4th hits 502.
- After: 4 photos × 25 s with concurrency-3 = max ≈ 50 s wall
  (3 concurrent + 1 queued briefly) → all complete under the 60 s
  ceiling.

**Kill switch:** Set `ANALYZE_CONCURRENCY=1` on RAM-constrained
production deploys (e.g. 1 GB Emergent host pod) to restore the
legacy single-lane behaviour without a code change.

## ✅ Patch M16 — Disable Nano Banana auto-reconstruction entirely (SHIPPED)

**Empirical observation from live closet screenshots after M14:**
The items the user saw in the closet (charcoal coat with the head
still visible underneath; pants crop with the coat overlapping the
top; smeared single sneaker; cap crop with the face below) are all
**raw SegFormer + rembg + `apply_alpha_intersection`** outputs.
Nano Banana never actually replaced them in practice — either it
silently failed, the BackgroundTask hadn't completed yet, or the
output failed validation. Yet on the hot path it was costing 20-40 s
per crop in the synchronous era and ~equivalent API spend now in the
deferred era. Burning that latency + API budget for no visible
quality gain is the wrong trade.

**Decision (user-confirmed):** Flag Nano Banana off completely on the
auto-reconstruction path. The triad alone is good enough; the manual
"Repair Photo" CTA stays available for explicit user requests.

**Implementation:**
- New config flag `ENABLE_RECONSTRUCTION` in `config.py` (default
  `false`).
- `services/reconstruction.should_reconstruct` short-circuits to
  `(False, [])` at the top of the function when the flag is off.
  This single gate covers BOTH the inline path (deprecated via M14)
  AND the deferred BackgroundTask path — neither ever fires.
- `closet._run_background_reconstruction` has a belt-and-braces early
  return (logs "SKIPPED — ENABLE_RECONSTRUCTION=false") in case an
  in-flight save from before the flag flip carries
  `needs_reconstruction=True` through.
- `/closet/{id}/reshoot` ("Repair Photo" CTA) intentionally NOT
  gated — explicit user action, still works.

**Effect:**
- `/analyze` no longer marks ANY item with `needs_reconstruction=True`.
- Post-save BackgroundTask for reconstruction never queued.
- Zero Nano Banana API spend on the auto-pipeline.
- Closet items now persist with their `clean_image_url` (SegFormer +
  rembg + `apply_alpha_intersection` triad) as the canonical source;
  the `thumbnails.pick_source_data_url` priority chain falls to
  `clean_image_url` since `reconstructed_image_url` will be `None`.

**Verified post-restart (live process):**
- `settings.ENABLE_RECONSTRUCTION = False`
- `should_reconstruct({'category':'top'}, [0,200,500,800])` →
  `(False, [])` (was edge-touching → would have triggered before)
- All 4 trigger cases (edge-touch / undersized / aspect-mismatch /
  whole-frame) return `(False, [])`.

**To re-enable in the future:** set `ENABLE_RECONSTRUCTION=true` in
`.env`. The defer machinery (M14) and concurrency lift (M15) remain
in place, so re-enabling is safe.

## Still open after this session (in priority order)

1. **Issue 1 (P0)** — Gemini overrides SegFormer category. Pants crops
   with coat tails visible in the top get classified as "Overcoat".
   Fix in `garment_vision.analyze_outfit`: pass SegFormer's category
   as a strict constraint in the prompt (`"this crop is pre-classified
   as {category} — you MUST respect this"`) and post-validate; if
   Gemini still disagrees, log + overwrite with the SegFormer category.
   Sub-category / title / colour / material stay Gemini's call.

2. **NEW — blouse-skirt rim from dilation overspill (P1)** — Screenshot 2
   shows the dilated alpha intersection pulling in a thin band of skirt
   waistband at the bottom of a top crop. Dilation is correct in
   principle (it rescued the puffy sleeves) but the 2.5% short-edge
   floor is slightly hot on tight torso crops. Two options to evaluate
   next session:
   - Per-category dilation budget: tops/bottoms get ~1.5% short-edge,
     accessories/footwear keep 2.5% (they need more halo).
   - Soft taper: dilate but use a falloff weight at the dilated edge
     rather than the current hard min(rembg, dilated_mask) — admit halo
     pixels with reduced alpha.

3. **Issue 4 (P1)** — Unsloth GGUF `--mmproj` `KeyError: 'image_mean'`.
   ✅ **RESOLVED** (out-of-band). Artifacts benchmarked successfully and
   stored on user's PC + Google Drive. Ready for VPS upload + cutover
   when the user decides to swap the live Eyes GGUFs.

4. **Task 3 (P1)** — Vertex AI Try-On widget. ⏸ **ON HOLD** (user-paused,
   not blocked). `.env` keys (`GOOGLE_APPLICATION_CREDENTIALS` +
   `VERTEX_*`) still need to be populated when the user is ready to
   resume.

## Critical notes for the next agent (DO NOT IGNORE)

- **NEVER reintroduce `HF_TOKEN` / `EYES_HF_TOKEN` / HuggingFace
  `transformers` for the Eyes service.** Those were sabotaged additions
  in a previous fork, now purged. Target architecture is
  **`llama.cpp` + GGUF**. Sabotaged docs are quarantined under
  `/app/quarantine/2026-05-sabotage/` — do not trust files there.
- `_run_background_matte(item_id, raw_bytes, category)` now **requires
  the `category` arg**. Any new caller must pass `payload.category` or
  the SegFormer mask picker will fall back to the largest-blob heuristic
  and the cutout quality will silently regress.
- `_recover_paired_footwear` is **intentionally conservative**: if the
  second SegFormer pass finds nothing on the missing half, the mask is
  unchanged so single-boot product shots stay faithful. **Do not "fix"
  this** — it's a product requirement.
- Card thumbnail priority chain in `thumbnails.pick_source_data_url`
  prefers `reconstructed_image_url` (from `/clean-background`) over
  `clean_image_url` (from `_run_background_matte`). Now that Patch 12h
  shipped, both endpoints produce equivalent triad output, so the order
  is no longer a regression risk — but keep this in mind when adding
  any third matte path.
- `apply_alpha_intersection` returns `None` when SegFormer mask covers
  <40% of bbox (Patch 12g). Caller MUST treat `None` as "keep rembg-
  only output", never as an error.
