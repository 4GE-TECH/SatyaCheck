"""Item 8: the authenticity branch abstains on audio unlike anything it was trained on.

Measured (data/spoof_eval_ifd*.json): Model A's EER is 9.7% on clean IFD audio, 17.2%
through G.711 and 25.5% through AMR-NB. On audio that far from its training data its
P(synthetic) is not evidence, and fusion must not weigh it as if it were.

The check is non-parametric: AASIST's own penultimate embedding (`last_hidden`) for each
window, compared by cosine distance to its k nearest neighbours in a reference bank of
IFD *training* windows. The threshold is a percentile of the same distance on IFD
*validation* windows, so by construction ~(100 - percentile)% of in-domain windows
exceed it. When at least `SPOOF_OOD_MAX_WINDOW_FRACTION` of a clip's windows exceed it,
the branch abstains through the existing path: `details["available"] = False`, fusion
drops w_cm and renormalises, and the reason code says why.

Nothing is trained: the bank is stored embeddings, not fitted weights.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

import config
from audio_ml import spoof
from audio_ml.ood import OodReference, knn_distance, load_reference, ood_verdict
from audio_ml.signals import SpoofSignal

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
needs_model = pytest.mark.skipif(not spoof.model_files_present(), reason="Model A not installed")


def _unit(rows):
    rows = np.asarray(rows, dtype=np.float32)
    return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def _reference(threshold=0.05, k=2):
    rng = np.random.default_rng(0)
    bank = _unit(rng.standard_normal((50, 16)) + np.array([5.0] + [0.0] * 15))
    return OodReference(embeddings=bank, threshold=threshold, k=k, percentile=95.0, n_reference=50)


# --- distance and decision ---------------------------------------------------------------

def test_a_reference_point_is_at_distance_zero():
    ref = _reference()
    d = knn_distance(ref.embeddings[:1], ref.embeddings, k=1)
    assert d[0] == pytest.approx(0.0, abs=1e-5)


def test_an_opposite_point_is_far():
    ref = _reference()
    far = -ref.embeddings[:1]
    # > 1.0 means the nearest neighbours point the other way (cosine similarity < 0)
    assert knn_distance(far, ref.embeddings, k=2)[0] > 1.0


def test_in_domain_windows_are_not_ood():
    ref = _reference(threshold=0.5)
    is_ood, score = ood_verdict(ref.embeddings[:4] * 3.0, ref, max_window_fraction=0.5)
    assert not is_ood and score == 0.0


def test_mostly_far_windows_are_ood_and_score_is_the_fraction():
    ref = _reference(threshold=0.5)
    windows = np.vstack([-ref.embeddings[:3], ref.embeddings[:1]])
    is_ood, score = ood_verdict(windows, ref, max_window_fraction=0.5)
    assert is_ood and score == pytest.approx(0.75)


def test_a_minority_of_far_windows_is_not_ood():
    ref = _reference(threshold=0.5)
    windows = np.vstack([-ref.embeddings[:1], ref.embeddings[:3]])
    assert not ood_verdict(windows, ref, max_window_fraction=0.5)[0]


def test_reference_round_trips_through_disk(tmp_path):
    ref = _reference()
    path = tmp_path / "ood_ref.npz"
    ref.save(path)
    again = load_reference(path)
    assert np.allclose(again.embeddings, ref.embeddings, atol=1e-6)  # re-normalised on load
    assert (again.threshold, again.k, again.percentile) == (ref.threshold, ref.k, ref.percentile)


def test_a_missing_reference_loads_as_none_and_says_so(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert load_reference(tmp_path / "absent.npz") is None
    assert any("ood" in r.getMessage().lower() for r in caplog.records)


# --- detect_spoof wiring -----------------------------------------------------------------------

def test_the_flag_defaults_off():
    assert config.SPOOF_OOD_ENABLED is False


@needs_model
def test_flag_off_changes_nothing(monkeypatch):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", False)
    s = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert s.ood is False and s.ood_score is None and s.n_chunks > 0


@needs_model
def test_a_clip_inside_its_own_reference_is_in_domain(monkeypatch):
    emb = spoof.window_embeddings(str(CLIPS / "friend_test.wav"))
    ref = OodReference(embeddings=_unit(emb), threshold=0.05, k=1, percentile=95.0, n_reference=len(emb))
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(spoof, "_ood_reference", lambda: ref)
    s = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert s.ood is False and s.ood_score == 0.0
    assert s.n_chunks > 0, "an in-domain clip is still scored"


@needs_model
def test_a_clip_far_from_the_reference_is_ood(monkeypatch):
    emb = spoof.window_embeddings(str(CLIPS / "friend_test.wav"))
    ref = OodReference(embeddings=-_unit(emb), threshold=0.05, k=1, percentile=95.0, n_reference=len(emb))
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(spoof, "_ood_reference", lambda: ref)
    s = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert s.ood is True and s.ood_score == 1.0


@needs_model
def test_flag_on_without_a_reference_bank_changes_nothing(monkeypatch):
    monkeypatch.setattr(config, "SPOOF_OOD_ENABLED", True)
    monkeypatch.setattr(spoof, "_ood_reference", lambda: None)
    s = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert s.ood is False and s.n_chunks > 0


# --- the server boundary ------------------------------------------------------------------------

def test_the_adapter_turns_ood_into_an_abstention():
    from server.audio_adapter import to_spoof_result

    result = to_spoof_result(SpoofSignal(score=0.97, peak=0.99, verdict="synthetic", n_chunks=3,
                                         ood=True, ood_score=0.8))
    assert result.details["available"] is False
    assert result.details["abstain_reason"] == "out_of_distribution"
    assert result.details["ood_score"] == 0.8


def test_fusion_explains_an_ood_abstention():
    from contracts import ScriptAnalysisResult, SpeakerVerdict, SpeakerVerificationResult
    from server.audio_adapter import to_spoof_result
    from server.orchestrator import _compute_fusion

    spoof_result = to_spoof_result(SpoofSignal(score=0.97, peak=0.99, verdict="synthetic",
                                               n_chunks=3, ood=True, ood_score=0.8))
    fusion = _compute_fusion(SpeakerVerificationResult(verdict=SpeakerVerdict.UNKNOWN, risk=0.5),
                             spoof_result, ScriptAnalysisResult(risk=0.1, details={"available": True}))
    codes = [rc.code for rc in fusion.reason_codes]
    assert "RC_SPOOF_OUT_OF_DOMAIN" in codes and "RC_SPOOF_UNAVAILABLE" not in codes
    assert fusion.weights_used.cm_weight == 0.0


# --- building the reference bank -----------------------------------------------------------------

def _toy_manifest(root):
    import csv

    rows = [("tr_b.wav", 1, "S1", "train"), ("tr_s.wav", 0, "S1", "train"),
            ("va_b.wav", 1, "S2", "val"), ("va_s.wav", 0, "S2", "val"),
            ("te.wav", 1, "S3", "test")]
    with (root / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filepath", "label", "speaker_id", "split", "orig_sr", "orig_channels", "duration_sec"])
        for f, label, spk, split in rows:
            (root / f).write_bytes(b"x")
            w.writerow([f, label, spk, split, 16000, 1, 4.0])
    return root / "manifest.csv"


_TOY = {
    "tr_b.wav": [[1, 0, 0], [0.9, 0.1, 0]],
    "tr_s.wav": [[0, 1, 0]],
    "va_b.wav": [[0.8, 0.2, 0]],
    "va_s.wav": [[0, 0.7, 0.7], [0, 0, 1]],
    "te.wav": [[5, 5, 5]],
}


def _toy_embedder(path):
    return np.asarray(_TOY[path.name], dtype=np.float32)


def test_builder_uses_train_for_the_bank_and_val_for_the_threshold(tmp_path):
    from audio_ml.eval import build_ood_ref

    out = tmp_path / "ood_ref.npz"
    code = build_ood_ref.main(["--manifest", str(_toy_manifest(tmp_path)), "--out", str(out),
                               "--k", "1", "--percentile", "50"], embedder=_toy_embedder)
    assert code == 0
    ref = load_reference(out)
    assert ref.n_reference == 3, "three train windows, no val or test windows"
    train = np.vstack([_TOY["tr_b.wav"], _TOY["tr_s.wav"]])
    val = np.vstack([_TOY["va_b.wav"], _TOY["va_s.wav"]])
    expected = float(np.percentile(knn_distance(val, train, 1), 50))
    assert ref.threshold == pytest.approx(expected, abs=1e-6)
    assert (ref.k, ref.percentile) == (1, 50.0)


def test_builder_fails_loudly_when_nothing_embeds(tmp_path):
    from audio_ml.eval import build_ood_ref

    code = build_ood_ref.main(["--manifest", str(_toy_manifest(tmp_path)), "--out", str(tmp_path / "o.npz")],
                              embedder=lambda p: np.zeros((0, 0), dtype=np.float32))
    assert code == 3
    assert not (tmp_path / "o.npz").exists()
