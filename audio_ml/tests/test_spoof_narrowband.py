"""Item 8, second rule: the authenticity branch abstains on telephony-band audio.

Model A was fine-tuned on wideband IFD. Through an 8 kHz phone channel its EER goes from
9.7% to 17.2% (G.711) and 25.5% (AMR-NB). The k-NN embedding gate in audio_ml/ood.py
does not see that channel (it flags ~14% of clean clips and ~11% of codec clips), so a
deterministic rule does: an 8 kHz channel has no content above ~4 kHz, whatever the
codec, so when a clip's spectrum is band-limited that way the branch abstains.

The feature is the share of spectral power above ~4 kHz, averaged over the energetic
frames of the whole clip. It is a measurement, not a fitted model (CLAUDE.md rule 1).
"""

from __future__ import annotations

import logging
import wave

import numpy as np
import pytest
from scipy.signal import resample_poly

import config
from audio_ml import spoof
from audio_ml.ood import hf_power_ratio, is_narrowband
from audio_ml.signals import SpoofSignal

SR = 16_000
CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
needs_model = pytest.mark.skipif(not spoof.model_files_present(), reason="Model A not installed")


def _white(seconds=3.0, seed=0):
    return (0.1 * np.random.default_rng(seed).standard_normal(int(seconds * SR))).astype(np.float32)


def _through_8k(x):
    """The same signal after an 8 kHz channel: down to 8 kHz and back up to 16 kHz."""
    return resample_poly(resample_poly(x, 1, 2), 2, 1).astype(np.float32)


def _write_wav(path, audio, sr=SR):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


# --- the measurement ------------------------------------------------------------------------

def test_white_noise_is_wideband():
    ratio = hf_power_ratio(_white(), SR)
    # White noise spreads power evenly over 0-8 kHz, so about half of it is above 4 kHz.
    assert 0.35 < ratio < 0.6
    assert not is_narrowband(_white(), SR, config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD)


def test_the_same_noise_through_an_8k_channel_is_narrowband():
    nb = _through_8k(_white())
    ratio = hf_power_ratio(nb, SR)
    assert ratio < 1e-3
    assert is_narrowband(nb, SR, config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD)


def test_audio_already_at_8k_is_narrowband_by_definition():
    # Nothing can exist above the 4 kHz Nyquist of an 8 kHz signal.
    x = resample_poly(_white(), 1, 2).astype(np.float32)
    assert hf_power_ratio(x, 8_000) == 0.0
    assert is_narrowband(x, 8_000, config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD)


def test_silence_is_unknown_not_narrowband(caplog):
    silence = np.zeros(3 * SR, dtype=np.float32)
    with caplog.at_level(logging.INFO, logger="audio_ml.ood"):
        assert hf_power_ratio(silence, SR) is None
        assert is_narrowband(silence, SR, config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD) is False
    assert any("narrowband" in r.getMessage().lower() for r in caplog.records), \
        "an unknown verdict must say why"


@pytest.mark.parametrize("audio", [np.zeros(0, dtype=np.float32), np.zeros(10, dtype=np.float32),
                                   np.full(SR, np.nan, dtype=np.float32), None])
def test_degenerate_input_is_unknown_and_never_raises(audio):
    assert hf_power_ratio(audio, SR) is None
    assert is_narrowband(audio, SR, 0.01) is False


def test_the_whole_clip_is_measured_not_just_its_start():
    # Long leading silence (where detect_condition's first-2048-sample window would sit),
    # then wideband audio. The silent frames must be ignored, not averaged in.
    clip = np.concatenate([np.zeros(2 * SR, dtype=np.float32), _white(2.0)])
    assert hf_power_ratio(clip, SR) > 0.35


def test_a_narrowband_clip_with_a_wideband_opening_is_still_judged_on_the_whole():
    clip = np.concatenate([_white(0.2, seed=1), _through_8k(_white(4.0))])
    ratio = hf_power_ratio(clip, SR)
    assert ratio < hf_power_ratio(_white(), SR) / 5


