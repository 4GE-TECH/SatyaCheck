# Test Anti-Patterns

Read when a test breaks on refactor, feels circular, or the plan is to write many tests before any implementation.

## Implementation-coupled

Mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface).

**The tell:** refactoring breaks the test while behavior is unchanged.

**Fix:** move the assertion to the public seam - observe what a caller would observe. See [tests.md](tests.md).

## Tautological

The expected value is recomputed the way the code computes it, so the test passes by construction and can never disagree with the code.

**The tell:** the assertion's expected value is derived in the test body rather than written down.

**Fix:** expected values come from an independent source - a known-good literal, a worked example, the spec.

## Horizontal slicing

All tests first, then all implementation. Bulk tests verify *imagined* behavior: they go insensitive to real changes and commit to test structure before the implementation is understood.

**The tell:** more than one failing test at a time.

**Fix:** slice vertically - one seam, one test, one implementation, then repeat.
