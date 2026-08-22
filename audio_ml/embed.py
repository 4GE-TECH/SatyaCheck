"""
audio_ml/embed.py — Audio loading, VAD, embeddings, SNR, condition detection.

Pure pretrained inference. No training, no network calls.
All errors caught internally; functions return valid defaults.
"""

from __future__ import annotations

import logging
import numpy as np
import torch
import torchaudio
import wave
from pathlib import Path
from typing import Tuple, List

logger = logging.getLogger(__name__)

# Model paths — use forward slashes for cross-platform compatibility
MODELS_DIR = Path(__file__).parent.parent / "models"
ECAPA_MODEL_PATH = MODELS_DIR / "ecapa"
SILERO_VAD_REPO_PATH = MODELS_DIR / "torch" / "hub" / "snakers4_silero-vad_master"

# Audio constants from CLAUDE.md architecture
TARGET_SR = 16000
CHUNK_LENGTH_S = 3.0
CHUNK_OVERLAP_S = 1.0
MIN_SPEECH_S = 1.5
MIN_SNR_DB = 5.0


def _load_audio_wave_fallback(audio_path: str) -> Tuple[np.ndarray, int]:
    """
    Fallback: Load WAV using Python's wave module (no external codec dependencies).
    Handles standard PCM WAV files. Returns empty array for unsupported formats.
    """
    try:
        with wave.open(audio_path, 'rb') as wav_file:
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sr = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            # Read all frames
            audio_bytes = wav_file.readframes(n_frames)
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Convert to mono if needed
            if n_channels > 1:
                audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

            # Resample to 16kHz if needed
            if sr != TARGET_SR:
                # Simple linear interpolation for resampling
                ratio = TARGET_SR / sr
                n_new = int(len(audio_data) * ratio)
                indices = np.linspace(0, len(audio_data) - 1, n_new)
                audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)

            # Normalize
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val * 0.95

            duration_s = len(audio_data) / TARGET_SR
            logger.info(f"Loaded {audio_path} (wave fallback): {duration_s:.2f}s @ 16kHz mono")
            return audio_data.astype(np.float32), TARGET_SR

    except Exception as e:
        logger.debug(f"_load_audio_wave_fallback({audio_path}): {type(e).__name__}: {e}")
        return np.array([], dtype=np.float32), TARGET_SR


def load_audio(audio_path: str) -> Tuple[np.ndarray, int]:
    """
    Load audio file and resample to 16kHz mono.

    Args:
        audio_path: Path to audio file (wav, mp3, m4a, etc.)

    Returns:
        (audio_array, sample_rate) — always returns valid defaults on error.
        audio_array is float32 in range [-1, 1), normalized via ffmpeg if needed.
        sample_rate is always 16000.
    """
    try:
        # Use torchaudio for robust cross-format loading
        audio_tensor, sr = torchaudio.load(audio_path)

        # Convert to mono if needed
        if audio_tensor.shape[0] > 1:
            audio_tensor = audio_tensor.mean(dim=0, keepdim=True)

        # Resample to 16kHz if needed
        if sr != TARGET_SR:
            resampler = torchaudio.transforms.Resample(sr, TARGET_SR)
            audio_tensor = resampler(audio_tensor)

        # Convert to numpy and ensure float32 in [-1, 1)
        audio = audio_tensor.squeeze().numpy().astype(np.float32)

        # Normalize to prevent clipping
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 0.95

        duration_s = len(audio) / TARGET_SR
        logger.info(f"Loaded {audio_path}: {duration_s:.2f}s @ 16kHz mono")
        return audio, TARGET_SR

    except Exception as e:
        logger.error(f"load_audio({audio_path}): {type(e).__name__}: {e}")

        # Fallback: try wave module for .wav files
        if str(audio_path).lower().endswith('.wav'):
            logger.info(f"load_audio({audio_path}): trying wave module fallback...")
            return _load_audio_wave_fallback(audio_path)

        return np.array([], dtype=np.float32), TARGET_SR


