#!/usr/bin/env bash
# Phase 6 fine-tune pipeline — runs on the big overlay (/) with
# aggressive cleanup between steps so we never exhaust the small /app
# or /root ephemeral partitions.
set -euo pipefail

LOG=/tmp/pog_phase6.log
STATUS_DIR=/models/status
mkdir -p "$STATUS_DIR"

# -------- config --------
ADAPTER_DIR=/app/models/pog_phase6/pog_phase6_model
BASE_MODEL="google/gemma-4-E2B-it"
MERGED_DIR=/models/pog_phase6_merged
GGUF_DIR=/models/pog_phase6_gguf
LLAMA_DIR=/models/llama.cpp
HF_REPO_MERGED="Yoram-Jacobs/dressapp-eyes-pog-phase6"
HF_REPO_GGUF="Yoram-Jacobs/dressapp-eyes-pog-phase6-gguf"
HF_TOKEN=$(grep HF_TOKEN /app/backend/.env | cut -d= -f2 | tr -d '"')
export HF_TOKEN HUGGINGFACE_HUB_TOKEN="$HF_TOKEN"
export HF_HOME=/hfcache
export HUGGINGFACE_HUB_CACHE=/hfcache
export TRANSFORMERS_CACHE=/hfcache
export HF_HUB_ENABLE_HF_TRANSFER=1  # faster parallel downloads

mkdir -p /hfcache "$MERGED_DIR" "$GGUF_DIR"

step() {
  echo "" | tee -a "$LOG"
  echo "[$(date +%T)] ===== $* =====" | tee -a "$LOG"
  df -h / /app /root 2>/dev/null | awk 'NR>1 {printf "  %-12s %5s used  %5s free  %s\n",$1,$3,$4,$6}' | tee -a "$LOG"
}

touch "$STATUS_DIR/running"
{
  step "Step 1: upgrade transformers + install peft/accelerate"
  pip install --quiet --upgrade "transformers>=4.57" "peft>=0.18" "accelerate>=1.0" \
      "sentencepiece" "protobuf" "hf_transfer" 2>&1 | tail -5
  python3 -c "import transformers, peft, accelerate; print('  transformers='+transformers.__version__+' peft='+peft.__version__+' accelerate='+accelerate.__version__)"

  step "Step 2: download base + merge LoRA (save merged to $MERGED_DIR)"
  python3 <<PY
import os, time, torch, gc, shutil
from transformers import AutoProcessor, AutoModelForImageTextToText, AutoModelForCausalLM
from peft import PeftModel

t0 = time.time()
base = "$BASE_MODEL"
adapter_dir = "$ADAPTER_DIR"
out_dir = "$MERGED_DIR"

print("[py] loading base (this downloads ~10 GB)...", flush=True)
try:
    model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.float16, low_cpu_mem_usage=True)
    print("[py] loaded via AutoModelForImageTextToText")
except Exception as e:
    print("[py] ImageTextToText failed (" + type(e).__name__ + "); trying CausalLM.", str(e)[:120])
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float16, low_cpu_mem_usage=True)
processor = AutoProcessor.from_pretrained(base)
print(f"[py] base loaded in {time.time()-t0:.1f}s", flush=True)

print("[py] applying LoRA adapter...", flush=True)
model = PeftModel.from_pretrained(model, adapter_dir)
print("[py] merging + unloading...", flush=True)
model = model.merge_and_unload()

print(f"[py] saving merged model to {out_dir} (safetensors)...", flush=True)
model.save_pretrained(out_dir, safe_serialization=True, max_shard_size="4GB")
processor.save_pretrained(out_dir)
print(f"[py] save done in {time.time()-t0:.1f}s total", flush=True)

# Free memory before next steps
del model, processor
gc.collect()
PY

  step "Step 3: push merged model to $HF_REPO_MERGED"
  python3 <<PY
from huggingface_hub import HfApi, create_repo
api = HfApi()
repo = "$HF_REPO_MERGED"
try: create_repo(repo, repo_type="model", private=True, exist_ok=True)
except Exception as e: print("  create_repo:", e)
api.upload_folder(folder_path="$MERGED_DIR", repo_id=repo, repo_type="model",
                  commit_message="DressApp Eyes — Phase 6 (Gemma 4 E2B LoRA merged)")
print("  uploaded: https://huggingface.co/" + repo)
PY

  step "Step 4: build llama.cpp quantiser only (skip full server for now)"
  if [ ! -d "$LLAMA_DIR" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"
  fi
  pip install --quiet -r "$LLAMA_DIR/requirements.txt" 2>&1 | tail -3
  if [ ! -f "$LLAMA_DIR/build/bin/llama-quantize" ]; then
    (cd "$LLAMA_DIR" && cmake -B build -DGGML_CUDA=OFF -DGGML_METAL=OFF \
        -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF >/dev/null)
    (cd "$LLAMA_DIR" && cmake --build build --config Release -j$(nproc) --target llama-quantize 2>&1 | tail -5)
  fi
  ls -l "$LLAMA_DIR/build/bin/llama-quantize"

  step "Step 5: convert merged HF -> GGUF f16"
  python3 "$LLAMA_DIR/convert_hf_to_gguf.py" "$MERGED_DIR" \
      --outfile "$GGUF_DIR/phase6-f16.gguf" --outtype f16 2>&1 | tail -10

  step "Step 6: quantise to Q4_K_M"
  "$LLAMA_DIR/build/bin/llama-quantize" \
      "$GGUF_DIR/phase6-f16.gguf" "$GGUF_DIR/phase6-Q4_K_M.gguf" Q4_K_M 2>&1 | tail -5
  ls -lh "$GGUF_DIR"

  step "Step 7: push GGUFs to $HF_REPO_GGUF"
  python3 <<PY
from huggingface_hub import HfApi, create_repo
api = HfApi()
repo = "$HF_REPO_GGUF"
try: create_repo(repo, repo_type="model", private=True, exist_ok=True)
except Exception as e: print("  create_repo:", e)
api.upload_folder(folder_path="$GGUF_DIR", repo_id=repo, repo_type="model",
                  commit_message="DressApp Eyes — Phase 6 GGUF (f16 + Q4_K_M)")
print("  uploaded: https://huggingface.co/" + repo)
PY

  echo "[$(date +%T)] ===== DONE =====" | tee -a "$LOG"
  echo "ok" > "$STATUS_DIR/done"
} 2>&1 | tee -a "$LOG"

rm -f "$STATUS_DIR/running"
