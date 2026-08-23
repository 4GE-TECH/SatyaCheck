"""Deterministic reason-code templates.

No LLM. `ENABLE_LLM_REWRITE` defaults to `False` and reason codes are the thing a judge
reads off the screen — latency variance and generated text both belong somewhere else.

Two schema constraints shape this module:

- `ReasonCode` has **no direction field**. Risk-lowering evidence therefore has to be
  conveyed through the code name (`RC_EXCULPATORY_EVIDENCE`) and an `INFO` severity.
  D cannot style "this lowers risk" from the schema; it has to key off the code.
- Only the intent branch has a retrieved citation. Identity and authenticity codes draw
  theirs from `nlp_rag.citations`.

Every branch is optional in practice: a failed branch must degrade the verdict, not fail
the request (`CLAUDE.md` rule 5), so this returns an empty list rather than raising.
"""

from __future__ import annotations

from contracts import (
    AntiSpoofResult,
    OperatingMode,
    QualityGateResult,
    ReasonCode,
    ScriptAnalysisResult,
    SeverityLevel,
    SignalType,
    SpeakerVerdict,
    SpeakerVerificationResult,
)
from nlp_rag import thresholds
from nlp_rag.citations import for_code

_SEVERITY_ORDER: dict[SeverityLevel, int] = {
    SeverityLevel.CRITICAL: 0,
    SeverityLevel.HIGH: 1,
    SeverityLevel.MEDIUM: 2,
    SeverityLevel.LOW: 3,
    SeverityLevel.INFO: 4,
}


def _code(
    code: str,
    signal: SignalType,
    value: str,
    explanation: str,
    severity: SeverityLevel,
    threshold: str | None = None,
    citation_title: str | None = None,
    citation_url: str | None = None,
) -> ReasonCode:
    if citation_url is None:
        registered = for_code(code)
        if registered is not None:
            citation_title = registered.title
            citation_url = registered.source_url
    return ReasonCode(
        code=code,
        signal=signal,
        value=value,
        threshold=threshold,
        explanation=explanation,
        citation_title=citation_title,
        citation_url=citation_url,
        severity=severity,
    )


def _identity_codes(
    speaker: SpeakerVerificationResult, mode: OperatingMode
) -> list[ReasonCode]:
    codes: list[ReasonCode] = []

    if speaker.is_replay:
        codes.append(
            _code(
                "RC_REPLAY_SUSPECTED",
                SignalType.IDENTITY,
                f"Cosine {speaker.raw_score:.2f}",
                "Similarity is higher than live speech from an enrolled person "
                "produces. The audio is likely a stored recording being replayed.",
                SeverityLevel.HIGH,
                threshold="> 0.95",
            )
        )

    if mode is OperatingMode.AUTHORITY_CHECK or speaker.verdict is SpeakerVerdict.UNKNOWN:
        # Never assert verification for a caller we did not match. Green means
        # "we verified this person", and here we verified nobody.
        codes.append(
            _code(
                "RC_UNKNOWN_CALLER_UNVERIFIED",
                SignalType.IDENTITY,
                "Unenrolled caller",
                # A asked for neutral wording here and was right to. "Unidentified
                # caller detected" reads as an accusation; unknown is the normal state
                # for every real bank, delivery driver and doctor. The closing clause
                # redirects the reader to the evidence that does discriminate.
                "This voice does not match anyone enrolled, which is normal for a "
                "genuine stranger. Identity cannot be confirmed either way, so judge "
                "this call on what the caller is asking for.",
                SeverityLevel.INFO,
                threshold="N/A",
            )
        )
    elif speaker.verdict is SpeakerVerdict.MATCH:
        codes.append(
            _code(
                "RC_SPEAKER_VERIFIED",
                SignalType.IDENTITY,
                f"Cosine {speaker.raw_score:.2f} (s-norm {speaker.norm_score:.2f})",
                f"Voice matches the enrolled voiceprint for "
                f"{speaker.matched_person_name or 'an enrolled contact'}.",
                SeverityLevel.INFO,
                threshold="> 1.20",
            )
        )
    elif speaker.verdict is SpeakerVerdict.MISMATCH:
        codes.append(
            _code(
                "RC_SPEAKER_MISMATCH",
                SignalType.IDENTITY,
                f"Cosine {speaker.raw_score:.2f} (s-norm {speaker.norm_score:.2f})",
                f"Voice does not match the enrolled voiceprint for "
                f"{speaker.matched_person_name or 'the claimed contact'}.",
                SeverityLevel.HIGH,
                threshold="> 1.20",
            )
        )
    return codes


