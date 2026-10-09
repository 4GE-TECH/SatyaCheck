import { useRef } from 'react';
import { ChatCircleText, Fingerprint, Waveform } from '@phosphor-icons/react';
import type { ScreeningResponse } from '../../types/contracts';
import { BANDS, displayBand, pct, signals, type SignalKey } from '../../lib/verdict';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';
import { FlagBadge } from '../../components/ui';

const ICONS: Record<SignalKey, typeof Fingerprint> = { identity: Fingerprint, authenticity: Waveform, intent: ChatCircleText };
const ROW = 96;

/** How the score was formed: each branch's risk, its weight in this check, and where they meet. */
export default function Fusion({ data }: { data: ScreeningResponse }) {
  const rows = signals(data);
  const band = displayBand(data);
  const tone = BANDS[band].tone;
  const insufficient = band === 'insufficient';
  const height = ROW * rows.length;
  const mid = height / 2;
  const root = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (reducedMotion()) return;
    const tl = gsap.timeline({ scrollTrigger: { trigger: root.current, start: 'top 80%', once: true } });
    tl.from('.fusion-signal', { x: -18, duration: 0.7, stagger: 0.09, ease: EASE.out })
      .fromTo('.fusion-wires', { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: 1.1, ease: EASE.inOut }, 0.2)
      .from('.fusion-result', { scale: 0.92, duration: 0.8, ease: 'back.out(1.6)' }, 0.85);
  }, { scope: root, dependencies: [data.session_id] });

  return (
    <div className="fusion" ref={root}>
      <ol className="fusion-signals">
        {rows.map(row => {
          const Icon = ICONS[row.key];
          return (
            <li key={row.key} className={`fusion-signal tone-${row.flag.tone}`}>
              <span className="fusion-icon"><Icon size={24} weight="light" aria-hidden="true" /></span>
              <div className="fusion-text">
                <span className="fusion-name">{row.name}</span>
                <span className="fusion-finding">{row.finding}</span>
                <span className="fusion-weight">{row.abstains ? 'Steps back in this check' : `Weight ${pct(row.weight)} of the score`}</span>
              </div>
              <div className="fusion-figures">
                <span className="num fusion-risk" aria-label={`Risk ${pct(row.risk)}`}>{Math.round(row.risk * 100)}</span>
                <FlagBadge flag={row.flag} />
              </div>
            </li>
          );
        })}
      </ol>

      <svg className="fusion-wires" viewBox={`0 0 200 ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {rows.map((row, i) => {
          const y = ROW * i + ROW / 2;
          return (
            <path
              key={row.key}
              d={`M0 ${y} C 110 ${y}, 90 ${mid}, 200 ${mid}`}
              className={`wire tone-${row.flag.tone}${row.abstains ? ' abstains' : ''}`}
              strokeWidth={1.5 + row.weight * 22}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      <div className={`fusion-result tone-${tone}`}>
        {insufficient
          ? <span className="fusion-result-value">—</span>
          : <span className="fusion-result-value num" aria-label={`Trust ${Math.round(data.fusion.trust_score)} out of 100`}>{Math.round(data.fusion.trust_score)}<small>/100</small></span>}
        <span className="fusion-result-band">{BANDS[band].label}</span>
        <span className="fusion-mode">{data.fusion.mode === 'authority_check' ? 'Authority check' : 'Identity check'}</span>
      </div>
    </div>
  );
}
