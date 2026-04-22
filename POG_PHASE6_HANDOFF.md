# DressApp Eyes — Phase 6 Hand-off

Your fine-tuned **Gemma 4 E2B LoRA** is saved at
`/app/models/pog_phase6/pog_phase6_model/` and the backend is fully wired
to consume it — we just need to move the **merge + GGUF conversion +
push** out of this sandbox pod because the 10 GB base download + 10 GB
merged + 10 GB GGUF pipeline trips the pod's ~40 GB ephemeral-storage
quota. Two OOM evictions confirmed this.

Instead, a ready-to-run Colab notebook does the whole pipeline on free
T4 hardware in ~15 minutes.

---

## Your next steps (~20 min total)

### 1. Run the notebook on Colab

* Open: `/app/scripts/pog_phase6_merge_gguf.ipynb`
* Upload it to Colab (**File → Upload notebook**)
* Upload the **7 adapter files** from `/app/models/pog_phase6/pog_phase6_model/` into `/content/adapter/` on Colab:
  * `adapter_model.safetensors`
  * `adapter_config.json`
  * `tokenizer.json`
  * `tokenizer_config.json`
  * `chat_template.jinja`
  * `processor_config.json`
  * `README.md`
* Paste your **HF write token** (Settings → Access Tokens → New token → scope `write`) into the first cell.
* **Runtime → Run all**.

The notebook will:
1. Download `google/gemma-4-E2B-it` (not gated, ~10 GB)
2. Apply your LoRA and merge to FP16
3. Push to `Yoram-Jacobs/dressapp-eyes-pog-phase6` *(private)*
4. Build llama.cpp, convert to **GGUF F16**, quantise to **Q4_K_M** (~2.5 GB)
5. Push GGUFs to `Yoram-Jacobs/dressapp-eyes-pog-phase6-gguf` *(private)*

Both artifacts are then on your HF account.

### 2. Deploy a serving endpoint (pick one)

| | When to pick | Steps |
|---|---|---|
| **a) HF Dedicated Inference Endpoint** ✅ easiest | You want server-side inference today without managing any infra | On HF: open `Yoram-Jacobs/dressapp-eyes-pog-phase6` → **Deploy → Inference Endpoints** → pick a GPU (T4 or L4 is plenty) → Create. Copy the returned URL. |
| **b) Your own llama.cpp `--server` on a VPS** | You have a Linux box with GPU/CPU and want zero cloud cost | `llama-server -m phase6-Q4_K_M.gguf -c 4096 --host 0.0.0.0 --port 8080`. The URL is `http://YOUR_VPS:8080/v1`. |
| **c) On-edge in the mobile/web client** | Long-term target (what you originally described) | Use the GGUF directly in llama.cpp / MLC / LiteRT-LM / WebLLM. No server needed. |

### 3. Flip DressApp to use your fine-tune

Once you have the endpoint URL from step 2a or 2b, add to `/app/backend/.env`:

```bash
GARMENT_VISION_PROVIDER=hf
GARMENT_VISION_MODEL=Yoram-Jacobs/dressapp-eyes-pog-phase6  # or the endpoint's model id
GARMENT_VISION_ENDPOINT_URL=https://xxx.endpoints.huggingface.cloud/v1    # full URL with /v1 suffix
GARMENT_VISION_ENDPOINT_KEY=hf_xxxxxxxxxxxx   # optional, defaults to HF_TOKEN
```

Then:

```bash
supervisorctl restart backend
```

That's it — the backend already ships with provider-dispatched analysis.
`/api/v1/closet/analyze` and the multi-item pipeline will route every
call to your Gemma 4 fine-tune automatically. Detection stays on Gemini
2.5 Flash for bbox quality.

### 4. Verify

```bash
# From the pod
REACT_APP_BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
TOKEN=$(curl -s -X POST "$REACT_APP_BACKEND_URL/api/v1/auth/dev-bypass" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST "$REACT_APP_BACKEND_URL/api/v1/closet/analyze" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"image_base64":"<your test b64>","multi":false}' | python3 -m json.tool | head -40
```

Look for `"model_used":"Yoram-Jacobs/dressapp-eyes-pog-phase6"` in the
response — confirms the router hit your fine-tune.

---

## What DressApp already supports end-to-end

* **Provider-dispatched Eyes** with `GARMENT_VISION_PROVIDER={gemini|hf}` and optional custom endpoint URL
* **Multi-item outfit extraction** (detect → crop → analyse, with IoU-NMS dedupe + already-cropped short-circuit)
* **FashionCLIP embedding** (local CPU) on every closet-item image
* **`POST /api/v1/closet/search`** — semantic search by text *or* image (cosine over 512-d vectors)
* **Native camera capture** on `/closet/add` (rear camera on mobile via `capture="environment"`)
* **Admin → Providers** tab shows live latency/error rate for whichever model is wired

When your fine-tune lands, all of the above light up without any code changes — just the env flip.
