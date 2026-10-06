"""Item 13: telephony augmentation must actually apply the condition it claims.

`codec.degrade` falls back to plain 8 kHz resampling when an encoder is missing and only
logs it. For enrollment that is a reasonable degradation; for building an evaluation or
training set it is a silent lie — a file labelled AMR-NB that is not. `augment` refuses
instead, and every check below observes the *output*, not the command line.
"""

from __future__ import annotations

import csv
import wave

import numpy as np
import pytest

from audio_ml import augment
from audio_ml.eval import eval_spoof

SR = 16_000


def _write_wav(path, samples, sr=SR):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def _read_wav(path):
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768.0, w.getframerate()


def _tones(seconds=2.0):
    t = np.arange(int(SR * seconds)) / SR
    return 0.3 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 6000 * t)


def _band_db(x, sr, lo, hi):
    spec = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return 10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-12)


# --- codecs ------------------------------------------------------------------------

@pytest.mark.parametrize("codec, probed", [
    ("g711_ulaw", "pcm_mulaw"), ("g711_alaw", "pcm_alaw"), ("amr_nb", "amr_nb"),
])
def test_codec_is_really_applied_and_band_limited(tmp_path, codec, probed):
    src = _write_wav(tmp_path / "in.wav", _tones())
    info = augment.apply_codec(src, tmp_path / "out.wav", codec)

    assert info["intermediate_codec"] == probed
    assert info["intermediate_sample_rate"] == 8000
    out, sr = _read_wav(tmp_path / "out.wav")
    assert sr == SR, "output must be 16 kHz for detect_spoof"
    # 6 kHz cannot survive an 8 kHz channel; 440 Hz must.
    assert _band_db(out, sr, 5500, 6500) < _band_db(out, sr, 300, 600) - 30


def test_a_missing_encoder_is_an_error_not_a_fallback(tmp_path, monkeypatch):
    monkeypatch.setitem(augment.CODECS, "amr_nb", ["-acodec", "libdoesnotexist"])
    src = _write_wav(tmp_path / "in.wav", _tones())
    with pytest.raises(augment.AugmentError):
        augment.apply_codec(src, tmp_path / "out.wav", "amr_nb")
    assert not (tmp_path / "out.wav").exists()


def test_an_unknown_codec_is_an_error(tmp_path):
    src = _write_wav(tmp_path / "in.wav", _tones())
    with pytest.raises(augment.AugmentError):
        augment.apply_codec(src, tmp_path / "out.wav", "opus_at_6k")


# --- noise --------------------------------------------------------------------------

def _snr_db(clean, noisy):
    noise = noisy - clean
    return 10 * np.log10(np.mean(clean ** 2) / np.mean(noise ** 2))


@pytest.mark.parametrize("kind", ["white", "pink"])
@pytest.mark.parametrize("snr", [0.0, 10.0, 20.0])
def test_noise_lands_at_the_requested_snr(kind, snr):
    clean = _tones()
    noisy = augment.add_noise(clean, snr, np.random.default_rng(0), kind=kind)
    assert _snr_db(clean, noisy) == pytest.approx(snr, abs=0.5)


def test_pink_noise_has_more_low_than_high_frequency_energy():
    silence = np.zeros(SR * 2)
    silence[::400] = 1e-3  # a non-silent reference so a level exists
    noise = augment.add_noise(silence, 0.0, np.random.default_rng(1), kind="pink") - silence
    assert _band_db(noise, SR, 100, 500) > _band_db(noise, SR, 4000, 4400) + 6


def test_noise_is_reproducible_from_the_seed():
    clean = _tones()
    a = augment.add_noise(clean, 10.0, np.random.default_rng(7))
    b = augment.add_noise(clean, 10.0, np.random.default_rng(7))
    assert np.array_equal(a, b)


def test_noise_from_a_directory_is_used(tmp_path):
    _write_wav(tmp_path / "hum.wav", 0.5 * np.sin(2 * np.pi * 50 * np.arange(SR * 3) / SR))
    clean = _tones()
    noisy = augment.add_noise(clean, 5.0, np.random.default_rng(0), noise_dir=tmp_path)
    added = noisy - clean
    assert _band_db(added, SR, 40, 60) > _band_db(added, SR, 1000, 8000) + 20


def test_silent_input_is_an_error_not_a_divide_by_zero():
    with pytest.raises(augment.AugmentError):
        augment.add_noise(np.zeros(SR), 10.0, np.random.default_rng(0))


