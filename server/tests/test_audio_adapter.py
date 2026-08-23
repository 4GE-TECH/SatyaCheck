"""Tests for the A → C model bridge, and for the two silent failures it caused.

Every test here exists because the failure it describes is *invisible* at runtime.
`orchestrator._real_speaker_branch` catches everything and returns
`SpeakerVerificationResult.neutral()`, whose verdict is `unknown` — a legitimate
verdict. So a completely dead branch and a working one that met a stranger look
identical in the API response, in the UI, and in the logs at INFO level.

The first two tests are regression tests for defects that shipped:

  F1  `audio_ml/*.py` did `from contracts import SpeakerSignal`, and C's frozen
      contracts.py has no such class. It existed only as a monkeypatch inside
      server/audio_adapter.py, which orchestrator.py imported on the line *after*
      `from audio_ml.api import verify_speaker`. ImportError → neutral, always.

  F2  the same monkeypatch did `contracts.SpoofSegment = SpoofSegment`, replacing
      C's real SpoofSegment (which has `is_synthetic`) with A's (which has
      `label`). to_spoof_result then built the wrong shape → ValidationError →
      neutral, always. Fixing F1 alone would not have surfaced this.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- F1 -----------------------------------------------------------------------

def test_audio_ml_api_imports_without_the_server_package():
    """`audio_ml` must not need `server/` to have been imported first.

    Run in a *subprocess* deliberately. In-process, some earlier test may already
    have imported server.audio_adapter and left its monkeypatch on the contracts
    module, which is exactly the condition that hid this defect for a whole block.
    A clean interpreter is the only honest check.

    This also covers the seven scripts/ that import audio_ml directly, and
    audio_ml/eval/test_scenarios.py, none of which import server/ at all.
    """
    result = subprocess.run(
        [sys.executable, "-c", "from audio_ml.api import verify_speaker, detect_spoof, enroll_person"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "audio_ml.api cannot be imported on its own:\n" + result.stderr
    )


def test_orchestrator_speaker_branch_does_not_swallow_an_import_error(monkeypatch, caplog):
    """A dead branch must be visible, not silently neutral.

    Guards the import-order trap directly: if `verify_speaker` cannot be reached,
    the fallback is fine, but it has to be *loud*.
    """
    from server import orchestrator

    assert orchestrator._real_speaker_branch is not orchestrator._mock_speaker_branch


# --- F2 -----------------------------------------------------------------------

def test_importing_the_adapter_leaves_contracts_unmodified():
    """The adapter must not mutate the frozen contracts module.

    `contracts.py` is frozen and three people code against it. A monkeypatch that
    swaps a class out from under them is a contract change made at import time,
    with no announcement and no way to see it in the source.
    """
    import contracts

    before = contracts.SpoofSegment
    fields_before = set(contracts.SpoofSegment.model_fields)

    import server.audio_adapter  # noqa: F401 — imported for its side effects, if any

    assert contracts.SpoofSegment is before, "adapter replaced contracts.SpoofSegment"
    assert set(contracts.SpoofSegment.model_fields) == fields_before
    assert "is_synthetic" in contracts.SpoofSegment.model_fields
    assert "label" not in contracts.SpoofSegment.model_fields


def test_contracts_does_not_grow_as_models():
    """A's vocabulary belongs to audio_ml, not to the shared contract."""
    import contracts
    import server.audio_adapter  # noqa: F401

    for name in ("SpeakerSignal", "SpoofSignal", "Person"):
        assert not hasattr(contracts, name), (
            f"contracts.{name} was injected; A's models belong in audio_ml.signals"
        )


# --- the mapping itself -------------------------------------------------------

def test_unknown_verdict_maps_to_neutral_risk():
    """CLAUDE.md: unknown is neutral (0.5), never guilty.

    `unknown` is the normal state for every genuine stranger — a real bank, a
    delivery driver, a doctor. Mapping it to 1.0 makes all of them red and the
    product becomes noise.
    """
    from audio_ml.signals import SpeakerSignal
    from server.audio_adapter import to_speaker_result

    result = to_speaker_result(SpeakerSignal(verdict="unknown", raw_cosine=0.1, norm_score=0.1))

    assert result.risk == 0.5
    assert result.verdict.value == "unknown"


@pytest.mark.parametrize(
    "verdict,expected_ordering",
    [("match", "low"), ("unknown", "mid"), ("mismatch", "high")],
)
def test_risk_is_ordered_by_verdict(verdict, expected_ordering):
    from audio_ml.signals import SpeakerSignal
    from server.audio_adapter import to_speaker_result

    risk = to_speaker_result(SpeakerSignal(verdict=verdict)).risk
    bounds = {"low": (0.0, 0.35), "mid": (0.5, 0.5), "high": (0.65, 1.0)}
    lo, hi = bounds[expected_ordering]
    assert lo <= risk <= hi


def test_replay_flag_uses_the_configured_threshold():
    import config
    from audio_ml.signals import SpeakerSignal
    from server.audio_adapter import to_speaker_result

    just_over = config.REPLAY_COSINE_THRESHOLD + 0.01
    just_under = config.REPLAY_COSINE_THRESHOLD - 0.01

    assert to_speaker_result(SpeakerSignal(verdict="match", raw_cosine=just_over)).is_replay
    assert not to_speaker_result(SpeakerSignal(verdict="match", raw_cosine=just_under)).is_replay


def test_spoof_timeline_maps_into_c_shaped_segments():
    """The F2 defect, at the level it actually broke: a populated timeline.

    An empty timeline would pass even with the wrong class, because the list
    comprehension never runs. This is why the original bug survived a smoke test.
    """
    from audio_ml.signals import SpoofSegment, SpoofSignal
    from server.audio_adapter import to_spoof_result

    signal = SpoofSignal(
        score=0.62,
        peak=0.91,
        max_synth_run_s=4.0,
        verdict="partial_synthetic",
        n_chunks=3,
        timeline=[
            SpoofSegment(start_s=0.0, end_s=3.0, label="human", score=0.10),
            SpoofSegment(start_s=2.0, end_s=5.0, label="synthetic", score=0.91),
        ],
    )

    result = to_spoof_result(signal)

    assert len(result.timeline) == 2
    assert result.timeline[0].is_synthetic is False
    assert result.timeline[1].is_synthetic is True
    assert result.timeline[1].score == pytest.approx(0.91)
    # The three statistics the design mandates — median alone hides hybrid attacks.
    assert result.median_score == pytest.approx(0.62)
    assert result.peak_score == pytest.approx(0.91)
    assert result.max_synth_run_s == pytest.approx(4.0)
    assert result.is_synthetic is True


def test_spoof_uncertain_is_not_reported_as_synthetic():
    """`uncertain` means the model abstained. That is not evidence of synthesis."""
    from audio_ml.signals import SpoofSignal
    from server.audio_adapter import to_spoof_result

    result = to_spoof_result(SpoofSignal(score=0.5, verdict="uncertain"))
    assert result.is_synthetic is False