def _authenticity_codes(
    spoof: AntiSpoofResult, script: ScriptAnalysisResult
) -> list[ReasonCode]:
    if not spoof.is_synthetic:
        return [
            _code(
                "RC_AUDIO_BONAFIDE",
                SignalType.AUTHENTICITY,
                f"Synthetic probability {spoof.median_score:.0%}",
                "Acoustic characteristics are consistent with organic human speech.",
                SeverityLevel.INFO,
                threshold="< 40%",
            )
        ]

    # Synthetic voice is a multiplier, not a source. A bank IVR is synthetic and
    # legitimate; without intent, synthesis alone is not evidence of fraud.
    if script.risk < thresholds.CORROBORATION_FLOOR:
        if not script.incriminating_markers:
            return [
                _code(
                    "RC_LEGIT_AUTOMATED_VOICE",
                    SignalType.AUTHENTICITY,
                    "Automated voice (intent gated)",
                    "Synthetic speech detected, but the caller makes no suspicious "
                    "request. Automated institutional calls are routinely synthetic.",
                    SeverityLevel.INFO,
                    threshold="Low intent risk",
                )
            ]

        # Synthetic *and* asking for something, but nothing we can cite. Calling this
        # legitimate contradicts the markers listed beside it; calling it a deepfake
        # asserts more than the evidence supports. There has to be a middle.
        return [
            _code(
                "RC_SYNTHETIC_VOICE_UNVERIFIED",
                SignalType.AUTHENTICITY,
                f"Synthetic probability {spoof.median_score:.0%}, unverified caller",
                "The caller's voice is synthetic and they are making a request. "
                "We could not match that request to a documented scam script, so this "
                "is a reason to verify independently rather than a finding of fraud.",
                SeverityLevel.MEDIUM,
                threshold="> 40%",
            )
        ]

    return [
        _code(
            "RC_SYNTHETIC_VOICE_DETECTED",
            SignalType.AUTHENTICITY,
            f"Peak synthetic {spoof.peak_score:.0%} "
            f"(longest run {spoof.max_synth_run_s:.1f}s)",
            "Synthetic-speech signatures detected alongside a suspicious request. "
            "Synthesis matters here because of what is being asked, not on its own.",
            SeverityLevel.CRITICAL,
            threshold="> 40%",
        )
    ]


#: The one fact that defuses each scam family, written for the person on the call.
#:
#: "Matches a documented scam playbook" is true and useless — it tells a frightened
#: relative nothing they can act on. Each of these is the single sentence that collapses
#: that specific script, drawn from the advisory the citation points at.
#:
#: Advisory, never accusatory. The caller may be genuine, the reader is often family, and
#: PRD NG2 forbids emitting a verdict. Each line says what is true of the *tactic*, so it
#: is safe to show even when the call turns out to be legitimate.
FAMILY_GUIDANCE: dict[str, str] = {
    "digital_arrest": (
        "There is no provision for digital arrest in Indian law. No police, CBI, customs "
        "or judicial officer arrests a person over a video call or asks for a payment to "
        "avoid arrest."
    ),
    "family_emergency": (
        "A voice can be cloned from a few seconds of audio. Hang up and call the family "
        "member back on the number you already have saved for them."
    ),
    "kyc_update": (
        "Banks do not complete KYC over a phone call or a link, and never ask for an OTP, "
        "PIN or CVV. KYC is updated at a branch or in the bank's own app."
    ),
    "financial_fraud": (
        "No bank, payment provider or government office asks for an OTP, PIN, CVV or card "
        "number, or asks you to install a screen-sharing app."
    ),
    "parcel_customs": (
        "Customs does not telephone people about seized parcels or take payment over a "
        "call. A real case arrives as a written notice."
    ),
    "utility_disconnection": (
        "Electricity and water boards do not take payment through a link or an app sent "
        "over a call. Pay at the board office or in its official app."
    ),
    "telecom_impersonation": (
        "TRAI and the telecom department do not call subscribers about disconnecting "
        "numbers, and do not transfer callers to police officers."
    ),
    "lottery_advance_fee": (
        "A genuine prize is never released against a fee paid first. A request to deposit "
        "tax, conversion or processing charges before receiving money is the fraud itself."
    ),
    "qr_code_fraud": (
        "Scanning a QR code and entering a UPI PIN authorises money leaving your account. "
        "No PIN is ever needed to receive a payment."
    ),
    "sms_fraud": (
        "Links in messages about refunds, redelivery, blocked accounts or expiring points "
        "lead to fake pages. Open the organisation's own app instead."
    ),
}


