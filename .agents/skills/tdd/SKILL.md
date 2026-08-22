---
name: tdd
description: Test-driven development - the red-green loop, seams, and test anti-patterns. Use for "TDD", "red-green-refactor", or building a feature test-first. Not for adding tests to finished code, running an existing suite, or debugging a failing test.
disable-model-invocation: true
---

# Test-Driven Development

Applies only to writing new behavior test-first. For adding tests to finished code, or debugging an already-failing test, stop - this skill does not apply.

Read `CONTEXT.md` if it exists, so test names and interface vocabulary match the project's domain language. Respect ADRs covering the area you touch.

## Route

Read only the row matching the current situation. Do not read the others.

| Situation | Where to look |
|---|---|
| Running a red-green cycle | "The loop" below - nothing else needed |
| Unsure what to test, or where | "Seams" below |
| Writing the test body, shape unclear | [references/tests.md](references/tests.md) |
| About to introduce a mock or double | [references/mocking.md](references/mocking.md) |
| Test breaks on refactor, or feels tautological | [references/anti-patterns.md](references/anti-patterns.md) |

## The loop

1. **Confirm the seam** - see below. No test is written at an unconfirmed seam.
2. **Red.** Write one failing test at that seam.
3. **Green.** Write only enough code to pass it - no speculative features, no anticipating later tests.
4. **Repeat.** One seam, one test, one implementation per cycle; each test is a tracer bullet shaped by what the last cycle taught you.

Refactoring is not part of the loop - it belongs to review (see the `code-review` skill).

## Seams

A *seam* is the public boundary you observe behavior through. Tests live at seams, never against internals: a good test reads like a specification ("user can checkout with valid cart"), survives refactors, and makes one logical assertion.

Name the seams under test and get the user to agree before writing anything. You can't test everything; agreeing seams up front puts the effort on critical paths and complex logic. Ask: "What's the public interface, and which seams should we test?"
