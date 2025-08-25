#!/usr/bin/env python3
"""
Remove all comments from Python files under the backend directory, without altering code or functions.
- Preserves docstrings (they are strings, not comments)
- Preserves shebang line and encoding declaration
- Skips virtual environments and __pycache__
"""
from __future__ import annotations
import io
import os
import re
import sys
import tokenize
from typing import List, Tuple

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {"venv", "__pycache__"}

ENCODING_RE = re.compile(rb"coding[:=]\s*([-_.a-zA-Z0-9]+)")


def has_encoding_decl(first_two_lines: bytes) -> bool:
    return bool(ENCODING_RE.search(first_two_lines))


def collect_python_files(root: str) -> List[str]:
    py_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # mutate dirnames in-place to prune traversal
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                py_files.append(os.path.join(dirpath, fn))
    return py_files


def strip_comments_from_code(path: str) -> Tuple[bytes, bytes]:
    """
    Returns (original_bytes, new_bytes)
    """
    with open(path, "rb") as f:
        original = f.read()

    # Capture shebang if present on very first line
    shebang = b""
    rest = original
    if original.startswith(b"#!/") or original.startswith(b"#! "):
        nl = original.find(b"\n")
        if nl != -1:
            shebang = original[: nl + 1]
            rest = original[nl + 1 :]
        else:
            # file only contains shebang
            return original, original

    # Preserve encoding declaration if present in first two lines (PEP 263)
    first_two_nls = rest.split(b"\n", 2)
    first_two = b"\n".join(first_two_nls[:2])
    preserve_encoding = has_encoding_decl(first_two)

    # Tokenize and drop COMMENT tokens
    out_tokens = []
    rdr = io.BytesIO(rest).readline
    try:
        for tok in tokenize.tokenize(rdr):
            tok_type = tok.type
            tok_str = tok.string
            # Keep ENCODING virtual token
            if tok_type == tokenize.ENCODING:
                out_tokens.append(tok)
                continue
            # Drop pure comments
            if tok_type == tokenize.COMMENT:
                # If it's an encoding comment on first/second line and we decided to preserve, keep it
                if preserve_encoding and ENCODING_RE.search(tok_str.encode() if isinstance(tok_str, str) else tok_str):
                    out_tokens.append(tok)
                # else drop
                continue
            # Keep everything else
            out_tokens.append(tok)
    except tokenize.TokenError:
        # If tokenization fails, do not modify the file
        return original, original

    new_body = tokenize.untokenize(out_tokens)
    if isinstance(new_body, str):
        new_body = new_body.encode("utf-8")

    # Post-process: remove trailing spaces on lines created by stripping inline comments
    new_body = b"\n".join(line.rstrip() for line in new_body.split(b"\n"))

    new_content = shebang + new_body
    return original, new_content


def main() -> int:
    root = BACKEND_ROOT
    py_files = collect_python_files(root)

    changed = 0
    for path in py_files:
        orig, new = strip_comments_from_code(path)
        if new != orig:
            with open(path, "wb") as f:
                f.write(new)
            changed += 1
            rel = os.path.relpath(path, root)
            print(f"Updated: {rel}")

    print(f"Done. Files updated: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
