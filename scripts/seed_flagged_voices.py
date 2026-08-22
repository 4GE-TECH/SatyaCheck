"""
scripts/seed_flagged_voices.py — Seed the negative voiceprint list.

Adds flagged voices from known fraud/scams so they can be detected in future calls.
Tests the "voice reported in previous fraud complaints" feature.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_ml.verify import add_flagged_voice, verify_speaker

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Fraudulent voices to flag
FLAGGED_VOICES = [
    ("data/demo_clips/cloned_scam.wav", "scam_001", "Cloned friend voice (social engineering)"),
    ("data/eval_set/raw/person1.wav", "scam_002", "Unknown voice (impersonation attempt)"),
    ("data/eval_set/raw/person3.wav", "scam_003", "Unknown voice (repeated scam caller)"),
]


def main():
    print("\n" + "=" * 80)
    print("SatyaCheck: Seed Flagged Voice List")
    print("=" * 80)

    print("\n📝 SEEDING FLAGGED VOICES")
    print("-" * 80)

    for audio_path, session_id, description in FLAGGED_VOICES:
        if not Path(audio_path).exists():
            logger.error(f"File not found: {audio_path}")
            continue

        logger.info(f"Flagging: {Path(audio_path).name}")
        logger.info(f"  Session ID: {session_id}")
        logger.info(f"  Description: {description}")

        add_flagged_voice(session_id, audio_path)
        logger.info(f"  ✓ Added to flagged voice list")

    print("\n" + "=" * 80)
    print("🔍 VERIFICATION TEST")
    print("=" * 80)
    print("\nRunning verify_speaker on cloned_scam.wav...")
    print("Expected: flagged_voice_hits >= 1 (match found in flagged voices)\n")

    result = verify_speaker("data/demo_clips/cloned_scam.wav")

    print("-" * 80)
    print(f"Raw cosine:         {result.raw_cosine:.4f}")
    print(f"Verdict:            {result.verdict}")
    print(f"Best match:         {result.best_match_name}")
    print(f"Flagged hits:       {result.flagged_voice_hits}")
    print("-" * 80)

    if result.flagged_voice_hits > 0:
        print(f"\n✅ SUCCESS: Voice detected in flagged list ({result.flagged_voice_hits} hits)")
        print("   This voice has been reported in previous fraud complaints!")
    else:
        print(f"\n⚠️  WARNING: No flagged voices matched")
        print("   This may indicate the flagged voice storage or matching failed")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
