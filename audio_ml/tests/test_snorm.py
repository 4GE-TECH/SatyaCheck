"""Tests for `audio_ml.verify.snorm` — s-normalisation against a background cohort.

CLAUDE.md: "Score normalisation is not optional. The published SASV result
(EER 23.83% → 1.71% from plain score-sum, no training) holds **only** with
normalised scores."

It also has to be a normalisation that *works*. The defect these tests were written
for: `data/cohort/cohort.npy` ships with row norms of 183–263 rather than 1.0, and
`snorm` computes `np.dot(cohort, probe_emb)` on the documented assumption that both
sides are unit length. With rows ~200x too long the cohort statistics land on the
wrong scale, the z-score collapses toward zero, and `sigmoid(z) ≈ 0.5` — under
`SPEAKER_UNKNOWN_FLOOR` (0.60).

The consequence is the worst kind: a genuine, correctly enrolled speaker comes back
`unknown`. Not an error, not a log line — a legitimate verdict that means "no
enrolled person is close". Enroll yourself, screen yourself, get *unverified*.

The `if raw > 0.7 and norm < 0.5: return raw` guard inside `snorm` does not catch
it, because ~0.504 is not below 0.5.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_ml.verify import snorm


def _unit(rng: np.random.Generator, n: int, dim: int = 192) -> np.ndarray:
    """`n` random unit-length embeddings, the shape ECAPA actually produces."""
    vectors = rng.normal(size=(n, dim)).astype(np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _probe_at(rng: np.random.Generator, enrolled: np.ndarray, cosine: float) -> np.ndarray:
    """A unit probe at an exact cosine to `enrolled`.

    Adding scaled Gaussian noise does not work here: in 192 dimensions a noise
    vector at scale 0.15 has norm ~2.1 and swamps the unit signal, which is how
    the first draft of these tests ended up asserting on a cosine of 0.475. Build
    the angle explicitly instead — decompose into the enrolled direction plus an
    orthogonal component.
    """
    perpendicular = rng.normal(size=enrolled.shape).astype(np.float32)
    perpendicular -= np.dot(perpendicular, enrolled) * enrolled
    perpendicular /= np.linalg.norm(perpendicular)
    probe = cosine * enrolled + np.sqrt(1.0 - cosine**2) * perpendicular
    return (probe / np.linalg.norm(probe)).astype(np.float32)


def test_snorm_is_invariant_to_cohort_row_scale():
    """The property that was violated, stated directly.

    A cohort is a set of *directions* — background speakers to measure against.
    Multiplying every row by 200 changes no speaker's identity, so it must not
    change the score. This fails on an implementation that dots against raw rows.
    """
    rng = np.random.default_rng(0)
    cohort = _unit(rng, 40)
    probe, enrolled = _unit(rng, 2)
    raw = float(np.dot(probe, enrolled))

    on_unit = snorm(raw, probe, enrolled, cohort)
    on_scaled = snorm(raw, probe, enrolled, cohort * 200.0)

    assert on_unit == pytest.approx(on_scaled, abs=1e-4), (
        "scaling the cohort rows changed the score; snorm is dotting against "
        "un-normalised vectors"
    )


def test_snorm_handles_the_real_cohort_scale_that_shipped():
    """Rows at the magnitude actually found in data/cohort/cohort.npy."""
    rng = np.random.default_rng(1)
    cohort = _unit(rng, 40) * rng.uniform(183.0, 264.0, size=(40, 1))
    enrolled = _unit(rng, 1)[0]

    # A genuine match, at the cosine A measured for a real genuine speaker (0.9464).
    probe = _probe_at(rng, enrolled, 0.9464)
    raw = float(np.dot(probe, enrolled))

    result = snorm(raw, probe, enrolled, cohort)

    assert result > 0.5, (
        f"a raw cosine of {raw:.4f} normalised to {result:.4f} — a clear match "
        "pushed to the neutral floor, which reads as 'unknown'"
    )


def test_snorm_separates_a_genuine_speaker_from_an_impostor():
    """Ordering is the whole point: genuine must outscore impostor."""
    rng = np.random.default_rng(2)
    cohort = _unit(rng, 40) * 200.0
    enrolled = _unit(rng, 1)[0]

    # A's measured pair: 0.9464 genuine against 0.7631 for a cloned voice.
    genuine = _probe_at(rng, enrolled, 0.9464)
    impostor = _probe_at(rng, enrolled, 0.7631)

    genuine_score = snorm(float(np.dot(genuine, enrolled)), genuine, enrolled, cohort)
    impostor_score = snorm(float(np.dot(impostor, enrolled)), impostor, enrolled, cohort)

    assert genuine_score > impostor_score


def test_snorm_returns_raw_when_the_cohort_is_too_small():
    """Under five background speakers there is no distribution to normalise against.

    Falling back to the raw cosine is right; inventing statistics from three
    samples is not.
    """
    rng = np.random.default_rng(3)
    probe, enrolled = _unit(rng, 2)
    raw = 0.42

    assert snorm(raw, probe, enrolled, _unit(rng, 3)) == pytest.approx(raw)


def test_snorm_never_raises_on_a_malformed_cohort():
    """CLAUDE.md rule 5. A corrupt artefact degrades the verdict, never the request."""
    rng = np.random.default_rng(4)
    probe, enrolled = _unit(rng, 2)

    for broken in (
        np.zeros((40, 192), dtype=np.float32),      # every row degenerate
        np.zeros((10, 7), dtype=np.float32),        # wrong dimension
        np.full((40, 192), np.nan, dtype=np.float32),
    ):
        result = snorm(0.5, probe, enrolled, broken)
        assert isinstance(result, float)
        assert not np.isnan(result), "a broken cohort produced NaN rather than a fallback"


def test_snorm_output_stays_in_range():
    """Downstream compares against thresholds in [0, 1]; a sigmoid must deliver that."""
    rng = np.random.default_rng(5)
    cohort = _unit(rng, 40) * 200.0
    probe, enrolled = _unit(rng, 2)

    for raw in (-1.0, -0.5, 0.0, 0.5, 0.99, 1.0):
        result = snorm(raw, probe, enrolled, cohort)
        assert 0.0 <= result <= 1.0, f"raw={raw} produced {result}, outside [0, 1]"
