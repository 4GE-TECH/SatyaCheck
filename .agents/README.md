# Skill authoring contract

Rules every skill in `skills/` must satisfy. `scripts/validate-skills.sh` enforces
the mechanical ones. This file is documentation - it is never loaded as a skill,
because it sits outside `skills/`.

## Verified harness constraints

Extracted from the shipped binaries and schema, not from documentation:

| Mechanism | Claude Code | codex / `.agents` | Antigravity |
|---|---|---|---|
| Frontmatter allowlist | permissive | `{name, description, license, allowed-tools, metadata}` - rejects others | documents only `name`, `description` |
| Frontmatter gate | `disable-model-invocation: true` | `policy.allow_implicit_invocation: false` | none documented |
| Settings gate | `skillOverrides` | - | - |
| Listing caps | `skillListingMaxDescChars` (default 1536), `skillListingBudgetFraction` (default 0.01) | - | - |
| As-needed dir | `references/` | `ALLOWED_RESOURCES = {scripts, references, assets}` | `references/` |
| `short_description` | n/a | must be 25-64 chars | n/a |
| Discovery | `.claude/skills/` | `.agents/skills/` | `.agents/skills/`, `.agents/skills.json` |

Sources: `codex.exe` skill-creator validator (`allowed_properties`, `ALLOWED_INTERFACE_KEYS`,
`ALLOWED_RESOURCES`, `MAX_SKILL_NAME_LENGTH`), Antigravity `language_server.exe` embedded
skill guide, `claude-code-settings.schema.json` (Claude Code 2.1.117).

**Antigravity honors no gate.** Descriptions and early-exit lines are the only
filter there, which is why both are mandatory below.

## Gating: set both files or neither

`disable-model-invocation` is Claude-Code-only and is *not* in codex's allowlist -
its authoring validator flags it; its runtime loader ignores unknown keys. That
divergence is accepted, so gating always takes two files:

```yaml
# SKILL.md frontmatter          # agents/openai.yaml
disable-model-invocation: true  policy:
                                  allow_implicit_invocation: false
```

One without the other silently leaves the skill auto-loading in one harness.
The validator fails on mismatch.

## Descriptions are the load gate

Shape: **what it does, then concrete trigger phrases, then explicit negative
triggers**, under 350 characters.

The negative triggers matter most. They cost ~15 tokens and save an entire body
when a near-miss would otherwise pull the skill in.

Two formatting constraints apply to the description, and they interact: a plain
YAML scalar cannot contain `": "` (it breaks parsing), and the working agreement
in AGENTS.md bans em dashes. Separate clauses with a period or a plain hyphen.

## Bodies are dispatchers, not documents

Open with an early-exit precondition so a wrong load is abandoned in ~20 tokens.
Then route by situation:

```markdown
| Situation | Where to look |
|---|---|
| Common case | "The loop" below - nothing else needed |
| Narrow case | `references/thing.md` |
```

### The splitting rule

Each extra `Read` is a round trip costing roughly 50-100 tokens. **Only split out
a fragment that is at least 100 words and needed less than half the time.** Below
that threshold, splitting costs more than it saves.

Applied here: `tdd` (291 words, four distinct situations) splits; `git-guardrails`
(184 words, one linear procedure) stays whole; `grill-me` (4 words) is untouched.

## Budgets

| Thing | Limit | Enforced by |
|---|---|---|
| `description` | 350 chars | validator, hard fail |
| `short_description` | 25-64 chars | validator, hard fail (codex requirement) |
| SKILL.md body | 2,000 words warn / 3,000 fail | validator |
| Subdirectories | `scripts`, `references`, `assets`, `agents` | validator, hard fail |
| Loose `.md` at skill root | none but `SKILL.md` | validator, hard fail |
| Unlinked `references/` file | none - dead weight that never loads | validator, hard fail |
| Decorative punctuation | none in `SKILL.md` or `references/` | validator, hard fail |

## Provenance

These skills began as `mattpocock/skills` (`tdd`, `grill-me`,
`git-guardrails-claude-code`) and are now **intentionally forked**: gated,
restructured, and rewritten as dispatchers. `skills-lock.json` no longer tracks
them, so the upstream tooling cannot revert the gating. Deleting that file
outright is also fine.
