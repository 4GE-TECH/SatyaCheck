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
)
from server.audio_ingest import AudioChunk, IngestedAudio

log = logging.getLogger("satyacheck.orchestrator")


# ── Branch stubs (active until USE_REAL_* flags are True) ────────────

def _mock_speaker_branch(
    chunks: list[AudioChunk],
    enrolled_embeddings: dict,
) -> SpeakerVerificationResult:
    """Mock speaker branch — returns neutral UNKNOWN result."""
    return SpeakerVerificationResult.neutral()


def _mock_spoof_branch(chunks: list[AudioChunk]) -> AntiSpoofResult:
    """Mock spoof branch — returns neutral (bonafide) result."""
    return AntiSpoofResult.neutral()


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

def _real_speaker_branch(
    chunks: list[AudioChunk],
    enrolled_embeddings: dict,
) -> SpeakerVerificationResult:
    try:
        from audio_ml.api import verify_speaker
        return verify_speaker(chunks, enrolled_embeddings)
    except Exception as e:
        log.error(f"[speaker] Real branch failed, falling back to neutral: {e}")
        return SpeakerVerificationResult.neutral()


def _real_spoof_branch(chunks: list[AudioChunk]) -> AntiSpoofResult:
    try:
        from audio_ml.api import detect_spoof
        return detect_spoof(chunks)
    except Exception as e:
        log.error(f"[spoof] Real branch failed, falling back to neutral: {e}")
        return AntiSpoofResult.neutral()


def _real_nlp_branch(
    wav_path: Optional[str],
    waveform: list[float],
) -> tuple[TranscriptResult, ScriptAnalysisResult]:
    try:
        from nlp_rag.api import transcribe, analyze_script
        transcript = transcribe(wav_path or waveform)
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
) -> TrustScoreResult:
    """
    Intent-gated, mode-aware fusion.

    intent   = max(script.risk, speaker.risk if verdict == mismatch else 0.0)
    r_cm_eff = spoof.risk * (CM_FLOOR + (1 - CM_FLOOR) * intent)
    combined = sum(w_i * r_i) renormalised by active weight sum
    trust    = (1 - combined) * 100

    Text-branch unavailability (B signals details['available']=False):
      - w_text is excluded and the remaining weights are renormalised.
      - intent for the CM gate becomes max(0.5, identity_risk_for_gate)
        — neutral, never 0.0.  A dead ASR branch must not soften the
        anti-spoof gate; in authority_check that is the only signal we have.

    Mode selection:
      unknown → authority_check (speaker abstains, weights shift)
      otherwise → identity_check
    """
    verdict = speaker.verdict
    is_identity_check = verdict != SpeakerVerdict.UNKNOWN
    mode = OperatingMode.IDENTITY_CHECK if is_identity_check else OperatingMode.AUTHORITY_CHECK

    weights = config.WEIGHTS_IDENTITY_CHECK if is_identity_check else config.WEIGHTS_AUTHORITY_CHECK
    w_asv = weights["asv"]
    w_cm = weights["cm"]
    w_text = weights["text"]

    r_asv = speaker.risk
    r_cm = spoof.risk
    r_text = script.risk

    # ── E1 FIX: detect B's unavailability sentinel ─────────────────────
    # B writes details["available"] = False on every abstention path.
    # risk=0.0 alone is ambiguous (genuine benign call also has risk 0.0).
    text_available: bool = script.details.get("available", True) is not False
    if not text_available:
        log.warning(
            "[fusion] text branch unavailable (details['available']=False) — "
            "renormalising weights, CM gate intent → neutral 0.5"
        )

    # ── Identity-contribution to CM gate ─────────────────────────────
    identity_risk_for_gate = r_asv if verdict == SpeakerVerdict.MISMATCH else 0.0

    # ── Intent for CM gate ────────────────────────────────────────────
    if text_available:
        intent = max(r_text, identity_risk_for_gate)
    else:
        # Neutral 0.5 — we have no transcript evidence either way.
        # Using 0.0 would floor r_cm_eff to CM_FLOOR and soften the
        # anti-spoof branch precisely when we can least afford to.
        intent = max(0.5, identity_risk_for_gate)

    r_cm_eff = r_cm * (config.CM_FLOOR + (1.0 - config.CM_FLOOR) * intent)

    # ── Weighted sum, renormalised over active branches ───────────────
    if text_available:
        combined_risk = w_asv * r_asv + w_cm * r_cm_eff + w_text * r_text
        active_weight_sum = 1.0  # weights already sum to 1.0
    else:
        # Drop w_text and renormalise so the remaining two branches
        # still span the full 0–1 risk range.
        active_weight_sum = w_asv + w_cm  # e.g. 0.55 in authority_check
        combined_risk = (w_asv * r_asv + w_cm * r_cm_eff) / active_weight_sum
        w_text = 0.0  # reflected in weights_used for transparency
        # Renormalise displayed weights proportionally
        w_asv = round(w_asv / active_weight_sum, 4)
        w_cm  = round(w_cm  / active_weight_sum, 4)

    combined_risk = round(min(1.0, max(0.0, combined_risk)), 4)

    trust_score = config.risk_to_trust_score(combined_risk)
    band = config.risk_to_band(combined_risk, is_authority_check=not is_identity_check)

    reason_codes = _build_reason_codes(speaker, spoof, script, mode, r_cm_eff)
    recommended_actions = _build_actions(band, verdict, script)

    # Fetch challenge question from NLP if identity is in question
    challenge_question: Optional[ChallengeQuestion] = None
    if verdict in (SpeakerVerdict.MISMATCH, SpeakerVerdict.UNKNOWN) and r_text > 0.3:
        try:
            from nlp_rag.api import challenge_question as cq_fn
            challenge_question = cq_fn(speaker.matched_person_id)
        except Exception:
            pass

    return TrustScoreResult(
        trust_score=trust_score,
        risk_score=combined_risk,
        band=band,
        mode=mode,
        weights_used=FusionWeights(asv_weight=w_asv, cm_weight=w_cm, text_weight=w_text),
        identity_risk=r_asv,
        authenticity_risk=r_cm,
        authenticity_risk_effective=round(r_cm_eff, 4),
        intent_risk=r_text,
        reason_codes=reason_codes,
        recommended_actions=recommended_actions,
        challenge_question=challenge_question,
        vernacular_warning=_get_vernacular_warning(band),
    )


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
    if speaker.verdict == SpeakerVerdict.MATCH:
        codes.append(ReasonCode(
            code="RC_SPEAKER_VERIFIED",
            signal=SignalType.IDENTITY,
            value=f"s-norm {speaker.norm_score:.2f}",
            threshold=f"> {config.ASV_MATCH_THRESHOLD}",
            explanation=f"Voice closely matches enrolled voiceprint for {speaker.matched_person_name or 'enrolled contact'}.",
            severity=SeverityLevel.INFO,
        ))
    elif speaker.verdict == SpeakerVerdict.MISMATCH:
        codes.append(ReasonCode(
            code="RC_SPEAKER_MISMATCH",
            signal=SignalType.IDENTITY,
            value=f"s-norm {speaker.norm_score:.2f}",
            threshold=f"< {config.ASV_MISMATCH_THRESHOLD}",
            explanation=f"Voice does NOT match enrolled voiceprint for {speaker.matched_person_name or 'claimed contact'}.",
            citation_title="ECAPA-TDNN Speaker Verification",
            severity=SeverityLevel.HIGH,
        ))
    else:  # UNKNOWN
        codes.append(ReasonCode(
            code="RC_SPEAKER_UNKNOWN",
            signal=SignalType.IDENTITY,
            value="No enrolled match found",
            threshold="N/A",
            explanation="Caller is not registered as an enrolled contact. Authority-check mode active.",
            severity=SeverityLevel.INFO,
        ))

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
    if spoof.is_synthetic and r_cm_eff > 0.3:
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


