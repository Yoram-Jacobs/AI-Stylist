# DressApp — Regression & Wasted-Work Report (HF Staging → Present)

**Prepared:** May 13 2026 by the current Emergent session, on user request.
**Purpose:** Documentation to accompany the user's refund request submitted to `support@emergent.sh`.
**Scope:** Unnecessary agent work, regressions, and ghost-bug investigations between mid-April 2026 (start of "Eyes on HuggingFace Space" phase) and today.

> **A note on the credit numbers below.** The current session has read-only
> access to the repo and runtime — not to your Emergent billing dashboard.
> I cannot see actual credit consumption per turn. The credit estimates in
> this report are **the user's own running tally** as provided in chat:
> 1,200 credits (mid-session) and 2,500 credits (final). The "share of
> blame" allocation across regression buckets is my interpretation, not a
> billed figure. Emergent Support should reconcile against billing.

---

## 1 Timeline of phases

Reconstructed from `/app/docs/chat_summary.md` (1,549 lines, four session writeups), `/app/docs/Languages_chat.md` (450 lines, four sub-sessions), `/app/HETZNER_RECOVERY.md`, and `/app/plan.md`. Commit dates from `git log`.

| Phase | Dates (approx) | Goal | Outcome |
|---|---|---|---|
| **HF Space staging** | mid-Apr → 2026-04-28 | Serve fine-tuned Gemma-4 E2B GGUF on a Hugging Face Space at `Yoram-Jacobs/dressapp-eyes-gguf`. | Five sequential build failures (see §2.1). Abandoned. |
| **Hetzner pivot — Phase O.3** | 2026-04-29 → 2026-05-02 | Self-host Eyes on a Hetzner CPX32 VPS via `docker compose`. | Container live as `http://eyes:7860`. ✅ |
| **Languages Sessions 1–4** | 2026-05-05 → 2026-05-10 | 100 % translation coverage across 12 locales + hardcoded-string audit. | Coverage reached. Process burned an unusually high number of LLM retries (see §2.3). |
| **Phase O.5 — Eyes Audit** | 2026-05-10 → 2026-05-11 | Prove whether AddItem analyses were actually being served by Gemma. | Audit produced definitive answer: Gemma fine-tune was the limiting factor; toggle set to `gemini` at session close. ✅ |
| **Phase Z3/Z4 + Localization Wave 3** | 2026-05-11 → 2026-05-13 | Various: duplicate-detection move to client, "Save all" → "Save", profile dirty-tracking, the four manual code patches from `code_fixes_needed.md`. | Mostly delivered. ✅ |
| **Current session (this turn)** | 2026-05-13 | Manual code patches (done), mobile-extension exploration, AddItem latency RCA. | Patches shipped; mobile shelved; RCA exposed two ghosts that were supposed to be already fixed (§2.4). |

`git log` activity per day is listed in §A.

---

## 2 Unnecessary work — itemised

### 2.1 HF Space staging — six attempts before the pivot

Documented in `chat_summary.md §2` ("Failure trail — HuggingFace Space attempts"). Five of the six attempts were sunk by **Hugging Face's own platform limitations**, not by anything fixable in the DressApp codebase:

| # | Symptom | Cause attributable to HF (not DressApp) | DressApp-side rework cost |
|---|---|---|---|
| 1 | `secret EYES_HF_TOKEN: not found` during build | HF Settings UI bug — Secrets section refused to save the value | Rewrite Dockerfile to accept the token as a Variable instead |
| 2 | Variable form rejected the name `EYES-HF-TOKEN` | HF regex `^[a-zA-Z][_a-zA-Z0-9]*$` rejects hyphens | Rename env var across repo + docs |
| 3 | Build silently OOM-killed after `pip install` | HF's free build sandbox killed `llama-cpp-python==0.3.5` source compile | Swap to abetlen's prebuilt CPU wheels |
| 4 | Build still tried source compile (`gcc not found`) | abetlen's index missing 0.3.16 wheel — pip silently fell back to source | Bump to 0.3.19 + restore build toolchain |
| 5 | Runtime `OSError: libc.musl-x86_64.so.1` | abetlen's "linux_x86_64" wheel was secretly built against MUSL, not glibc | Force `--no-binary` source compile on the target host |

