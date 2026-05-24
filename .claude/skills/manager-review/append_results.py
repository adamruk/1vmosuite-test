#!/usr/bin/env python3
"""Append-safe writer for the manager-review audit log (RESULTS.md).

B-050: the manager-review skill used to write RESULTS.md with the Write
tool, which replaces the whole file — every VERIFY run silently wiped the
prior cumulative audit history (672 lines lost in commit 7318ae4). This
helper makes the operation non-destructive *structurally* rather than
relying on the model to remember to read-then-write: it reads the existing
RESULTS.md, PREPENDS the new dated verdict block (newest-first, `---`
separated), and writes the combined content back atomically. The prior
content is always carried through verbatim.

Usage:
    python append_results.py <new_block_file> [results_md_path]

    <new_block_file>   path to a file holding the new verdict block
                       (markdown). Use "-" to read the block from stdin.
    [results_md_path]  target log (default: RESULTS.md in the cwd).

Exit codes: 0 ok, 2 usage/IO error. Prints the new total line count.
"""

from __future__ import annotations

import os
import sys
import tempfile

SEPARATOR = "\n---\n\n"


def prepend_verdict_block(results_path: str, new_block: str) -> str:
    """Prepend ``new_block`` above the existing RESULTS.md content.

    Reads the existing file first (if any) and includes it verbatim below a
    ``---`` separator, then writes the combined text atomically (temp file +
    os.replace) so a write failure can never truncate the existing log. The
    returned string is the new full file content. NEVER truncates: any
    non-empty prior content is guaranteed to survive in the output.
    """
    block = new_block.rstrip("\n") + "\n"
    existing = ""
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as fh:
            existing = fh.read()

    combined = block + SEPARATOR + existing if existing.strip() else block

    target_dir = os.path.dirname(os.path.abspath(results_path)) or "."
    fd, tmp = tempfile.mkstemp(dir=target_dir, suffix=".results.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(combined)
        os.replace(tmp, results_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return combined


def main(argv: list[str]) -> int:
    if not (2 <= len(argv) <= 3):
        sys.stderr.write(
            "usage: python append_results.py <new_block_file|-> [results_md_path]\n"
        )
        return 2
    block_arg = argv[1]
    results_path = argv[2] if len(argv) == 3 else "RESULTS.md"
    try:
        if block_arg == "-":
            new_block = sys.stdin.read()
        else:
            with open(block_arg, encoding="utf-8") as fh:
                new_block = fh.read()
    except OSError as exc:
        sys.stderr.write(f"error reading block: {exc}\n")
        return 2
    if not new_block.strip():
        sys.stderr.write("error: new verdict block is empty; refusing to write\n")
        return 2
    try:
        combined = prepend_verdict_block(results_path, new_block)
    except OSError as exc:
        sys.stderr.write(f"error writing {results_path}: {exc}\n")
        return 2
    print(f"{results_path}: {len(combined.splitlines())} lines after prepend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
