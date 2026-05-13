# Languages Workflow — Session Log

> Session log covering the locale-translation backfill effort and the
> subsequent backend i18n consolidation. Captured for handoff so the next
> agent (or you) can resume without re-deriving context.

---

## Goal

The DressApp frontend supports 12 languages via `react-i18next`. During testing
in Hebrew and Arabic we discovered that several locale files were silently
incomplete — a previous agent had reported them as "merged" but the values
were still raw English. This session:

1. Audited every locale file vs `en.json` to quantify the real gap.
2. Built scripts to safely merge translations from external LLMs without
   regressing existing work.
3. Drove translations through Gemini and DeepSeek for `de/es/hi/it/pt/zh`.
4. Consolidated the language data into a backend service so the FastAPI
   server can render content in the user's chosen language.

---

## Final coverage

| Locale | Coverage | Notes |
|--------|----------|-------|
| `en`   | source   | — |
| `hi`   | 100.00%  | Fully translated. |
| `ar` / `he` / `ja` / `ru` / `zh` | 99.7–100% | Residue is legitimate cognates (`GTIN`, `kg`, `cm`, `Email`, etc.). |
| `de` / `es` / `it` / `pt` | 96–99% | Residue is mostly cognates + a handful of borderline strings (`Admin`, `Trend-Scout`, `Fashion Scout`). |
| `fr`   | ~65%     | **Outstanding** — 358 raw-English keys remain in `fr.json`. Backfill payload prepared but not yet fed back through an LLM. |

---

## Tooling built (lives under /app/scripts/ and /app/backend/)

### 1. `/app/scripts/apply_locale_backfill.py`

Safely merges a translation payload into `/app/frontend/src/locales/<loc>.json`.

* Auto-detects two input shapes:
  * **Starter** — `{_summary, locales: {fr: {strings: {nested...}}}}`
  * **Flat** — `{ "fr": {"nav.experts": "Experts", ...} }`
* Strips UTF-8 BOM (`utf-8-sig`).
* Rejects unknown keys with a warning (cannot inject a hallucinated key).
* Warns on placeholder drift (`{{count}}` vs `{{n}}` etc.) without blocking.
* Deep-merges, preserves existing translations, writes 2-space-indent JSON
  with `ensure_ascii=False` to match repo convention.
* Creates `<loc>.json.bak` alongside each write for instant rollback.
* `--dry-run`, `--only fr,ja`, `--no-backup` flags supported.

Usage:

```bash
python3 /app/scripts/apply_locale_backfill.py /path/to/translations.json --dry-run
python3 /app/scripts/apply_locale_backfill.py /path/to/translations.json
```

### 2. `/app/scripts/fix_json_quotes.py`

Auto-repairs the recurring LLM bug of unescaped inner double-quotes inside
JSON string values (e.g. Gemini emitting `"…un marcador "día laboral"…"`).

* Strips UTF-8 BOM.
* If the file already parses, exits 0 untouched.
* Otherwise walks every `"key": "value"` line and escapes any bare `"`
  inside the value's outer quote pair.
* Re-validates the result; if still broken, writes a partial output for
  manual inspection and exits 2.

Usage:

```bash
python3 /app/scripts/fix_json_quotes.py /path/to/in.json /path/to/out.json
```

### 3. `/app/backend/app/services/i18n.py`

Single-source-of-truth backend i18n service. Reads the frontend's locale
JSON files at process start — no duplication, no drift.

Public API:

```python
from app.services import i18n

i18n.t(key, lang="en", **vars)        # translate a dotted key, with interpolation
i18n.available_languages()            # → ['en','he','ar','es','fr','de','it','pt','ru','zh','ja','hi']
i18n.has_language("fr")               # → True
i18n.is_rtl("ar")                     # → True
i18n.LANG_NAMES["fr"]                 # → 'French'
i18n.SUPPORTED_LANGUAGES              # list of {code, native_name, english_name, dir}
i18n.RTL_LANGUAGES                    # frozenset({'ar', 'he'})
i18n.language_directive("fr")         # LLM "OUTPUT LANGUAGE = X" block
```

Behaviour:

* Walks dotted paths through nested JSON.
* Falls back to English if the key is missing/empty in the requested locale.
* Returns the raw key string if missing from both (never raises).
* Interpolates `{{var}}`, `{var}`, and `%(var)s` placeholders.
* BOM-tolerant load.
* Override via env var `DRESSAPP_LOCALES_DIR=/some/path` (useful for Docker).