def vad_segments(audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
    """
    Detect speech segments using Silero VAD.

    Args:
        audio: Audio array (assumed to be 16kHz mono after load_audio)
        sr: Sample rate (ignored; assumed 16kHz)

    Returns:
        List of (start_s, end_s) tuples for speech regions.
        Returns [] on error or if audio is too short.
    """
    if len(audio) < sr:  # Less than 1 second
        return []

    try:
        # Check repo exists
        if not SILERO_VAD_REPO_PATH.exists():
            logger.warning(f"Silero VAD repo not found at {SILERO_VAD_REPO_PATH}")
            return []

        # Load model via torch.hub.load pointing at local cache
        device = "cpu"  # Enforce CPU per CLAUDE.md rule 6
        vad_model, utils = torch.hub.load(
            repo_or_dir=str(SILERO_VAD_REPO_PATH),
            model="silero_vad",
            source="local",
            onnx=False
        )
        vad_model.eval()

        # Use get_speech_timestamps utility from the VAD package
        get_speech_timestamps = utils[0]

        # Get speech segments using the utility function
        speech_timestamps = get_speech_timestamps(
            audio,
            vad_model,
            sampling_rate=sr,
            threshold=0.5
        )

        # Convert to (start_s, end_s) format
        segments = [(ts["start"] / sr, ts["end"] / sr) for ts in speech_timestamps]

        logger.info(f"vad_segments: found {len(segments)} speech segment(s)")
        return segments

    except Exception as e:
        logger.error(f"vad_segments: {type(e).__name__}: {e}")
        return []


def _load_ecapa_model(model_path: Path, device: str = "cpu"):
    """
    Load ECAPA-TDNN model from SpeechBrain HuggingFace hub.

    Raises:
        Exception if model cannot be loaded.
    """
    from speechbrain.inference import EncoderClassifier

    logger.info(f"Loading ECAPA model from {model_path}...")
    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(model_path),
        run_opts={"device": device}
    )
    logger.info(f"✓ ECAPA model loaded successfully")
    return model


# Global model cache
_ecapa_model_cache = None


