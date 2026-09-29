"""Regression: the combined pytest run must not leave BGE-m3 markers-only.

Measured in Phase 0: `audio_ml/tests` and `server/tests` run alphabetically before
`nlp_rag/tests`, and their test *bodies* (not their module-level imports) load
speechbrain for ECAPA. If that happens before anything wires `nlp_rag.api`'s retriever,
BGE-m3's load raises `Lazy import of LazyModule(...k2_fsa...) failed` and the intent
branch silently latches into markers-only for the rest of the process — `nlp_rag.api`
only calls `configure()` once (`_configured` guards it), so there is no second chance.

The live server is unaffected: `server/main.py`'s `lifespan()` calls
`nlp_rag.api.configure()` before any request can reach the speaker branch, and nothing
else in `server/` imports speechbrain at module level. Verified directly below. The
fix belongs in the root `conftest.py`, which preloads the retriever before pytest
collects anything — see `test_conftest_preloads_before_speechbrain_is_ever_imported`.

Both assertions run in a subprocess: within one pytest session `sys.modules` already
carries whatever earlier tests imported, so the failure would not reproduce in-process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_WITHOUT_PRELOAD = """
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import config
import speechbrain.inference  # what an audio_ml test body does, unprotected
from nlp_rag.embed import load_encoder
encoder = load_encoder()
assert encoder is None, "expected the known collision to reproduce without the fix"
print("REPRODUCED")
"""

_WITH_CONFTEST_PRELOAD = """
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import config
import conftest  # root conftest.py; pytest_configure runs this before collection
conftest.pytest_configure(None)
import speechbrain.inference  # audio_ml test bodies do this next, in the real run
import nlp_rag.api as api
assert api._retriever is not None, "BGE-m3 was not wired before speechbrain loaded"
print("OK")
"""


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )


def test_speechbrain_first_breaks_bge_m3_without_the_fix():
    """Documents the root cause. Not the fix under test — see the next test."""
    result = _run(_WITHOUT_PRELOAD)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "REPRODUCED" in result.stdout


def test_conftest_preloads_before_speechbrain_is_ever_imported():
    result = _run(_WITH_CONFTEST_PRELOAD)
    assert result.returncode == 0, (
        f"root conftest.py did not preload BGE-m3 ahead of speechbrain\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


if __name__ == "__main__":
    test_speechbrain_first_breaks_bge_m3_without_the_fix()
    test_conftest_preloads_before_speechbrain_is_ever_imported()
    print("smoke test passed")
