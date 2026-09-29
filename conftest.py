"""Root pytest configuration.

`pytest_configure` runs once, before any test module is collected or imported — the
only hook point that is guaranteed to run before `audio_ml`'s test *bodies* (not their
imports; the collision is at speechbrain construction time, inside a test function)
pull in speechbrain for ECAPA. If speechbrain loads first, `nlp_rag`'s BGE-m3 encoder
fails to construct (`Lazy import of LazyModule(...k2_fsa...) failed`) and the intent
branch latches into markers-only for the rest of the process — `nlp_rag.api.configure`
only ever runs once per process (`_configured` guards it).

Preloading here mirrors what `server/main.py`'s `lifespan()` already does correctly for
the live server: wire the retriever before anything else in the process can touch
speechbrain. See `nlp_rag/tests/test_import_order.py` for the regression test and the
full explanation of why the live server was never actually affected by this.
"""

from __future__ import annotations


def pytest_configure(config) -> None:  # noqa: ARG001 - pytest's hook signature
    try:
        from nlp_rag.api import configure as configure_nlp

        configure_nlp()
    except Exception:
        # Same rule as everywhere else in this codebase: a broken model stack degrades
        # to markers-only, it does not fail collection. A test that depends on the real
        # encoder will fail on its own merits and say so.
        pass
