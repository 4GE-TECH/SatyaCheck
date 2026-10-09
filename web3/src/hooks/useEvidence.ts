import { useEffect, useState } from 'react';
import { computeSpectrogram, decodeFile, peaks, type Spectrogram } from '../lib/audio';

export interface Evidence {
  status: 'none' | 'loading' | 'ready' | 'unavailable';
  spectrogram: Spectrogram | null;
  waveform: Float32Array | null;
  duration: number;
  url: string | null;
}

const EMPTY: Evidence = { status: 'none', spectrogram: null, waveform: null, duration: 0, url: null };

/** Decodes a recording and computes its spectrogram off the main thread. */
export function useEvidence(file: File | null | undefined): Evidence {
  const [evidence, setEvidence] = useState<Evidence>(EMPTY);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    const url = URL.createObjectURL(file);
    queueMicrotask(() => { if (!cancelled) setEvidence({ ...EMPTY, status: 'loading', url }); });
    (async () => {
      const audio = await decodeFile(file);
      if (cancelled) return;
      if (!audio) { setEvidence({ ...EMPTY, status: 'unavailable', url }); return; }
      const waveform = peaks(audio.samples, 480);
      setEvidence({ status: 'loading', spectrogram: null, waveform, duration: audio.duration, url });
      try {
        const spectrogram = await computeSpectrogram(audio);
        if (!cancelled) setEvidence({ status: 'ready', spectrogram, waveform, duration: audio.duration, url });
      } catch {
        if (!cancelled) setEvidence({ status: 'ready', spectrogram: null, waveform, duration: audio.duration, url });
      }
    })();
    return () => {
      cancelled = true;
      URL.revokeObjectURL(url);
    };
  }, [file]);

  return file ? evidence : EMPTY;
}
