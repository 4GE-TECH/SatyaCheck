import { useRef } from 'react';
import { trustIntervals } from '../../lib/verdict';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';

/**
 * The trust score as a reference interval: the scale, its printed limits, and where this check landed.
 * The top interval is green only when this check could verify someone (identity check with a match);
 * otherwise it is neutral and reads "Unverified".
 */
export default function TrustScale({ score, verified }: { score: number; verified: boolean }) {
  const value = Math.max(0, Math.min(100, score));
  const zones = trustIntervals(verified);
  const root = useRef<HTMLDivElement>(null);
  const number = useRef<HTMLSpanElement>(null);

  useGSAP(() => {
    if (reducedMotion()) return;
    const counter = { v: 0 };
    gsap.timeline({ delay: 0.25 })
      .to(counter, { v: value, duration: 1.6, ease: 'expo.out', onUpdate: () => { if (number.current) number.current.textContent = String(Math.round(counter.v)); } }, 0)
      .fromTo('.scale-marker', { left: '0%' }, { left: `${value}%`, duration: 1.6, ease: EASE.out }, 0)
      .from('.scale-zone', { scaleX: 0, transformOrigin: '0% 50%', duration: 0.9, stagger: 0.08, ease: EASE.out }, 0);
  }, { scope: root, dependencies: [value] });

  return (
    <div className="trust-scale" ref={root}>
      <div className="trust-number" aria-label={`Trust score ${Math.round(value)} out of 100`}>
        <span className="num" ref={number}>{Math.round(value)}</span>
        <span className="trust-of">/100 trust</span>
      </div>
      <div className="scale" aria-hidden="true">
        <div className="scale-track">
          {zones.map(zone => (
            <span key={zone.label} className={`scale-zone tone-${zone.tone}`} style={{ left: `${zone.from}%`, width: `${zone.to - zone.from}%` }} />
          ))}
          <span className="scale-marker" style={{ left: `${value}%` }} />
        </div>
        <div className="scale-limits num">
          {[35, 60, 85].map(limit => <span key={limit} style={{ left: `${limit}%` }}>{limit}</span>)}
        </div>
        <div className="scale-labels">
          {zones.map(zone => <span key={zone.label} style={{ left: `${(zone.from + zone.to) / 2}%` }}>{zone.label}</span>)}
        </div>
      </div>
      <p className="trust-note">Higher means more trust. Not a probability, and never a guarantee.</p>
    </div>
  );
}
