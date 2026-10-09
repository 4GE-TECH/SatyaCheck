import { useEffect, useRef } from 'react';
import { colorRamp, type Spectrogram } from '../lib/audio';

/** Draws a precomputed spectrogram, recolouring when the theme changes. */
export default function SpectrogramCanvas({ spectrogram, label }: { spectrogram: Spectrogram; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const paint = () => {
      const light = document.documentElement.dataset.theme === 'light';
      const lut = colorRamp(light);
      const { data, columns, rows } = spectrogram;
      node.width = columns;
      node.height = rows;
      const ctx = node.getContext('2d');
      if (!ctx) return;
      const image = ctx.createImageData(columns, rows);
      for (let i = 0; i < data.length; i++) {
        const v = data[i] * 4;
        image.data[i * 4] = lut[v];
        image.data[i * 4 + 1] = lut[v + 1];
        image.data[i * 4 + 2] = lut[v + 2];
        image.data[i * 4 + 3] = lut[v + 3];
      }
      ctx.putImageData(image, 0, 0);
    };
    paint();
    const watch = new MutationObserver(paint);
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => watch.disconnect();
  }, [spectrogram]);

  return <canvas ref={canvas} className="spectrogram" role="img" aria-label={label} />;
}

/** A scrolling spectrogram drawn live from an AnalyserNode. */
export function LiveSpectrogram({ analyser, label }: { analyser: AnalyserNode | null; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const ctx = node.getContext('2d', { willReadFrequently: false });
    if (!ctx) return;
    const rows = 160;
    const columns = 520;
    node.width = columns;
    node.height = rows;
    const light = () => document.documentElement.dataset.theme === 'light';
    let lut = colorRamp(light());
    const watch = new MutationObserver(() => { lut = colorRamp(light()); });
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    if (!analyser) {
      ctx.clearRect(0, 0, columns, rows);
      return () => watch.disconnect();
    }
    const bins = new Uint8Array(analyser.frequencyBinCount);
    const nyquist = analyser.context.sampleRate / 2;
    const column = ctx.createImageData(1, rows);
    // Log-frequency rows between 60 Hz and 8 kHz, matching the stored spectrograms.
    const rowBin = Array.from({ length: rows }, (_, r) => {
      const hz = 60 * Math.pow(8000 / 60, (rows - 1 - r) / (rows - 1));
      return Math.min(bins.length - 1, Math.round((hz / nyquist) * bins.length));
    });
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (now - last < 1000 / 45) return;
      last = now;
      analyser.getByteFrequencyData(bins);
      ctx.drawImage(node, -1, 0);
      for (let r = 0; r < rows; r++) {
        const v = Math.min(255, Math.round(Math.pow(bins[rowBin[r]] / 255, 1.4) * 255)) * 4;
        column.data[r * 4] = lut[v];
        column.data[r * 4 + 1] = lut[v + 1];
        column.data[r * 4 + 2] = lut[v + 2];
        column.data[r * 4 + 3] = lut[v + 3];
      }
      ctx.putImageData(column, columns - 1, 0);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); watch.disconnect(); };
  }, [analyser]);

  return <canvas ref={canvas} className="spectrogram live" role="img" aria-label={label} />;
}
