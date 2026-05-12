#!/usr/bin/env python3
"""Apply translation backfills into /app/frontend/src/locales/<loc>.json.

The script auto-detects two input shapes:

  1) Starter format (produced by the helper that builds locale_backfill_starters.json):
     {
       "_summary": {...},
       "locales": {
         "fr": {
           "_meta": {...},
           "strings": { "nav": { "experts": "Experts", ... }, ... }
         },
         ...
       }
     }

  2) Flat dotted-key format (what humans / LLMs usually paste back):
     {
       "fr": {
         "nav.experts": "Experts",
         "addItem.removeTagAria": "Supprimer l'étiquette {{label}}",
         ...
       },
       ...
     }

For every (locale, key, value) triple it:
  • Verifies the key exists in en.json (else: warn + skip).
  • Verifies the value preserves the placeholder set of the English source
    ({name}, {{count}}, %s, %d). Mismatches are warnings, not blockers,
    because some languages legitimately drop placeholders in plural forms
    (e.g. Arabic *_one).
  • Deep-merges into the existing locale file, preserving every other key.

Usage
-----
    python scripts/apply_locale_backfill.py <translations.json> [options]

Options
-------
    --dry-run        Show what would change without writing anything.
    --no-backup      Don't write a .bak alongside each locale file.
    --locales-dir P  Override the locales directory (default
                     /app/frontend/src/locales).
    --en-path P      Override en.json path (default <locales-dir>/en.json).
    --only loc[,loc] Limit to a subset of locales from the payload.

Exit codes
----------
    0  changes applied (or would be applied in --dry-run)
    1  payload could not be parsed or no locales matched
    2  every locale had hard validation errors (none written)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable

DEFAULT_LOCALES_DIR = Path("/app/frontend/src/locales")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|\{[^{}]+\}|%[sd]")


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def flatten(tree: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict/list tree into dotted/bracketed paths."""
    out: dict[str, Any] = {}
    if isinstance(tree, dict):
        for k, v in tree.items():
            path = f"{prefix}.{k}" if prefix else k
            out.update(flatten(v, path))
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = tree
    return out


_PART_RE = re.compile(r"^([^\[]+)((?:\[\d+\])*)$")
_SPLIT_RE = re.compile(r"\.(?![^\[]*\])")  # split on '.' that aren't inside [..]


def set_by_path(root: dict, path: str, value: Any) -> None:
    """Set value at a dotted/bracketed path, creating containers as needed."""
    parts = _SPLIT_RE.split(path)
    cur: Any = root
    for i, part in enumerate(parts):
        m = _PART_RE.match(part)
        if not m:
            raise ValueError(f"Bad path segment: {part!r} in {path!r}")
        key = m.group(1)
        idxs = [int(x) for x in re.findall(r"\[(\d+)\]", m.group(2))]
        last = i == len(parts) - 1
        if not idxs:
            if last:
                cur[key] = value
                return
            cur = cur.setdefault(key, {})
        else:
            cur = cur.setdefault(key, [])
            for j, idx in enumerate(idxs):
                while len(cur) <= idx:
                    cur.append({})
                inner_last = last and j == len(idxs) - 1
                if inner_last:
                    cur[idx] = value
                    return
                if not isinstance(cur[idx], (dict, list)):
                    cur[idx] = {}
                cur = cur[idx]


# ---------------------------------------------------------------------------
# Payload normalisation
# ---------------------------------------------------------------------------

def normalise_payload(payload: dict) -> dict[str, dict[str, Any]]:
    """Return {locale_code: {dotted_key: value}} regardless of input shape."""
    # Starter format
    if isinstance(payload, dict) and "locales" in payload and isinstance(payload["locales"], dict):
        out: dict[str, dict[str, Any]] = {}
        for loc, body in payload["locales"].items():
            if not isinstance(body, dict):
                continue
            strings = body.get("strings", body)
            out[loc] = flatten(strings)
        return out

    # Flat dotted-key format
    if isinstance(payload, dict) and all(isinstance(v, dict) for v in payload.values()):
        out = {}
        for loc, kv in payload.items():
            # Could itself be nested or already flat — flatten either way.
            out[loc] = flatten(kv)
        return out

    raise ValueError(
        "Unrecognised payload shape — expected either {_summary, locales:{...}} "
        "or {locale: {dotted.key: value}}."
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def placeholders(s: Any) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(s)) if isinstance(s, str) else []


# ---------------------------------------------------------------------------
# Per-locale apply
# ---------------------------------------------------------------------------

