import { useEffect, useRef } from 'react';
import { ambient } from './AmbientField';

/**
 * A small live waveform set inside a headline, like an inline image in type. It idles as a
 * slow pulse and follows the shared microphone level whenever one is active.
 */
export default function InlineWave({ bars = 18 }: { bars?: number }) {
  const host = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const items = Array.from(node.querySelectorAll<HTMLElement>('i'));
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach((bar, i) => { bar.style.transform = `scaleY(${0.35 + 0.5 * Math.abs(Math.sin(i * 0.9))})`; });
      return;
    }
    let frame = 0;
    let visible = true;
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    io.observe(node);
    const started = performance.now();
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (!visible) return;
      const t = (now - started) / 1000;
      const energy = 0.25 + ambient.level * 0.9;
      items.forEach((bar, i) => {
        const envelope = Math.sin((Math.PI * (i + 0.5)) / items.length);
        const v = 0.18 + envelope * (0.35 + 0.4 * Math.abs(Math.sin(t * 2.1 + i * 0.55)) * (0.6 + energy));
        bar.style.transform = `scaleY(${Math.min(1, v).toFixed(3)})`;
      });
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); io.disconnect(); };
  }, [bars]);

  return (
    <span ref={host} className="inline-wave" aria-hidden="true">
      {Array.from({ length: bars }, (_, i) => <i key={i} />)}
    </span>
  );
}
