#!/usr/bin/env bash
# SessionStart: tell Claude which OpenSpec changes are open and which stories have evidence.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$PWD}" || exit 0
changes=$(find openspec/changes -mindepth 1 -maxdepth 1 -type d ! -name archive -exec basename {} \; 2>/dev/null | sort | tr '\n' ' ')
stories=$(find evidence -mindepth 1 -maxdepth 1 -type d -name 'US-*' -exec basename {} \; 2>/dev/null | sort -V | tr '\n' ' ')
ctx="ClaimCoach delivery state. Open OpenSpec changes: ${changes:-none}. Stories with evidence: ${stories:-none}. Deliver new stories with the deliver-story skill."
jq -n --arg c "$ctx" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}'
