import { gsap } from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';

gsap.registerPlugin(useGSAP, ScrollTrigger, SplitText);

/** The house curves. Everything settles; nothing bounces. */
export const EASE = {
  out: 'expo.out',
  soft: 'power3.out',
  inOut: 'power2.inOut',
} as const;

gsap.defaults({ ease: EASE.soft, duration: 0.6 });
// Several timelines target optional parts (a slice with no bars, a report with no wires).
gsap.config({ nullTargetWarn: false });

export function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export { gsap, useGSAP, ScrollTrigger, SplitText };
