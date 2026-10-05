"""Item 12: the authenticity evaluation must refuse to report a number from a leaky split.

An EER measured on test files that also appear in training, or on speakers the model
trained on, is not a measurement of anything. `eval_spoof` checks both *before* it
scores a single file and exits non-zero on any overlap.

The metric functions are checked against hand-computed values, not against themselves.
Score convention throughout: P(synthetic), higher = more likely spoof — the convention
`audio_ml.spoof.detect_spoof` reports.
"""

from __future__ import annotations

import csv
import json

import pytest

from audio_ml.eval import eval_spoof as ev

BONAFIDE = [0.1, 0.2, 0.3, 0.4]
SPOOF = [0.35, 0.6, 0.7, 0.8]


# --- EER ------------------------------------------------------------------------

def test_eer_at_an_exact_crossing():
    # threshold 0.4: bonafide 0.4 rejected (1/4), spoof 0.35 accepted (1/4)
    eer, _ = ev.compute_eer(BONAFIDE, SPOOF)
    assert eer == pytest.approx(0.25)


def test_eer_is_zero_when_classes_separate():
    eer, threshold = ev.compute_eer([0.1, 0.2], [0.8, 0.9])
    assert eer == 0.0
    assert 0.2 < threshold <= 0.8


def test_eer_needs_both_classes():
    with pytest.raises(ValueError):
        ev.compute_eer([], [0.5])


# --- min t-DCF ---------------------------------------------------------------------

def test_min_tdcf_with_an_ideal_asv_matches_a_hand_calculation():
    """Ideal ASV: C1 = Ptar*Cmiss_cm = 0.9405, C2 = Cfa_cm*Pspoof = 0.5.

    Normalised t-DCF = (0.9405*Pmiss_cm + 0.5*Pfa_cm) / 0.5, minimised over thresholds.
    At threshold 0.6 no bonafide is rejected and 1/4 spoofs are accepted -> 0.25,
    the minimum over every operating point of the toy scores.
    """
    assert ev.min_tdcf(BONAFIDE, SPOOF, ev.IDEAL_ASV) == pytest.approx(0.25)


def test_min_tdcf_is_zero_when_classes_separate():
    assert ev.min_tdcf([0.1, 0.2], [0.8, 0.9], ev.IDEAL_ASV) == pytest.approx(0.0)


def test_min_tdcf_rejects_an_asv_worse_than_useless():
    with pytest.raises(ValueError):
        ev.min_tdcf(BONAFIDE, SPOOF, ev.AsvRates(p_miss=1.0, p_fa=1.0, p_miss_spoof=0.0))


# --- leakage checks ------------------------------------------------------------------

def _rows(*specs):
    return [ev.ManifestRow(f, label, spk, split, orig_sr=16000) for f, label, spk, split in specs]


def test_shared_speaker_across_train_and_test_is_reported():
    rows = _rows(("a.wav", 1, "Speaker-1", "train"), ("b.wav", 1, "Speaker-1", "test"))
    problems = ev.check_speaker_disjoint(rows)
    assert problems and "Speaker-1" in problems[0]


def test_disjoint_speakers_pass():
    rows = _rows(("a.wav", 1, "Speaker-1", "train"), ("b.wav", 0, "Speaker-2", "test"))
    assert ev.check_speaker_disjoint(rows) == []


def test_identical_audio_under_two_names_is_reported(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"same audio")
    (tmp_path / "b.wav").write_bytes(b"same audio")
    rows = _rows(("a.wav", 1, "Speaker-1", "train"), ("b.wav", 1, "Speaker-2", "test"))
    problems = ev.check_hash_disjoint(rows, tmp_path)
    assert problems and "a.wav" in problems[0] and "b.wav" in problems[0]


def test_a_missing_file_is_a_problem_not_a_pass(tmp_path):
    rows = _rows(("gone.wav", 1, "Speaker-1", "test"))
    assert ev.check_hash_disjoint(rows, tmp_path)


# --- the CLI ---------------------------------------------------------------------------

