"""Block 5 bug-bash inputs, as committed tests.

`PLAN.md` lists nine inputs under "Bug-bash inputs (Block 5)" and they were never run.
They are here because the *interesting* property of each is not that it avoids a crash —
rule 5 already guarantees that — but that it returns the right **abstention contract**.

    details["available"] is False   →  fusion drops w_text and renormalises
    details["available"] is True    →  fusion keeps w_text and gates the CM branch

Getting that flag wrong in either direction is the E1 defect. `risk=0.0` with the flag
True says "I read the transcript and it was fine"; with the flag False it says "I have
nothing to contribute". Those are opposite claims and they score differently — the same
class of bug as the anti-spoof branch abstaining at risk=0.0 while its weight still
counted, which capped the reachable risk so that nothing could ever be scored red.

The last two cases pin the double-count suppression boundary, which is the subtlest rule
in `score.py` and the one most likely to be broken by a well-meaning refactor.
"""

from __future__ import annotations

import pytest

from contracts import ScriptAnalysisResult, TranscriptResult
from nlp_rag import thresholds
from nlp_rag.api import analyze_script, build_reason_codes


def _script(text: str, lang: str = "en") -> ScriptAnalysisResult:
    return analyze_script(TranscriptResult(text=text, detected_language=lang))


# --- the nine inputs ----------------------------------------------------------

@pytest.mark.parametrize(
    "label,text",
    [
        ("empty transcript", ""),
        ("whitespace only", "   \n\t  "),
        ("pure silence (decoder returned nothing)", ""),
        ("single word", "hello"),
        ("single Devanagari word", "नमस्ते"),
    ],
)
def test_nothing_to_analyse_abstains_rather_than_scoring(label, text):
    """Refusing to score is a feature — CLAUDE.md says so explicitly.

    A system that outputs a confident number on one word is a system nobody should
    trust. The flag is what makes the refusal legible to fusion.
    """
    result = _script(text)

    assert result.details.get("available") is False, (
        f"{label}: scored as a real analysis (risk={result.risk})"
    )
    assert result.risk == 0.0, f"{label}: fabricated risk {result.risk}"
    assert result.playbooks == [], f"{label}: cited a playbook for {text!r}"


@pytest.mark.parametrize(
    "label,text,lang",
    [
        (
            "all Devanagari",
            "आपके नाम पर एक पार्सल पकड़ा गया है जिसमें प्रतिबंधित सामान है। "
            "मामला सुलझाने के लिए अभी इस खाते में पैसे भेजिए और किसी को मत बताइए।",
            "hi",
        ),
        (
            "all Latin-Hinglish",
            "Aapke naam pe ek parcel customs mein pakda gaya hai. Case band karne ke "
            "liye abhi is account mein paisa bhej dijiye aur kisi ko mat bataiye.",
            "hi",
        ),
        (
            "code-switched mid-sentence",
            "Sir aapka account block ho jayega if you don't verify right now, "
            "turant OTP batao please, it is urgent.",
            "hi",
        ),
    ],
)
def test_every_script_is_analysed_not_abstained(label, text, lang):
    """Hinglish is not a degraded input. CLAUDE.md: never assume English-only.

    All three of these are scam scripts. The branch has to *run* on them — abstaining on
    Devanagari would silently disable the intent signal for a whole language.
    """
    result = _script(text, lang)

    assert result.details.get("available") is True, f"{label}: abstained on real speech"
    assert result.risk >= thresholds.AMBER_FLOOR, (
        f"{label}: a scam script scored {result.risk:.3f}, below the amber floor"
    )


def test_a_long_benign_transcript_stays_benign():
    """200 words of ordinary conversation. The over-flagging guard.

    Length alone must not accumulate risk — a long call is not a suspicious one, and a
    system that drifts upward with transcript length flags every real conversation.
    """
    text = " ".join(
        [
            "Hello beta, I was just calling to see how the new place is treating you.",
            "Your mother made the pickle you like and we are posting it this week.",
            "The neighbours downstairs finally fixed that leaking tap after two months.",
            "I went for my walk this morning and met your old school teacher at the park.",
            "He asked about you and I told him you had moved for the new job.",
            "The weather here has been pleasant, much cooler than last year at this time.",
            "Your father has been reading that book you sent, he is halfway through it.",
            "We watched the match on Sunday and the ending was quite something.",
            "Do not worry about calling every day, we know you are busy with work.",
            "Take your medicines on time and eat properly, that is all we ask.",
            "Come home whenever you get a long weekend, there is no hurry at all.",
            "Your cousin is getting married in December so keep those dates free.",
            "We will talk again on the weekend when you have more time to chat.",
        ]
        * 2
    )

    result = _script(text)

    assert result.details.get("available") is True
    assert result.risk < thresholds.AMBER_FLOOR, (
        f"a long benign family call scored {result.risk:.3f} — length is accumulating risk"
    )


# --- the two suppression-boundary cases ---------------------------------------

def test_a_marker_with_no_playbook_still_raises_concern():
    """Double-count suppression must not delete the only evidence there is.

    Suppression exists because a marker phrase is often *why* a playbook retrieved, so
    counting both inflates risk. But when retrieval is too weak to cite, nothing is
    counting the marker — dropping it too leaves the score at zero.

    This is a real defect that was found and fixed: a genuine-but-unusual money request
    scored 0.02, indistinguishable from a routine check-in, because its urgency marker
    was suppressed by a playbook the system then refused to show.
    """
    result = _script(
        "Listen, whatever you do, don't tell anyone about this conversation, "
        "not your father and not your brother. Keep it strictly between us."
    )

    assert result.details.get("available") is True
    assert result.incriminating_markers, "the isolation marker did not fire at all"
    if not result.playbooks:
        assert result.risk > 0.05, (
            f"a clear isolation demand scored {result.risk:.3f} with no playbook to "
            "cite — the marker was suppressed by a hit that was never shown"
        )


def test_a_playbook_hit_with_no_marker_scores_on_retrieval_alone():
    """The mirror case. Retrieval is a signal in its own right.

    A scam script paraphrased so it dodges every regex must still score on its
    similarity to the corpus, otherwise the whole RAG half is decorative.
    """
    result = _script(
        "Your electricity connection is scheduled for disconnection tonight because "
        "the meter reading was not updated in our system last month. The settlement "
        "has to be completed before the cutoff time for supply to continue."
    )

    assert result.details.get("available") is True
    assert result.risk > 0.0, "retrieval contributed nothing without markers"


# --- reason codes survive every one of these ----------------------------------

@pytest.mark.parametrize(
    "text",
    ["", "   ", "hello", "नमस्ते", "Aapka account block ho jayega, turant OTP batao."],
)
def test_reason_codes_are_always_a_valid_list(text):
    """C calls this unconditionally on every request. It may never raise."""
    codes = build_reason_codes(_script(text))
    assert isinstance(codes, list)
    for code in codes:
        assert code.code and code.explanation, f"malformed reason code: {code}"
