"""
Codec degradation module for condition-matched enrollment.

Produces degraded copies of audio to match phone-quality conditions
(8 kHz, various codecs). Enrollment must be condition-matched:
comparing a phone-quality probe against a studio-quality reference
measures channel difference as much as speaker difference.

Public functions never raise. All failures are logged and return None.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def degrade(in_path: str, out_path: str, mode: str) -> Optional[str]:
    """
    Degrade audio to simulate lower-quality conditions (phone, codec artifacts).

    Always resamples output back to 16 kHz to maintain downstream model input shape.

    Args:
        in_path: Path to input WAV file.
        out_path: Path to output WAV file.
        mode: One of 'nb8k' (8 kHz resample), 'ulaw', 'gsm', 'amr'.

    Returns:
        out_path on success, None on failure. Output is always 16 kHz mono PCM.
    """
    try:
        in_path = str(in_path)
        out_path = str(out_path)

        # Ensure output directory exists.
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        # Create temporary file for intermediate degradation.
        temp_path = str(
            Path(out_path).with_stem(Path(out_path).stem + "_degraded_temp")
        )

        # Step 1: Apply degradation to 8 kHz with selected codec.
        if mode == "nb8k":
            # Direct resample to 8 kHz.
            degrade_cmd = [
                "ffmpeg",
                "-i",
                in_path,
                "-ar",
                "8000",
                "-acodec",
                "pcm_s16le",
                "-y",
                temp_path,
            ]
        elif mode == "ulaw":
            degrade_cmd = [
                "ffmpeg",
                "-i",
                in_path,
                "-acodec",
                "pcm_mulaw",
                "-ar",
                "8000",
                "-y",
                temp_path,
            ]
        elif mode == "gsm":
            degrade_cmd = [
                "ffmpeg",
                "-i",
                in_path,
                "-acodec",
                "libgsm",
                "-ar",
                "8000",
                "-y",
                temp_path,
            ]
        elif mode == "amr":
            degrade_cmd = [
                "ffmpeg",
                "-i",
                in_path,
                "-acodec",
                "libopencore_amrnb",
                "-ar",
                "8000",
                "-y",
                temp_path,
            ]
        else:
            logger.warning(f"Unknown degrade mode: {mode}")
            return None

        # Run degradation step (capture both stdout and stderr).
        result = subprocess.run(
            degrade_cmd, capture_output=True, text=True, timeout=60
        )
        # Merge stdout and stderr for better error detection on Windows.
        full_output = (result.stdout or "") + (result.stderr or "")

        if result.returncode != 0:
            # If degradation failed and it's not already nb8k, try fallback.
            # This handles missing encoders gracefully on systems without libgsm/libopencore_amrnb.
            if mode != "nb8k":
                logger.warning(
                    f"Mode '{mode}' failed, falling back to nb8k (encoder likely unavailable)."
                )
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return degrade(in_path, out_path, "nb8k")
            else:
                # Already tried nb8k and it failed.
                output_snippet = full_output[:200] if full_output else "(no error output)"
                logger.error(f"Degradation failed for mode {mode}: {output_snippet}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None

        # Step 2: Resample back to 16 kHz.
        resample_cmd = [
            "ffmpeg",
            "-i",
            temp_path,
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            "-y",
            out_path,
        ]

        result = subprocess.run(
            resample_cmd, capture_output=True, text=True, timeout=60
        )

        # Clean up temp file.
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if result.returncode == 0:
            logger.info(f"Degraded {in_path} with mode '{mode}' → {out_path}")
            return out_path
        else:
            full_output_resample = (result.stdout or "") + (result.stderr or "")
            logger.error(f"Resampling to 16 kHz failed: {full_output_resample[:200]}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"ffmpeg timeout processing {in_path}")
        return None
    except Exception as e:
        logger.error(f"Error degrading audio: {e}")
        return None


def batch_degrade(folder: str, mode: str, out_folder: str) -> list[str]:
    """
    Degrade all WAV files in a folder.

    Args:
        folder: Input folder path.
        mode: Degradation mode ('nb8k', 'ulaw', 'gsm', 'amr').
        out_folder: Output folder path.

    Returns:
        List of successfully processed output paths (empty list if none succeeded).
    """
    try:
        folder_path = Path(folder)
        out_folder_path = Path(out_folder)
        out_folder_path.mkdir(parents=True, exist_ok=True)

        results = []
        wav_files = list(folder_path.glob("*.wav"))

        for wav_file in wav_files:
            out_path = out_folder_path / wav_file.name
            result = degrade(str(wav_file), str(out_path), mode)
            if result:
                results.append(result)

        logger.info(f"batch_degrade: processed {len(results)}/{len(wav_files)} files")
        return results

    except Exception as e:
        logger.error(f"batch_degrade error: {e}")
        return []


if __name__ == "__main__":
    import sys

    # Configure logging.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python -m audio_ml.codec <input_wav_path>")
        print("Degrades input through all modes (nb8k, ulaw, gsm, amr)")
        print("Outputs to data/demo_clips/")
        sys.exit(1)

    input_wav = sys.argv[1]
    output_folder = "data/demo_clips"

    if not os.path.exists(input_wav):
        logger.error(f"Input file not found: {input_wav}")
        sys.exit(1)

    modes = ["nb8k", "ulaw", "gsm", "amr"]
    input_stem = Path(input_wav).stem

    print(f"\nDegrading {input_wav} through all modes...\n")

    for mode in modes:
        output_path = os.path.join(output_folder, f"{input_stem}_{mode}.wav")
        result = degrade(input_wav, output_path, mode)

        if result and os.path.exists(result):
            # Get duration and sample rate using ffmpeg (more reliable than ffprobe).
            try:
                import wave

                # Try using Python's wave module for quick read.
                try:
                    with wave.open(result, "rb") as wav:
                        n_frames = wav.getnframes()
                        sample_rate = wav.getframerate()
                        duration = n_frames / sample_rate
                        print(
                            f"✓ {mode:6s} | Duration: {duration:>6.1f}s | Sample rate: {sample_rate:>5d} Hz | {output_path}"
                        )
                except Exception:
                    # Fallback: use ffmpeg info parsing.
                    info_cmd = ["ffmpeg", "-i", result]
                    info_result = subprocess.run(
                        info_cmd, capture_output=True, text=True, timeout=10
                    )
                    stderr = info_result.stderr or ""

                    # Parse "Duration: HH:MM:SS.ms" from stderr.
                    duration_str = "?"
                    sample_rate_str = "?"
                    for line in stderr.split("\n"):
                        if "Duration:" in line:
                            parts = line.split("Duration:")[1].split(",")[0].strip()
                            duration_str = parts
                        if "Hz" in line:
                            sample_rate_str = line.split()[0].split(",")[-1]
                    print(
                        f"✓ {mode:6s} | Duration: {duration_str:>6s} | Sample rate: {sample_rate_str:>5s} Hz | {output_path}"
                    )
            except Exception as e:
                logger.warning(f"Could not read audio properties: {e}")
                print(f"✓ {mode:6s} | {output_path}")
        else:
            print(f"✗ {mode:6s} | FAILED")
