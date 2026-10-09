import { useEffect, useRef } from 'react';

interface Props {
  /** Live microphone level, 0–1. */
  level?: number;
  /** Real min/max peaks of a chosen recording. When present, the field resolves into it. */
  waveform?: Float32Array | null;
  /** Sweeps a reading line across the waveform while a check runs. */
  scanning?: boolean;
  className?: string;
}

const LINES = 7;

function cssVar(name: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/**
 * The home screen's living surface. Ambient voice lines drift until there is real audio;
 * then they settle into the recording's actual waveform. Static under reduced motion.
 */
export default function VoiceField({ level = 0, waveform = null, scanning = false, className = '' }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const state = useRef({ level, waveform, scanning, morph: 0, pointer: 0.5, energy: 0 });

  useEffect(() => {
    state.current.level = level;
    state.current.waveform = waveform;
    state.current.scanning = scanning;
  }, [level, waveform, scanning]);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const ctx = node.getContext('2d');
    if (!ctx) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 0;
    let height = 0;
    let frame = 0;
    let visible = true;
    const started = performance.now();
    const colors = { c1: '', c2: '', c3: '' };
    const readColors = () => {
      colors.c1 = cssVar('--voice-1', '#3c56ff');
      colors.c2 = cssVar('--voice-2', '#7a5cff');
      colors.c3 = cssVar('--voice-3', '#39c6ff');
    };
    readColors();
    const themeWatch = new MutationObserver(readColors);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    const resize = () => {
      const rect = node.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = rect.width;
      height = rect.height;
      node.width = Math.round(width * dpr);
      node.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible && !reduced) loop(); });
    io.observe(node);
    const onPointer = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect();
      state.current.pointer = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    };
    node.addEventListener('pointermove', onPointer);

    const draw = (now: number) => {
      const s = state.current;
      const t = (now - started) / 1000;
      const { c1, c2, c3 } = colors;
      s.morph += ((s.waveform ? 1 : 0) - s.morph) * (reduced ? 1 : 0.06);
      s.energy += (s.level - s.energy) * 0.18;
      ctx.clearRect(0, 0, width, height);
      // Ambient lines ride high so prompts below them stay legible; the real waveform is centred.
      const mid = height * (0.28 + 0.22 * s.morph);
      const glow = document.documentElement.dataset.theme !== 'light';
      const gradient = ctx.createLinearGradient(0, 0, width, 0);
      gradient.addColorStop(0, c1);
      gradient.addColorStop(0.55, c2);
      gradient.addColorStop(1, c3);

      // Ambient voice lines: layered sines whose amplitude swells with the mic and the pointer.
      if (s.morph < 0.995) {
        ctx.globalAlpha = 1 - s.morph;
        for (let line = 0; line < LINES; line++) {
          const depth = line / (LINES - 1);
          ctx.beginPath();
          ctx.lineWidth = 1 + (1 - depth) * 1.4;
          ctx.strokeStyle = gradient;
          ctx.globalAlpha = (1 - s.morph) * (0.16 + (1 - depth) * 0.6);
          ctx.shadowBlur = glow && line === 0 ? 18 : 0;
          ctx.shadowColor = c3;
          for (let x = 0; x <= width; x += 4) {
            const u = x / width;
            const envelope = Math.sin(Math.PI * u) ** 1.6;
            const focus = 1 + 0.9 * Math.exp(-((u - s.pointer) ** 2) / 0.02);
            const amp = (height * (width < 520 ? 0.11 : 0.2) + s.energy * height * 0.3) * envelope * focus * (0.45 + depth * 0.55);
            const y = mid
              + Math.sin(u * (7 + line * 1.3) + t * (0.9 + line * 0.17)) * amp * 0.6
              + Math.sin(u * (17 - line) - t * 1.4 + line) * amp * 0.25 * (0.4 + s.energy);
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      }

      ctx.shadowBlur = 0;
      // The real recording: mirrored peak bars, resolving in from the centre outwards.
      if (s.waveform && s.morph > 0.005) {
        const buckets = s.waveform.length / 2;
        const bar = Math.max(2, width / buckets);
        ctx.globalAlpha = s.morph;
        ctx.fillStyle = gradient;
        const scanX = s.scanning ? ((t * 0.32) % 1) * width : -1;
        for (let b = 0; b < buckets; b++) {
          const x = b * bar;
          const distance = Math.abs(b / buckets - 0.5) * 2;
          const reveal = Math.max(0, Math.min(1, (s.morph - distance * 0.6) / 0.4));
          const top = Math.max(0.02, s.waveform[b * 2 + 1]) * height * 0.42 * reveal;
          const bottom = Math.max(0.02, -s.waveform[b * 2]) * height * 0.42 * reveal;
          const lit = scanX >= 0 && Math.abs(x - scanX) < 36;
          ctx.globalAlpha = s.morph * (lit ? 1 : s.scanning ? 0.45 : 0.9);
          ctx.fillRect(x + bar * 0.18, mid - top, bar * 0.64, top + bottom);
        }
        if (scanX >= 0) {
          ctx.globalAlpha = 1;
          const sweep = ctx.createLinearGradient(scanX - 60, 0, scanX + 2, 0);
          sweep.addColorStop(0, 'transparent');
          sweep.addColorStop(1, c3);
          ctx.fillStyle = sweep;
          ctx.fillRect(scanX - 60, 0, 62, height);
        }
      }
      ctx.globalAlpha = 1;
    };

    const loop = () => {
      cancelAnimationFrame(frame);
      const tick = (now: number) => {
        draw(now);
        if (visible && !reduced) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    };
    if (reduced) draw(performance.now()); else loop();
    const redrawStatic = reduced ? window.setInterval(() => draw(performance.now()), 500) : undefined;

    return () => {
      cancelAnimationFrame(frame);
      window.clearInterval(redrawStatic);
      observer.disconnect();
      io.disconnect();
      themeWatch.disconnect();
      node.removeEventListener('pointermove', onPointer);
    };
  }, []);

  return <canvas ref={canvas} className={`voice-field ${className}`.trim()} aria-hidden="true" />;
}