def _matched_explanation(title: str, family: str | None) -> str:
    """Name the advisory, then give the fact that defuses this family.

    Guidance is additive: an unrecognised or missing family still produces the code with
    the citation, because losing the evidence is worse than losing the advice.
    """
    base = f"The caller's request matches a documented scam playbook: {title}."
    guidance = FAMILY_GUIDANCE.get(family or "")
    return f"{base} {guidance}" if guidance else base


def _intent_codes(script: ScriptAnalysisResult) -> list[ReasonCode]:
    codes: list[ReasonCode] = []

    if script.playbooks and script.risk >= thresholds.CORROBORATION_FLOOR:
        top = script.playbooks[0]
        severity = (
            SeverityLevel.CRITICAL
            if script.risk >= thresholds.SCRIPT_HIGH_RISK
            else SeverityLevel.HIGH
        )
        markers = ", ".join(m.category for m in script.incriminating_markers)
        codes.append(
            _code(
                "RC_SCAM_SCRIPT_MATCH",
                SignalType.INTENT,
                f"Script risk {script.risk:.0%}" + (f" ({markers})" if markers else ""),
                _matched_explanation(top.title, script.details.get("scam_family")),
                severity,
                threshold=f"> {thresholds.CORROBORATION_FLOOR:.0%}",
                citation_title=top.title,
                citation_url=top.source_url,
            )
        )
    elif script.incriminating_markers:
        listed = ", ".join(m.matched_text for m in script.incriminating_markers[:3])
        codes.append(
            _code(
                "RC_RISK_MARKERS_PRESENT",
                SignalType.INTENT,
                listed,
                "Risk markers are present but no documented scam script matched. "
                "Treated as a reason to verify, not as a verdict.",
                SeverityLevel.MEDIUM,
                threshold=f"> {thresholds.CORROBORATION_FLOOR:.0%}",
            )
        )

    if script.exculpatory_markers:
        listed = ", ".join(m.matched_text for m in script.exculpatory_markers[:3])
        codes.append(
            _code(
                "RC_EXCULPATORY_EVIDENCE",
                SignalType.INTENT,
                listed,
                "The caller invites verification or makes no financial request. "
                "This evidence lowers the assessed risk.",
                SeverityLevel.INFO,
            )
        )
    return codes


#: Why the branch abstained, in words a frightened relative can act on. The keys are the
#: `reason` values `nlp_rag.score.abstain` is called with.
_GATE_REASONS: dict[str, str] = {
    "empty_transcript": "no speech could be transcribed from this audio",
    "empty_text": "no speech could be transcribed from this audio",
    "asr_gate": "the transcript did not pass the reliability check",
    "no_speech": "the audio was mostly silence",
    "repetition": "the transcript looped, which means the decoder was guessing",
    "low_logprob": "the decoder had low confidence in what it heard",
    "too_short": "there was too little speech to analyse",
    "index_missing": "the scam-playbook index was unavailable",
    "exception": "the analysis could not be completed",
}