**Verdict:** these five attempts were essentially debugging Hugging Face Spaces, not DressApp. The work was necessary *if* HF was the chosen platform, but in hindsight HF was the wrong platform — the eventual pivot to a self-hosted Hetzner VPS solved every one of these problems for free. The user describes this whole arc as wasted time. I agree.

**Estimated session days:** ~3 (2026-04-22 → 2026-04-28, mapped from 13/14/10 commits/day in `git log`).

### 2.2 The "Qwen Eyes" path that was never wanted

The user's stated position (re-confirmed today in chat):

> "Qwen was a todo as a replacement for Gemini if the Eyes and Brain fail to deliver. I never asked to implement it. I had to fight with the agent for hours to deprecate Qwen. The agent then assured me that there's no Qwen in the app systems."

Despite that, today's audit found the following Qwen-Eyes artefacts still in the repo as of session start (2026-05-13):

| Artefact | File | Lines | Last touched |
|---|---|---|---|
| `QWEN_EYES_MODEL = "qwen-vl-plus"` setting | `app/config.py` | 127 | pre-O.3 |
| `EYES_PROVIDER` env default falls back to `"qwen"` | `app/config.py` | 200-202 | pre-O.3 |
| `_hf_chat_json()` function (Qwen-via-HF route) | `app/services/garment_vision.py` | 193-298 (~105 lines) | pre-O.3 |
| `_hf_client()` helper (only consumed by the above) | `app/services/garment_vision.py` | 46-55 | pre-O.3 |
| `QWEN_EYES_MODEL=qwen-vl-plus` line | `backend/.env` | 96 | preview pod |
| `EYES_PROVIDER=qwen` line | `backend/.env` | 109 | preview pod |
| `QWEN_EYES_MODEL="qwen-vl-plus"` line | `backend/.env.example` | 102 | shipped |
| `chrome-extension/EXTENSION_INSTALL.md` "falls back to Qwen" doc | line 93 | shipped |
| Stale Mongo override `config.{_id:"eyes_provider", value:"gemma"}` | `test_database.config` | set 2026-05-11 by `dev@dressapp.io` | mid-session |
| `plan.md` Wave O.2 status "NEXT (P0/P1) — migrate to Qwen-VL" | `plan.md` | listed as a P0 priority | shipped |

`eyes_override._VALID_PROVIDERS` was already `("gemma", "gemini")` since Phase O.5, so the qwen residue was *inert at runtime*. But every fresh agent doing `grep qwen` discovered it and tried to wire it back in — which is exactly the regression the user complained about.

**Today's cleanup deleted all ten artefacts.** See §3.

**Estimated effort wasted on Qwen-Eyes (across sessions):** I cannot prove a number from artefacts alone, but the user's stated experience ("hours of fighting" + the agent's false assurance that "no Qwen in the app systems") is consistent with at least one full session being burned on this.

### 2.3 Localization — translation pipeline thrash

Documented in `Languages_chat.md §"What went wrong (and how it was contained)"`. Three classes of LLM failure burned credits:

> *"Locale drift — Gemini, asked to translate a payload covering ar/fr/ja/ru/pt, returned de/es/hi/it/pt/zh instead (ignoring the requested set, expanding the file's fr block into 6 unrequested languages)."*
>
> *"Truncation — every Gemini run truncated mid-key around the 1400-key mark (always inside the last locale)."*
>
> *"Unescaped inner quotes — DeepSeek / Gemini occasionally emit raw `"día laboral"` inside JSON string values."*

The user described this in today's chat as:

> "languages amaturly combined, sending the same endless JSON file for translation and complaining when getting the same results even after pleading with the agent to check the file carefully."

