/** Decoded mono audio, ready for drawing. */
export interface DecodedAudio {
  samples: Float32Array;
  sampleRate: number;
  duration: number;
}

/** Decodes a file in the browser. Returns null for formats the browser cannot decode (for example AMR). */
export async function decodeFile(file: File): Promise<DecodedAudio | null> {
  try {
    const bytes = await file.arrayBuffer();
    const context = new OfflineAudioContext(1, 1, 44_100);
    const buffer = await context.decodeAudioData(bytes);
    const samples = new Float32Array(buffer.length);
    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      const data = buffer.getChannelData(channel);
      for (let i = 0; i < data.length; i++) samples[i] += data[i] / buffer.numberOfChannels;
    }
    return { samples, sampleRate: buffer.sampleRate, duration: buffer.duration };
  } catch (error) {
    console.info('SatyaCheck: this browser could not decode the file for preview', error);
    return null;
  }
}

/** Min/max peaks per bucket, normalised to the loudest sample. */
export function peaks(samples: Float32Array, buckets: number): Float32Array {
  const out = new Float32Array(buckets * 2);
  const size = Math.max(1, Math.floor(samples.length / buckets));
  let loudest = 1e-6;
  for (let b = 0; b < buckets; b++) {
    let min = 0;
    let max = 0;
    const start = b * size;
    for (let i = start; i < Math.min(samples.length, start + size); i++) {
      const s = samples[i];
      if (s < min) min = s;
      if (s > max) max = s;
    }
    out[b * 2] = min;
    out[b * 2 + 1] = max;
    loudest = Math.max(loudest, -min, max);
  }
  for (let i = 0; i < out.length; i++) out[i] /= loudest;
  return out;
}

export interface Spectrogram { data: Uint8Array; columns: number; rows: number }

export function computeSpectrogram(audio: DecodedAudio, columns = 640, rows = 120): Promise<Spectrogram> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./spectrogram.worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = event => { resolve(event.data as Spectrogram); worker.terminate(); };
    worker.onerror = event => { reject(new Error(event.message)); worker.terminate(); };
    const copy = audio.samples.slice();
    worker.postMessage({ samples: copy, sampleRate: audio.sampleRate, columns, rows }, [copy.buffer]);
  });
}

/** Linear-interpolation resample of mono float samples. */
export function resample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const output = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < output.length; i++) {
    const position = i * ratio;
    const index = Math.floor(position);
    const next = Math.min(index + 1, input.length - 1);
    output[i] = input[index] + (input[next] - input[index]) * (position - index);
  }
  return output;
}

/** Encodes mono float samples as a self-contained 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

export function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function rms(samples: Float32Array): number {
  let total = 0;
  for (let i = 0; i < samples.length; i++) total += samples[i] * samples[i];
  return samples.length ? Math.sqrt(total / samples.length) : 0;
}

/**
 * The spectrogram colour ramp, from silence to loud: night, indigo, the logo's electric blue,
 * cyan, then near-white. Returns a 256-entry RGBA lookup table.
 */
export function colorRamp(light: boolean): Uint8ClampedArray {
  const stops: [number, [number, number, number, number]][] = light
    ? [[0, [245, 246, 252, 0]], [0.25, [200, 205, 250, 255]], [0.5, [96, 92, 245, 255]], [0.75, [40, 52, 210, 255]], [1, [10, 14, 70, 255]]]
    : [[0, [7, 8, 26, 0]], [0.22, [32, 26, 110, 255]], [0.5, [62, 70, 255, 255]], [0.78, [56, 196, 255, 255]], [1, [236, 248, 255, 255]]];
  const lut = new Uint8ClampedArray(256 * 4);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let k = 0;
    while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
    const [t0, c0] = stops[k];
    const [t1, c1] = stops[k + 1];
    const f = (t - t0) / (t1 - t0);
    for (let ch = 0; ch < 4; ch++) lut[i * 4 + ch] = c0[ch] + (c1[ch] - c0[ch]) * f;
  }
  return lut;
}