# --- the CLI -------------------------------------------------------------------------

def _toy_set(root):
    rows = [
        ("Speaker-1/Bonafides/a.wav", 1, "Speaker-1", "train"),
        ("Speaker-2/Bonafides/b.wav", 1, "Speaker-2", "test"),
        ("Speaker-3/Deepfakes/c.wav", 0, "Speaker-3", "test"),
    ]
    with (root / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filepath", "label", "speaker_id", "split", "orig_sr", "orig_channels", "duration_sec"])
        for i, (f, label, spk, split) in enumerate(rows):
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            _write_wav(root / f, _tones(1.0) * (0.5 + 0.1 * i))
            w.writerow([f, label, spk, split, 44100, 1, 1.0])
    return root / "manifest.csv"


def test_cli_writes_a_manifest_that_keeps_splits_and_passes_the_leakage_checks(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _toy_set(src)
    out = tmp_path / "aug"
    code = augment.main(["--manifest", str(manifest), "--out", str(out),
                         "--conditions", "g711_ulaw", "amr_nb+noise10", "--seed", "3"])
    assert code == 0

    rows = eval_spoof.load_manifest(out / "manifest.csv")
    assert len(rows) == 3 * 2
    by_source = {}
    with (out / "manifest.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            by_source.setdefault(r["source_filepath"], set()).add((r["split"], r["speaker_id"], r["label"]))
            assert r["condition"] in {"g711_ulaw", "amr_nb+noise10"}
            assert len(r["source_sha256"]) == 64
            assert (out / r["filepath"]).is_file()
    assert all(len(v) == 1 for v in by_source.values()), "an augmented copy changed split or label"
    assert eval_spoof.check_speaker_disjoint(rows) == []
    assert eval_spoof.check_hash_disjoint(rows, out) == []


def test_cli_can_restrict_to_some_splits(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _toy_set(src)
    out = tmp_path / "aug"
    assert augment.main(["--manifest", str(manifest), "--out", str(out),
                         "--conditions", "g711_alaw", "--splits", "test"]) == 0
    assert {r.split for r in eval_spoof.load_manifest(out / "manifest.csv")} == {"test"}


def test_cli_rejects_a_malformed_condition(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _toy_set(src)
    assert augment.main(["--manifest", str(manifest), "--out", str(tmp_path / "aug"),
                         "--conditions", "noiseloud"]) == 1


def _dup_set(root):
    """Same bytes at two paths, one in train and one in test: a cross-split leak."""
    clip = _tones(1.0) * 0.5
    with (root / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filepath", "label", "speaker_id", "split", "orig_sr", "orig_channels", "duration_sec"])
        for f, spk, split in [("A/x.wav", "Speaker-1", "train"), ("B/y.wav", "Speaker-2", "test")]:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            _write_wav(root / f, clip)
            w.writerow([f, 1, spk, split, 16000, 1, 1.0])
    return root / "manifest.csv"


@pytest.mark.parametrize("condition", ["g711_ulaw", "noise20", "amr_nb+noise20"])
def test_a_cross_split_duplicate_is_still_caught_after_augmentation(tmp_path, condition):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _dup_set(src)
    assert eval_spoof.check_hash_disjoint(eval_spoof.load_manifest(manifest), src) != []
    out = tmp_path / "aug"
    assert augment.main(["--manifest", str(manifest), "--out", str(out),
                         "--conditions", condition]) == 0
    rows = eval_spoof.load_manifest(out / "manifest.csv")
    assert eval_spoof.check_hash_disjoint(rows, out) != [], "noise hid a train/test leak"


@pytest.mark.parametrize("breakage", ["unreadable", "missing"])
def test_a_failed_run_leaves_no_manifest_behind(tmp_path, breakage):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _toy_set(src)
    out = tmp_path / "aug"
    assert augment.main(["--manifest", str(manifest), "--out", str(out),
                         "--conditions", "g711_ulaw"]) == 0
    assert (out / "manifest.csv").is_file()

    broken = src / "Speaker-2/Bonafides/b.wav"
    if breakage == "unreadable":
        broken.write_bytes(b"not audio")
    else:
        broken.unlink()
    try:
        code = augment.main(["--manifest", str(manifest), "--out", str(out),
                             "--conditions", "g711_ulaw", "noise10"])
    except Exception:
        code = None
    assert code != 0
    # Neither a partial manifest nor the previous run's (whose files were just overwritten).
    assert not (out / "manifest.csv").exists()
