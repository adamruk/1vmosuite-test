#!/usr/bin/env bash
# .claude/hooks/block-dangerous.sh
# PreToolUse hook (matcher: Bash). Blocks destructive/unsafe commands by
# emitting a structured JSON deny decision on stdout, then exit 0.
#
# Why JSON-deny and never exit 2: claude-code issue #24327 reports a
# PreToolUse exit 2 intermittently stops the whole session instead of
# recovering. permissionDecision:"deny" is the robust block path.
#
# Why python and not jq: jq is not installed on this host; python (3.13)
# is, and runs cleanly under the absolute Git-Bash path.
set -u

input="$(cat)"

cmd="$(printf '%s' "$input" | python -c 'import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
print(data.get("tool_input", {}).get("command", "") or "")
')"

emit() {  # $1 = decision, $2 = reason
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s","permissionDecisionReason":"%s"}}\n' "$1" "$2"
  exit 0
}
deny()  { emit "deny"  "$1"; }
allow() { emit "allow" "$1"; }

# Empty / malformed payload: let normal permission flow handle it.
[ -z "$cmd" ] && exit 0

# Lowercased, single-line, whitespace-collapsed copy for matching.
low="$(printf '%s' "$cmd" | tr '\n' ' ' | tr -s ' ' | tr '[:upper:]' '[:lower:]')"
m() { printf '%s' "$low" | grep -Eq "$1"; }

# 1. rm -rf / -fr  (recursive AND force; combined or split; any flag order)
if m '(^|[;&| ])rm +(-[a-z]+ +)*-[a-z]*r[a-z]*f' \
   || m '(^|[;&| ])rm +(-[a-z]+ +)*-[a-z]*f[a-z]*r' \
   || m '(^|[;&| ])rm +.*--recursive.*--force' \
   || m '(^|[;&| ])rm +.*--force.*--recursive'; then
  deny "Blocked: recursive-force rm is irreversible. Remove specific paths explicitly, or ask Adam to run it."
fi

# 2. git push --force / -f  (both flag positions)
if m '(^|[;&| ])git +push +.*(--force\b|--force-with-lease\b)' \
   || m '(^|[;&| ])git +push +.* -f\b'; then
  deny "Blocked: force-push rewrites shared history. Use a normal push; force-push only with Adam's go-ahead."
fi

# 3. git reset --hard
if m '(^|[;&| ])git +reset +.*--hard\b'; then
  deny "Blocked: git reset --hard discards uncommitted work. Stash or commit first, or ask Adam."
fi

# 4. git clean -f  (covers -f, -fd, -df, -ffd, ...)
if m '(^|[;&| ])git +clean +.*-[a-z]*f'; then
  deny "Blocked: git clean -f deletes untracked files permanently. Review with 'git clean -n' first, or ask Adam."
fi

# 5. Reading .env via cat/type/less/more/head/tail/...
if m '(^|[;&| ])(cat|type|less|more|head|tail|nl|xxd|strings|od) +[^|;&]*\.env(\b|$)'; then
  deny "Blocked: .env may hold secrets. Reading it is denied by policy (also blocked in settings.json deny)."
fi

# 6. curl|wget|iwr piped straight into a shell/interpreter
if m '(curl|wget|iwr|invoke-webrequest)\b[^|]*\| *(bash|sh|zsh|iex|invoke-expression)\b'; then
  deny "Blocked: piping a download into a shell runs unreviewed remote code. Download, inspect, then run."
fi

# 7. Ad-hoc NVENC ffmpeg from bash (single RTX 4080 contention, B-032).
if m '(^|[;&| ])ffmpeg\b' && m '_nvenc\b'; then
  deny "Blocked (B-032): single RTX 4080 - never run an ad-hoc *_nvenc ffmpeg from bash. Render via the app and coordinate the GPU through .agent-status/ so MAIN and VERIFY never collide."
fi

# Non-force git push: let settings.json 'ask' govern -> fall through silently.
if m '(^|[;&| ])git +push\b'; then
  exit 0
fi

# Default: no dangerous pattern matched -> allow.
allow "No dangerous pattern matched."