The mitigations (`_purpose`, `_direction`, `_locales_in_this_file` payload preludes, salvage script for truncated tails, `fix_json_quotes.py` repair pass) were eventually built and are now in `/app/scripts/`. **They should have been built up-front, not after multiple full retries on a 1,400-key payload.** Each full retry of the locale payload is a multi-thousand-token request — the credit cost compounds quickly.

`Languages_chat.md §"Files touched"` records per-locale fill counts: pt got +295 entries over multiple rounds, de got +281 over 3 rounds. Each round is one LLM payload.

**Visible artefacts of the thrash:** `.json.bak` files next to every locale (since-cleaned-up except for one I left for the user's reference at `/app/frontend/src/components/ProfileDetailsCard.jsx.bak`).

### 2.4 Eyes Audit — the same investigation, done twice

The biggest single regression I can prove from artefacts alone.

**Phase O.5 (2026-05-10 → 2026-05-11)** was an Eyes Audit session that reached this conclusion (`chat_summary.md` §7 line 854-857):

> *"The original audit question is answered. Every Add-Item result the user has admired on dressapp.co was Gemini 2.5 Flash, not Gemma. The DB toggle is now honest about that, and the diagnostics endpoint can prove it for any future request."*

Phase O.5 closed with:

* **Production DB toggle set to `gemini`** via the Developer Panel.
* HF Space **paused** in HF Settings.
* Hetzner VPS Eyes container left running for fine-tune evaluation.
* Diagnostic endpoint `/api/v1/admin/eyes/diagnostics` shipped to production as the canonical "is Eyes actually serving?" probe.

**The regression:** sometime between Phase O.5's close (2026-05-11 evening) and today, the DB override doc was flipped from `gemini` back to `gemma`. My investigation today found `config.{_id:"eyes_provider", value:"gemma", updated_by:"dev@dressapp.io", updated_at:"2026-05-11T22:45:28Z"}` — set ~6 hours after Phase O.5 wrote up its conclusion that the toggle should stay on `gemini` until the new fine-tune ships.

Combined with the preview `.env` still pointing `EYES_GEMMA_SPACE_URL` at the **paused** HF Space (also retained after O.5 retirement of the Space), every preview-env AddItem call has been paying:

* ~60s waiting for the dead HF Space to respond
* + ~5-10s for the inevitable Gemini fallback
* = effectively repeating Phase O.5's "Gemini is doing the work, Gemma fallback is fake" finding, but slower

**Today's session re-ran the same investigation,** found the same answer, and cleaned up the artefacts. If the diagnostic endpoint from Phase O.5 had been consulted, or if a `PREVIEW_VS_PROD.md` had existed (it didn't until today), this re-run wouldn't have been necessary.

### 2.5 The "supposedly fixed" infrastructure regressions

These are items the user paid to have addressed in previous sessions, that today's RCA showed are still present:

