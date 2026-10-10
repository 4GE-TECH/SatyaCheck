"""Upgrade plan, Phase 0 step 2: enrollment computes, the database persists.

`enroll_person` wrote `data/enrollments/<id>.npz` and returned only metadata, while
`server/enroll_router.py` read `result.get("wb")` — always empty — and returned 201 with
"0 voiceprints". `compute_voiceprint` is the pure half: vectors in memory, no files, so
the server can write person and vectors in one transaction.

The model is faked here (deterministic vectors keyed by the audio), so these run without
`models/`. What they pin is the data flow, not ECAPA's accuracy.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_ml import codec, embed, enroll


def _unit(seed: int, dim: int = 192) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    """Paths starting with 'silent' load as empty audio; everything else as 1 s of tone.
    Degraded audio embeds differently from wideband, so the two centroids differ."""
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path / "enrollments")

    def load_audio(path):
        name = str(path)
        if "silent" in name:
            return np.zeros(0, dtype=np.float32), 16000
        level = 0.25 if "degraded" in name else 0.5
        return np.full(16000, level, dtype=np.float32), 16000

    def embed_chunks(audio, sr, segments):
        seed = 2 if float(audio[0]) == 0.25 else 1
        return [_unit(seed) * 3.0, _unit(seed) * 5.0]   # un-normalised on purpose

    def degrade(src, dst, mode="nb8k"):
        return str(tmp_path / "degraded.wav")

    monkeypatch.setattr(embed, "load_audio", load_audio)
    monkeypatch.setattr(embed, "vad_segments", lambda audio, sr: [(0, len(audio))])
    monkeypatch.setattr(embed, "embed_chunks", embed_chunks)
    monkeypatch.setattr(codec, "degrade", degrade)
    return tmp_path


def test_returns_unit_length_centroids_per_condition(fake_model):
    vp = enroll.compute_voiceprint(["a.wav"])
    assert vp is not None
    assert set(vp) >= {"wb", "nb8k_sim", "n_samples"}
    assert "nb8k_real" not in vp
    for key in ("wb", "nb8k_sim"):
        assert vp[key].shape == (192,)
        assert abs(float(np.linalg.norm(vp[key])) - 1.0) < 1e-5
    assert float(np.dot(vp["wb"], vp["nb8k_sim"])) < 0.99, "the two conditions must differ"


def test_writes_no_files(fake_model):
    enroll.compute_voiceprint(["a.wav"])
    assert not (fake_model / "enrollments").exists() or not any((fake_model / "enrollments").iterdir())


def test_real_narrowband_paths_add_a_third_centroid(fake_model):
    vp = enroll.compute_voiceprint(["a.wav"], nb8k_real_paths=["call.wav"])
    assert vp is not None and vp["nb8k_real"].shape == (192,)


@pytest.mark.parametrize("paths", [[], ["silent.wav"]])
def test_no_usable_audio_returns_none(fake_model, paths, caplog):
    assert enroll.compute_voiceprint(paths) is None
    assert any("compute_voiceprint" in r.getMessage() for r in caplog.records), "a degrade must be logged"


def test_failed_degradation_returns_none_rather_than_a_partial_voiceprint(fake_model, monkeypatch):
    monkeypatch.setattr(codec, "degrade", lambda src, dst, mode="nb8k": None)
    assert enroll.compute_voiceprint(["a.wav"]) is None


def test_enroll_person_still_writes_the_cli_file_from_the_same_vectors(fake_model):
    """The CLI and test path keep their signature and their .npz."""
    expected = enroll.compute_voiceprint(["a.wav"])
    result = enroll.enroll_person("p1", "Ma", "Mother", ["a.wav"])
    assert result and result["person_id"] == "p1"
    stored = enroll.load_voiceprint("p1")
    assert np.allclose(stored["wb"], expected["wb"])
    assert np.allclose(stored["nb8k_sim"], expected["nb8k_sim"])
