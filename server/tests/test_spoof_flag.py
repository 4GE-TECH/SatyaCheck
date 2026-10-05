"""`USE_REAL_SPOOF` end to end: what the flag does to a real screening (item 7).

`test_fusion.py` pins the arithmetic of a cut spoof branch on hand-built contracts. This
pins the wiring: the flag picks the branch in `screen_audio`, the cut branch reaches
fusion as an *abstention* (weight dropped, `RC_SPOOF_UNAVAILABLE`), and the live branch
contributes. The default is pinned too, because flipping it after the demo (item 7b)
changes every verdict in DEMO_RUNBOOK.md and must be a deliberate, visible edit.

Speaker and intent run as mocks so this tests only the spoof wiring, in seconds.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import pytest

import config
from audio_ml import spoof
from server.audio_ingest import ingest_audio
from server.orchestrator import screen_audio

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "cloned_scam.wav"

pytestmark = pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setattr(config, "USE_REAL_SPEAKER", False)
    monkeypatch.setattr(config, "USE_REAL_NLP", False)

    def run(use_real_spoof: bool):
        monkeypatch.setattr(config, "USE_REAL_SPOOF", use_real_spoof)
        return asyncio.run(screen_audio(ingest_audio(audio_path=str(CLIP))))

    return run


def test_the_demo_default_is_on():
    """Flip deliberately in item 7b, together with DEMO_RUNBOOK.md."""
    assert config.USE_REAL_SPOOF is True


@pytest.mark.parametrize("value, expected", [("false", False), ("FALSE", False), ("true", True)])
def test_the_env_var_controls_the_flag(value, expected):
    out = subprocess.run(
        [sys.executable, "-c", "import config; print(config.USE_REAL_SPOOF)"],
        capture_output=True, text=True, cwd=str(config.REPO_ROOT),
        env={**os.environ, "USE_REAL_SPOOF": value}, timeout=60,
    )
    assert out.stdout.strip() == str(expected), out.stderr


def test_flag_off_is_an_abstention_not_a_clean_bill(screen):
    result = screen(False)
    assert result.spoof.details.get("available") is False
    assert result.fusion.weights_used.cm_weight == 0.0
    codes = [rc.code for rc in result.fusion.reason_codes]
    assert "RC_SPOOF_UNAVAILABLE" in codes
    assert "RC_AUDIO_BONAFIDE" not in codes, "a branch that never ran must not exonerate"


@pytest.mark.skipif(not spoof.model_files_present(), reason="Model A not installed")
def test_flag_on_scores_and_carries_weight(screen):
    result = screen(True)
    assert result.spoof.details.get("available") is True
    assert result.spoof.details.get("n_chunks", 0) > 0
    assert result.fusion.weights_used.cm_weight > 0.0
    assert "RC_SPOOF_UNAVAILABLE" not in [rc.code for rc in result.fusion.reason_codes]
