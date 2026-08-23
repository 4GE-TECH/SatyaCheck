"""
scripts/download_models.py

Downloads every model SatyaCheck needs into ./models/ so the demo runs with the
wifi switched off.

    python scripts/download_models.py            # download everything
    python scripts/download_models.py --verify   # load from cache only, no network

RUN THIS IN THE FIRST FIFTEEN MINUTES. Venue wifi will betray you at hour nine.
"""

from __future__ import annotations
import os
import sys
import argparse

MODELS_DIR = os.path.abspath("models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Point every HuggingFace-backed library at our local folder
os.environ["HF_HOME"] = os.path.join(MODELS_DIR, "hf")
os.environ["TORCH_HOME"] = os.path.join(MODELS_DIR, "torch")

OK, FAIL = [], []


def step(name):
    def deco(fn):
        def wrapper(verify: bool):
            print(f"  {name:<34} ", end="", flush=True)
            try:
                fn(verify)
                print("OK")
                OK.append(name)
            except Exception as e:
                print(f"FAILED  ({type(e).__name__}: {str(e)[:70]})")
                FAIL.append(name)
        return wrapper
    return deco


@step("ECAPA-TDNN speaker embedding")
def ecapa(verify: bool):
    from speechbrain.inference import EncoderClassifier
    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        # Removed savedir to bypass speechbrain symlinking on Windows.
        # HF_HOME is already set to models/hf, so it will cache there.
    )


@step("Silero VAD")
def silero(verify: bool):
    import torch
    torch.hub.load("snakers4/silero-vad", "silero_vad",
                   trust_repo=True, onnx=False)


@step("faster-whisper (small, int8)")
def whisper(verify: bool):
    from faster_whisper import WhisperModel
    WhisperModel("small", device="cpu", compute_type="int8",
                 download_root=os.path.join(MODELS_DIR, "whisper"))


@step("BGE-m3 text embedding")
def bge(verify: bool):
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("BAAI/bge-m3",
                        cache_folder=os.path.join(MODELS_DIR, "bge"))


@step("anti-spoof checkpoint")
def antispoof(verify: bool):
    # Member A: if this specific checkpoint 404s, swap the id for any
    # AASIST / wav2vec2-antispoofing model on the Hub. Take the FIRST one that
    # loads and returns sane scores — do not shop around, fusion gates it anyway.
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    mid = "MelodyMachine/Deepfake-audio-detection-V2"
    AutoFeatureExtractor.from_pretrained(mid, cache_dir=os.path.join(MODELS_DIR, "hf"))
    AutoModelForAudioClassification.from_pretrained(mid, cache_dir=os.path.join(MODELS_DIR, "hf"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="load from cache only; fails if anything needs the network")
    args = ap.parse_args()

    if args.verify:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        print("\nVERIFY MODE — offline. Turn your wifi off before trusting this.\n")
    else:
        print("\nDOWNLOADING to ./models — this takes several minutes.\n")

    for fn in (bge, antispoof, ecapa, silero, whisper):
        fn(args.verify)

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {', '.join(FAIL)}")
        if args.verify:
            print("Not cached. Re-run WITHOUT --verify while you still have wifi.")
        return 1

    print("ALL MODELS CACHED" if args.verify else "ALL MODELS DOWNLOADED")
    if not args.verify:
        print("\nNext: turn wifi OFF, then run")
        print("      python scripts/download_models.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
