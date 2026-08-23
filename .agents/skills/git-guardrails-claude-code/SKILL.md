---
name: git-guardrails-claude-code
description: Install a Claude Code PreToolUse hook blocking destructive git commands (push, reset --hard, clean -f, branch -D). Use for "git guardrails" or "block dangerous git". Claude Code only; not for running git commands.
disable-model-invocation: true
---

# Setup Git Guardrails

Claude Code only. If the current harness is not Claude Code, stop and say so - the hook has no effect elsewhere.

Installs a PreToolUse hook that blocks dangerous git commands before Claude runs them. The blocked patterns are the `DANGEROUS_PATTERNS` array in [scripts/block-dangerous-git.sh](scripts/block-dangerous-git.sh); on a match the hook exits 2 and tells Claude it lacks authority for that command.

## Steps

1. **Ask scope** - this project (`.claude/`) or all projects (`~/.claude/`)? `<root>` below is the chosen directory.

2. **Install** - copy `scripts/block-dangerous-git.sh` to `<root>/hooks/block-dangerous-git.sh`, then `chmod +x` it.

3. **Register** in `<root>/settings.json`, merging into any existing `hooks.PreToolUse` array rather than overwriting other settings:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [{ "type": "command", "command": "<hook-path>" }]
         }
       ]
     }
   }
   ```

   `<hook-path>` is `\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-dangerous-git.sh` for a project install (the inner quotes are backslash-escaped inside the JSON string) or `~/.claude/hooks/block-dangerous-git.sh` for a global one.

4. **Ask about customization** - any patterns to add or remove? Edit the copied script.

5. **Verify**:

   ```bash
   echo '{"tool_input":{"command":"git push origin main"}}' | <root>/hooks/block-dangerous-git.sh
   ```

   Expect exit code 2 and a `BLOCKED` message on stderr.