def test_low_level_hiss_in_quiet_frames_does_not_make_a_clip_wideband():
    # Narrowband speech-level signal with a faint wideband noise floor between "words":
    # the energetic frames decide, the near-silent ones do not.
    rng = np.random.default_rng(3)
    loud = _through_8k(_white(1.0))
    hiss = (1e-4 * rng.standard_normal(SR)).astype(np.float32)
    clip = np.concatenate([loud, hiss, loud, hiss])
    assert is_narrowband(clip, SR, config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD)


# --- config ---------------------------------------------------------------------------------

def test_narrowband_rule_defaults_on_but_only_inside_the_ood_flag():
    assert config.SPOOF_OOD_NARROWBAND_ENABLED is True
    assert config.SPOOF_OOD_ENABLED is False
    assert 0.0 < config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD < 0.1


# --- detect_spoof wiring (model stubbed: the rule is about audio, not the network) ------------

@pytest.fixture
def stub_model(monkeypatch):
    monkeypatch.setattr(spoof, "_load_model", lambda: object())
    monkeypatch.setattr(spoof, "_infer",
                        lambda model, chunks: ([0.9] * len(chunks), np.zeros((len(chunks), 4), np.float32)))
    monkeypatch.setattr(spoof, "_ood_reference", lambda: None)


@pytest.fixture
def nb_wav(tmp_path):
    return str(_write_wav(tmp_path / "nb.wav", _through_8k(_white(5.0))))


@pytest.fixture
def wb_wav(tmp_path):
    return str(_write_wav(tmp_path / "wb.wav", _white(5.0)))


def test_flag_off_leaves_a_narrowband_clip_untouched(monkeypatch, stub_model, nb_wav):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", False)
    s = spoof.detect_spoof(nb_wav)
    assert (s.ood, s.ood_score, s.ood_reason, s.hf_ratio) == (False, None, None, None)
    assert s.n_chunks > 0


def test_flag_on_abstains_on_a_narrowband_clip(monkeypatch, stub_model, nb_wav):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(config, "SPOOF_OOD_NARROWBAND_ENABLED", True)
    s = spoof.detect_spoof(nb_wav)
    assert s.ood is True and s.ood_reason == "narrowband_channel"
    assert s.hf_ratio is not None and s.hf_ratio < config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD
    assert s.n_chunks > 0 and s.score == pytest.approx(0.9), "scores are still reported"


def test_flag_on_keeps_a_wideband_clip(monkeypatch, stub_model, wb_wav):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    s = spoof.detect_spoof(wb_wav)
    assert s.ood is False and s.ood_reason is None
    assert s.hf_ratio > config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD


def test_narrowband_subflag_off_disables_only_that_rule(monkeypatch, stub_model, nb_wav):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(config, "SPOOF_OOD_NARROWBAND_ENABLED", False)
    s = spoof.detect_spoof(nb_wav)
    assert s.ood is False and s.ood_reason is None and s.hf_ratio is None


def test_embedding_rule_is_labelled_when_it_fires(monkeypatch, stub_model, wb_wav):
    from audio_ml.ood import OodReference

    bank = np.tile(np.array([[1.0, 0, 0, 0]], np.float32), (5, 1))
    ref = OodReference(embeddings=bank, threshold=0.05, k=1, percentile=95.0, n_reference=5)
    monkeypatch.setattr(spoof, "_infer",
                        lambda model, chunks: ([0.9] * len(chunks),
                                               np.tile(np.array([[-1.0, 0, 0, 0]], np.float32), (len(chunks), 1))))
    monkeypatch.setattr(spoof, "_ood_reference", lambda: ref)
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    s = spoof.detect_spoof(wb_wav)
    assert s.ood is True and s.ood_reason == "embedding_distance" and s.ood_score == 1.0


def test_narrowband_takes_precedence_and_embedding_score_is_still_reported(monkeypatch, stub_model, nb_wav):
    from audio_ml.ood import OodReference

    bank = np.tile(np.array([[1.0, 0, 0, 0]], np.float32), (5, 1))
    ref = OodReference(embeddings=bank, threshold=0.05, k=1, percentile=95.0, n_reference=5)
    monkeypatch.setattr(spoof, "_infer",
                        lambda model, chunks: ([0.9] * len(chunks),
                                               np.tile(np.array([[1.0, 0, 0, 0]], np.float32), (len(chunks), 1))))
    monkeypatch.setattr(spoof, "_ood_reference", lambda: ref)
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    s = spoof.detect_spoof(nb_wav)
    assert s.ood is True and s.ood_reason == "narrowband_channel" and s.ood_score == 0.0


