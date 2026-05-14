#!/usr/bin/env python3
"""Audit the React frontend for hard-coded user-facing English strings
and emit a JSON file suitable for handing to an LLM for translation.

Heuristics
----------
1. JSX text content between tags is captured when it contains 2+ ASCII
   alphabetic words (>= 3 chars total).
2. Attribute values are captured for these "user-visible" attributes:
   placeholder, title, alt, aria-label, aria-description, defaultValue.
3. Plain-string arguments to toast helpers, alert(), confirm(), and the
   `useTranslation` `defaultValue` option are captured.
4. Findings already wrapped in `t(`, `i18n.t(`, or located inside a comment
   line are skipped.
5. The same English source string only appears once in the output, keyed
   by a deterministic dotted path derived from the file and a short slug.

Output shape
------------
{
  "_purpose":            "INPUT IS ENGLISH. OUTPUT MUST BE all 12 locales.",
  "_source_language":    "English (en)",
  "_target_languages":   ["ar","de","es","fr","he","hi","it","ja","pt","ru","zh"],
  "_instructions":       "...",
  "_examples":           [...],
  "findings": [
    {
      "suggested_key":   "listingDetail.localPickupPreferred",
      "english":         "🌱 Local pickup preferred — no shipping fee",
      "occurrences": [
        {"file": "src/pages/ListingDetail.jsx", "line": 144, "kind": "jsx-text"}
      ]
    },
    ...
  ]
}
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("/app/frontend/src")
LOCALES_EN = Path("/app/frontend/src/locales/en.json")

# ---------------------------------------------------------------------------
# Existing i18n key set — we don't want to suggest a string we already cover.
# ---------------------------------------------------------------------------

def flatten(d, p=""):
    out = {}
    for k, v in d.items():
        path = f"{p}.{k}" if p else k
        if isinstance(v, dict):
            out.update(flatten(v, path))
        else:
            out[path] = v
    return out

EN_FLAT = flatten(json.loads(LOCALES_EN.read_text(encoding="utf-8")))
KNOWN_VALUES = {v for v in EN_FLAT.values() if isinstance(v, str)}

# ---------------------------------------------------------------------------
# Filters for what counts as "user-facing English"
# ---------------------------------------------------------------------------

# Strings that contain at least two ASCII letters separated by whitespace
# OR a single alpha-word of length >= 4 (catches single-word labels too).
_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# Skip strings that look obviously technical.
_TECHNICAL_RE = re.compile(
    r"""^
        (
          [a-z][a-zA-Z0-9_-]*           # camelCase / kebab-case identifier
          | [A-Z][A-Z0-9_]+             # ALL_CAPS_CONST
          | https?://\S+                # URL
          | /[a-z0-9/_.-]+              # path
          | \w+\.\w+(\.\w+)*            # dotted token (a.b.c) — could be i18n key
          | [a-z]+(-[a-z]+)+            # css-like-token
          | \w+/\w+                     # mime/type
          | rgba?\(.*?\)|hsla?\(.*?\)   # colors
        )
        $
    """,
    re.VERBOSE,
)

# Strings that are pure punctuation / symbols / emoji / numbers
def _is_noise(s: str) -> bool:
    s = s.strip()
    if not s:
        return True
    # Has at least one ASCII letter
    if not re.search(r"[A-Za-z]", s):
        return True
    # Contains JS-syntax noise — catches ternary fragments captured between
    # adjacent JSX boundaries (e.g. "') : connected ? ('").
    if re.search(r"[;()?]|\?\.|&&|\|\||=>|\breturn\b", s):
        return True
    # Looks like a JSX attribute fragment that slipped through
    if re.search(r"[a-z]+=[\"']", s):
        return True
    # Dotted JS identifier with no spaces (e.g. "status.connected")
    if re.fullmatch(r"[\w$.]+(\s+[\w$.]+)?", s) and "." in s and " " not in s:
        return True
    # Single token that looks technical
    if len(s.split()) == 1 and _TECHNICAL_RE.match(s):
        return True
    # CSS class names that snuck through
    if re.fullmatch(r"[\w-]+(\s+[\w-]+)*", s) and not re.search(r"[A-Z][a-z]+\s[A-Z]?[a-z]+", s):
        # All-lowercase / kebab tokens — but allow if it has a capitalised
        # word pair (e.g. "Local pickup")
        if not re.search(r"[A-Z][a-z]+", s):
            return True
    return False


# ---------------------------------------------------------------------------
# Regex patterns for extracting candidate strings from a source line.
# ---------------------------------------------------------------------------

PATTERNS = [
    # placeholder="..." (single or double quoted, no JS expression).
    ("placeholder", re.compile(r'\bplaceholder\s*=\s*"([^"]{3,})"')),
    ("placeholder", re.compile(r"\bplaceholder\s*=\s*'([^']{3,})'")),

    # aria-label="..."
    ("aria-label", re.compile(r'\baria-label\s*=\s*"([^"]{3,})"')),
    ("aria-label", re.compile(r"\baria-label\s*=\s*'([^']{3,})'")),

    # title="..."
    ("title", re.compile(r'\btitle\s*=\s*"([^"]{3,})"')),
    ("title", re.compile(r"\btitle\s*=\s*'([^']{3,})'")),

    # alt="..."
    ("alt", re.compile(r'\balt\s*=\s*"([^"]{3,})"')),
    ("alt", re.compile(r"\balt\s*=\s*'([^']{3,})'")),

    # defaultValue: 'English fallback' inside i18n t() options
    ("defaultValue", re.compile(r"\bdefaultValue\s*:\s*['\"]([^'\"]{3,})['\"]")),

    # toast.success / toast.error / toast() / sonner toast()
    ("toast", re.compile(r"\btoast(?:\.(?:success|error|info|warning|message))?\(\s*['\"]([^'\"]{3,})['\"]")),

    # alert("...") / confirm("...")
    ("alert", re.compile(r"\balert\(\s*['\"]([^'\"]{3,})['\"]")),

    # Object-literal string properties commonly used for user-facing copy
    # (FALLBACK_TRENDS fixtures, default chip lists, etc.).
    ("object-literal", re.compile(
        r"\b(?:label|headline|summary|description|title|name|message|text|"
        r"subtitle|caption|tagline|cta|hint|tooltip|emptyTitle|emptyDescription)"
        r"\s*:\s*['\"]([A-Z][^'\"]{2,})['\"]"
    )),
]

# Multi-line JSX-text regex — scans whole-file with DOTALL so it catches text
# split across lines (e.g. a <div>...newline...text...newline...</div>).
# Reject any match containing JSX/JS metacharacters so we only keep pure text.
_JSX_TEXT_MULTI = re.compile(r">\s*([^<>{}=]+?)\s*<", re.DOTALL)

# Lines we want to skip entirely.
_SKIP_LINE_RE = re.compile(r"""
    ^\s*//                          # // single-line comment
    | ^\s*\*                        # JSDoc continuation
    | ^\s*import\b                  # import statement
    | console\.(log|warn|error|info|debug) # console.* (developer-only)
    | data-testid\s*=               # test ids
