#!/usr/bin/env python3
"""Patch JSX/JS source files to replace hard-coded English strings with
``t('the.i18n.key')`` calls, using the audit produced by
audit_hardcoded_strings.py.

Strategy
--------
For each finding, locate the source line and apply ONE of these targeted
rewrites depending on the audit `kind`:

  jsx-text         '>Some English<'                       -> '>{t("key")}<'
  placeholder      'placeholder="Some English"'           -> 'placeholder={t("key")}'
  aria-label       'aria-label="Some English"'            -> 'aria-label={t("key")}'
  title            'title="Some English"'                 -> 'title={t("key")}'
  alt              'alt="Some English"'                   -> 'alt={t("key")}'
  defaultValue     "t('foo', { defaultValue: 'Some' })"   -> 't("foo")'
                   (only when 'foo' was the suggested key being added —
                    we keep defaultValue otherwise as a soft fallback)
  toast            "toast.error('Some English')"          -> "toast.error(t('key'))"
  alert            "alert('Some English')"                -> "alert(t('key'))"
  object-literal   "label: 'Some English'"                -> "label: t('key')"
                   (skipped for module-scope literals — those are listed
                    in a separate report for manual treatment)

Safeguards
----------
* Files are scanned to confirm `useTranslation` is imported and `t` is
  in scope; module-scope literals (FALLBACK_TRENDS, SeoBase META, …) are
  skipped because `t` is not available at module load time.
* `.bak` is written for every patched file (`--no-backup` to disable).
* `--dry-run` shows the planned edits without writing.
* Each occurrence is patched at most once per pass; if the same English
  string appears in multiple files, every occurrence is patched.

Usage
-----
    python3 patch_hardcoded_strings.py <audit_file> [--dry-run] [--no-backup]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path("/app/frontend")
SRC_ROOT = REPO_ROOT / "src"


# ---------------------------------------------------------------------------
# Per-file scope detection
# ---------------------------------------------------------------------------

def find_component_function_lines(text: str) -> list[tuple[int, int]]:
    """Return [(start_line, end_line), ...] for top-level function components.

    A "component" here is any `function Foo(...)` or `const Foo = (...) => {`
    declared at module scope. The end is detected by matching braces from
    the function's opening `{`.
    """
    lines = text.splitlines()
    ranges = []
    func_re = re.compile(
        r"^(?:export\s+default\s+|export\s+)?"
        r"(?:function\s+([A-Z]\w*)\s*\(|const\s+([A-Z]\w*)\s*=\s*(?:\([^)]*\)|\w+)\s*=>\s*\{)"
    )
    for i, ln in enumerate(lines):
        m = func_re.match(ln)
        if not m:
            continue
        # Find the opening brace position
        start = i
        depth = 0
        seen_open = False
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == "{":
                    depth += 1
                    seen_open = True
                elif ch == "}":
                    depth -= 1
                    if seen_open and depth == 0:
                        ranges.append((start + 1, j + 1))  # 1-indexed
                        break
            else:
                continue
            break
    return ranges


def in_any_range(lineno: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= lineno <= hi for lo, hi in ranges)


# ---------------------------------------------------------------------------
# Per-kind patch helpers
# ---------------------------------------------------------------------------

def _escape_for_regex(s: str) -> str:
    return re.escape(s)


def _t_call(key: str) -> str:
    return f"t('{key}')"


def patch_attribute(line: str, attr: str, english: str, key: str) -> str | None:
    """Replace `attr="english"` (or `'english'`) with `attr={t('key')}`. """
    for quote in ('"', "'"):
        needle = f'{attr}={quote}{english}{quote}'
        if needle in line:
            return line.replace(needle, f"{attr}={{{_t_call(key)}}}", 1)
    return None


def patch_jsx_text(text: str, english: str, key: str) -> str | None:
    """Replace a JSX text run with `{t('key')}`. Match the inner content
    between `>` and `<`. The audit collapses whitespace runs in the captured
    English, so we rebuild a pattern that allows any whitespace between the
    original words to handle multi-line JSX text."""
    # Word-split the English and rebuild a regex that allows \s+ between words.
    words = english.split(" ")
    inner = r"\s+".join(re.escape(w) for w in words)
    pattern = r"(>)(\s*)" + inner + r"(\s*)(<)"
    new = re.sub(
        pattern,
        lambda m: f"{m.group(1)}{m.group(2)}{{{_t_call(key)}}}{m.group(3)}{m.group(4)}",
        text,
        count=1,
        flags=re.DOTALL,
    )
    return new if new != text else None


def patch_toast(line: str, english: str, key: str) -> str | None:
    """toast.xxx('Some') / toast('Some') -> toast.xxx(t('key'))."""
    for quote in ('"', "'"):
        pattern = re.compile(
            r"(toast(?:\.\w+)?\(\s*)" + quote + re.escape(english) + quote
        )
        new = pattern.sub(lambda m: f"{m.group(1)}{_t_call(key)}", line, count=1)
        if new != line:
            return new
    return None


def patch_alert(line: str, english: str, key: str) -> str | None:
    for quote in ('"', "'"):
        pattern = re.compile(r"(\balert\(\s*)" + quote + re.escape(english) + quote)
        new = pattern.sub(lambda m: f"{m.group(1)}{_t_call(key)}", line, count=1)
        if new != line:
            return new
    return None


_OL_PROPS = "label|headline|summary|description|title|name|message|text|subtitle|caption|tagline|cta|hint|tooltip|emptyTitle|emptyDescription"


def patch_object_literal(line: str, english: str, key: str) -> str | None:
    """label: 'English' -> label: t('key')."""
    for quote in ('"', "'"):
        pattern = re.compile(
            r"\b(" + _OL_PROPS + r")(\s*:\s*)" + quote + re.escape(english) + quote
        )
        new = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{_t_call(key)}", line, count=1
        )
        if new != line:
            return new
    return None


def patch_default_value(line: str, english: str, key: str) -> str | None:
    """Inside `t('foo', { defaultValue: 'English' })`:

    * If `foo` equals the new suggested key, just trim the defaultValue.
    * Otherwise (existing key already in i18n), the defaultValue stays —
      we don't rewrite, because the existing i18n key may legitimately
      be different from the suggested one.
    """
    # Look for t('existing_key', { defaultValue: 'English' })
    for q in ('"', "'"):
        m = re.search(
            r"\bt\(\s*([\"'])([^\"']+)\1\s*,\s*\{\s*defaultValue\s*:\s*"
            + q + re.escape(english) + q + r"\s*\}\s*\)",
            line,
        )
        if not m:
            continue
        existing_key = m.group(2)
        if existing_key == key:
            # Trim the { defaultValue: ... } block since the key now has a translation.
            new = re.sub(
                r"\bt\(\s*([\"'])" + re.escape(existing_key)
                + r"\1\s*,\s*\{\s*defaultValue\s*:\s*"
                + q + re.escape(english) + q + r"\s*\}\s*\)",
                f"t('{existing_key}')",
                line, count=1,
            )
            return new
        # Existing key differs — keep the defaultValue as a safety net.
        return None
    return None


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audit", help="audit_hardcoded_strings.py output file")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    args = p.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8-sig"))
    findings = audit["findings"]

    # Index by file -> list of (lineno, english, kind, suggested_key)
    by_file: dict[Path, list[tuple[int, str, str, str]]] = defaultdict(list)
    for f in findings:
        for occ in f["occurrences"]:
            path = REPO_ROOT / occ["file"]
            by_file[path].append((occ["line"], f["english"], occ["kind"], f["suggested_key"]))

    patched = 0
    skipped_module_scope = []
    skipped_no_t = []
    not_found = []
    files_changed: dict[Path, str] = {}

    for path, occs in sorted(by_file.items()):
        if not path.exists():
            print(f"  ! missing file: {path}")
            continue
        original = path.read_text(encoding="utf-8")
        text = original

        # Pre-compute component ranges (where `t` is in scope) for this file.
        comp_ranges = find_component_function_lines(text)
        has_t_import = "useTranslation" in text and ("const { t" in text or "{ t " in text or "{ t,") or "import.*t.*from" in text
        # If the file doesn't import useTranslation at all, every patch
        # would create a ReferenceError. Skip.
        if "useTranslation" not in text:
            for (lineno, english, kind, key) in occs:
                skipped_no_t.append((path, lineno, english, kind, key))
            continue

        # Sort occurrences by descending line number so multi-line jsx-text
        # edits don't shift later line offsets within a single pass.
        occs_sorted = sorted(occs, key=lambda x: (-x[0], x[2]))

        for (lineno, english, kind, key) in occs_sorted:
            in_component = in_any_range(lineno, comp_ranges)

            # Module-scope object literals can't call t() — skip.
            if kind == "object-literal" and not in_component:
                skipped_module_scope.append((path, lineno, english, key))
                continue

            new_text = None
            if kind == "jsx-text":
                new_text = patch_jsx_text(text, english, key)
            else:
                # Line-based patches.
                lines = text.splitlines(keepends=True)
                idx = lineno - 1
                # Search a small window around the reported line to be
                # forgiving of multi-line attribute formatting.
                for offset in range(0, 5):
                    if idx + offset >= len(lines):
                        break
                    line = lines[idx + offset]
                    patched_line: str | None = None
                    if kind == "placeholder":
                        patched_line = patch_attribute(line, "placeholder", english, key)
                    elif kind == "aria-label":
                        patched_line = patch_attribute(line, "aria-label", english, key)
                    elif kind == "title":
                        patched_line = patch_attribute(line, "title", english, key)
                    elif kind == "alt":
                        patched_line = patch_attribute(line, "alt", english, key)
                    elif kind == "toast":
                        patched_line = patch_toast(line, english, key)
                    elif kind == "alert":
                        patched_line = patch_alert(line, english, key)
                    elif kind == "object-literal":
                        patched_line = patch_object_literal(line, english, key)
                    elif kind == "defaultValue":
                        patched_line = patch_default_value(line, english, key)
                    if patched_line is not None:
                        lines[idx + offset] = patched_line
                        new_text = "".join(lines)
                        break

            if new_text is None:
                not_found.append((path, lineno, english, kind, key))
                continue

            text = new_text
            patched += 1

        if text != original:
            files_changed[path] = text

    # Apply writes
    if not args.dry_run:
        for path, text in files_changed.items():
            if not args.no_backup:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            path.write_text(text, encoding="utf-8")

    # Reports
    print(f"\n=== Patcher report ===")
    print(f"  successful patches:        {patched}")
    print(f"  files modified:            {len(files_changed)}")
    print(f"  skipped — module scope:    {len(skipped_module_scope)}")
    print(f"  skipped — no useTranslation:{len(skipped_no_t)}")
    print(f"  not found at expected loc: {len(not_found)}")

    if skipped_module_scope:
        print("\n  Module-scope literals (need manual treatment — see code_fixes_needed.md):")
        for path, lineno, english, key in skipped_module_scope[:20]:
            rel = path.relative_to(REPO_ROOT)
            print(f"    {rel}:{lineno}  {english[:50]!r}  -> {key}")
        if len(skipped_module_scope) > 20:
            print(f"    ... +{len(skipped_module_scope) - 20} more")

    if skipped_no_t:
        print("\n  Files missing useTranslation import (need manual treatment):")
        seen = set()
        for path, lineno, english, kind, key in skipped_no_t:
            if path not in seen:
                rel = path.relative_to(REPO_ROOT)
                print(f"    {rel}  ({sum(1 for x in skipped_no_t if x[0] == path)} strings)")
                seen.add(path)

    if not_found:
        print("\n  Couldn't apply (English not found at reported location):")
        for path, lineno, english, kind, key in not_found[:15]:
            rel = path.relative_to(REPO_ROOT)
            print(f"    {rel}:{lineno}  ({kind})  {english[:50]!r}")
        if len(not_found) > 15:
            print(f"    ... +{len(not_found) - 15} more")

    if args.dry_run:
        print("\n  (dry-run — no files written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
