#!/usr/bin/env bash
# Pre-commit check: block git commit if CHANGELOG.md is not staged,
# unless commit message contains [skip changelog].
# Invoked as a Claude Code PreToolUse hook on Bash tool calls.

# Read JSON input from stdin (Claude Code hook contract)
INPUT=$(cat)

# Extract the bash command being run.
# Using Python instead of jq — jq is not universally available on Windows
# git-bash, whereas Python is guaranteed present for this project.
COMMAND=$(printf '%s' "$INPUT" | python -c "import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    pass" 2>/dev/null)

# Only check when the command is a git commit
if ! echo "$COMMAND" | grep -qE 'git[[:space:]]+commit\b'; then
    exit 0  # not a commit, allow
fi

# Check for [skip changelog] escape hatch in the command string
# (commit message will appear as -m "..." arg in the command)
if echo "$COMMAND" | grep -qF '[skip changelog]'; then
    echo "CHANGELOG hook: bypass requested via [skip changelog] marker — commit allowed." >&2
    exit 0
fi

# Check if CHANGELOG.md is in the staged diff
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" 2>/dev/null || true
STAGED=$(git diff --cached --name-only 2>/dev/null)

if echo "$STAGED" | grep -qx "CHANGELOG.md"; then
    exit 0  # CHANGELOG.md is staged, allow
fi

# CHANGELOG.md not staged and no bypass marker — block
cat >&2 <<MSG
CHANGELOG hook: git commit BLOCKED.

Reason: CHANGELOG.md is not in the staged diff, and the commit message
does not contain the [skip changelog] escape marker.

Per CLAUDE.md §4 and amended rule 7: every commit that adds tooling,
creates user-visible files, or changes behavior must include a
CHANGELOG.md entry. Pure internal refactors may bypass by adding
[skip changelog] to the commit message.

To proceed:
  (a) Stage a CHANGELOG.md edit:  git add CHANGELOG.md  →  retry commit
  (b) Or bypass for internal-only refactor:  add [skip changelog] to
      the commit message (e.g., -m "Refactor X [skip changelog]")

Blocking exit code 2.
MSG
exit 2
