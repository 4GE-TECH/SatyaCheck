"""Whisper on 8 kHz phone audio drops Hindi aspiration and shortens words: भेज comes out as
बेज, अभी as अबी, तुरंत as तुरन. The urgent-transfer marker must still fire on those
spellings, or the verdict depends on which spelling one decode happened to produce.

Found by scripts/device_parity.py: the same narrowband clip decoded on CPU (int8) gave
"अभी ... भेज्दो" and the marker fired; on GPU (float16) it gave "अभी ... बेज्दो" and it did
not. Neither spelling is wrong; the marker was too exact.
"""

from __future__ import annotations

import pytest

from nlp_rag.markers import find_markers

MARKER = "MK_URGENT_FINANCIAL_UPI"

GPU_DECODE = ("प्लीस ममी को मतबदाना में टेंचन में लगी अभी तुरन तिस नमबर पे पच्टाँ साथार "
              "बेज्दो में बाद में सब समजा दोंगा")


def _ids(text: str) -> set[str]:
    return {m.marker_id for m in find_markers(text)}


def test_the_gpu_decode_of_the_family_emergency_clip_fires_the_marker():
    assert MARKER in _ids(GPU_DECODE)


@pytest.mark.parametrize("text", [
    "अभी इस नंबर पे पैसे भेजो",
    "अबी इस नंबर पे पचास हजार भेज दो",
    "तुरन्त इस नंबर पर बेज दो",
    "तुरन इस नंबर पर बेजो",
    "जल्दी से बेजिए पैसे",
    "तुरंत ट्रान्सफर करो",
])
def test_aspiration_and_shortening_variants_fire(text):
    assert MARKER in _ids(text)


@pytest.mark.parametrize("text", [
    "अभी मैं बहुत बेजार हूँ",          # "I am very fed up right now"
    "अभी वो बेजुबान जानवर ठीक है",      # "the voiceless animal is fine now"
    "कभी भी आके ले लेना",               # "collect it whenever": kabhi is not abhi
])
def test_innocent_words_that_share_the_letters_do_not(text):
    assert MARKER not in _ids(text)
