import { useId } from 'react';
import './VoiceHero.css';

// Decorative acoustic geometry, never a measurement of the selected audio.
const ribbons = Array.from({ length: 34 }, (_, line) => Array.from({ length: 81 }, (_, step) => {
  const x = step * 7;
  const envelope = Math.sin(step / 80 * Math.PI);
  const y = 145 + Math.sin(step / 12 + line * .065) * (32 + line * 2.3) * envelope + (line - 17) * 2.15;
  return `${step === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
}).join(' '));

export default function VoiceHero() {
  const gradient = useId();
  return (
    <section className="voice-hero" aria-labelledby="voice-heading">
      <div className="voice-hero-copy">
        <p className="hero-eyebrow">A little clarity before you act</p>
        <h1 id="voice-heading">A familiar voice.<br /><span>A clearer picture.</span></h1>
        <p className="hero-description">Check a recording for signs of voice cloning and concerning requests. Understand the evidence. Choose your next step.</p>
      </div>
      <div className="acoustic-ribbon" aria-hidden="true">
        <svg viewBox="0 0 560 290" fill="none" focusable="false">
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="560" y2="220" gradientUnits="userSpaceOnUse">
              <stop stopColor="var(--ribbon-color)" stopOpacity="0" />
              <stop offset=".28" stopColor="var(--ribbon-color)" stopOpacity=".65" />
              <stop offset=".7" stopColor="var(--ribbon-color)" />
              <stop offset="1" stopColor="var(--ribbon-color)" stopOpacity=".12" />
            </linearGradient>
          </defs>
          {ribbons.map((d, index) => <path key={index} d={d} stroke={`url(#${gradient})`} strokeWidth="1.15" />)}
        </svg>
        <span>Listen beyond the familiar.</span>
      </div>
    </section>
  );
}
