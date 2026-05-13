#!/usr/bin/env python3
"""Auto-repair the common 'unescaped inner double-quotes' bug in line-oriented
JSON payloads pasted by LLMs.

Assumes each leaf is on a single line of the form:
    "key.path": "value",          (with optional trailing comma)
or inside an array/braces nested object — anything where the line, after
stripping the leading whitespace, starts with a quoted string followed by ':'.

For such lines the script keeps the key untouched, finds the value's outer
quote pair, and escapes any unescaped `"` characters strictly inside it.

Lines that don't look like leaf lines (object/array braces, blank lines) are
copied verbatim. Already-valid JSON is left untouched.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LEAF_RE = re.compile(
    r'^(?P<lead>\s*)'
    r'(?P<key>"(?:[^"\\]|\\.)*")'
    r'(?P<sep>\s*:\s*)'
    r'"(?P<val>.*)"'
    r'(?P<tail>,?\s*)$'
)


def repair_line(line: str) -> tuple[str, bool]:
    """Return (possibly-repaired line, whether a fix was applied)."""
    m = LEAF_RE.match(line.rstrip("\n"))
    if not m:
        return line, False
    raw_val = m.group("val")
    # Are inner double quotes unescaped? An escaped one is preceded by an odd
    # number of backslashes. We re-escape any bare " into \".
    fixed = re.sub(r'(?<!\\)"', r'\\"', raw_val)
    if fixed == raw_val:
        return line, False
    repaired = (
        f'{m.group("lead")}{m.group("key")}{m.group("sep")}'
        f'"{fixed}"{m.group("tail")}\n'
    )
    return repaired, True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: fix_json_quotes.py <input.json> [<output.json>]",
              file=sys.stderr)
        return 1
    src = Path(argv[1])
    dst = Path(argv[2]) if len(argv) > 2 else src
    text = src.read_text(encoding="utf-8-sig")

    # First, try parsing as-is. If it works, copy through and exit.
    try:
        json.loads(text)
        if dst != src:
            dst.write_text(text, encoding="utf-8")
        print(f"OK: {src} already parses as valid JSON.")
        return 0
    except json.JSONDecodeError as exc:
        print(f"Initial parse failed at {exc.lineno}:{exc.colno} — attempting repair.")

    out_lines: list[str] = []
    fixes = 0
    fix_locations: list[int] = []
    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        repaired, fixed = repair_line(line)
        out_lines.append(repaired)
        if fixed:
            fixes += 1
            fix_locations.append(i)

    repaired_text = "".join(out_lines)
    try:
        json.loads(repaired_text)
    except json.JSONDecodeError as exc:
        # Report what we did before bailing.
        print(f"Applied {fixes} inner-quote escape(s) but JSON still invalid "
              f"at {exc.lineno}:{exc.colno}: {exc.msg}", file=sys.stderr)
        dst.write_text(repaired_text, encoding="utf-8")
        print(f"Partial output written to {dst} for manual inspection.",
              file=sys.stderr)
        return 2

    dst.write_text(repaired_text, encoding="utf-8")
    print(f"Repaired {fixes} line(s); wrote valid JSON to {dst}")
    if fix_locations:
        preview = ", ".join(str(n) for n in fix_locations[:10])
        more = "" if len(fix_locations) <= 10 else f", … +{len(fix_locations) - 10}"
        print(f"Fixed lines: {preview}{more}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
