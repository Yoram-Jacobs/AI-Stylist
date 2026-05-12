"""Backend i18n service — single source of truth across frontend & backend.

This module reads the locale JSON files that ship with the React frontend
(``/app/frontend/src/locales/*.json``) at process start, so there is no
duplicated dictionary on the server. Anything the user sees in their chosen
language on the web app can be rendered the same way on the server (system
emails, stylist prompts, push notifications, …).

Public API
----------
- ``SUPPORTED_LANGUAGES``  – list[dict] mirroring the frontend metadata.
- ``LANG_NAMES``           – dict[str, str] mapping ISO code -> English name.
- ``RTL_LANGUAGES``        – set[str] of right-to-left language codes.
- ``available_languages()``– list[str] of loaded locale codes.
- ``is_rtl(code)``         – bool
- ``has_language(code)``   – bool, case-insensitive
- ``t(key, lang='en', **vars)``    – translate a dotted key with interpolation
                                     and English fallback.
- ``language_directive(code)``     – build the LLM "OUTPUT LANGUAGE = X" block
                                     that the stylist services prepend to
                                     system prompts.

The module is safe to import multiple times — locale files are loaded once
at first import. Hot-reload during development picks up frontend edits on
the next backend restart (supervisor restart).
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locale source — the frontend JSON files are the canonical store.
# ---------------------------------------------------------------------------

# Allow override via env var so tests / Docker images can point elsewhere.
LOCALES_DIR = Path(
    os.environ.get("DRESSAPP_LOCALES_DIR", "/app/frontend/src/locales")
).resolve()

# Mirrors SUPPORTED_LANGUAGES in /app/frontend/src/lib/i18n.js — keep in sync.
SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "native_name": "English",          "english_name": "English",              "dir": "ltr"},
    {"code": "he", "native_name": "עברית",            "english_name": "Hebrew",               "dir": "rtl"},
    {"code": "ar", "native_name": "العربية",          "english_name": "Arabic",               "dir": "rtl"},
    {"code": "es", "native_name": "Español",          "english_name": "Spanish",              "dir": "ltr"},
    {"code": "fr", "native_name": "Français",         "english_name": "French",               "dir": "ltr"},
    {"code": "de", "native_name": "Deutsch",          "english_name": "German",               "dir": "ltr"},
    {"code": "it", "native_name": "Italiano",         "english_name": "Italian",              "dir": "ltr"},
    {"code": "pt", "native_name": "Português",        "english_name": "Portuguese",           "dir": "ltr"},
    {"code": "ru", "native_name": "Русский",          "english_name": "Russian",              "dir": "ltr"},
    {"code": "zh", "native_name": "中文（简体）",       "english_name": "Chinese (Simplified)", "dir": "ltr"},
    {"code": "ja", "native_name": "日本語",            "english_name": "Japanese",             "dir": "ltr"},
    {"code": "hi", "native_name": "हिन्दी",           "english_name": "Hindi",                "dir": "ltr"},
]

LANG_NAMES: dict[str, str] = {
    item["code"]: item["english_name"] for item in SUPPORTED_LANGUAGES
}

RTL_LANGUAGES: frozenset[str] = frozenset(
    item["code"] for item in SUPPORTED_LANGUAGES if item["dir"] == "rtl"
)

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_locale(code: str) -> dict[str, Any]:
    path = LOCALES_DIR / f"{code}.json"
    if not path.is_file():
        log.warning("i18n: locale file missing for %r (looked at %s)", code, path)
        return {}
    try:
        # utf-8-sig tolerates a stray BOM, matching the apply script behaviour.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("i18n: failed to load %s: %s", path, exc)
        return {}


_TRANSLATIONS: dict[str, dict[str, Any]] = {
    item["code"]: _load_locale(item["code"]) for item in SUPPORTED_LANGUAGES
}


def _walk_leaves(tree: Any):
    if isinstance(tree, dict):
        for v in tree.values():
            yield from _walk_leaves(v)
    elif isinstance(tree, list):
        for v in tree:
            yield from _walk_leaves(v)
    else:
        yield tree


_LEAF_COUNTS = {code: sum(1 for _ in _walk_leaves(tree)) for code, tree in _TRANSLATIONS.items()}

log.info(
    "i18n: loaded %d locales from %s — %s",
    sum(1 for v in _TRANSLATIONS.values() if v),
    LOCALES_DIR,
    ", ".join(f"{c}={_LEAF_COUNTS[c]}" for c in _TRANSLATIONS),
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def available_languages() -> list[str]:
    """Locale codes that loaded successfully (non-empty dict)."""
    return [code for code, tree in _TRANSLATIONS.items() if tree]


def has_language(code: str | None) -> bool:
    if not code:
        return False
    return code.lower() in _TRANSLATIONS


def is_rtl(code: str | None) -> bool:
    return bool(code) and code.lower() in RTL_LANGUAGES


def _resolve(tree: dict[str, Any], dotted_key: str) -> Any:
    """Walk a dotted/bracketed path through a nested dict."""
    cur: Any = tree
    for part in dotted_key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# Matches {{var}}, {var}, %(var)s — the same shapes the frontend handles.
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}|\{(\w+)\}|%\((\w+)\)s")


def _interpolate(template: str, variables: dict[str, Any]) -> str:
    if not variables or not isinstance(template, str):
        return template

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2) or m.group(3)
        if name in variables:
            return str(variables[name])
        return m.group(0)  # leave untouched if not provided

    return _PLACEHOLDER_RE.sub(_sub, template)


def t(key: str, lang: str | None = "en", /, **variables: Any) -> str:
    """Translate a dotted i18n key into the requested language.

    Resolution order:
        1. Exact ``lang`` (or its lower-cased form).
        2. English (``en``) — falls back automatically when the key is
           missing or empty in ``lang``.
        3. The raw ``key`` itself, so the caller always gets a string back.

    Placeholders ``{{var}}``, ``{var}``, ``%(var)s`` are interpolated with
    ``variables`` if provided.

    >>> t("nav.experts", "fr")
    'Experts'
    >>> t("market.netShort", "de", amount="€19,90")
    'netto €19,90'
    """
    code = (lang or "en").lower()
    tree = _TRANSLATIONS.get(code) or _TRANSLATIONS.get("en") or {}
    value = _resolve(tree, key)

    if not isinstance(value, str) or not value.strip():
        # Fall back to English if missing/empty in the requested locale.
        en_tree = _TRANSLATIONS.get("en") or {}
        value = _resolve(en_tree, key)

    if not isinstance(value, str):
        return key  # last-resort: give the caller something printable

    return _interpolate(value, variables)


# ---------------------------------------------------------------------------
# LLM-facing helpers (used by the stylist services)
# ---------------------------------------------------------------------------

def language_directive(code: str | None) -> str:
    """Return the ``LANGUAGE DIRECTIVE`` block appended to LLM system prompts.

    For ``en`` (the default UI language) it returns an empty string so we
    don't waste tokens telling the model to write in English.
    """
    code = (code or "en").lower()
    name = LANG_NAMES.get(code, "English")
    if code == "en":
        return ""
    return (
        f"\n\nLANGUAGE DIRECTIVE: The user's preferred UI language is "
        f"{name} (code: {code}). Write every human-readable string you "
        f"return — including `reasoning_summary`, each item `description`, "
        f"each recommendation `name` and `why`, every entry of `do_dont`, "
        f"`shopping_suggestions`, and the final `spoken_reply` — in "
        f"natural, idiomatic {name}. Keep JSON keys and enum-ish values "
        f"(like `role: top|bottom|outerwear|shoes|accessory|dress`) "
        f"in English exactly as specified above."
    )
