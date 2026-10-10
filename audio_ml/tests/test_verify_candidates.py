"""Upgrade plan, Phase 0 step 3: verification reads candidates it is given.

`verify_speaker` globbed `data/enrollments/*.npz` while the UI read SQLite, so the two
disagreed about who was enrolled (3 people vs 0) and a deleted person kept matching.
With `candidates=` the server passes the database's voiceprints in and the verifier
reads no files at all. `candidates=None` keeps the legacy disk path for the CLI.
"""

from __future__ import annotations

import numpy as np
import pytest

import config
from audio_ml import embed, enroll, verify


def _unit(seed: int, dim: int = 192) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _towards(target: np.ndarray, other_seed: int, cosine: float) -> np.ndarray:
    """A unit vector with the given cosine to `target`."""
    o = _unit(other_seed)
    o = o - float(np.dot(o, target)) * target
    o = o / np.linalg.norm(o)
    v = cosine * target + np.sqrt(1.0 - cosine ** 2) * o
    return (v / np.linalg.norm(v)).astype(np.float32)


PROBE = _unit(7)


@pytest.fixture(autouse=True)
def fake_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(embed, "load_audio", lambda p: (np.full(16000, 0.5, dtype=np.float32), 16000))
    monkeypatch.setattr(embed, "detect_condition", lambda a, sr: "wb")
    monkeypatch.setattr(embed, "vad_segments", lambda a, sr: [(0, len(a))])
    monkeypatch.setattr(embed, "embed_chunks", lambda a, sr, s: [PROBE])
    monkeypatch.setattr(config, "FLAGGED_DIR", tmp_path / "no-flagged")
    monkeypatch.setattr(config, "COHORT_DIR", tmp_path / "no-cohort")


@pytest.fixture
def no_disk(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("verify_speaker read the legacy .npz store although candidates were given")
    monkeypatch.setattr(enroll, "list_persons", refuse)
    monkeypatch.setattr(enroll, "load_voiceprint", refuse)


def _cand(person_id, name, **centroids):
    return {"person_id": person_id, "name": name, "relationship": "Family", "centroids": centroids}


def test_given_candidates_are_scored_and_no_file_is_read(no_disk):
    papa = _cand("p_papa", "Papa", wb=_towards(PROBE, 1, 0.93))
    stranger = _cand("p_x", "Someone", wb=_towards(PROBE, 2, 0.30))
    sig = verify.verify_speaker("probe.wav", candidates=[stranger, papa])
    assert sig.verdict == "match"
    assert sig.best_match_id == "p_papa" and sig.best_match_name == "Papa"
    assert sig.raw_cosine == pytest.approx(0.93, abs=1e-4)


def test_best_condition_wins_per_person(no_disk):
    """Max over stored conditions, exactly as the disk path does."""
    papa = _cand("p_papa", "Papa", wb=_towards(PROBE, 1, 0.70), nb8k_sim=_towards(PROBE, 3, 0.91))
    sig = verify.verify_speaker("probe.wav", candidates=[papa])
    assert sig.verdict == "match" and sig.condition_used == "nb8k_sim"


def test_empty_candidates_is_unknown_without_touching_disk(no_disk):
    """Nobody enrolled in the database means nobody — not 'go look in the old folder'."""
    sig = verify.verify_speaker("probe.wav", candidates=[])
    assert sig.verdict == "unknown" and sig.best_match_id is None


def test_unusable_centroids_are_skipped_not_fatal(no_disk):
    broken = _cand("p_bad", "Bad", wb=np.zeros(192, dtype=np.float32))
    wrong_dim = _cand("p_dim", "Dim", wb=np.ones(10, dtype=np.float32))
    nan = _cand("p_nan", "Nan", wb=np.full(192, np.nan, dtype=np.float32))
    good = _cand("p_ok", "Ok", wb=_towards(PROBE, 4, 0.88))
    sig = verify.verify_speaker("probe.wav", candidates=[broken, wrong_dim, nan, good])
    assert sig.best_match_id == "p_ok"


def test_claimed_person_restricts_the_comparison(no_disk):
    """A 1:1 check: the closest voice overall is ignored when someone else is claimed."""
    papa = _cand("p_papa", "Papa", wb=_towards(PROBE, 1, 0.95))
    rahul = _cand("p_rahul", "Rahul", wb=_towards(PROBE, 2, 0.40))
    sig = verify.verify_speaker("probe.wav", candidates=[papa, rahul], claimed_person_id="p_rahul")
    assert sig.best_match_id == "p_rahul"
    assert sig.verdict != "match"


def test_claimed_person_not_among_candidates_is_unknown(no_disk, caplog):
    papa = _cand("p_papa", "Papa", wb=_towards(PROBE, 1, 0.95))
    sig = verify.verify_speaker("probe.wav", candidates=[papa], claimed_person_id="p_gone")
    assert sig.verdict == "unknown"
    assert any("p_gone" in r.getMessage() for r in caplog.records)


def test_without_candidates_the_legacy_disk_path_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    np.savez(tmp_path / "p_disk.npz", wb=_towards(PROBE, 5, 0.9), nb8k=_towards(PROBE, 6, 0.5),
             name="Disk", relationship="Friend", n_samples=16000, enrolled_at="2026-10-01")
    sig = verify.verify_speaker("probe.wav")
    assert sig.best_match_id == "p_disk" and sig.verdict == "match"


def test_a_flagged_voice_is_caught_even_with_nobody_enrolled(no_disk):
    """The flagged check used to run only after a best match, so a user with no contacts
    was never warned about a reported scammer's voice."""
    sig = verify.verify_speaker("probe.wav", candidates=[], flagged=[_towards(PROBE, 9, 0.97)])
    assert sig.flagged_voice_hits == 1
    assert sig.verdict == "unknown"


def test_given_flagged_list_replaces_the_folder(tmp_path, monkeypatch, no_disk):
    folder = tmp_path / "flagged"
    folder.mkdir()
    np.save(folder / "old.npy", PROBE)
    monkeypatch.setattr(config, "FLAGGED_DIR", folder)
    papa = _cand("p_papa", "Papa", wb=_towards(PROBE, 1, 0.93))
    assert verify.verify_speaker("probe.wav", candidates=[papa], flagged=[]).flagged_voice_hits == 0
    assert verify.verify_speaker("probe.wav", candidates=[papa]).flagged_voice_hits == 1