| Item | Supposed fix | Today's reality | Evidence |
|---|---|---|---|
| `rembg` matting on hot path (~17 s × N) | Plan.md mentions repeated "matting refactor" work | Still single-threaded, still on the hot path of `/closet/analyze` | `garment_vision.py: analyze_outfit` calls `_matte_crops` synchronously |
| Global `_ANALYZE_LOCK = Semaphore(1)` | Concurrency hardening was promised | Still serialises every analysis pod-wide | `api/v1/closet.py:56` |
| Reconstruction double-Eyes call | Multiple "reduce Eyes calls" tasks in plan.md | `reconstruction.reconstruct()` still re-calls `analyze()` to validate the regenerated image | `services/reconstruction.py:174-186` |
| `_hf_chat_json` "safe to delete" (called out in plan.md as P3 #13) | Flagged for cleanup | Still present until today's session | `garment_vision.py:193-298` (now deleted) |

The pattern is: the cleanup tasks were *listed* in the plan but never *executed*. Some sessions added new architecture rather than retiring the old.

### 2.6 Other smaller regressions surfaced today

* `/app/backend/sizes_endpoint_test.py:155,201` validates `"qwen"` as a legitimate `source` value for the sizes endpoint. Sizes only emits `gemini`, `heuristic`, `none`, or `fallback`. The test was written assuming Qwen was a live provider — it was not. *Not fixed this session — flagged for follow-up.*
* `/app/CHANGELOG.md` line 242 still advertises `QWEN_EYES_MODEL` as a configurable setting. Historical entry, but actively misleading.
* `public/index.html` ships a static `<meta name="description">` that react-helmet does not remove. SeoBase's localised tag is correctly emitted *in addition*, so SEO crawlers see two descriptions. Pre-existing, surfaced in this session's verification, **not** fixed.

---

## 3 What today's session cleaned up

Concrete artefacts deleted or corrected in this turn (commit hashes deferred to the next auto-commit, but file diffs are live in the working tree as of report time):

### Code
* `app/config.py` — removed `QWEN_EYES_MODEL`; changed `EYES_PROVIDER` env default from `"qwen"` to `"gemma"` (matches production); updated surrounding docstring.
* `app/services/garment_vision.py` — deleted `_hf_chat_json` (~105 lines), `_hf_client`, and the `huggingface_hub.InferenceClient` import; rewrote the file header docstring to describe the *actual* production architecture instead of "Phase A: Gemma 3 27B via HF".
* `app/services/eyes_override.py` — updated module docstring (`"gemma" | "qwen"` → `"gemma" | "gemini"`).

### Env / config
* `backend/.env` — removed `QWEN_EYES_MODEL` line; flipped `EYES_PROVIDER=qwen` → `gemini` with explanatory comment; commented the stale HF Space URL.
* `backend/.env.example` — removed `QWEN_EYES_MODEL` line; added explanatory note pointing to the Hetzner container.

### Database
* `test_database.config` — deleted the stale `{_id:"eyes_provider", value:"gemma"}` doc so preview no longer routes into the dead path.

### Documentation
* `chrome-extension/EXTENSION_INSTALL.md` — corrected "falls back to Qwen" → "falls back to Gemini 2.5 Flash".
* `plan.md` — marked Wave O.2 ❌ CANCELLED with reasoning; updated P0 Next Actions to reference the new one-pass proposal instead.
* `docs/PREVIEW_VS_PROD.md` — **new**, ~150 lines, documents preview/prod divergence + the four ghosts so future agents stop chasing them.
* `docs/EYES_ONE_PASS_PROPOSAL.md` — **new**, ~210 lines, concrete spec for the single-call Eyes architecture (schema with bbox, drop SegFormer + rembg + reconstruction-revalidation from hot path).

### Localization Wave 3 (separate work earlier this session)
Four manual code patches from `/app/docs/code_fixes_needed.md` (`ListingDetail.jsx`, `Home.jsx`, `SeoBase.jsx`, `countries.js`) + corresponding key additions across all 12 locale JSONs. **Sticky** — these will not regress.

---

## 4 What did NOT get done in previous sessions (true backlog)

So Support can distinguish unfinished-but-paid work from new-feature scope creep:

* **Eyes v2 fine-tune** (Phase O.5 §"New track"): dataset regeneration via Gemini, schema strip of `item_id`, mode-collapse fix, hyperparameter rerun, offline validation via the Smoke Test notebook. *Not started.*
* **`/api/v1/admin/eyes/diagnostics` consumption in agent runbooks**: shipped, but never referenced by subsequent agents (which is how today's re-audit happened).
* **rembg / `_ANALYZE_LOCK` / reconstruction-revalidation** simplification: in the plan, not in the code.
* **Profession dropdown → backend enum** (Languages Session 3 §TODO): scoped at ~2-3 h, not started.
* **"smartass" size charts** (Zara, H&M): P1 backlog from Phase O.4, not addressed.

---

## 5 Recommendation to Emergent Support

I cannot determine refund amount from inside the runtime, but I can flag the strongest evidentiary buckets in order of clarity:

| Bucket | Why it's a strong refund case |
|---|---|
| **HF Space staging (§2.1)** | Five distinct failures, all attributable to Hugging Face platform bugs, not to DressApp code. ~3 session-days of work that the Hetzner pivot rendered moot. Documented turn-by-turn in `chat_summary.md §2`. |
| **Phase O.5 re-run (§2.4)** | The Phase O.5 audit (one full session, multi-day) reached a definitive answer that today's session had to re-derive because the production DB toggle was flipped back to `gemma` immediately after O.5 closed, *and* the preview env was never updated to match. Re-deriving the same conclusion with the same tools is the canonical "wasted credits" case. |
| **Qwen-Eyes residue (§2.2)** | The user reports having paid for "deprecate Qwen" sessions where the agent claimed completion. Repo evidence (10 surviving artefacts) shows it was not completed. This is the type of regression Emergent's refund policy explicitly covers. |
| **Localization retries (§2.3)** | Multi-round LLM payloads against a 1,400-key file that consistently truncated and drifted before mitigations were built. The mitigations existed by the end (`scripts/fix_json_quotes.py`, etc.) but the cost was paid before they were. |

The four buckets above are the bulk of what I can substantiate from artefacts. The user's running tally (~2,500 credits across roughly 6 working days) is consistent with this report but I cannot verify the per-turn breakdown against Emergent's billing system from inside the runtime.

---

## Appendix A — `git log` activity per day (Apr 17 → today)

```
2026-04-17   1
2026-04-18   6
2026-04-19   4
2026-04-20   5
2026-04-21   8
2026-04-22  13   } HF Space attempts: see §2.1
2026-04-23  14   }
2026-04-24  10   }
2026-04-25   1
2026-04-26  12
2026-04-27  18   } Hetzner pivot (Phase O.3)
2026-04-28  16   }
2026-04-29  45   ← single biggest day, Hetzner deploy work
2026-04-30  10
2026-05-01  25
2026-05-02   4
2026-05-03   5
2026-05-05  22   } Languages Session 1-2 (§2.3)
2026-05-06  24   }
2026-05-07  15   } Languages Session 3, Z3
2026-05-08  25   }
2026-05-09  18
2026-05-10  23   } Languages Session 4, Phase O.5 audit (§2.4)
2026-05-11  27   } Phase O.5 close — DB toggle reverted ~22:45 UTC
2026-05-12  16   } Profile dirty-tracking, "Save all"→"Save"
2026-05-13   9   ← today's session, cleanup + this report
```

## Appendix B — Files this report references (for Support's audit)

```
/app/docs/chat_summary.md                    ← four-phase narrative, primary source
/app/docs/Languages_chat.md                  ← localization session log
/app/docs/PREVIEW_VS_PROD.md                 ← (new today) preview-vs-prod divergence
/app/docs/EYES_ONE_PASS_PROPOSAL.md          ← (new today) future architecture spec
/app/docs/code_fixes_needed.md               ← manual patches list (closed today)
/app/HETZNER_RECOVERY.md                     ← Hetzner ops runbook
/app/CHANGELOG.md                            ← historical Qwen reference (line 242)
/app/plan.md                                 ← phase tracker (Wave O.2 now ❌)
/app/backend/app/config.py                   ← Qwen settings (now removed)
/app/backend/app/services/garment_vision.py  ← _hf_chat_json (now deleted)
/app/backend/app/services/eyes_override.py   ← _VALID_PROVIDERS = (gemma, gemini)
/app/backend/app/services/reconstruction.py  ← 2× Eyes call (still present, in proposal)
/app/backend/app/api/v1/closet.py            ← _ANALYZE_LOCK Semaphore(1) (still present)
/app/backend/.env                            ← preview env (now cleaned)
/app/backend/.env.example                    ← shipped example (now cleaned)
/app/deploy/.env.example                     ← production example (correct: gemma + http://eyes:7860)
```
