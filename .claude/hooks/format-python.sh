#!/usr/bin/env bash
# PostToolUse (Write|Edit): ruff format + ruff check --fix on the edited Python file (ES-2).
# Lint findings ruff cannot fix are handed back to Claude as context; the edit itself stands.
set -uo pipefail
path=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
case "$path" in *.py | *.pyi) ;; *) exit 0 ;; esac
[ -f "$path" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$PWD}" || exit 0
uv run --quiet ruff format --quiet "$path" >/dev/null 2>&1
if ! out=$(uv run --quiet ruff check --fix --quiet --output-format concise "$path" 2>&1); then
  jq -n --arg o "$out" \
    '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: ("ruff still reports:\n" + $o)}}'
fi
exit 0