def test_a_broken_narrowband_measurement_degrades_to_no_abstention(monkeypatch, stub_model, nb_wav, caplog):
    def boom(*a, **k):
        raise RuntimeError("fft exploded")

    monkeypatch.setattr(spoof, "hf_power_ratio", boom)
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    with caplog.at_level(logging.WARNING):
        s = spoof.detect_spoof(nb_wav)
    assert s.n_chunks > 0 and s.ood is False, "a failed check must not discard the scores"
    assert any("narrowband" in r.getMessage().lower() for r in caplog.records)


# Note: data/eval_set/clips/*_nb8k*.wav are NOT band-limited (measured: their 4.5-7.6 kHz
# bands sit -18 to -25 dB re 1-3 kHz, like their wideband sources), so they cannot be
# used here. This test makes a real 8 kHz-channel copy of a real clip instead.
@needs_model
def test_a_real_clip_through_an_8k_channel_abstains_and_the_original_does_not(monkeypatch, tmp_path):
    from audio_ml import embed

    audio, sr = embed.load_audio(str(CLIPS / "friend_test.wav"))
    nb_path = _write_wav(tmp_path / "friend_test_8k.wav", _through_8k(np.asarray(audio, np.float32)))
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(spoof, "_ood_reference", lambda: None)
    nb = spoof.detect_spoof(str(nb_path))
    wb = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert nb.ood and nb.ood_reason == "narrowband_channel" and nb.n_chunks > 0
    assert not wb.ood and wb.ood_reason is None


# --- the server boundary ----------------------------------------------------------------------

def test_flag_off_adapter_output_is_unchanged():
    from server.audio_adapter import to_spoof_result

    r = to_spoof_result(SpoofSignal(score=0.3, peak=0.4, verdict="bonafide", n_chunks=2))
    assert set(r.details) == {"verdict", "n_chunks", "available"}


def test_the_adapter_carries_the_reason():
    from server.audio_adapter import to_spoof_result

    r = to_spoof_result(SpoofSignal(score=0.97, peak=0.99, verdict="synthetic", n_chunks=3,
                                    ood=True, ood_reason="narrowband_channel", hf_ratio=0.0004))
    assert r.details["available"] is False
    assert r.details["abstain_reason"] == "out_of_distribution"
    assert r.details["ood_reason"] == "narrowband_channel"
    assert r.details["hf_ratio"] == 0.0004


def _codes(signal):
    from contracts import ScriptAnalysisResult, SpeakerVerdict, SpeakerVerificationResult
    from server.audio_adapter import to_spoof_result
    from server.orchestrator import _compute_fusion

    fusion = _compute_fusion(SpeakerVerificationResult(verdict=SpeakerVerdict.UNKNOWN, risk=0.5),
                             to_spoof_result(signal),
                             ScriptAnalysisResult(risk=0.1, details={"available": True}))
    return {rc.code: rc for rc in fusion.reason_codes}, fusion


def test_reason_code_names_the_phone_channel():
    codes, fusion = _codes(SpoofSignal(score=0.97, peak=0.99, verdict="synthetic", n_chunks=3,
                                       ood=True, ood_reason="narrowband_channel", hf_ratio=0.0004))
    rc = codes["RC_SPOOF_OUT_OF_DOMAIN"]
    assert "phone" in rc.explanation.lower()
    assert "windows" not in rc.value, "the value must describe the channel, not k-NN windows"
    assert fusion.weights_used.cm_weight == 0.0


def test_reason_code_for_the_embedding_rule_is_unchanged():
    codes, _ = _codes(SpoofSignal(score=0.97, peak=0.99, verdict="synthetic", n_chunks=3,
                                  ood=True, ood_score=0.8, ood_reason="embedding_distance"))
    rc = codes["RC_SPOOF_OUT_OF_DOMAIN"]
    assert rc.value == "80% of windows out of domain"
