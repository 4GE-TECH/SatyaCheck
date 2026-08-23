"""The intent branch must say when it abstained, not fall silent.

`PLAN.md` §7 specifies `RC_TRANSCRIPT_UNRELIABLE` with `signal=SignalType.QUALITY` so
that an abstention is "visible in the panel rather than silent". It was never built:
`build_intent_reason_codes` returned `[]` whenever `details["available"]` was False.

Confirmed live before writing this — screening `me.wav`, whose transcript the ASR gate
rejects, produced **no intent reason code at all**. The evidence panel showed identity
and authenticity and simply nothing for intent, which reads as "the intent branch looked
and found nothing wrong". It didn't look.

This is the same class of defect as the anti-spoof branch returning `risk=0.0` while
abstaining, and the same fix: **absence of a warning is not evidence of safety, and the
panel has to say so.**

Note what this does NOT change: `risk` stays 0.0 and `details["available"]` stays False,
so fusion still drops `w_text` and renormalises. This is about what the user is told, not
about the arithmetic.
"""

from __future__ import annotations

import pytest

from contracts import ScriptAnalysisResult, SeverityLevel, SignalType, TranscriptResult
from nlp_rag.api import analyze_script, build_reason_codes
from nlp_rag.score import abstain

CODE = "RC_TRANSCRIPT_UNRELIABLE"


def _codes(script: ScriptAnalysisResult):
    return {c.code: c for c in build_reason_codes(script)}


@pytest.mark.parametrize(
    "reason",
    ["empty_transcript", "asr_gate", "exception", "index_missing"],
)
def test_every_abstention_path_reports_itself(reason):
    """One code on every path that sets available=False. No silent abstentions."""
    assert CODE in _codes(abstain(reason)), (
        f"abstention '{reason}' produced no reason code — the panel shows nothing"
    )


def test_the_code_is_a_quality_signal_not_an_intent_finding():
    """§7 is explicit about the signal type.

    INTENT would place it beside genuine scam findings in the panel and imply the branch
    reached a conclusion about the caller. It didn't — the audio was unreadable, which
    is a quality fact.
    """
    code = _codes(abstain("asr_gate"))[CODE]
    assert code.signal is SignalType.QUALITY
    assert code.severity is SeverityLevel.INFO, (
        "an unreadable transcript is not evidence against the caller"
    )


def test_the_explanation_does_not_imply_safety():
    """The whole point. A reader must not take silence for a clean result."""
    explanation = _codes(abstain("asr_gate"))[CODE].explanation.lower()
    assert "not" in explanation, f"explanation asserts nothing negative: {explanation!r}"
    for forbidden in ("no scam", "appears safe", "no risk detected", "nothing suspicious"):
        assert forbidden not in explanation


def test_the_gate_reason_is_carried_through():
    """`api.analyze_script` already records why; the panel should show it.

    Without this the code is honest but useless for debugging — "something went wrong"
    with no way to tell a silent clip from a hallucinating decoder.
    """
    script = abstain("asr_gate")
    script.details["gate_reason"] = "no_speech"

    code = _codes(script)[CODE]
    assert "no_speech" in (code.value or "") + (code.threshold or ""), (
        f"gate_reason not surfaced: value={code.value!r} threshold={code.threshold!r}"
    )


def test_an_abstention_emits_nothing_else():
    """Only the abstention code. A branch that abstained has no findings to report."""
    codes = _codes(abstain("asr_gate"))
    assert set(codes) == {CODE}, f"abstention emitted extra codes: {sorted(codes)}"


def test_a_working_branch_does_not_emit_it():
    """The code must mean something. Emitting it always would make it furniture."""
    script = analyze_script(
        TranscriptResult(
            text=(
                "Papa emergency ho gaya hai. Phone kisi ko mat dena, turant 50000 bhejo "
                "is UPI ID pe."
            ),
            detected_language="hi",
        )
    )
    assert script.details.get("available") is True, "test premise: branch should be live"
    assert CODE not in _codes(script)


def test_the_abstention_contract_is_unchanged():
    """Fusion's arithmetic must not shift — this change is presentational only.

    `server/orchestrator.py` reads `details["available"]` to decide whether to drop
    `w_text` and renormalise. If adding a reason code disturbed that, a dead branch would
    start counting as a measured benign result.
    """
    script = abstain("asr_gate")
    assert script.risk == 0.0
    assert script.details.get("available") is False


def test_build_reason_codes_never_raises_on_a_malformed_script():
    """CLAUDE.md rule 5 — this runs inside a live request."""
    broken = abstain("asr_gate")
    del broken.details["available"]          # missing key, not False
    assert isinstance(build_reason_codes(broken), list)

    assert build_reason_codes(None) == []  # type: ignore[arg-type]