def _get_vernacular_warning(band: TrustBand) -> Optional[str]:
    warnings = {
        TrustBand.HIGH_RISK: "सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।",
        TrustBand.SUSPICIOUS: "सतर्क रहें। इस कॉल में संदिग्ध संकेत हैं। कोई भी कार्रवाई करने से पहले सत्यापित करें।",
        TrustBand.CAUTION: "कृपया सावधानी बरतें। पैसे भेजने से पहले व्यक्ति की पहचान सुनिश्चित करें।",
    }
    return warnings.get(band)


# ── Main orchestration entry point ────────────────────────────────────

async def screen_audio(
    audio: IngestedAudio,
    caller_metadata: Optional[CallerMetadata] = None,
    enrolled_embeddings: Optional[dict] = None,
) -> ScreeningResponse:
    """
    Run quality gate, then dispatch all three branches concurrently, fuse results.

    Returns a complete ScreeningResponse. Never raises.
    """
    t_start = time.perf_counter()
    enrolled_embeddings = enrolled_embeddings or {}
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    # ── Quality gate: early exit ──────────────────────────────────────
    if not audio.quality.passed:
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
        )

    # ── Select branch implementations ─────────────────────────────────
    run_speaker = _real_speaker_branch if config.USE_REAL_SPEAKER else _mock_speaker_branch
    run_spoof = _real_spoof_branch if config.USE_REAL_SPOOF else _mock_spoof_branch
    run_nlp = _real_nlp_branch if config.USE_REAL_NLP else _mock_nlp_branch

    # ── Concurrent branch execution ───────────────────────────────────
    loop = asyncio.get_event_loop()
    try:
        speaker_task = loop.run_in_executor(
            None, run_speaker, audio.chunks, enrolled_embeddings
        )
        spoof_task = loop.run_in_executor(
            None, run_spoof, audio.chunks
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

    # ── Fusion ────────────────────────────────────────────────────────
    if config.USE_REAL_FUSION:
        try:
            from audio_ml.api import fuse
            from nlp_rag.api import build_reason_codes
            fusion = fuse(speaker_result, spoof_result, script_result)
            # Merge reason codes from NLP
            extra_codes = build_reason_codes(script_result)
            fusion.reason_codes.extend(extra_codes)
        except Exception as e:
            log.error(f"Real fusion failed, falling back: {e}")
            fusion = _compute_fusion(speaker_result, spoof_result, script_result)
    else:
        fusion = _compute_fusion(speaker_result, spoof_result, script_result)

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
    )


if __name__ == "__main__":
    import asyncio
    from server.audio_ingest import ingest_audio
    from contracts import CallerMetadata

    async def _smoke():
        # Test with empty waveform (insufficient quality)
        audio = ingest_audio(audio_bytes=b"")
        result = await screen_audio(audio)
        print(f"[SMOKE] Band={result.fusion.band} Score={result.fusion.trust_score}")
        assert result.fusion.band == TrustBand.INSUFFICIENT, "Expected INSUFFICIENT for empty audio"
        print("[OK] Orchestrator smoke test passed")

    asyncio.run(_smoke())