def apply_locale(
    locale: str,
    new_kv: dict[str, Any],
    en_flat: dict[str, Any],
    locales_dir: Path,
    dry_run: bool,
    backup: bool,
) -> dict[str, int]:
    locale_path = locales_dir / f"{locale}.json"
    if not locale_path.exists():
        print(f"[{locale}] ! locale file not found at {locale_path}, skipping")
        return {"applied": 0, "unchanged": 0, "skipped_unknown": 0, "placeholder_warn": 0}

    tree = json.loads(locale_path.read_text(encoding="utf-8"))
    existing_flat = flatten(tree)

    applied = 0
    unchanged = 0
    skipped_unknown = 0
    placeholder_warn = 0

    for key, new_val in new_kv.items():
        if key not in en_flat:
            print(f"[{locale}] ! unknown key not in en.json: {key} (skipped)")
            skipped_unknown += 1
            continue
        en_val = en_flat[key]
        if isinstance(en_val, str) and isinstance(new_val, str):
            en_ph = placeholders(en_val)
            new_ph = placeholders(new_val)
            if en_ph != new_ph:
                print(
                    f"[{locale}] ~ placeholder drift on {key}: "
                    f"en={en_ph} new={new_ph} (applied anyway)"
                )
                placeholder_warn += 1
        if existing_flat.get(key) == new_val:
            unchanged += 1
            continue
        set_by_path(tree, key, new_val)
        applied += 1

    if applied == 0:
        print(f"[{locale}] no changes ({unchanged} already up-to-date, "
              f"{skipped_unknown} unknown, {placeholder_warn} placeholder warns)")
        return {"applied": 0, "unchanged": unchanged,
                "skipped_unknown": skipped_unknown,
                "placeholder_warn": placeholder_warn}

    if dry_run:
        print(f"[{locale}] DRY-RUN would apply {applied} change(s) "
              f"({unchanged} unchanged, {skipped_unknown} unknown, "
              f"{placeholder_warn} placeholder warns)")
    else:
        if backup:
            shutil.copy2(locale_path, locale_path.with_suffix(".json.bak"))
        # Pretty-print to match existing locale-file formatting (2-space indent,
        # ensure_ascii=False, trailing newline).
        locale_path.write_text(
            json.dumps(tree, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[{locale}] wrote {applied} change(s) "
              f"({unchanged} unchanged, {skipped_unknown} unknown, "
              f"{placeholder_warn} placeholder warns)"
              + (" + backup" if backup else ""))

    return {"applied": applied, "unchanged": unchanged,
            "skipped_unknown": skipped_unknown,
            "placeholder_warn": placeholder_warn}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge a translation payload into locale JSON files.")
    p.add_argument("payload", help="Path to the translations JSON file.")
    p.add_argument("--dry-run", action="store_true", help="Show diffs without writing.")
    p.add_argument("--no-backup", action="store_true", help="Skip writing .bak files.")
    p.add_argument("--locales-dir", default=str(DEFAULT_LOCALES_DIR),
                   help=f"Locales directory (default {DEFAULT_LOCALES_DIR}).")
    p.add_argument("--en-path", default=None,
                   help="Override en.json path (default <locales-dir>/en.json).")
    p.add_argument("--only", default=None,
                   help="Comma-separated locale codes to limit application to.")
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    payload_path = Path(args.payload)
    if not payload_path.exists():
        print(f"Payload not found: {payload_path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Payload is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        per_locale = normalise_payload(payload)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    locales_dir = Path(args.locales_dir)
    en_path = Path(args.en_path) if args.en_path else locales_dir / "en.json"
    if not en_path.exists():
        print(f"en.json not found at {en_path}", file=sys.stderr)
        return 1
    en_flat = flatten(json.loads(en_path.read_text(encoding="utf-8")))

    only = {c.strip() for c in args.only.split(",")} if args.only else None
    if only:
        per_locale = {k: v for k, v in per_locale.items() if k in only}
    if not per_locale:
        print("No locales selected from payload.", file=sys.stderr)
        return 1

    totals: dict[str, int] = {"applied": 0, "unchanged": 0,
                              "skipped_unknown": 0, "placeholder_warn": 0}
    for locale in sorted(per_locale):
        stats = apply_locale(
            locale=locale,
            new_kv=per_locale[locale],
            en_flat=en_flat,
            locales_dir=locales_dir,
            dry_run=args.dry_run,
            backup=not args.no_backup,
        )
        for k, v in stats.items():
            totals[k] += v

    print("\n=== summary ===")
    print(f"  applied:          {totals['applied']}")
    print(f"  unchanged:        {totals['unchanged']}")
    print(f"  unknown-skipped:  {totals['skipped_unknown']}")
    print(f"  placeholder warns:{totals['placeholder_warn']}")
    if args.dry_run:
        print("  (dry-run — no files were modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