""", re.VERBOSE)


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s]", "", s).strip().lower()
    parts = s.split()[:5]
    return "_".join(parts) or "untitled"


def suggested_key(rel_path: Path, english: str) -> str:
    """Derive a dotted i18n key from the file location and a slug."""
    # src/pages/ListingDetail.jsx -> listingDetail
    stem = rel_path.stem
    stem_l = stem[0].lower() + stem[1:] if stem else "page"
    parts = list(rel_path.parts)
    # Drop "src" prefix
    if parts and parts[0] == "src":
        parts = parts[1:]
    # Use top-level folder as namespace: pages / components / hooks
    namespace = parts[0] if len(parts) > 1 else "page"
    return f"{namespace}.{stem_l}.{slugify(english)}"


def context_excludes_string(line: str, value: str) -> bool:
    """Return True if this literal is OK (already i18n-wrapped or noise)."""
    # If the line wraps this exact string in t(...) or i18n.t(...), skip.
    if f"t('{value}'" in line or f't("{value}"' in line:
        return True
    if f"i18n.t('{value}'" in line or f'i18n.t("{value}"' in line:
        return True
    return False


def main() -> int:
    findings: dict[str, dict] = defaultdict(
        lambda: {"english": None, "occurrences": [], "kinds": set()}
    )
    files_scanned = 0
    skipped_known = 0

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in (".js", ".jsx", ".ts", ".tsx"):
            continue
        # Skip generated / vendored / test code
        if "__tests__" in path.parts or path.name.endswith(".test.js") or path.name.endswith(".test.jsx"):
            continue
        if "/locales/" in str(path):
            continue
        # countries.js is a 250-entry ISO list — should be handled via
        # Intl.DisplayNames or a dedicated i18n library, NOT by translating
        # each name through the same dictionary as UI copy.
        if path.name == "countries.js":
            continue
        # components/ui/* are Shadcn primitives — pure wrappers, no copy.
        if "components/ui/" in str(path) and path.name not in ("toaster.jsx",):
            continue
        files_scanned += 1
        rel = path.relative_to(ROOT.parent)

        try:
            full_text = path.read_text(encoding="utf-8")
            lines = full_text.splitlines()

            # ---- Pass 1: JSX text (multi-line scan over whole file) ----
            for m in _JSX_TEXT_MULTI.finditer(full_text):
                raw = m.group(1)
                text = raw.replace("&nbsp;", " ").replace("&amp;", "&").strip()
                # Collapse whitespace runs (newlines, tabs) inside JSX text
                text = re.sub(r"\s+", " ", text)
                if _is_noise(text):
                    continue
                if not _WORD_RE.search(text):
                    continue
                # Locate which source line this match starts on so the
                # report points somewhere meaningful.
                lineno = full_text.count("\n", 0, m.start()) + 1
                # Skip if the line is a comment or import or wraps the text in t()
                line_ctx = lines[lineno - 1] if lineno - 1 < len(lines) else ""
                if _SKIP_LINE_RE.search(line_ctx):
                    continue
                if context_excludes_string(line_ctx, text):
                    continue
                if text in KNOWN_VALUES:
                    skipped_known += 1
                    continue
                entry = findings[text]
                entry["english"] = text
                entry["occurrences"].append({
                    "file": str(rel),
                    "line": lineno,
                    "kind": "jsx-text",
                })
                entry["kinds"].add("jsx-text")

            # ---- Pass 2: per-line attribute / toast / alert scans ----
            for lineno, line in enumerate(lines, start=1):
                if _SKIP_LINE_RE.search(line):
                    continue
                for kind, regex in PATTERNS:
                    for m in regex.finditer(line):
                        raw = m.group(1).strip()
                        text = raw.replace("&nbsp;", " ").replace("&amp;", "&")
                        if _is_noise(text):
                            continue
                        if not _WORD_RE.search(text):
                            continue
                        if context_excludes_string(line, text):
                            continue
                        if text in KNOWN_VALUES:
                            skipped_known += 1
                            continue
                        entry = findings[text]
                        entry["english"] = text
                        entry["occurrences"].append({
                            "file": str(rel),
                            "line": lineno,
                            "kind": kind,
                        })
                        entry["kinds"].add(kind)
        except Exception as exc:
            print(f"  ! failed to read {rel}: {exc}")

    # Build deterministic, ordered output
    findings_list = []
    used_keys = set()
    for english in sorted(findings):
        entry = findings[english]
        rel_first = Path(entry["occurrences"][0]["file"])
        key = suggested_key(rel_first, english)
        # Disambiguate if collision
        base = key
        i = 2
        while key in used_keys:
            key = f"{base}_{i}"
            i += 1
        used_keys.add(key)
        findings_list.append({
            "suggested_key": key,
            "english": english,
            "kinds": sorted(entry["kinds"]),
            "occurrences": entry["occurrences"],
        })

    out = {
        "_purpose": (
            "These English strings are currently hard-coded in the React "
            "frontend and are NOT yet wired through react-i18next. Translate "
            "each `english` value into ALL 11 non-English target languages "
            "listed below. The keys / occurrences are reference only — do "
            "not invent or rename them. Return ONE JSON object whose top "
            "level has each ISO language code as a key, and whose values "
            "are dictionaries keyed by `suggested_key` -> translated string."
        ),
        "_source_language": "English (en)",
        "_target_languages": ["ar", "de", "es", "fr", "he", "hi", "it",
                              "ja", "pt", "ru", "zh"],
        "_instructions": (
            "RULES (read every one):\n"
            "1. Output ONE valid JSON object. Top-level keys are the 11 "
            "ISO language codes listed in _target_languages.\n"
            "2. For each language, return a dict mapping every "
            "suggested_key to the translated string.\n"
            "3. Translate every entry from `findings[*].english`. Do not "
            "skip, merge, or rename keys.\n"
            "4. Preserve emoji, punctuation, capitalisation conventions of "
            "the target language, and any text in {curly} or {{double-curly}} "
            "braces — those are placeholders, leave them verbatim.\n"
            "5. Keep these proper nouns / brand terms untranslated: "
            "DressApp, Trend-Scout, Fashion Scout, FashionCLIP, Google "
            "Calendar, Levi's, Stripe, GitHub, Business of Fashion.\n"
            "6. 'AI' should be translated to 'IA' in fr/es/pt/it (and the "
            "natural local equivalent elsewhere — e.g. 'KI' in de, 'AI' "
            "in ja/zh, 'ИИ' in ru).\n"
            "7. Use straight ASCII quotes (\") as JSON delimiters. Escape "
            "any literal double quote inside a value with a backslash: \\\".\n"
            "8. Use the target-language's typographic conventions (e.g. "
            "espace insécable before « : ; ! ? » in French).\n"
            "9. Do NOT wrap the JSON in markdown code fences.\n"
        ),
        "_examples": [
            {
                "suggested_key": "components.profileDetailsCard.eg_marketing_manager_student_barista",
                "english": "e.g. Marketing manager, Student, Barista",
                "fr": "ex. responsable marketing, étudiant·e, barista",
                "de": "z. B. Marketing-Manager, Student, Barista",
                "zh": "例如：市场经理、学生、咖啡师",
                "note": "Placeholder for an Occupation input field.",
            },
            {
                "suggested_key": "pages.listingDetail.local_pickup_preferred_no_shipping_fee",
                "english": "🌱 Local pickup preferred — no shipping fee",
                "fr": "🌱 Retrait en personne privilégié — pas de frais d'expédition",
                "note": "Keep the emoji and the em-dash.",
            },
        ],
        "findings": findings_list,
    }

    out_path = Path("/app/docs/locale_backfill_untranslated.json")
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Console summary
    print(f"\nFiles scanned:                {files_scanned}")
    print(f"Distinct English strings:     {len(findings_list)}")
    print(f"Strings already in en.json:   {skipped_known}")
    print(f"\nKind breakdown:")
    kind_counts: dict[str, int] = defaultdict(int)
    for entry in findings_list:
        for k in entry["kinds"]:
            kind_counts[k] += 1
    for k in sorted(kind_counts):
        print(f"  {k:<15} {kind_counts[k]}")
    print(f"\nWrote -> {out_path}  ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
