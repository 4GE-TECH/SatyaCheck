"""The scenario matrix as a pytest, on both paths (signal level and production).

`python -m audio_ml.eval.test_scenarios` is the CLI gate CLAUDE.md requires; this runs the
same checks inside the suite without rewriting data/scenario_matrix.json.
"""

from __future__ import annotations

import logging

import pytest

from audio_ml.eval import test_scenarios as gate
from audio_ml.fusion import BAND_COLOUR

IVR = "2  AI voice, legitimate IVR"


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("name,speaker,spoof,script,ok", [s for s in gate.SCENARIOS if s[0] != IVR],
                         ids=[s[0].strip() for s in gate.SCENARIOS if s[0] != IVR])
def test_scenario_on_both_paths(name, speaker, spoof, script, ok):
    signal = gate.fuse(speaker, spoof, script).band
    production = gate.production_band(speaker, spoof, script)
    assert signal in ok, f"signal path: {signal}"
    assert BAND_COLOUR[production] in ok, f"production path: {production}"


def test_a_legitimate_ivr_is_unverified_not_amber():
    """At CM_FLOOR 0.25 production fused this to caution (amber); the old gate hid it."""
    _, speaker, spoof, script, ok = next(s for s in gate.SCENARIOS if s[0] == IVR)
    assert BAND_COLOUR[gate.production_band(speaker, spoof, script)] in ok


@pytest.mark.parametrize("check", [c[0] for c in gate.production_checks()])
def test_production_check(check):
    passed, observed = next((p, o) for c, p, o in gate.production_checks() if c == check)
    assert passed, f"{check}: observed {observed}"
