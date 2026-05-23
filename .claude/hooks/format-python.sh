#!/usr/bin/env bash
# .claude/hooks/format-python.sh
# PostToolUse hook (matcher: Edit|Write|MultiEdit). If the edited file is a
# .py, run `ruff format` then `ruff check --fix --quiet` on it. Best-effort:
# swallow all errors, always exit 0 so a format hiccup never blocks an edit.
#
# ruff is not on the Git-Bash PATH on this host, so we invoke it via
# `python -m ruff` (verified working: ruff 0.15.12).
set -u

input="$(cat)"

fp="$(printf '%s' "$input" | python -c 'import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
ti = d.get("tool_input", {})
print(ti.get("file_path") or ti.get("filePath") or "")
')"

case "$fp" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$fp" ] || exit 0

run_ruff() {
  if command -v ruff >/dev/null 2>&1; then
    ruff "$@" >/dev/null 2>&1 || true
  else
    python -m ruff "$@" >/dev/null 2>&1 || true
  fi
}

run_ruff format "$fp"
run_ruff check --fix --quiet "$fp"
exit 0