def _write_set(root, rows, contents=None):
    with (root / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filepath", "label", "speaker_id", "split", "orig_sr", "orig_channels", "duration_sec"])
        for i, (f, label, spk, split, sr) in enumerate(rows):
            (root / f).write_bytes((contents or {}).get(f, f"audio-{i}".encode()))
            w.writerow([f, label, spk, split, sr, 1, 5.0])
    return root / "manifest.csv"


CLEAN = [
    ("t1.wav", 1, "Speaker-1", "train", 16000),
    ("t2.wav", 0, "Speaker-1", "train", 16000),
    ("e1.wav", 1, "Speaker-2", "test", 16000),
    ("e2.wav", 1, "Speaker-2", "test", 44100),
    ("e3.wav", 0, "Speaker-3", "test", 16000),
    ("e4.wav", 0, "Speaker-3", "test", 44100),
]
FAKE_SCORES = {"e1.wav": 0.1, "e2.wav": 0.2, "e3.wav": 0.9, "e4.wav": 0.8}


def _fake_scorer(path):
    return FAKE_SCORES.get(path.name)


def test_cli_exits_2_and_scores_nothing_on_speaker_leakage(tmp_path):
    rows = CLEAN + [("leak.wav", 0, "Speaker-1", "test", 16000)]
    manifest = _write_set(tmp_path, rows)
    scored = []
    code = ev.main(["--manifest", str(manifest), "--out", str(tmp_path / "r.json")],
                   scorer=lambda p: scored.append(p) or 0.5)
    assert code == 2
    assert scored == [], "must not score a leaky split"
    assert not (tmp_path / "r.json").exists()


def test_cli_exits_2_on_identical_bytes_across_splits(tmp_path):
    manifest = _write_set(tmp_path, CLEAN, contents={"t1.wav": b"dup", "e1.wav": b"dup"})
    code = ev.main(["--manifest", str(manifest), "--out", str(tmp_path / "r.json")],
                   scorer=_fake_scorer)
    assert code == 2


def test_cli_reports_eer_counts_and_per_sample_rate_breakdown(tmp_path):
    manifest = _write_set(tmp_path, CLEAN)
    out = tmp_path / "r.json"
    assert ev.main(["--manifest", str(manifest), "--out", str(out)], scorer=_fake_scorer) == 0
    report = json.loads(out.read_text())
    test = report["splits"]["test"]
    assert test["eer"] == 0.0
    assert test["n_bonafide"] == 2 and test["n_spoof"] == 2
    assert set(test["by_orig_sr"]) == {"16000", "44100"}
    assert report["leakage"] == {"speaker_overlap": [], "hash_overlap": []}
    assert report["tdcf_asv_assumption"] == "ideal"


def test_cli_exits_3_when_nothing_could_be_scored(tmp_path):
    """A missing checkpoint scores every file as None. That is a failure, not an EER."""
    manifest = _write_set(tmp_path, CLEAN)
    assert ev.main(["--manifest", str(manifest), "--out", str(tmp_path / "r.json")],
                   scorer=lambda _p: None) == 3


def test_limit_keeps_both_classes_even_when_the_manifest_is_sorted_by_label(tmp_path):
    """IFD lists every bonafide file before any deepfake; a plain head(N) scores one class."""
    rows = [("t1.wav", 1, "Speaker-1", "train", 16000)]
    rows += [(f"b{i}.wav", 1, "Speaker-2", "test", 16000) for i in range(5)]
    rows += [(f"s{i}.wav", 0, "Speaker-3", "test", 16000) for i in range(5)]
    manifest = _write_set(tmp_path, rows)
    out = tmp_path / "r.json"
    scores = lambda p: 0.1 if p.name.startswith("b") else 0.9  # noqa: E731
    assert ev.main(["--manifest", str(manifest), "--out", str(out), "--limit", "2"], scorer=scores) == 0
    test = json.loads(out.read_text())["splits"]["test"]
    assert (test["n_bonafide"], test["n_spoof"]) == (2, 2)
