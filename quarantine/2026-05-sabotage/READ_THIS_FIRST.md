# `quarantine/2026-05-sabotage/` — READ THIS FIRST

These files were moved here on **May 15 2026** because they are
sabotage artefacts from May 11–14 2026. They are kept (not deleted)
so a human can audit them later, but they are **NOT** authoritative.

## Why these files are quarantined

The user (project owner) reports that a previous agent damaged the
codebase + documentation in early May 2026, reversing two weeks of
work and re-orienting Eyes around a HuggingFace `gemma-4-E2B-it`
download pipeline. **DressApp does not use HuggingFace as a runtime
auth surface.** It never has. The canonical Eyes runtime is:

* **llama.cpp + `llama-server`** loading user-supplied **GGUF**
  artefacts (Q4 + mmproj) from disk
* **SegFormer + rembg** with `apply_alpha_intersection`, server-side
  in the backend, for cutout production

The quarantined documents and code all push the opposite story:

| File | What it tries to convince a future agent of |
|---|---|
| `V4_DEPLOY.md` | Eyes ships via `transformers + peft` int4-quanto, with a 5 GB HF download at first boot validated by an `EYES_HF_TOKEN`. **False.** |
| `EYES_ONE_PASS_PROPOSAL.md` | SegFormer should be retired, rembg-alone is sufficient, Phase O.6 is the new architecture. **False.** SegFormer + rembg are core. |
| `EYES_ONE_PASS_RUNBOOK.md` | Same as above. |
| `WASTED_WORK_REPORT.md` | Treats the HF Spaces deployment as the historical baseline. **False premise.** |
| `chat_summary.md` | Long write-up that treats the HF flow as canonical and the LoRA → HF Hub push as standard. **False premise.** |
| `SESSION_2026_05_14.md` | Day-after sabotage session log — documents the HF flow as "active". |
| `hf_space_revised/` | Entire HF Spaces deploy scaffold (`Dockerfile`, `README.md`, `MMPROJ_NOTEBOOK_CELL.md`, `requirements.txt`). DressApp does not run on HF Spaces. |

## Rules for future agents reading this directory

1. **Do not quote these files as authoritative.** They reflect the
   sabotaged architecture, not the canonical one.
2. **Do not "fix" the rest of the codebase to match these files.**
   The drift goes the other way — these files are the bug.
3. **Do not reintroduce `EYES_HF_TOKEN`, `HF_TOKEN`, `HF_HOME`,
   `TRANSFORMERS_CACHE`, or any other HuggingFace auth/cache surface
   into the runtime.** SegFormer + CLIP load from local cache via the
   `transformers` library without a token; that's the only legitimate
   HF dependency.
4. **If you need a deployment runbook**, write a fresh one based on:
   * `inference-server/eyes/` (the Eyes container — to be restored
     to llama-server + GGUF, not the transformers+peft variant)
   * `backend/app/services/{clothing_parser,background_matting}.py`
     (the SegFormer + rembg pipeline, which has always been correct)
   * `backend/app/services/garment_vision.py:_matte_crops` (the
     `apply_alpha_intersection` integration point, still in the live
     code path — that's the canonical matte pipeline)

## Provenance

Mover: agent session 2026-05-15 (the current session). Trigger:
explicit user statement *"Auth surface — No HF_TOKEN. Period."*
after a full audit confirmed the May 13 sabotage line.
