"""Model A on phone audio: rescale its score against the threshold measured for the channel.

Measured on IFD test (data/spoof_eval_ifd*.json): Model A's EER threshold is 0.71 on clean
audio but 0.973 through G.711 and 0.985 through AMR-NB. On 8 kHz audio a genuine voice
routinely scores 0.8-0.93 (seen live on an Exotel call, which then latched suspicious).
So on a narrowband channel the score is mapped s -> max(0, (s - T) / (1 - T)) with
T = SPOOF_PHONE_THRESHOLD: ordinary phone voice reads ~0, strong synthetic signatures
above T still flag. Wideband audio is untouched.
"""

from __future__ import annotations

import numpy as np
import pytest

import config
from audio_ml import spoof

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"


def test_the_mapping_is_exact():
    assert spoof.calibrate_phone_scores([0.5, 0.93, 0.97, 0.985, 1.0], threshold=0.97) == \
        pytest.approx([0.0, 0.0, 0.0, 0.5, 1.0])


def test_defaults_are_on_with_the_measured_threshold():
    assert config.SPOOF_PHONE_CALIBRATION_ENABLED is True
    assert config.SPOOF_PHONE_THRESHOLD == pytest.approx(0.973)


@pytest.mark.skipif(not spoof.model_files_present(), reason="Model A not installed")
def test_a_phone_band_clip_is_calibrated_and_a_wideband_clip_is_not(tmp_path):
    import wave

    from scipy.signal import resample_poly

    from audio_ml import embed

    audio, sr = embed.load_audio(str(CLIPS / "friend_test.wav"))
    phone = resample_poly(resample_poly(np.asarray(audio, dtype=np.float64), 1, 2), 2, 1)
    path = tmp_path / "phone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes((np.clip(phone, -1, 1) * 32767).astype("<i2").tobytes())

    wide = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    narrow = spoof.detect_spoof(str(path))
    assert wide.calibration is None
    assert narrow.calibration == "phone_channel"
    assert narrow.score <= max(0.0, (narrow.raw_median - config.SPOOF_PHONE_THRESHOLD)
                               / (1 - config.SPOOF_PHONE_THRESHOLD)) + 1e-9
    assert narrow.n_chunks > 0, "calibrated, not abstained"


@pytest.mark.skipif(not spoof.model_files_present(), reason="Model A not installed")
def test_calibration_off_leaves_scores_raw(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SPOOF_PHONE_CALIBRATION_ENABLED", False)
    s = spoof.detect_spoof(str(CLIPS / "friend_test_nb8k_probe.wav"))
    assert s.calibration is None


def test_a_single_window_spike_on_a_phone_line_is_not_a_cloned_voice():
    """Seen live: one 4 s window over the phone threshold made the call 'partial_synthetic'
    and the panel said synthetic speech, though every other window was bonafide."""
    from audio_ml.spoof import _phone_verdict

    assert _phone_verdict("partial_synthetic", max_synth_run_s=4.04, median=0.0) == "bonafide"
    assert _phone_verdict("partial_synthetic", max_synth_run_s=8.0, median=0.0) == "partial_synthetic"
    assert _phone_verdict("synthetic", max_synth_run_s=4.04, median=0.9) == "synthetic"
    assert config.SPOOF_PHONE_MIN_SYNTH_RUN_S == pytest.approx(6.0)