Refactor side-effect: `gemini_stylist.py`'s hard-coded `_LANG_NAMES` and inline
`_language_directive()` were replaced with thin re-exports delegating to this
module. `stylist_brain.py` picks it up transparently since it already imported
from `gemini_stylist`.

---

## Pending translation handoff — fr.json

`/app/docs/locale_backfill_fr_only.json` is a verified single-locale payload
covering all 358 still-English keys in `fr.json`.

Audit guarantees (asserted at generation time):

* Exactly one locale block (`"fr"`) — no de/es/it/pt/zh content.
* `payload.fr.keys() == { k ∈ en.json | fr.json[k] == en.json[k] } \ {brand}`
* All values are non-empty English source strings.
* Placeholders intact (`{{label}}`, `{{count}}`, `{{amount}}`, `{{km}}`).
* `_instructions` covers: French-only output, placeholders, no markdown fences,
  plural forms, French typographic conventions.
* Token budget: ~4.9K input, ~5.5K output → ~10K total. Fits any modern
  GPT-4-class model in one shot.

When the LLM reply arrives:

```bash
python3 /app/scripts/fix_json_quotes.py    /path/to/fr_translated.json /tmp/fr.fixed.json
python3 /app/scripts/apply_locale_backfill.py /tmp/fr.fixed.json --dry-run
python3 /app/scripts/apply_locale_backfill.py /tmp/fr.fixed.json
```

---

## What went wrong (and how it was contained)

Three recurring LLM failure modes surfaced during the session:

1. **Locale drift** — Gemini, asked to translate a payload covering
   `ar/fr/ja/ru/pt`, returned `de/es/hi/it/pt/zh` instead (ignoring the
   requested set, expanding the file's `fr` block into 6 unrequested
   languages). Mitigation: `_purpose`, `_direction`, `_locales_in_this_file`,
   and worked `_examples` fields were added to the payload to make the
   target unambiguous.

2. **Truncation** — every Gemini run truncated mid-key around the 1400-key
   mark (always inside the last locale). Mitigation: salvage script that
   discards the truncated tail, plus follow-up "missing" payload regenerated
   from what was delivered vs what's still English-bleed.

3. **Unescaped inner quotes** — DeepSeek / Gemini occasionally emit raw
   `"día laboral"` inside JSON string values. Mitigation: `fix_json_quotes.py`
   auto-repair pass before the merge.

4. **Token-limited reply** — DeepSeek delivered the cleanest 6-locale
   dictionary; ChatGPT and Claude both refused / hit ceilings on the user
   side. The user's preferred completion path for `fr` is therefore an
   independent LLM round-trip using `locale_backfill_fr_only.json`.

The safe-fill strategy throughout was: **only apply a new translation if
the current locale value is verbatim English**. This prevented any of the
~425 "stylistic overwrites" that Gemini wanted to apply (e.g. swapping a
valid Italian translation for a slightly different valid Italian translation)
from re-litigating already-translated work.

---

## Cleanup / leftovers

* `.bak` files were created next to every locale file the script touched
  (`de.json.bak`, `es.json.bak`, etc.). Roll back instantly with
  `mv de.json.bak de.json`. Safe to delete once you're happy with the result.
* `/app/docs/locale_backfill_starters.json` (nested-shape) was removed —
  superseded by the flat-shape payloads.
* `/app/docs/locale_backfill_missing.json` (the ar/fr/ja/ru/pt round-trip
  payload) and `/app/docs/locale_backfill_fr_only.json` (the focused fr
  payload) remain in `/app/docs/`.

---

## Files touched

```
created   /app/scripts/apply_locale_backfill.py
created   /app/scripts/fix_json_quotes.py
created   /app/backend/app/services/i18n.py
created   /app/docs/locale_backfill_fr_only.json
created   /app/docs/locale_backfill_missing.json
created   /app/docs/Languages_chat.md           (this file)
edited    /app/backend/app/services/gemini_stylist.py     (deduped lang map + directive)
edited    /app/frontend/src/locales/de.json               (+19 to +281 fills across 3 rounds)
edited    /app/frontend/src/locales/es.json               (+12 to +292 fills)
edited    /app/frontend/src/locales/hi.json               (+6 to +131 fills)
edited    /app/frontend/src/locales/it.json               (+14 to +276 fills)
edited    /app/frontend/src/locales/pt.json               (+295 fills — bulk of the work)
edited    /app/frontend/src/locales/zh.json               (+50 fills)
```

