"""Check local links in current documentation, excluding immutable evidence.

Run from any directory; only Python's standard library is required.
Paths recorded inside code fences are examples/history and are not links.
Use --root to check a candidate checkout before committing a reorganization.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def check(root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    # Archives deliberately retain the original, now obsolete paths.
    excluded = {".git", "legacy", "provenance", "demo", "tmp", "local_cache",
                "node_modules", ".build", "__pycache__", "archive"}
    for document in sorted(root.rglob("*.md")):
        relative = document.relative_to(root)
        if any(part in excluded or part.startswith((".venv", ".codex"))
               for part in relative.parts):
            continue
        source = document.read_text(encoding="utf-8")
        source = re.sub(r"^\s*(```|~~~).*?^\s*\1\s*$", "", source,
                        flags=re.MULTILINE | re.DOTALL)
        # Supports ordinary relative links and angle-wrapped paths with spaces.
        for match in re.finditer(r"\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", source):
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            count += 1
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.exists():
                errors.append(f"{relative.as_posix()}: missing {target}")
    return count, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    count, errors = check(args.root.resolve())
    print(f"Checked {count} current-document local links; {len(errors)} missing.")
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