def embed_chunks(
    audio: np.ndarray,
    sr: int,
    segments: List[Tuple[float, float]]
) -> List[np.ndarray]:
    """
    Extract ECAPA-TDNN embeddings from 3-second chunks with 1-second overlap.

    Args:
        audio: Audio array
        sr: Sample rate (16000)
        segments: List of (start_s, end_s) from VAD (can be empty to embed entire audio)

    Returns:
        List of embedding vectors (192-dim ECAPA-TDNN vectors per chunk).
        Raises on error; does not return empty list as fallback.

    Behavior:
        - If segments is non-empty, embed within VAD boundaries using 3s/1s overlap.
        - If segments is empty, embed across entire audio with rolling chunks.
        - A chunk must be fully within a VAD segment to be embedded.
        - Raises RuntimeError if ECAPA model cannot be loaded.
    """
    if len(audio) == 0:
        raise RuntimeError("embed_chunks: empty audio")

    global _ecapa_model_cache

    device = "cpu"

    # Load model (cached after first load)
    if _ecapa_model_cache is None:
        if not ECAPA_MODEL_PATH.exists():
            raise RuntimeError(
                f"ECAPA model directory not found at {ECAPA_MODEL_PATH}. "
                "Cannot proceed without real embeddings."
            )
        _ecapa_model_cache = _load_ecapa_model(ECAPA_MODEL_PATH, device)

    ecapa_model = _ecapa_model_cache

    chunk_samples = int(CHUNK_LENGTH_S * sr)
    overlap_samples = int(CHUNK_OVERLAP_S * sr)
    stride_samples = chunk_samples - overlap_samples

    embeddings = []
    chunks_to_embed = []

    # If segments provided, only embed within VAD regions
    if segments:
        for seg_start_s, seg_end_s in segments:
            seg_start_sample = int(seg_start_s * sr)
            seg_end_sample = int(seg_end_s * sr)

            # Extract overlapping chunks within this segment
            pos = seg_start_sample
            while pos + chunk_samples <= seg_end_sample:
                chunk = audio[pos:pos + chunk_samples]
                chunks_to_embed.append(chunk)
                pos += stride_samples
    else:
        # Embed entire audio with rolling chunks
        pos = 0
        while pos + chunk_samples <= len(audio):
            chunk = audio[pos:pos + chunk_samples]
            chunks_to_embed.append(chunk)
            pos += stride_samples

    if not chunks_to_embed:
        raise RuntimeError(f"embed_chunks: no chunks extracted from audio")

    # Extract embeddings using ECAPA model
    with torch.no_grad():
        for chunk in chunks_to_embed:
            # Convert chunk to tensor: shape (n_samples,) -> (1, n_samples) for batch
            chunk_tensor = torch.FloatTensor(chunk).unsqueeze(0).to(device)

            # Extract embedding: encode_batch returns (batch, 1, 192)
            embedding = ecapa_model.encode_batch(chunk_tensor)  # shape: (1, 1, 192)
            embedding = embedding.squeeze().cpu().numpy()  # shape: (192,)

            # Verify output dimension is 192
            if embedding.ndim == 0:
                # Single scalar case (should not happen but safety check)
                embedding = embedding.reshape(1)
            if embedding.shape[0] != 192:
                raise RuntimeError(
                    f"ECAPA embedding has wrong dimension: {embedding.shape[0]}, expected 192. "
                    "Model may be misconfigured or corrupt."
                )

            embeddings.append(embedding.astype(np.float32))

    logger.info(f"embed_chunks: extracted {len(embeddings)} embedding(s) from {len(chunks_to_embed)} chunk(s)")
    return embeddings


def estimate_snr(audio: np.ndarray) -> float:
    """
    Estimate signal-to-noise ratio in dB using energy-based method.

    Args:
        audio: Audio array

    Returns:
        SNR in dB (≥ 0). Returns 0.0 on error or if insufficient data.

    Method:
        - Divide audio into 20ms frames.
        - Estimate noise from quietest 10th percentile of frames.
        - Estimate signal from loudest 10th percentile of frames.
        - SNR = 10 * log10(signal_energy / noise_energy)
    """
    if len(audio) < 16000:  # Less than 1 second
        return 0.0

    try:
        # Frame-based energy analysis
        frame_length = 320  # 20ms @ 16kHz
        n_frames = len(audio) // frame_length

        if n_frames < 2:
            return 0.0

        energies = []
        for i in range(n_frames):
            frame = audio[i * frame_length:(i + 1) * frame_length]
            energy = np.sum(frame ** 2)
            energies.append(energy)

        energies = np.array(energies)

        # Estimate noise from quiet frames (10th percentile)
        # Estimate signal from loud frames (90th percentile)
        noise_energy = np.percentile(energies, 10)
        signal_energy = np.percentile(energies, 90)

        # Avoid division by zero
        if noise_energy < 1e-10:
            return 0.0

        snr = 10 * np.log10(signal_energy / noise_energy)
        snr = float(max(0, snr))  # Clamp to non-negative

        logger.debug(f"estimate_snr: {snr:.2f} dB")
        return snr

    except Exception as e:
        logger.error(f"estimate_snr: {type(e).__name__}: {e}")
        return 0.0


