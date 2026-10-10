"""SatyaCheck — Orchestrator

Runs the three independent branches concurrently and fuses results.

Block 0/1: All branches return mock/neutral contracts.
Block 2: Swap in real imports one at a time using USE_REAL_* flags in config.py.

NEVER call this module from audio_ml or nlp_rag — only server/ uses it.
C owns this file.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

import config
from contracts import (
    AntiSpoofResult,
    CallerMetadata,
    FusionWeights,
    OperatingMode,
    QualityGateResult,
    ReasonCode,
    RetrievedPlaybook,
    ScreeningResponse,
    ScriptAnalysisResult,
    SeverityLevel,
    SignalType,
    SpeakerVerdict,
    SpeakerVerificationResult,
    TranscriptResult,
    TrustBand,
    TrustScoreResult,
    ChallengeQuestion,
    ThreatLabel,
)
from server.audio_ingest import AudioChunk, IngestedAudio

log = logging.getLogger("satyacheck.orchestrator")


# ── Branch stubs (active until USE_REAL_* flags are True) ────────────

def _mock_speaker_branch(
    wav_path: str,
    owner_id: Optional[str] = None,
) -> SpeakerVerificationResult:
    """Mock speaker branch — returns neutral UNKNOWN result."""
    return SpeakerVerificationResult.neutral()


def _mock_spoof_branch(wav_path: str) -> AntiSpoofResult:
    """Mock spoof branch — an *abstention*, not a clean bill of health.

    NOTE: returns risk=0.0 WITH available=False, the same convention B uses for the
    text branch. The flag is the whole point. In a weighted sum `risk=0.0` does not
    read as "no opinion", it reads as "definitely authentic" and raises trust — so a
    branch that never ran would hand every call its full 0.35 weight of innocence.
    Fusion drops the weight and renormalises instead.
    """
    result = AntiSpoofResult.neutral()
    result.details["available"] = False
    return result


def _mock_nlp_branch(
    wav_path: Optional[str],
    waveform: list[float],
) -> tuple[TranscriptResult, ScriptAnalysisResult]:
    """Mock NLP branch — returns abstention sentinel (details['available']=False).
    
    NOTE: returns risk=0.0 WITH available=False so fusion can distinguish
    this from a genuinely benign call (which also has risk=0.0 but available=True).
    """
    abstain = ScriptAnalysisResult.neutral()
    abstain.details["available"] = False
    return TranscriptResult.empty(), abstain


# ── Real branch wrappers (activated in Block 2) ──────────────────────

def _speaker_candidates(owner_id: Optional[str]) -> tuple[list[dict], list]:
    """This owner's enrolled voiceprints and flagged scam voices, for verify_speaker: the
    database's, plus — only while LEGACY_NPZ_FALLBACK is on — legacy .npz people the
    database lacks. With no owner, nobody: identity abstains (logged).
    Raises if the database cannot be read; the caller degrades the branch."""
    from server import database, voiceprint_store

    if not owner_id:
        log.warning("[speaker] no owner for this screening; comparing against nobody")
        return [], []
    with database.owner_session(owner_id) as db:
        candidates = voiceprint_store.get_candidates(db, owner_id)
        flagged = voiceprint_store.get_flagged(db, owner_id)
    if config.LEGACY_NPZ_FALLBACK:
        from audio_ml.api import legacy_candidates

        known = {c["person_id"] for c in candidates}
        legacy = [c for c in legacy_candidates() if c["person_id"] not in known]
        if legacy:
            log.info(f"[speaker] LEGACY_NPZ_FALLBACK adds {len(legacy)} person(s) from .npz files "
                     f"not yet in the database (run scripts/import_npz_voiceprints.py)")
        candidates += legacy
    return candidates, flagged


def _real_speaker_branch(
    wav_path: str,
    owner_id: Optional[str] = None,
) -> SpeakerVerificationResult:
    try:
        from audio_ml.api import verify_speaker
        from server.audio_adapter import to_speaker_result
        from server.capacity import inference_slot

        candidates, flagged = _speaker_candidates(owner_id)
        with inference_slot("speaker"):
            signal = verify_speaker(wav_path, candidates=candidates, flagged=flagged)
        return to_speaker_result(signal)
    except Exception as e:
        log.error(f"[speaker] Real branch failed, falling back to neutral: {e}")
        return SpeakerVerificationResult.neutral()


def _real_spoof_branch(wav_path: str) -> AntiSpoofResult:
    try:
        from audio_ml.api import detect_spoof
        from server.audio_adapter import to_spoof_result
        from server.capacity import inference_slot

        with inference_slot("anti-spoof"):
            signal = detect_spoof(wav_path)
        return to_spoof_result(signal)
    except Exception as e:
        log.error(f"[spoof] Real branch failed, falling back to neutral: {e}")
        # available=False, so fusion renormalises rather than reading the 0.0 risk
        # as evidence of authenticity.
        result = AntiSpoofResult.neutral()
        result.details["available"] = False
        return result


def _real_nlp_branch(
    wav_path: Optional[str],
    waveform: list[float],
) -> tuple[TranscriptResult, ScriptAnalysisResult]:
    try:
        from nlp_rag.api import transcribe, analyze_script
        from server.capacity import inference_slot

        with inference_slot("asr"):
            transcript = transcribe(wav_path or waveform)
        with inference_slot("intent"):
            script = analyze_script(transcript)
        return transcript, script
    except Exception as e:
        log.error(f"[nlp] Real branch failed, falling back to neutral: {e}")
        abstain = ScriptAnalysisResult.neutral()
        abstain.details["available"] = False
        return TranscriptResult.empty(), abstain


# ── Fusion ────────────────────────────────────────────────────────────

def _compute_fusion(
    speaker: SpeakerVerificationResult,
    spoof: AntiSpoofResult,
    script: ScriptAnalysisResult,
    owner_id: Optional[str] = None,
) -> TrustScoreResult:
    """
    Intent-gated, mode-aware fusion. The arithmetic is `audio_ml.fusion_core.fuse_risk`,
    the one implementation the scenario matrix also runs:

    intent   = max(script.risk, speaker.risk if verdict == mismatch else 0.0)
    r_cm_eff = spoof.risk * (CM_FLOOR + (1 - CM_FLOOR) * intent)
    combined = sum(w_i * r_i) renormalised by active weight sum
    combined = max(combined, floors)   intent sufficiency, flagged voice, replay
    trust    = (1 - combined) * 100

    Branch unavailability (details['available'] = False on either branch):
      - that branch's weight is excluded and the rest are renormalised, so the
        live branches still span the full 0–1 risk range.
      - when text is unavailable, intent for the CM gate becomes
        max(0.5, identity_risk_for_gate) — neutral, never 0.0 — and no intent
        floor applies.
      - the identity branch always participates. In authority_check it abstains by
        carrying a neutral 0.5 at reduced weight.

    The authenticity input blends the peak back in for `partial_synthetic`: the median
    alone hides a hybrid attack.

    Mode selection:
      unknown → authority_check (speaker abstains, weights shift)
      otherwise → identity_check
    """
    from audio_ml.api import authenticity_base, fuse_risk

    verdict = speaker.verdict
    is_identity_check = verdict != SpeakerVerdict.UNKNOWN

    r_asv = speaker.risk
    r_cm = spoof.risk
    r_text = script.risk

    # B writes details["available"] = False on every abstention path, and the spoof
    # branch follows the same convention. risk=0.0 alone is ambiguous — a genuine
    # benign call also has risk 0.0.
    text_available: bool = script.details.get("available", True) is not False
    cm_available: bool = spoof.details.get("available", True) is not False
    if not text_available:
        log.warning(
            "[fusion] text branch unavailable (details['available']=False) — "
            "renormalising weights, CM gate intent → neutral 0.5"
        )
    if not cm_available:
        log.warning(
            "[fusion] anti-spoof branch unavailable (details['available']=False) — "
            "dropping w_cm and renormalising"
        )

    core = fuse_risk(
        SpeakerVerdict(verdict).value,
        r_asv,
        authenticity_base(r_cm, spoof.peak_score, partial=spoof.details.get("verdict") == "partial_synthetic"),
        r_text,
        text_available=text_available,
        cm_available=cm_available,
        replay=speaker.is_replay,
        flagged_hits=int(speaker.details.get("flagged_voice_hits") or 0),
    )
    if core.floors:
        log.info(f"[fusion] floor(s) raised risk to {core.risk}: {core.floors}")
    mode = OperatingMode(core.mode)
    r_cm_eff = core.r_cm_eff
    combined_risk = core.risk
    # The weights that actually contributed, renormalised, so the evidence panel and the
    # incident report agree with the arithmetic.
    w_asv, w_cm, w_text = core.weights["asv"], core.weights["cm"], core.weights["text"]

    trust_score = config.risk_to_trust_score(combined_risk)
    band = config.risk_to_band(combined_risk, is_authority_check=not is_identity_check)

    reason_codes = _build_reason_codes(speaker, spoof, script, mode, r_cm_eff)
    recommended_actions = _build_actions(band, verdict, script)

    # Fetch challenge question from NLP if identity is in question
    challenge_question: Optional[ChallengeQuestion] = None
    if verdict in (SpeakerVerdict.MISMATCH, SpeakerVerdict.UNKNOWN) and r_text > 0.3:
        from server.database import current_owner_var

        token = current_owner_var.set(owner_id)   # the lookup only sees this owner's people
        try:
            from nlp_rag.api import challenge_question as cq_fn
            target_id = speaker.matched_person_id or speaker.claimed_person_id
            challenge_question = cq_fn(target_id, band=band)
        except Exception:
            pass
        finally:
            current_owner_var.reset(token)

    return TrustScoreResult(
        trust_score=trust_score,
        risk_score=combined_risk,
        band=band,
        mode=mode,
        weights_used=FusionWeights(asv_weight=w_asv, cm_weight=w_cm, text_weight=w_text),
        identity_risk=r_asv,
        authenticity_risk=r_cm,
        # An abstaining branch contributed nothing; reporting its gated risk would put
        # a "probability the audio is synthetic" on screen that fusion did not use.
        authenticity_risk_effective=round(r_cm_eff, 4) if cm_available else 0.0,
        intent_risk=r_text,
        reason_codes=reason_codes,
        recommended_actions=recommended_actions,
        challenge_question=challenge_question,
        vernacular_warning=_get_vernacular_warning(band, script),
        threat_label=_threat_label(band, script),
    )


_LABELLED_BANDS = (TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK)


def _threat_label(band: TrustBand, script: ScriptAnalysisResult) -> Optional[ThreatLabel]:
    """The intent branch's sector/threat, shown only beside a warning (item 10).

    B reports the cited family whatever the risk; fusion owns the band. A benign call
    that loosely resembles a KYC script must not read "banking / KYC update fraud" under
    a calm verdict, and a label with no cited playbook has nothing behind it.
    """
    if band not in _LABELLED_BANDS or not script.playbooks:
        return None
    raw = script.details.get("threat_label")
    if not raw:
        return None
    try:
        return ThreatLabel(**raw)
    except Exception as e:
        log.warning(f"[fusion] dropping malformed threat_label {raw!r}: {e}")
        return None


_SOURCE_WORDS = {"user": "you said", "caller_id": "caller ID shows", "transcript": "the caller said"}


def _claim_phrase(check: dict) -> str:
    """'you said Ramesh; the caller said Papa' — who claimed what, in plain words."""
    return "; ".join(f"{_SOURCE_WORDS.get(c['source'], c['source'])} "
                     f"{', '.join(c['people']) if c['source'] != 'transcript' else repr(c['said'])}"
                     for c in check.get("claims", []))


def _identity_codes(speaker: SpeakerVerificationResult) -> list[ReasonCode]:
    """Identity evidence, including who the caller claimed to be (server/claims.py).
    Worded as levels and next steps, never as an accusation."""
    check = speaker.details.get("claim_check") or {}
    outcome = check.get("outcome")
    t = check.get("thresholds") or {"match": config.SPEAKER_MATCH_THRESHOLD, "low": config.SPEAKER_MATCH_THRESHOLD}
    person = check.get("person") or speaker.matched_person_name or "the claimed contact"
    claimed_by = _claim_phrase(check)
    cosine = f"cosine {speaker.raw_score:.2f}"
    codes: list[ReasonCode] = []

    if speaker.verdict == SpeakerVerdict.MATCH:
        corroborated = f" ({claimed_by})" if outcome == "match" and claimed_by else ""
        codes.append(ReasonCode(
            code="RC_SPEAKER_VERIFIED", signal=SignalType.IDENTITY, value=cosine, threshold=f"≥ {t['match']}",
            explanation=f"Voice closely matches the enrolled voiceprint for "
                        f"{speaker.matched_person_name or 'an enrolled contact'}{corroborated}.",
            severity=SeverityLevel.INFO))
    elif speaker.verdict == SpeakerVerdict.MISMATCH:
        codes.append(ReasonCode(
            code="RC_SPEAKER_MISMATCH", signal=SignalType.IDENTITY, value=cosine, threshold=f"< {t['low']}",
            explanation=f"The caller is presented as {person} ({claimed_by}), but the voice does not match "
                        f"{person}'s enrolled voiceprint. Call {person} back on a number you already have.",
            citation_title="ECAPA-TDNN Speaker Verification", severity=SeverityLevel.HIGH))
    else:
        codes.append(ReasonCode(
            code="RC_SPEAKER_UNKNOWN", signal=SignalType.IDENTITY, value="No enrolled match found", threshold="N/A",
            explanation="The voice is not a confirmed match for any enrolled contact. Authority-check mode active.",
            severity=SeverityLevel.INFO))

    if outcome == "inconclusive":
        codes.append(ReasonCode(
            code="RC_CLAIM_INCONCLUSIVE", signal=SignalType.IDENTITY, value=cosine,
            threshold=f"{t['low']}-{t['match']}",
            explanation=f"The voice is close to {person} ({claimed_by}) but not close enough to confirm. "
                        f"Ask the challenge question, or call {person} back on a number you already have.",
            severity=SeverityLevel.MEDIUM))
    elif outcome == "conflict":
        codes.append(ReasonCode(
            code="RC_CLAIM_CONFLICT", signal=SignalType.IDENTITY, value=claimed_by, threshold="N/A",
            explanation="The claims about who is calling do not agree, so the voice was not checked against "
                        "either. Verify by calling back on a number you already have.",
            severity=SeverityLevel.MEDIUM))
    elif outcome == "ambiguous":
        codes.append(ReasonCode(
            code="RC_CLAIM_AMBIGUOUS", signal=SignalType.IDENTITY, value=claimed_by, threshold="N/A",
            explanation="That name fits more than one of your contacts and the voice matches neither. "
                        "Pick who is calling to check the voice against them.",
            severity=SeverityLevel.LOW))
    elif outcome == "unconfirmed":
        codes.append(ReasonCode(
            code="RC_CLAIM_UNCONFIRMED", signal=SignalType.IDENTITY, value=cosine, threshold=f"≥ {t['match']}",
            explanation=f"The number is saved for {person}, but the voice does not match {person}. Numbers can "
                        f"be spoofed or shared, so this is not proof either way.",
            severity=SeverityLevel.LOW))
    elif outcome == "no_voiceprint":
        codes.append(ReasonCode(
            code="RC_CLAIM_NO_VOICEPRINT", signal=SignalType.IDENTITY, value=claimed_by, threshold="N/A",
            explanation="The caller is presented as one of your contacts, but that contact has no voiceprint "
                        "enrolled, so the voice could not be checked.",
            severity=SeverityLevel.INFO))
    return codes


def _build_reason_codes(
    speaker: SpeakerVerificationResult,
    spoof: AntiSpoofResult,
    script: ScriptAnalysisResult,
    mode: OperatingMode,
    r_cm_eff: float,
) -> list[ReasonCode]:
    """Assemble ordered list of reason codes from all three branches."""
    codes: list[ReasonCode] = []

    # ── Identity ──────────────────────────────────────────────────────
    # `value`/`threshold` quote the raw cosine and the claim threshold actually applied
    # (config.CLAIM_THRESHOLDS for the measured channel), never the s-norm score against
    # ASV_MATCH_THRESHOLD (1.20): "s-norm 0.95 > 1.2" is not evidence a reader can check.
    # The s-normalised score is still carried in `speaker.norm_score`.
    codes.extend(_identity_codes(speaker))

    if speaker.is_replay:
        codes.append(ReasonCode(
            code="RC_REPLAY_SUSPECTED",
            signal=SignalType.IDENTITY,
            value=f"Cosine {speaker.raw_score:.3f}",
            threshold=f"> {config.REPLAY_COSINE_THRESHOLD}",
            explanation="Anomalously high voice similarity suggests a recorded clip is being replayed rather than live speech.",
            severity=SeverityLevel.CRITICAL,
        ))

    # ── Authenticity ──────────────────────────────────────────────────
    cm_available = spoof.details.get("available", True) is not False
    if (not cm_available and spoof.details.get("abstain_reason") == "out_of_distribution"
            and spoof.details.get("ood_reason") == "narrowband_channel"):
        hf_ratio = spoof.details.get("hf_ratio")
        codes.append(ReasonCode(
            code="RC_SPOOF_OUT_OF_DOMAIN",
            signal=SignalType.AUTHENTICITY,
            value=(f"Phone-band audio: {hf_ratio:.3%} of power above 4.5 kHz"
                   if hf_ratio is not None else "Phone-band audio"),
            threshold=f">= {config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD:.3%}",
            explanation=(
                "This audio came through a phone line (an 8 kHz channel such as a mobile or "
                "landline call), which the synthetic-voice detector was not trained on, so "
                "its score was not used. The call was scored on identity and intent only."
            ),
            severity=SeverityLevel.INFO,
        ))
    elif not cm_available and spoof.details.get("abstain_reason") == "out_of_distribution":
        codes.append(ReasonCode(
            code="RC_SPOOF_OUT_OF_DOMAIN",
            signal=SignalType.AUTHENTICITY,
            value=f"{spoof.details.get('ood_score') or 0:.0%} of windows out of domain",
            threshold=f"< {config.SPOOF_OOD_MAX_WINDOW_FRACTION:.0%}",
            explanation=(
                "This audio is unlike anything the synthetic-voice detector was trained on "
                "(often phone-network compression), so its score was not used. The call was "
                "scored on identity and intent only."
            ),
            severity=SeverityLevel.INFO,
        ))
    elif not cm_available:
        # Say nothing was measured. The old fall-through emitted RC_AUDIO_BONAFIDE
        # here — "Audio appears to be organic human speech" — for a branch that
        # never ran, which on a cloned-voice clip is a false exoneration printed as
        # evidence.
        codes.append(ReasonCode(
            code="RC_SPOOF_UNAVAILABLE",
            signal=SignalType.AUTHENTICITY,
            value="Not measured",
            threshold="N/A",
            explanation=(
                "Synthetic-speech detection did not run, so this call was scored on "
                "identity and intent only. Absence of a synthetic-voice warning here "
                "is not evidence the voice is genuine."
            ),
            severity=SeverityLevel.INFO,
        ))
    elif spoof.is_synthetic and r_cm_eff > 0.3:
        codes.append(ReasonCode(
            code="RC_SYNTHETIC_VOICE_DETECTED",
            signal=SignalType.AUTHENTICITY,
            value=f"Median {spoof.median_score:.0%} / Peak {spoof.peak_score:.0%} / Run {spoof.max_synth_run_s:.1f}s",
            threshold=f"> {config.CM_SYNTHETIC_THRESHOLD:.0%}",
            explanation="Neural vocoder / voice-cloning artifacts detected in audio spectrogram.",
            citation_title="ASVspoof 2019 Anti-Spoof Challenge",
            severity=SeverityLevel.CRITICAL if spoof.peak_score > 0.85 else SeverityLevel.HIGH,
        ))
    elif spoof.is_synthetic and r_cm_eff <= 0.3:
        codes.append(ReasonCode(
            code="RC_LEGIT_AUTOMATED_VOICE",
            signal=SignalType.AUTHENTICITY,
            value=f"Synthetic prob {spoof.median_score:.0%} (gated by low intent)",
            threshold="Intent-gated",
            explanation="Synthetic speech detected but low scam intent suggests this may be a legitimate automated service (IVR, notification).",
            severity=SeverityLevel.INFO,
        ))
    else:
        codes.append(ReasonCode(
            code="RC_AUDIO_BONAFIDE",
            signal=SignalType.AUTHENTICITY,
            value=f"Synthetic prob {spoof.median_score:.0%}",
            threshold=f"< {config.CM_SYNTHETIC_THRESHOLD:.0%}",
            explanation="No significant synthetic speech artifacts detected. Audio appears to be organic human speech.",
            severity=SeverityLevel.INFO,
        ))

    # ── Intent / Script ───────────────────────────────────────────────
    try:
        from nlp_rag.api import build_reason_codes as nlp_build_rc
        nlp_codes = nlp_build_rc(script)
        if nlp_codes:
            codes.extend(nlp_codes)
    except Exception:
        # Fallback to direct marker/playbook iteration if nlp_rag.api fails
        for marker in script.incriminating_markers[:3]:  # top 3
            codes.append(ReasonCode(
                code=f"RC_{marker.marker_id}",
                signal=SignalType.INTENT,
                value=f'"{marker.matched_text[:60]}"',
                threshold=f"Category: {marker.category}",
                explanation=marker.description,
                severity=SeverityLevel.HIGH if marker.weight > 0.7 else SeverityLevel.MEDIUM,
            ))

        for marker in script.exculpatory_markers[:2]:  # top 2
            codes.append(ReasonCode(
                code=f"RC_{marker.marker_id}",
                signal=SignalType.INTENT,
                value=f'"{marker.matched_text[:60]}"',
                threshold=f"Category: {marker.category}",
                explanation=marker.description,
                severity=SeverityLevel.INFO,
            ))

        for pb in script.playbooks[:2]:  # top 2 citations
            codes.append(ReasonCode(
                code=f"RC_PLAYBOOK_{pb.playbook_id}",
                signal=SignalType.INTENT,
                value=f"RAG similarity {pb.similarity_score:.0%}",
                threshold=f"> {config.RAG_SIMILARITY_THRESHOLD:.0%}",
                explanation=f"Matches known fraud pattern: {pb.title}",
                citation_title=pb.title,
                citation_url=pb.source_url,
                severity=SeverityLevel.HIGH if pb.similarity_score > 0.80 else SeverityLevel.MEDIUM,
            ))

    return codes


def _build_actions(band: TrustBand, verdict: SpeakerVerdict, script: ScriptAnalysisResult) -> list[str]:
    actions: dict[str, list[str]] = {
        TrustBand.VERIFIED: ["No action required. Call verified as genuine enrolled contact."],
        TrustBand.UNVERIFIED: ["Caller is not an enrolled contact. Verify identity before taking any action."],
        TrustBand.CAUTION: [
            "Proceed cautiously — verify identity through a separate channel.",
            "Do not share OTP, PIN, or Aadhaar details.",
        ],
        TrustBand.SUSPICIOUS: [
            "Do NOT transfer money or share financial credentials.",
            "Tell caller you will call back on their registered number.",
            "Alert a family member before taking any action.",
        ],
        TrustBand.HIGH_RISK: [
            "DO NOT transfer money via UPI or any other channel.",
            "Disconnect the call immediately.",
            "Call back the person directly using their saved contact number.",
            "Report to Cyber Crime helpline 1930 if you suspect fraud.",
        ],
        TrustBand.INSUFFICIENT: ["Ask caller to speak clearly on speakerphone for at least 3 seconds and try again."],
    }
    return actions.get(band, ["Use caution."])


def _get_vernacular_warning(
    band: TrustBand,
    script: ScriptAnalysisResult,
) -> Optional[str]:
    """Select the vernacular warning for the *fused* band, not the intent-only band.

    Priority:
      1. B's details['vernacular_warnings'] dict — keyed by band value string.
         B emits all templates so C picks the right one after fusion.
         Until B ships the full table, this key won't be present and we fall
         through to C's own hardcoded strings below.
      2. C's own hardcoded fallback dict — always correct because it uses the
         fused band argument, never the provisional intent-only band.

    This is the E3 fix: analyze_script's provisional band (intent alone) must
    never determine what the protected person hears. Fusion owns the band;
    fusion owns the warning selection.
    """
    # ── Prefer B's full table if already present ──────────────────────
    b_table: dict = script.details.get("vernacular_warnings", {})
    if b_table and isinstance(b_table, dict):
        b_warning = b_table.get(band.value)
        if b_warning:
            return b_warning

    # ── C's own fallback dict (fused band, always safe) ───────────────
    c_warnings = {
        TrustBand.HIGH_RISK:   "सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।",
        TrustBand.SUSPICIOUS:  "सतर्क रहें। इस कॉल में संदिग्ध संकेत हैं। कोई भी कार्रवाई करने से पहले सत्यापित करें।",
        TrustBand.CAUTION:     "कृपया सावधानी बरतें। पैसे भेजने से पहले व्यक्ति की पहचान सुनिश्चित करें।",
    }
    return c_warnings.get(band)


# ── Main orchestration entry point ────────────────────────────────────

async def screen_audio(
    audio: IngestedAudio,
    caller_metadata: Optional[CallerMetadata] = None,
    owner_id: Optional[str] = None,
) -> ScreeningResponse:
    """
    Run quality gate, then dispatch all three branches concurrently, fuse results.

    Returns a complete ScreeningResponse. Never raises.
    """
    t_start = time.perf_counter()
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    # ── Quality gate: early exit ──────────────────────────────────────
    if not audio.quality.passed:
        # Log it. This branch used to return in silence, so a call whose audio was captured,
        # sent and received still produced no server-side trace at all — indistinguishable
        # from audio that never arrived. Every "everything comes back unverified" report
        # lands here, and without this line there is nothing to diagnose it with.
        log.info(
            f"[{session_id}] quality gate REJECTED: {audio.quality.reason} "
            f"(speech={audio.quality.speech_duration_s:.2f}s "
            f"snr={audio.quality.snr_db:.2f}dB "
            f"min_speech={audio.quality.min_speech_threshold_s}s "
            f"min_snr={audio.quality.min_snr_threshold_db}dB)"
        )
        fusion = TrustScoreResult.insufficient(reason=audio.quality.reason or "Quality gate failed")
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return ScreeningResponse(
            session_id=session_id,
            audio_sha256=audio.audio_sha256,
            quality=audio.quality,
            speaker=SpeakerVerificationResult.neutral(),
            spoof=AntiSpoofResult.neutral(),
            transcript=TranscriptResult.empty(),
            script=ScriptAnalysisResult.neutral(),
            fusion=fusion,
            processing_time_ms=elapsed_ms,
            caller_context=caller_metadata,
        )

    # ── Select branch implementations ─────────────────────────────────
    run_speaker = _real_speaker_branch if config.USE_REAL_SPEAKER else _mock_speaker_branch
    run_spoof = _real_spoof_branch if config.USE_REAL_SPOOF else _mock_spoof_branch
    run_nlp = _real_nlp_branch if config.USE_REAL_NLP else _mock_nlp_branch

    # ── Concurrent branch execution ───────────────────────────────────
    loop = asyncio.get_event_loop()
    try:
        speaker_task = loop.run_in_executor(
            None, run_speaker, audio.normalized_wav_path, owner_id
        )
        spoof_task = loop.run_in_executor(
            None, run_spoof, audio.normalized_wav_path
        )
        nlp_task = loop.run_in_executor(
            None, run_nlp, audio.normalized_wav_path, audio.waveform
        )

        speaker_result, spoof_result, (transcript_result, script_result) = await asyncio.gather(
            speaker_task, spoof_task, nlp_task,
            return_exceptions=False,
        )
    except Exception as e:
        log.error(f"Branch execution failed: {e}")
        speaker_result = SpeakerVerificationResult.neutral()
        spoof_result = AntiSpoofResult.neutral()
        transcript_result = TranscriptResult.empty()
        script_result = ScriptAnalysisResult.neutral()

    # ── Identity: who the caller claims to be (server/claims.py) ──────
    speaker_result = await _resolve_identity(speaker_result, spoof_result, transcript_result,
                                             caller_metadata, owner_id)

    # ── Fusion ────────────────────────────────────────────────────────
    fusion = _compute_fusion(speaker_result, spoof_result, script_result, owner_id=owner_id)

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)
    log.info(
        f"[{session_id}] Trust={fusion.trust_score} Band={fusion.band} "
        f"Mode={fusion.mode} ({elapsed_ms}ms)"
    )

    return ScreeningResponse(
        session_id=session_id,
        audio_sha256=audio.audio_sha256,
        quality=audio.quality,
        speaker=speaker_result,
        spoof=spoof_result,
        transcript=transcript_result,
        script=script_result,
        fusion=fusion,
        processing_time_ms=elapsed_ms,
        # Carried, never read: _compute_fusion takes no caller input (CLAUDE.md, FR-17).
        caller_context=caller_metadata,
    )


def _text_abstains() -> ScriptAnalysisResult:
    """No transcript yet: the text branch abstains so fusion renormalises and the CM
    gate reads neutral intent (see `_compute_fusion`), instead of a benign 0.0."""
    abstain = ScriptAnalysisResult.neutral()
    abstain.details["available"] = False
    return abstain


def _spoof_abstains() -> AntiSpoofResult:
    result = AntiSpoofResult.neutral()
    result.details["available"] = False
    return result


def _guarded(branch, name: str, session_id: str, fallback):
    """Run one branch; on any exception log why, with the session, and return `fallback`.

    The real wrappers already catch, but a branch that raises past them must cost that
    branch only — not neutralise the other one, as `screen_audio`'s single gather does.
    """
    def run(wav_path: Optional[str], *args):
        try:
            return branch(wav_path, *args)
        except Exception as e:  # noqa: BLE001 — rule 5: degrade the verdict, not the call
            log.error(f"[{session_id}] {name} branch raised, using its neutral result: "
                      f"{type(e).__name__}: {e}")
            return fallback()
    return run


async def _resolve_identity(
    speaker: SpeakerVerificationResult,
    spoof: AntiSpoofResult,
    transcript: Optional[TranscriptResult],
    caller_metadata: Optional[CallerMetadata],
    owner_id: Optional[str],
) -> SpeakerVerificationResult:
    """The identity verdict from the voice scores and who the caller claims to be
    (server/claims.py). The phone channel is measured from the audio by the anti-spoof
    branch, never taken from caller metadata. Never raises."""
    from server import claims

    try:
        directory = await asyncio.to_thread(claims.load_directory, owner_id) if owner_id else []
        found = claims.gather_claims(directory, caller_metadata, transcript.text if transcript else "")
        narrowband = spoof.details.get("calibration") == "phone_channel"
        return claims.resolve(speaker, found, directory, narrowband=narrowband)
    except Exception as e:  # noqa: BLE001
        log.error(f"[identity] claim resolution failed, using the open-set result: {type(e).__name__}: {e}")
        return claims.resolve(speaker, [], [], narrowband=False)


async def screen_window(
    audio: IngestedAudio,
    transcript: Optional[TranscriptResult],
    script: Optional[ScriptAnalysisResult],
    caller_metadata: Optional[CallerMetadata] = None,
    session_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> ScreeningResponse:
    """Score one streaming window: speaker and anti-spoof only, concurrently.

    Text is not computed here. It comes from the session's transcript worker
    (server/pipeline/transcript_worker.py), which runs beside the acoustic path, so a
    verdict never waits for Whisper. With no transcript yet the text branch abstains
    (`details['available'] = False`) and fusion renormalises over what was measured.

    Same branch selection, quality gate and fusion (`_compute_fusion`) as `screen_audio`.
    `caller_metadata` is explanation only (FR-17) and is never scored. Never raises.
    """
    t_start = time.perf_counter()
    session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
    if transcript is None:
        transcript = TranscriptResult.empty()
    if script is None:
        script = _text_abstains()

    try:
        if not audio.quality.passed:
            log.info(
                f"[{session_id}] quality gate REJECTED window: {audio.quality.reason} "
                f"(speech={audio.quality.speech_duration_s:.2f}s "
                f"snr={audio.quality.snr_db:.2f}dB "
                f"min_speech={audio.quality.min_speech_threshold_s}s "
                f"min_snr={audio.quality.min_snr_threshold_db}dB)"
            )
            return ScreeningResponse(
                session_id=session_id,
                audio_sha256=audio.audio_sha256,
                quality=audio.quality,
                speaker=SpeakerVerificationResult.neutral(),
                spoof=AntiSpoofResult.neutral(),
                # The transcript is the session's (cumulative), not this window's: a
                # quiet final window must not erase it from the final record.
                transcript=transcript,
                script=script,
                fusion=TrustScoreResult.insufficient(
                    reason=audio.quality.reason or "Quality gate failed"),
                processing_time_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )

        run_speaker = _guarded(
            _real_speaker_branch if config.USE_REAL_SPEAKER else _mock_speaker_branch,
            "speaker", session_id, SpeakerVerificationResult.neutral)
        run_spoof = _guarded(
            _real_spoof_branch if config.USE_REAL_SPOOF else _mock_spoof_branch,
            "spoof", session_id, _spoof_abstains)

        speaker_result, spoof_result = await asyncio.gather(
            asyncio.to_thread(run_speaker, audio.normalized_wav_path, owner_id),
            asyncio.to_thread(run_spoof, audio.normalized_wav_path),
        )

        # A start-of-call window shorter than one anti-spoof input is tiled up to it, and
        # on genuine speech that scored P(synthetic) 0.998 (config.STREAM_SPOOF_MIN_WINDOW_S).
        # Its score is kept for the record; the branch abstains so fusion renormalises.
        if (audio.total_duration_s < config.STREAM_SPOOF_MIN_WINDOW_S
                and spoof_result.details.get("available", True) is not False):
            log.info(
                f"[{session_id}] anti-spoof abstains on a {audio.total_duration_s:.2f}s window "
                f"(< {config.STREAM_SPOOF_MIN_WINDOW_S:.2f}s model input; tiled score "
                f"{spoof_result.risk:.3f} not used)"
            )
            details = {**spoof_result.details, "available": False,
                       "abstained": "window shorter than model input"}
            spoof_result = spoof_result.model_copy(update={"details": details})

        # Identity first (server/claims.py): the check below must see the resolved verdict,
        # not verification's raw open-set one.
        speaker_result = await _resolve_identity(speaker_result, spoof_result, transcript,
                                                 caller_metadata, owner_id)

        # Nothing measured: identity's `unknown` is a deliberate neutral 0.5, and with
        # anti-spoof and text both abstaining that constant would be the whole verdict —
        # which bands as suspicious. Refuse to score instead (CLAUDE.md: refusing to score
        # is a feature). On the streaming path this is the normal state before the first
        # transcript when the anti-spoof branch is off or short-windowed.
        if (speaker_result.verdict == SpeakerVerdict.UNKNOWN
                and spoof_result.details.get("available", True) is False
                and script.details.get("available", True) is False):
            log.info(f"[{session_id}] nothing measured on this window (speaker unknown, "
                     f"anti-spoof and text abstaining); returning insufficient")
            return ScreeningResponse(
                session_id=session_id,
                audio_sha256=audio.audio_sha256,
                quality=audio.quality,
                speaker=speaker_result,
                spoof=spoof_result,
                transcript=transcript,
                script=script,
                fusion=TrustScoreResult.insufficient(
                    reason="Nothing measurable yet: caller not enrolled, no transcript, "
                           "synthetic-voice check unavailable for this window"),
                processing_time_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )

        fusion = _compute_fusion(speaker_result, spoof_result, script, owner_id=owner_id)
    except Exception as e:  # noqa: BLE001
        log.error(f"[{session_id}] window scoring failed, returning insufficient: "
                  f"{type(e).__name__}: {e}")
        return ScreeningResponse(
            session_id=session_id,
            audio_sha256=audio.audio_sha256 or "",
            quality=audio.quality,
            speaker=SpeakerVerificationResult.neutral(),
            spoof=_spoof_abstains(),
            transcript=TranscriptResult.empty(),
            script=_text_abstains(),
            fusion=TrustScoreResult.insufficient(reason=f"Scoring failed: {type(e).__name__}"),
            processing_time_ms=round((time.perf_counter() - t_start) * 1000, 1),
        )

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)
    text_on = script.details.get("available", True) is not False
    log.info(
        f"[{session_id}] window Trust={fusion.trust_score} Band={fusion.band} "
        f"Mode={fusion.mode} text={'live' if text_on else 'abstained'} ({elapsed_ms}ms)"
    )
    return ScreeningResponse(
        session_id=session_id,
        audio_sha256=audio.audio_sha256,
        quality=audio.quality,
        speaker=speaker_result,
        spoof=spoof_result,
        transcript=transcript,
        script=script,
        fusion=fusion,
        processing_time_ms=elapsed_ms,
    )


if __name__ == "__main__":
    import asyncio
    from server.audio_ingest import ingest_audio, ingest_pcm
    from contracts import CallerMetadata

    async def _smoke():
        # Test with empty waveform (insufficient quality)
        audio = ingest_audio(audio_bytes=b"")
        result = await screen_audio(audio)
        print(f"[SMOKE] Band={result.fusion.band} Score={result.fusion.trust_score}")
        assert result.fusion.band == TrustBand.INSUFFICIENT, "Expected INSUFFICIENT for empty audio"
        windowed = await screen_window(ingest_pcm([]), None, None, session_id="smoke")
        assert windowed.fusion.band == TrustBand.INSUFFICIENT, "Expected INSUFFICIENT window"
        print("[OK] Orchestrator smoke test passed")

    asyncio.run(_smoke())