def _abstention_code(script: ScriptAnalysisResult) -> ReasonCode:
    """Report that the intent branch did not run. PLAN.md §7.

    Emitted instead of an empty list, which is what this used to return. An empty list
    puts nothing in the panel where the intent evidence belongs, and a reader takes that
    for "we looked and found nothing" — the branch never looked.

    Same principle as `RC_SPOOF_UNAVAILABLE` on the authenticity side: **absence of a
    warning is not evidence of safety.** The wording says so outright rather than leaving
    it to be inferred.

    QUALITY, not INTENT: an unreadable transcript is a fact about the audio, not a
    finding about the caller. INFO severity for the same reason — nobody should be
    treated as more suspicious because their line was noisy.
    """
    reason = str(script.details.get("gate_reason") or script.details.get("reason") or "")
    detail = _GATE_REASONS.get(reason, "the transcript could not be analysed")

    return _code(
        "RC_TRANSCRIPT_UNRELIABLE",
        SignalType.QUALITY,
        f"Not analysed ({reason})" if reason else "Not analysed",
        (
            f"What was said on this call was not checked — {detail}. This is not a "
            "sign that the call is safe: the scam-language check simply did not run, "
            "so judge this call on the other signals and on your own read of it."
        ),
        SeverityLevel.INFO,
        threshold=reason or None,
    )


def build_intent_reason_codes(script: ScriptAnalysisResult) -> list[ReasonCode]:
    """Intent-branch codes only — B's half of the evidence list.

    `server/orchestrator.py` merges these onto the codes A's `fuse` already produced:

        extra_codes = build_reason_codes(script_result)
        fusion.reason_codes.extend(extra_codes)

    So this must NOT emit identity or authenticity codes; doing so double-reports the
    same finding twice in one panel. Use `build_reason_codes` below when you own the
    whole list (the mock path, and the CLI smoke test).
    """
    try:
        if script is None or not isinstance(script, ScriptAnalysisResult):
            return []
        if script.details.get("available", True) is False:
            return [_abstention_code(script)]
        return sorted(_intent_codes(script), key=lambda rc: _SEVERITY_ORDER[rc.severity])
    except Exception:  # noqa: BLE001 - rule 5: degrade, never raise into the caller
        return []


def build_reason_codes(
    quality: QualityGateResult,
    speaker: SpeakerVerificationResult,
    spoof: AntiSpoofResult,
    script: ScriptAnalysisResult,
    mode: OperatingMode,
) -> list[ReasonCode]:
    """Assemble the ordered evidence list. Never raises."""
    try:
        if quality is None or not quality.passed:
            reason = getattr(quality, "reason", None) or (
                "Audio sample insufficient or too noisy to evaluate"
            )
            return [
                _code(
                    "RC_QUALITY_INSUFFICIENT",
                    SignalType.QUALITY,
                    "Below minimum duration/SNR",
                    reason,
                    SeverityLevel.INFO,
                    threshold=(
                        f"{quality.min_speech_threshold_s}s speech, "
                        f"{quality.min_snr_threshold_db} dB SNR"
                    ),
                )
            ]

        codes = (
            _identity_codes(speaker, mode)
            + _authenticity_codes(spoof, script)
            + _intent_codes(script)
        )
        return sorted(codes, key=lambda rc: _SEVERITY_ORDER[rc.severity])
    except Exception:  # noqa: BLE001 - rule 5: degrade, never raise into the caller
        return []


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    from contracts import create_mock_fixture

    for scenario in ("green", "red", "unverified", "insufficient"):
        fixture = create_mock_fixture(scenario)
        print(f"\n--- {scenario} ---")
        for rc in build_reason_codes(
            quality=fixture.quality,
            speaker=fixture.speaker,
            spoof=fixture.spoof,
            script=fixture.script,
            mode=fixture.fusion.mode,
        ):
            print(f"  [{rc.severity.value:8}] {rc.code:32} {rc.value}")
            if rc.citation_url:
                print(f"  {'':11} ↳ {rc.citation_url}")
