#!/usr/bin/env python3
"""Inject `useTranslation` import and the `const { t } = useTranslation();`
hook call into React components that don't have them yet. Idempotent.

Usage:
    python3 inject_use_translation.py <file1.jsx> [<file2.jsx> ...]

For each file:
1. Add `import { useTranslation } from 'react-i18next';` right after the
   last existing `import` statement, unless already present.
2. Inside every default-exported function component (or named function
   matching the file basename), insert `const { t } = useTranslation();`
   as the first line of the body, unless already present.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

IMPORT_LINE = "import { useTranslation } from 'react-i18next';\n"
HOOK_LINE = "  const { t } = useTranslation();\n"


def inject(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    # 1) Add the import if missing
    if "from 'react-i18next'" not in text and 'from "react-i18next"' not in text:
        # Place after the last existing top-level `import ... from ...;` line.
        import_lines = list(re.finditer(r"^import\s.+;\s*$", text, flags=re.MULTILINE))
        if import_lines:
            last = import_lines[-1]
            text = text[: last.end()] + "\n" + IMPORT_LINE.rstrip() + text[last.end():]
            changed = True
        else:
            text = IMPORT_LINE + text
            changed = True

    # 2) Add the hook to every default-exported function component (or named
    #    `function Component()` that starts with a capital letter) that
    #    doesn't already have it.
    func_pattern = re.compile(
        r"(export\s+default\s+function\s+([A-Z]\w*)\s*\([^)]*\)\s*\{|"
        r"function\s+([A-Z]\w*)\s*\([^)]*\)\s*\{)"
    )
    # We'll iterate matches from end to start so insertions don't shift positions
    matches = list(func_pattern.finditer(text))
    for m in reversed(matches):
        head = m.group(0)
        # Skip if the function body already calls useTranslation in the next ~10 lines
        body_start = m.end()
        peek = text[body_start: body_start + 400]
        if "useTranslation" in peek:
            continue
        # Skip nested function components that don't render JSX/translated text.
        # Scan a much larger window because some components have deep `if` blocks
        # before the final `return (...)`.
        peek_long = text[body_start: body_start + 12000]
        if "return (" not in peek_long and "return <" not in peek_long:
            continue
        # Insert at the start of the body
        text = text[: body_start] + "\n" + HOOK_LINE + text[body_start:]
        changed = True

    if changed:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: inject_use_translation.py <file> [<file> ...]")
        return 1
    for arg in sys.argv[1:]:
        path = Path(arg).resolve()
        if not path.is_file():
            print(f"  ! not a file: {path}")
            continue
        if inject(path):
            print(f"  patched: {path}")
        else:
            print(f"  unchanged: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
