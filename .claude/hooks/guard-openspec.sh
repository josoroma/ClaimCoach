#!/usr/bin/env bash
# PreToolUse (Write|Edit): keep the OpenSpec record honest.
# openspec/specs/ and openspec/changes/archive/ change only through `openspec archive`;
# evidence JUnit files only through `make evidence STORY=US-x.y`.
set -euo pipefail
path=$(jq -r '.tool_input.file_path // empty')
[ -n "$path" ] || exit 0
rel=${path#"${CLAUDE_PROJECT_DIR:-$PWD}/"}
reason=""
case "$rel" in
  openspec/specs/*) reason="openspec/specs/ is updated only by 'openspec archive <change>'; edit the change's spec delta under openspec/changes/<change>/specs/ instead." ;;
  openspec/changes/archive/*) reason="Archived OpenSpec changes are the delivery record and stay immutable; open a new change instead." ;;
  evidence/US-*/junit*.xml) reason="JUnit evidence is generated; run 'make evidence STORY=US-x.y' instead of writing it." ;;
esac
[ -z "$reason" ] && exit 0
jq -n --arg r "$reason" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