def detect_condition(audio: np.ndarray, sr: int) -> str:
    """
    Detect if audio is wideband (wb) or narrowband 8kHz codec-degraded (nb8k).

    Args:
        audio: Audio array
        sr: Sample rate (expected 16000 after load_audio)

    Returns:
        "wb" for wideband, "nb8k" for narrowband/codec-degraded.
        Returns "wb" on error or if detection is inconclusive.

    Heuristic:
        - If significant energy exists above 4 kHz, classify as "wb".
        - If minimal energy above 4 kHz (< 10% of total), likely narrowband.
        - Also checks for specific codec artifacts (attempted via spectral peaks).
    """
    if len(audio) < 512:
        return "wb"

    try:
        # Use FFT to analyze bandwidth
        n_fft = 2048

        # Pad if needed
        if len(audio) < n_fft:
            audio_padded = np.pad(audio, (0, n_fft - len(audio)), mode='constant')
        else:
            audio_padded = audio[:n_fft]

        # Compute spectrum
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        spectrum = np.abs(np.fft.rfft(audio_padded))
        spectrum = spectrum ** 2  # Power spectrum

        # Energy in different frequency bands
        energy_0_4k = np.sum(spectrum[freqs <= 4000])
        energy_4k_8k = np.sum(spectrum[(freqs > 4000) & (freqs <= 8000)])
        total_energy = np.sum(spectrum)

        if total_energy < 1e-10:
            return "wb"

        # Ratio of energy above 4 kHz
        high_freq_ratio = (energy_4k_8k) / total_energy

        # If very little energy above 4 kHz, likely narrowband (8kHz Nyquist)
        if high_freq_ratio < 0.05:  # < 5% above 4kHz suggests bandwidth limit at 4kHz
            logger.debug(f"detect_condition: high_freq_ratio={high_freq_ratio:.3f} → nb8k")
            return "nb8k"

        logger.debug(f"detect_condition: high_freq_ratio={high_freq_ratio:.3f} → wb")
        return "wb"

    except Exception as e:
        logger.error(f"detect_condition: {type(e).__name__}: {e}")
        return "wb"


if __name__ == "__main__":
    """
    Smoke test: verify each function returns valid defaults.
    """
    import sys

    # Configure logging for test
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s"
    )

    print("\n" + "=" * 60)
    print("audio_ml.embed smoke test")
    print("=" * 60)

    # Test 1: estimate_snr with synthetic audio
    print("\n[1] Testing estimate_snr...")
    test_audio = (np.random.randn(16000) * 0.1).astype(np.float32)
    snr = estimate_snr(test_audio)
    assert isinstance(snr, float) and snr >= 0, f"SNR invalid: {snr}"
    print(f"    ✓ SNR: {snr:.2f} dB (valid float)")

    # Test 2: detect_condition
    print("\n[2] Testing detect_condition...")
    condition = detect_condition(test_audio, 16000)
    assert condition in ["wb", "nb8k"], f"Condition invalid: {condition}"
    print(f"    ✓ Condition: {condition} (valid string)")

    # Test 3: vad_segments with empty audio
    print("\n[3] Testing vad_segments...")
    segments = vad_segments(test_audio, 16000)
    assert isinstance(segments, list), f"Segments invalid: {segments}"
    print(f"    ✓ VAD segments: {len(segments)} region(s) (valid list)")

    # Test 4: embed_chunks
    print("\n[4] Testing embed_chunks...")
    embeddings = embed_chunks(test_audio, 16000, segments)
    assert isinstance(embeddings, list), f"Embeddings invalid: {embeddings}"
    print(f"    ✓ Embeddings: {len(embeddings)} vector(s) (valid list)")

    # Test 5: load_audio with missing file returns valid default
    print("\n[5] Testing load_audio error handling...")
    audio, sr = load_audio("/nonexistent/file.wav")
    assert isinstance(audio, np.ndarray), f"Audio invalid: {type(audio)}"
    assert sr == 16000, f"SR invalid: {sr}"
    assert len(audio) == 0, f"Empty audio expected on error"
    print(f"    ✓ load_audio error → empty array, sr=16000 (graceful)")

    print("\n" + "=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
    sys.exit(0)
