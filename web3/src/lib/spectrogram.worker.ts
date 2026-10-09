/// <reference lib="webworker" />
/**
 * Computes a log-frequency magnitude spectrogram from mono samples.
 * Input:  { samples: Float32Array, sampleRate: number, columns: number, rows: number }
 * Output: { data: Uint8Array (rows × columns, row 0 = highest frequency), columns, rows }
 */

const FFT_SIZE = 1024;

function hann(size: number): Float32Array {
  const window = new Float32Array(size);
  for (let i = 0; i < size; i++) window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (size - 1));
  return window;
}

/** In-place iterative radix-2 FFT. */
function fft(re: Float32Array, im: Float32Array) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const angle = (-2 * Math.PI) / len;
    const wr = Math.cos(angle);
    const wi = Math.sin(angle);
    for (let i = 0; i < n; i += len) {
      let cr = 1;
      let ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k;
        const b = a + len / 2;
        const tr = re[b] * cr - im[b] * ci;
        const ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
        const next = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = next;
      }
    }
  }
}

self.onmessage = (event: MessageEvent<{ samples: Float32Array; sampleRate: number; columns: number; rows: number }>) => {
  const { samples, sampleRate, columns, rows } = event.data;
  const window = hann(FFT_SIZE);
  const re = new Float32Array(FFT_SIZE);
  const im = new Float32Array(FFT_SIZE);
  const bins = FFT_SIZE / 2;
  const magnitudes = new Float32Array(columns * rows);

  // Map each output row to an FFT bin on a log scale between 60 Hz and 8 kHz (or Nyquist).
  const minHz = 60;
  const maxHz = Math.min(8000, sampleRate / 2);
  const rowBin = new Int32Array(rows + 1);
  for (let r = 0; r <= rows; r++) {
    const hz = minHz * Math.pow(maxHz / minHz, r / rows);
    rowBin[r] = Math.min(bins - 1, Math.max(1, Math.round((hz / sampleRate) * FFT_SIZE)));
  }

  const hop = Math.max(1, (samples.length - FFT_SIZE) / Math.max(1, columns - 1));
  let peak = 1e-9;
  for (let c = 0; c < columns; c++) {
    const start = Math.floor(c * hop);
    for (let i = 0; i < FFT_SIZE; i++) {
      re[i] = (samples[start + i] ?? 0) * window[i];
      im[i] = 0;
    }
    fft(re, im);
    for (let r = 0; r < rows; r++) {
      const lo = rowBin[r];
      const hi = Math.max(lo + 1, rowBin[r + 1]);
      let sum = 0;
      for (let b = lo; b < hi; b++) sum += Math.hypot(re[b], im[b]);
      const value = Math.log10(1 + sum / (hi - lo));
      magnitudes[(rows - 1 - r) * columns + c] = value;
      if (value > peak) peak = value;
    }
  }

  // Normalise against the loudest cell with a floor, so quiet recordings stay legible.
  const floor = peak * 0.18;
  const data = new Uint8Array(columns * rows);
  for (let i = 0; i < data.length; i++) {
    const v = (magnitudes[i] - floor) / (peak - floor);
    data[i] = Math.round(Math.max(0, Math.min(1, v)) ** 1.15 * 255);
  }
  (self as unknown as Worker).postMessage({ data, columns, rows }, [data.buffer]);
};
