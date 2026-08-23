#!/bin/bash
# PreToolUse hook: block destructive git commands. Exit 2 = blocked.

INPUT=$(cat)

# jq is frequently absent on Windows. Without a fallback this script used to
# produce an empty command, match nothing, and exit 0 - silently allowing
# git push. Parse with jq when present, sed otherwise, and fail closed if
# neither yields a command.
if command -v jq >/dev/null 2>&1; then
  COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
else
  COMMAND=$(printf '%s' "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(\([^"\\]\|\\.\)*\)".*/\1/p')
fi

if [ -z "$COMMAND" ]; then
  echo "BLOCKED: git guardrails could not read the command from the tool input, so it could not be checked. Install jq, or remove this hook from settings.json." >&2
  exit 2
fi

DANGEROUS_PATTERNS=(
  "git push"
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "push --force"
  "reset --hard"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' matches dangerous pattern '$pattern'. The user has prevented you from doing this." >&2
    exit 2
  fi
done

exit 0
