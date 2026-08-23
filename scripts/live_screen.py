"""Screen a live conversation using the laptop microphone.

Why this exists
---------------
Android gives the microphone exclusively to the dialer during a call and hands every other
app digital silence. Measured on a Galaxy S23 FE running Android 16: 576,000 consecutive
samples captured during a live call, every one of them zero. No permission or audio source
changes that -- AudioSource.VOICE_CALL needs CAPTURE_AUDIO_OUTPUT, which is
signature|privileged, and Google closed third-party call recording in Android 10.

A machine that is not the one in the call is under no such restriction. Put the call on
speakerphone, let the laptop listen, and the pipeline gets real audio. This is also what the
product actually claims to do -- screen a call it is a bystander to -- so it is the honest
demo rather than a workaround for one.

Everything downstream is unchanged: the same 9-second windows with 3 seconds of overlap the
Android service produces, over the same /api/ws/screen socket, scored by the same fusion.

Usage
-----
    python -m scripts.live_screen                  # default mic, until Ctrl-C
    python -m scripts.live_screen --list-devices
    python -m scripts.live_screen --device 11 --seconds 60
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import time
import wave

import numpy as np

SAMPLE_RATE = 16_000
WINDOW_S = 9.0
OVERLAP_S = 3.0

# A live microphone always carries some self-noise. Exact zeros mean the OS substituted
# silence -- the failure mode that made the Android path look healthy while hearing nothing.
SILENCE_FLOOR = 2

BANDS = {
    "verified": "\033[92mVERIFIED\033[0m",
    "caution": "\033[93mCAUTION\033[0m",
    "suspicious": "\033[91mSUSPICIOUS\033[0m",
    "high_risk": "\033[91mHIGH RISK\033[0m",
    "unverified": "\033[90mUNVERIFIED\033[0m",
    "insufficient": "\033[90minsufficient\033[0m",
}


def to_wav(pcm: np.ndarray) -> bytes:
    """Wrap PCM16 in a RIFF header -- ffmpeg cannot infer rate or depth from raw bytes."""
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SAMPLE_RATE)
    w.writeframes(pcm.astype("<i2").tobytes())
    w.close()
    return buf.getvalue()


def list_devices() -> None:
    import sounddevice as sd

    print("input devices:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print("  [%2d] %s" % (i, d["name"][:60]))


def resample_to_16k(block: np.ndarray, src_rate: int) -> np.ndarray:
    """Linear resample to 16 kHz.

    Good enough for speech features at these ratios (44.1/48k -> 16k) and it avoids adding
    scipy for one call. ECAPA and Whisper both consume 16 kHz mono.
    """
    if src_rate == SAMPLE_RATE:
        return block.astype(np.int16)
    n_out = int(len(block) * SAMPLE_RATE / src_rate)
    if n_out <= 0:
        return np.zeros(0, dtype=np.int16)
    x_in = np.arange(len(block), dtype=np.float64)
    x_out = np.linspace(0, len(block) - 1, n_out)
    return np.interp(x_out, x_in, block.astype(np.float64)).astype(np.int16)


def pick_live_device(sd):
    """Return the input device that actually delivers signal, loudest first.

    Windows lists a dozen inputs and most of them are virtual or muted: on this machine
    seven of sixteen returned exact zeros. Choosing by name or by the system default picks
    one of those about as often as not.
    """
    best, best_rms = None, 0.0
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        rate = int(d["default_samplerate"])
        try:
            a = sd.rec(int(0.7 * rate), samplerate=rate, channels=1,
                       dtype="int16", device=i)
            sd.wait()
        except Exception:
            continue
        a = a[:, 0].astype(np.float64)
        rms = float(np.sqrt((a ** 2).mean())) if a.size else 0.0
        if rms > best_rms:
            best, best_rms = i, rms
    if best is not None:
        print("auto-selected input [%d] (rms=%.1f)" % (best, best_rms))
    return best


async def run(device, seconds, base: str) -> int:
    import sounddevice as sd
    import websockets

    window = int(SAMPLE_RATE * WINDOW_S)
    stride = int(SAMPLE_RATE * (WINDOW_S - OVERLAP_S))

    session = "laptop-%d" % int(time.time() * 1000)
    uri = base.replace("http", "ws") + "/api/ws/screen/" + session
    print("session  : " + session)
    print("backend  : " + uri)
    print("windows  : %.0fs every %.0fs\n" % (WINDOW_S, WINDOW_S - OVERLAP_S))

    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_audio(indata, frames, time_info, status):
        # Runs on sounddevice's own thread; hop back to the loop thread to enqueue.
        loop.call_soon_threadsafe(queue.put_nowait, indata[:, 0].copy())

    # Capture at the device's own rate and resample.
    #
    # Most laptop arrays refuse 16 kHz outright ("Invalid sample rate"), and the ones that
    # accept it are often virtual devices that return silence. Probing for a device that
    # actually delivers signal is the same lesson the Android path taught: a stream that
    # opens is not a stream that hears anything.
    if device is None:
        device = pick_live_device(sd)
        if device is None:
            print("no input device delivered audible signal -- check the mic is unmuted "
                  "and Windows lets this app use it", file=sys.stderr)
            return 1

    native = int(sd.query_devices(device)["default_samplerate"])
    print("device   : [%d] %s @ %d Hz\n"
          % (device, sd.query_devices(device)["name"][:48], native))

    try:
        stream = sd.InputStream(
            samplerate=native, channels=1, dtype="int16",
            device=device, blocksize=4096, callback=on_audio,
        )
    except Exception as exc:
        print("could not open the microphone: %s" % exc, file=sys.stderr)
        return 1

    async with websockets.connect(uri, max_size=None, open_timeout=15) as ws:

        async def reader() -> None:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "error":
                    print("  server: %s" % msg.get("detail"))
                    continue
                if msg.get("type") != "screening_update":
                    continue
                r = msg["response"]
                f = r.get("fusion", {})
                sp = r.get("speaker", {})
                tr = r.get("transcript", {})
                q = r.get("quality", {})
                band = BANDS.get(f.get("band", ""), f.get("band", "?"))
                print("\n  %s  trust=%s  mode=%s" % (band, f.get("trust_score"), f.get("mode")))
                print("  speaker : %s raw=%.4f -> %s" % (
                    sp.get("verdict"), sp.get("raw_score") or 0.0, sp.get("matched_person_name")))
                print("  quality : speech=%ss snr=%sdB" % (
                    q.get("speech_duration_s"), q.get("snr_db")))
                text = (tr.get("text") or "").strip()
                if text:
                    print("  heard   : %s" % text[:100])
                for rc in f.get("reason_codes", [])[:3]:
                    print("    - %s: %s" % (rc.get("code"), (rc.get("explanation") or "")[:70]))

        reader_task = asyncio.create_task(reader())
        buf = np.zeros(0, dtype=np.int16)
        index = 0
        started = time.time()

        with stream:
            print("listening -- put the call on speakerphone next to this machine")
            print("Ctrl-C to stop\n")
            try:
                while True:
                    if seconds and time.time() - started > seconds:
                        break
                    block = await queue.get()
                    buf = np.concatenate([buf, resample_to_16k(block, native)])

                    while len(buf) >= window:
                        w = buf[:window]
                        buf = buf[stride:]
                        peak = int(np.abs(w).max())
                        if peak <= SILENCE_FLOOR:
                            # Never send silence and call it evidence. This is the exact
                            # check whose absence hid the Android failure for hours.
                            print("  [%d] SILENT (peak=%d) -- wrong input device?"
                                  % (index, peak))
                            index += 1
                            continue
                        rms = float(np.sqrt((w.astype(np.float32) ** 2).mean()))
                        print("  [%d] sent 9.0s  peak=%5d rms=%7.1f" % (index, peak, rms))
                        await ws.send(json.dumps({
                            "type": "audio_chunk",
                            "session_id": session,
                            "chunk_index": index,
                            "audio_base64": base64.b64encode(to_wav(w)).decode(),
                            "is_final": False,
                        }))
                        index += 1
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

        reader_task.cancel()

    print("\nstopped after %d window(s)" % index)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--backend", default="http://localhost:8000")
    a = ap.parse_args()

    if a.list_devices:
        list_devices()
        return 0
    try:
        return asyncio.run(run(a.device, a.seconds, a.backend))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