---

## Next steps when you come back

1. **Run `locale_backfill_fr_only.json` through any GPT-4-class model** — file
   is verified solid; one round-trip plus the apply script closes `fr` to
   ~100% coverage.
2. **Cleanup** — once you've QA'd the locale changes in the running app,
   delete the `.json.bak` files.
3. **Adopt `app.services.i18n`** — start using `i18n.t(...)` in any new
   backend code that produces user-facing strings (system emails, stylist
   prompts, push notifications). The dictionary is loaded once at import,
   so calls are cheap.
4. **Pending issue from the handover** — Profile "Save changes" button
   always active (P2). Not started in this session.

---

## Session 2 — Hard-coded string audit + auto-patch

After the first round of locale fills, several UI screens still showed
English fragments on non-English locales (screenshots provided by the user:
Profile occupation field, listing detail chips, donation banner, trend cards,
duplicate-detection dialog). Cause: **hard-coded English strings in JSX/JS
source that never went through `react-i18next`**.

### Tooling added

```
/app/scripts/audit_hardcoded_strings.py     — finds user-facing English in /app/frontend/src
/app/scripts/apply_audit_translations.py    — merges LLM-translated dict back into the 12 locale JSON files
/app/scripts/patch_hardcoded_strings.py     — rewrites JSX/JS to replace English literals with t('key') calls
/app/scripts/inject_use_translation.py      — bootstraps the useTranslation hook + import in components missing it
/app/docs/locale_backfill_untranslated.json — audit output (post-merge: 0 findings)
/app/docs/code_fixes_needed.md              — module-scope literals & raw-enum bleeds that need manual code work
```

The audit detects: JSX text content (multi-line tolerant), HTML-attribute
strings (`placeholder`, `title`, `aria-label`, `alt`), toast/alert calls,
`t('key', { defaultValue: 'English' })` patterns where the key is missing in
en.json, and object-literal labels in fixture/array data.

Cross-references every candidate against existing values in `en.json` so
already-translated strings (rendered raw because the code uses a raw enum
rather than `t()`) are skipped — those are listed in
`code_fixes_needed.md` for manual fixes.

### Translation round

* Audit found **154 distinct English strings** across **68 files**.
* DeepSeek translated all 154 × 11 locales in one shot — payload validated
  clean (the script auto-repaired 10 inner-quote escapes).
* Apply script detected **13 `defaultValue` findings** whose existing i18n
  key was already chosen by the developer (e.g. `home.trendsRefreshed`) —
  translations got written under the developer's key, not the audit's
  synthetic `suggested_key`. Avoids dead translation entries.
* `apply_audit_translations.py` then wrote 154 × 12 locales = **1,848
  merged entries** (zero placeholder drift).

### Source-code patch round

* `patch_hardcoded_strings.py` rewrote each finding in place. Two passes:
  - **Pass 1:** 69 patches applied across 8 files.
  - **Pass 2** (after `inject_use_translation.py` added the hook to four
    components missing it): 23 more patches across SwapPickerModal,
    OutfitCanvas, ExtensionConnect, TransactionLanding.
* **92 source-code patches total** across 12 files.
* Backups (`.bak`) written alongside every modified file.
* Whitespace-flexible multi-line JSX regex handles `<p>multi-line\nblock</p>`
  patterns automatically.

### Final state after Session 2

* **Audit re-run shows 0 hard-coded English strings** in the auditable scope.
* Frontend builds clean (`esbuild` no errors).
* All 12 locale files extended with the 154 new keys.

### Manual code work still required (see code_fixes_needed.md)

* `src/pages/ListingDetail.jsx` — 4 chip patches to pipe `listing.mode` /
  `listing.category` / `listing.condition` / `listing.size` through their
  existing `taxonomy.*` translations.
* `src/pages/Home.jsx` — restructure `FALLBACK_TRENDS` (module scope), add
  `trends.bucket.*` map for Trend-Scout backend labels.
* `src/components/SeoBase.jsx` — META map at module scope, refactor to use
  i18n keys.
* `src/lib/countries.js` — adopt `Intl.DisplayNames` instead of translating
  the 250-entry ISO country list through the same dictionary.

Estimated effort for the manual fixes: **~50 minutes** to close the last
gap that translation alone can't reach.

---

*End of Session 2.*
