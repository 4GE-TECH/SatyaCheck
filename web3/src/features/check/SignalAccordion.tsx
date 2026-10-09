import { useRef, useState } from 'react';
import { ChatCircleText, Fingerprint, Waveform } from '@phosphor-icons/react';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';

const SLICES = [
  {
    key: 'identity',
    icon: Fingerprint,
    title: 'Who is speaking?',
    rule: 'The voice is compared with people you enrolled. A stranger stays unverified, not guilty: banks and couriers are strangers too.',
  },
  {
    key: 'authenticity',
    icon: Waveform,
    title: 'Is the voice synthetic?',
    rule: 'Every moment is scored, so a cloned voice switched in mid-call still shows. Synthetic speech only counts when the request is alarming.',
  },
  {
    key: 'intent',
    icon: ChatCircleText,
    title: 'What is being asked?',
    rule: 'Secrecy, urgency and payment demands raise risk. Invitations to verify lower it. A real emergency asks you to check; a scam asks you not to.',
  },
] as const;

const BARS = [0.22, 0.28, 0.19, 0.31, 0.26, 0.72, 0.88, 0.94, 0.81, 0.3, 0.24, 0.2];

export default function SignalAccordion() {
  const [open, setOpen] = useState(1);
  const root = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const slices = gsap.utils.toArray<HTMLElement>('.slice', root.current);
    const wide = window.matchMedia('(min-width: 900px)').matches;
    const quick = reducedMotion();
    slices.forEach((slice, i) => {
      const active = i === open;
      if (wide) gsap.to(slice, { flexGrow: active ? 2.6 : 1, duration: quick ? 0 : 0.8, ease: EASE.out });
      gsap.to(slice.querySelector('.slice-body'), { autoAlpha: active || !wide ? 1 : 0, y: active || !wide ? 0 : 12, duration: quick ? 0 : 0.5, delay: active && !quick ? 0.15 : 0 });
    });
    if (quick) return;
    const current = slices[open];
    if (!current) return;
    const tl = gsap.timeline({ delay: 0.2 });
    tl.fromTo(current.querySelectorAll('.vp-b'), { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: 1.4, ease: EASE.inOut })
      .fromTo(current.querySelectorAll('.bar'), { scaleY: 0.05 }, { scaleY: 1, duration: 0.7, stagger: 0.04, ease: EASE.out, transformOrigin: '50% 100%' }, 0)
      .fromTo(current.querySelectorAll('.phrase mark'), { backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%', duration: 0.6, stagger: 0.35, ease: EASE.inOut }, 0.1);
  }, { dependencies: [open], scope: root });

  return (
    <div className="accordion" ref={root}>
      {SLICES.map((slice, i) => {
        const Icon = slice.icon;
        const active = i === open;
        return (
          <section key={slice.key} className={`slice slice-${slice.key}${active ? ' is-open' : ''}`} aria-labelledby={`slice-${slice.key}`}>
            <button
              type="button"
              id={`slice-${slice.key}`}
              className="slice-head"
              aria-expanded={active}
              aria-controls={`slice-body-${slice.key}`}
              onClick={() => setOpen(i)}
              onMouseEnter={() => { if (window.matchMedia('(pointer: fine)').matches) setOpen(i); }}
            >
              <Icon size={30} weight="light" aria-hidden="true" />
              <span>{slice.title}</span>
            </button>
            <div id={`slice-body-${slice.key}`} className="slice-body">
              <p>{slice.rule}</p>
              <figure className="slice-visual" aria-hidden="true">
                {slice.key === 'identity' && (
                  <svg viewBox="0 0 320 90" preserveAspectRatio="none">
                    <path className="vp-a" d="M0 45 C 20 10, 40 80, 60 45 S 100 15, 120 45 S 160 85, 180 45 S 220 5, 240 45 S 280 75, 320 45" />
                    <path className="vp-b" d="M0 45 C 20 14, 40 76, 60 45 S 100 19, 120 45 S 160 81, 180 45 S 220 9, 240 45 S 280 71, 320 45" />
                  </svg>
                )}
                {slice.key === 'authenticity' && (
                  <div className="bars">
                    <span className="bars-threshold" />
                    {BARS.map((v, b) => <span key={b} className={`bar${v >= 0.4 ? ' is-synth' : ''}`} style={{ height: `${v * 100}%` }} />)}
                  </div>
                )}
                {slice.key === 'intent' && (
                  <div className="phrases" lang="hi-Latn">
                    <p className="phrase">“<mark className="concern">Phone kisi ko mat dena</mark>, turant bhejo.”</p>
                    <p className="phrase">“Doctor se baat karo, <mark className="reassure">Papa ko call karo</mark>.”</p>
                  </div>
                )}
                <figcaption>Illustration</figcaption>
              </figure>
            </div>
          </section>
        );
      })}
    </div>
  );
}
