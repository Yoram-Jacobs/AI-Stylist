#!/usr/bin/env python3
"""Merge translations from the audit dictionary into the locale JSON files.

Input shapes accepted:
    A) {locale: {suggested_key: translated_value, ...}, ...}
       (Gemini / DeepSeek / GPT format for new-key dictionaries)
    B) {findings: [...], _examples: [...], ...}
       (the audit file itself — used to seed en.json with English source)

For every (locale, suggested_key, value) triple it deep-merges the value
into the nested location implied by the dotted suggested_key, writing the
12 locale files in /app/frontend/src/locales/.

Usage:
    python3 apply_audit_translations.py <audit_file> <translations_file> [options]

Options:
    --dry-run        Show what would change without writing.
    --no-backup      Skip writing .bak alongside each locale file.
    --skip-en        Don't seed en.json with the English source values.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

DEFAULT_LOCALES_DIR = Path("/app/frontend/src/locales")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|\{[^{}]+\}|%[sd]")
KNOWN_LOCALES = {"ar", "de", "es", "fr", "he", "hi", "it", "ja", "pt", "ru", "zh"}


def set_by_dotted(tree: dict, dotted: str, value: Any) -> None:
    """Set tree[a][b][c] = value for a dotted key 'a.b.c', creating dicts."""
    parts = dotted.split(".")
    cur: Any = tree
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def get_by_dotted(tree: dict, dotted: str) -> Any:
    cur: Any = tree
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def placeholders(s: str) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(s)) if isinstance(s, str) else []


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audit", help="The audit file produced by audit_hardcoded_strings.py")
    p.add_argument("translations", help="LLM-translated dictionary {locale: {suggested_key: value}}")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--skip-en", action="store_true",
                   help="Don't seed en.json with the English source values.")
    p.add_argument("--locales-dir", default=str(DEFAULT_LOCALES_DIR))
    args = p.parse_args()

    audit_path = Path(args.audit)
    trans_path = Path(args.translations)
    locales_dir = Path(args.locales_dir)
    if not audit_path.exists():
        print(f"Audit not found: {audit_path}", file=sys.stderr)
        return 1
    if not trans_path.exists():
        print(f"Translations not found: {trans_path}", file=sys.stderr)
        return 1

    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    translations = json.loads(trans_path.read_text(encoding="utf-8-sig"))

    # Build (suggested_key -> english) map from audit.
    findings = audit.get("findings") or []
    audit_map = {f["suggested_key"]: f["english"] for f in findings}
    print(f"Audit: {len(audit_map)} keys")

    # ------------------------------------------------------------------
    # defaultValue redirection: when a finding's kind is `defaultValue`,
    # the developer already chose an i18n key — they just forgot to add
    # it to en.json. Inspect the source line and redirect the translation
    # to that existing key rather than minting the `suggested_key`.
    # ------------------------------------------------------------------
    repo_root = Path("/app/frontend")
    key_alias: dict[str, str] = {}  # suggested_key -> existing_key
    _DV_RE = re.compile(
        r"\bt\(\s*['\"]([\w.]+)['\"]\s*,\s*\{\s*defaultValue\s*:\s*"
        r"['\"]([^'\"]+)['\"]\s*\}\s*\)"
    )
    for f in findings:
        # Only kind == defaultValue matters for redirection.
        kinds = set(f.get("kinds") or [])
        if "defaultValue" not in kinds:
            continue
        suggested = f["suggested_key"]
        for occ in f["occurrences"]:
            if occ.get("kind") != "defaultValue":
                continue
            src = repo_root / occ["file"]
            if not src.exists():
                continue
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
                ctx = "\n".join(lines[max(0, occ["line"] - 2): occ["line"] + 2])
                m = _DV_RE.search(ctx)
                if m and m.group(2) == f["english"]:
                    existing = m.group(1)
                    key_alias[suggested] = existing
                    break
            except Exception:
                pass

    if key_alias:
        print(f"  -> redirected {len(key_alias)} defaultValue findings to existing keys:")
        for k, v in list(key_alias.items())[:5]:
            print(f"     {k}  ->  {v}")
        if len(key_alias) > 5:
            print(f"     ... +{len(key_alias) - 5} more")

    def effective_key(suggested: str) -> str:
        return key_alias.get(suggested, suggested)

    # Drop meta keys from translations
    trans_locales = {k: v for k, v in translations.items()
                     if k in KNOWN_LOCALES and isinstance(v, dict)}
    print(f"Translation locales: {sorted(trans_locales.keys())}")

    # Sanity checks: every translation key must be in the audit map
    for loc, kv in trans_locales.items():
        unknown = set(kv) - set(audit_map)
        missing = set(audit_map) - set(kv)
        if unknown:
            print(f"  ! {loc}: {len(unknown)} keys not in audit (will be skipped): "
                  f"{sorted(unknown)[:3]}{'...' if len(unknown) > 3 else ''}")
        if missing:
            print(f"  ! {loc}: {len(missing)} audit keys missing from translations: "
                  f"{sorted(missing)[:3]}{'...' if len(missing) > 3 else ''}")

    # Per-locale merge
    total = {"applied": 0, "unchanged": 0, "skipped": 0, "placeholder_warn": 0}
    locales_to_write: list[tuple[str, dict, Path]] = []

    # Seed en.json with the English source values first
    if not args.skip_en:
        trans_locales = {"en": audit_map, **trans_locales}

    for loc, kv in trans_locales.items():
        loc_path = locales_dir / f"{loc}.json"
        if not loc_path.is_file():
            print(f"  ! {loc}: locale file missing, skipping")
            continue
        tree = json.loads(loc_path.read_text(encoding="utf-8-sig"))
        applied = 0
        unchanged = 0
        warns = 0
        for key, value in kv.items():
            if key not in audit_map:
                continue  # already warned above
            if not isinstance(value, str):
                continue
            target_key = effective_key(key)
            en_val = audit_map[key]
            en_ph = placeholders(en_val)
            new_ph = placeholders(value)
            if en_ph != new_ph and loc != "en":
                print(f"    ~ {loc}/{key}: placeholder drift en={en_ph} new={new_ph}")
                warns += 1
            existing = get_by_dotted(tree, target_key)
            if existing == value:
                unchanged += 1
                continue
            set_by_dotted(tree, target_key, value)
            applied += 1

        total["applied"] += applied
        total["unchanged"] += unchanged
        total["placeholder_warn"] += warns

        suffix = " (DRY-RUN)" if args.dry_run else ""
        print(f"  [{loc}] +{applied}  ={unchanged}  ~{warns}{suffix}")
        if not args.dry_run and applied:
            locales_to_write.append((loc, tree, loc_path))

    # Write
    for loc, tree, path in locales_to_write:
        if not args.no_backup:
            shutil.copy2(path, path.with_suffix(".json.bak"))
        path.write_text(
            json.dumps(tree, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print()
    print("=== summary ===")
    print(f"  applied:          {total['applied']}")
    print(f"  unchanged:        {total['unchanged']}")
    print(f"  placeholder warns:{total['placeholder_warn']}")
    if args.dry_run:
        print("  (dry-run — no files were modified)")
    elif not args.no_backup:
        print(f"  backups written:  {len(locales_to_write)} files (*.json.bak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
