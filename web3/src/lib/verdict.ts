import type { ScreeningResponse, TrustBand } from '../types/contracts';

export type Tone = 'safe' | 'caution' | 'danger' | 'neutral';

export interface BandCopy {
  label: string;
  headline: string;
  tone: Tone;
  summary: string;
}

export const BANDS: Record<TrustBand, BandCopy> = {
  verified: {
    label: 'Voice verified',
    headline: 'This is a voice you know.',
    tone: 'safe',
    summary: 'The voice matches someone you enrolled. Still verify anything unexpected, like a payment request.',
  },
  caution: {
    label: 'Caution',
    headline: 'Take a moment to verify.',
    tone: 'caution',
    summary: 'Something here deserves a closer look. Confirm the request through a number you already trust.',
  },
  suspicious: {
    label: 'Suspicious',
    headline: 'Check before you act.',
    tone: 'danger',
    summary: 'The analysis found concerning signals. Call the person back on a number you trust before doing anything.',
  },
  high_risk: {
    label: 'High risk',
    headline: 'Pause. Verify independently.',
    tone: 'danger',
    summary: 'Several signals raise concern. Do not send money or share codes until you have verified the caller.',
  },
  unverified: {
    label: 'Unverified',
    headline: 'We don’t know this voice.',
    tone: 'neutral',
    summary: 'No enrolled person matched. That is normal for banks, couriers and doctors, and is not a sign of fraud on its own.',
  },
  insufficient: {
    label: 'Not enough audio',
    headline: 'Not enough speech to judge.',
    tone: 'neutral',
    summary: 'There was too little clear speech for a reliable check, so no score is given. Try a longer, clearer recording.',
  },
};

/** The band shown to people. Unknown voices and authority checks never display as verified. */
export function displayBand(data: ScreeningResponse): TrustBand {
  if (!data.quality.passed || data.fusion.band === 'insufficient') return 'insufficient';
  if (data.fusion.band === 'verified' && (data.fusion.mode === 'authority_check' || data.speaker.verdict !== 'match')) {
    return 'unverified';
  }
  return Object.hasOwn(BANDS, data.fusion.band) ? data.fusion.band : 'unverified';
}

/**
 * Reference intervals for the trust score. Mirrors config.BAND_THRESHOLDS on fused risk
 * (0.15 / 0.40 / 0.65) through trust = (1 − risk) × 100. The top interval is green only when
 * a known voice was actually verified; otherwise it is neutral, because nobody was verified.
 */
export function trustIntervals(verified: boolean): { from: number; to: number; tone: Tone; label: string }[] {
  return [
    { from: 0, to: 35, tone: 'danger', label: 'High risk' },
    { from: 35, to: 60, tone: 'danger', label: 'Suspicious' },
    { from: 60, to: 85, tone: 'caution', label: 'Caution' },
    verified ? { from: 85, to: 100, tone: 'safe', label: 'Verified' } : { from: 85, to: 100, tone: 'neutral', label: 'Unverified' },
  ];
}

/** Per-segment synthetic threshold. Mirrors config.CM_SYNTHETIC_THRESHOLD. */
export const SYNTH_THRESHOLD = 0.4;

export type FlagMark = 'H' | 'L' | 'OK' | '—';
export interface Flag { mark: FlagMark; tone: Tone; label: string }

// Labels are what people read on screen: words, not letters, for the three-metre read.
const FLAG = {
  high: { mark: 'H', tone: 'danger', label: 'Concern' },
  low: { mark: 'L', tone: 'caution', label: 'Below minimum' },
  ok: { mark: 'OK', tone: 'safe', label: 'Expected' },
  none: { mark: '—', tone: 'neutral', label: 'Not assessed' },
  heldBack: { mark: '—', tone: 'neutral', label: 'Not trusted' },
} satisfies Record<string, Flag>;

/**
 * A voiceprint match counts as verification only when the voice itself is not flagged as
 * synthetic or replayed. A clone that matches the voiceprint is the attack, not reassurance.
 */
export function trustedMatch(data: ScreeningResponse): boolean {
  return data.speaker.verdict === 'match' && !data.spoof.is_synthetic && !data.speaker.is_replay;
}

/** Whether green ("Verified") is reachable at all for this check. */
export function verifiable(data: ScreeningResponse): boolean {
  return data.fusion.mode !== 'authority_check' && trustedMatch(data);
}

export function identityText(data: ScreeningResponse): string {
  const name = data.speaker.matched_person_name || 'an enrolled voice';
  if (data.speaker.verdict === 'match') return trustedMatch(data) ? `Matches ${name}` : `Sounds like ${name}`;
  return data.speaker.verdict === 'mismatch' ? 'Differs from the claimed person' : 'No enrolled voice matched';
}

export type SignalKey = 'identity' | 'authenticity' | 'intent';

export interface Signal {
  key: SignalKey;
  name: string;
  question: string;
  finding: string;
  detail: string;
  risk: number;
  weight: number;
  flag: Flag;
  abstains: boolean;
}

/** The three branches as the person reads them, derived only from contract fields. */
export function signals(data: ScreeningResponse): Signal[] {
  const { fusion, speaker, spoof, script } = data;
  const authority = fusion.mode === 'authority_check';
  const concerns = script.incriminating_markers.length;
  const reassurances = script.exculpatory_markers.length;
  const gated = Math.abs(fusion.authenticity_risk - fusion.authenticity_risk_effective) > 0.005;
  return [
    {
      key: 'identity',
      name: 'Identity',
      question: 'Who is speaking?',
      finding: identityText(data),
      detail: authority
        ? 'No one you know is speaking, so identity steps back and counts as neutral.'
        : speaker.verdict === 'match' && !trustedMatch(data)
          ? 'A synthetic or replayed voice can imitate someone you know, so this match is not trusted.'
          : 'Compared with the voices you enrolled.',
      risk: clamp(fusion.identity_risk),
      weight: fusion.weights_used.asv_weight,
      flag: speaker.verdict === 'mismatch' ? FLAG.high : speaker.verdict === 'match' ? (trustedMatch(data) ? FLAG.ok : FLAG.heldBack) : FLAG.none,
      abstains: authority,
    },
    {
      key: 'authenticity',
      name: 'Authenticity',
      question: 'Is the voice synthetic?',
      finding: !spoof.timeline.length
        ? 'No segment evidence returned'
        : spoof.is_synthetic ? `Synthetic for ${seconds(spoof.max_synth_run_s)} straight` : 'No sustained synthetic speech',
      detail: gated
        ? `Counted at ${pct(fusion.authenticity_risk_effective)} of its ${pct(fusion.authenticity_risk)} raw risk, because what was asked is not alarming.`
        : 'Synthetic speech only counts in proportion to what is being asked.',
      risk: clamp(fusion.authenticity_risk_effective),
      weight: fusion.weights_used.cm_weight,
      flag: !spoof.timeline.length ? FLAG.none : spoof.is_synthetic ? FLAG.high : FLAG.ok,
      abstains: false,
    },
    {
      key: 'intent',
      name: 'Intent',
      question: 'What is being asked?',
      finding: script.intent_summary || (concerns ? `${concerns} concerning ${plural(concerns, 'phrase')}` : 'Nothing concerning was asked'),
      detail: `${concerns} concerning and ${reassurances} reassuring ${plural(reassurances, 'phrase')} found.`,
      risk: clamp(fusion.intent_risk),
      weight: fusion.weights_used.text_weight,
      flag: concerns ? FLAG.high : reassurances ? FLAG.ok : FLAG.none,
      abstains: false,
    },
  ];
}

/** Every measurement with its reference and flag, in one table: recording quality, then synthetic speech. */
export function measurements(data: ScreeningResponse) {
  const q = data.quality;
  const sp = data.spoof;
  const hasSegments = sp.timeline.length > 0;
  const synthFlag = (value: number) => (!hasSegments ? FLAG.none : value >= SYNTH_THRESHOLD ? FLAG.high : FLAG.ok);
  return [
    {
      name: 'Usable speech',
      value: seconds(q.speech_duration_s),
      reference: `at least ${seconds(q.min_speech_threshold_s)}`,
      flag: q.speech_duration_s >= q.min_speech_threshold_s ? FLAG.ok : FLAG.low,
    },
    {
      name: 'Signal-to-noise',
      value: `${fixed(q.snr_db)} dB`,
      reference: `at least ${fixed(q.min_snr_threshold_db)} dB`,
      flag: q.snr_db >= q.min_snr_threshold_db ? FLAG.ok : FLAG.low,
    },
    {
      name: 'Median synthetic score',
      value: hasSegments ? pct(sp.median_score) : '—',
      reference: `below ${pct(SYNTH_THRESHOLD)}`,
      flag: synthFlag(sp.median_score),
    },
    {
      name: 'Peak synthetic score',
      value: hasSegments ? pct(sp.peak_score) : '—',
      reference: `below ${pct(SYNTH_THRESHOLD)}`,
      flag: synthFlag(sp.peak_score),
    },
    {
      name: 'Longest synthetic run',
      value: hasSegments ? seconds(sp.max_synth_run_s) : '—',
      reference: '0 s in natural speech',
      flag: !hasSegments ? FLAG.none : sp.max_synth_run_s > 0 ? FLAG.high : FLAG.ok,
    },
  ];
}

/**
 * Some reply templates shout ("DO NOT transfer money"). Shown calmly here; acronyms such as UPI
 * and OTP keep their capitals. The template text itself belongs to nlp_rag.
 */
export function calm(text: string): string {
  const softened = text.replace(/\b(DO|NOT|NEVER|DON'T|DONT|STOP|PLEASE|IMMEDIATELY|ANY|NO)\b/g, word => word.toLowerCase());
  return softened.charAt(0).toUpperCase() + softened.slice(1);
}

export interface TranscriptRun { text: string; kind?: 'concern' | 'reassure'; note?: string }

/** Splits text into plain runs and runs matching a marker phrase. Overlapping matches keep the first. */
export function markPhrases(text: string, data: ScreeningResponse): TranscriptRun[] {
  if (!text) return [];
  const marks = [
    ...data.script.incriminating_markers.map(m => ({ phrase: m.matched_text, kind: 'concern' as const, note: m.description || m.category })),
    ...data.script.exculpatory_markers.map(m => ({ phrase: m.matched_text, kind: 'reassure' as const, note: m.description || m.category })),
  ];
  const lower = text.toLocaleLowerCase();
  const found: { start: number; end: number; kind: 'concern' | 'reassure'; note: string }[] = [];
  for (const mark of marks) {
    const phrase = mark.phrase?.trim();
    if (!phrase) continue;
    const start = lower.indexOf(phrase.toLocaleLowerCase());
    if (start < 0 || found.some(f => start < f.end && start + phrase.length > f.start)) continue;
    found.push({ start, end: start + phrase.length, kind: mark.kind, note: mark.note });
  }
  found.sort((a, b) => a.start - b.start);
  const runs: TranscriptRun[] = [];
  let cursor = 0;
  for (const f of found) {
    if (f.start > cursor) runs.push({ text: text.slice(cursor, f.start) });
    runs.push({ text: text.slice(f.start, f.end), kind: f.kind, note: f.note });
    cursor = f.end;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor) });
  return runs;
}

/** Total length of the evidence: the furthest end among spoof segments and transcript segments. */
export function evidenceDuration(data: ScreeningResponse): number {
  return Math.max(0, ...data.spoof.timeline.map(s => s.end_s), ...data.transcript.segments.map(s => s.end_s));
}

export function clamp(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
}
export function pct(value: number): string {
  return `${Math.round(clamp(value) * 100)}%`;
}
export function fixed(value: number | undefined, digits = 1): string {
  return Number.isFinite(value) ? value!.toFixed(digits) : '—';
}
export function seconds(value: number | undefined): string {
  return Number.isFinite(value) ? `${value!.toFixed(1)} s` : '—';
}
export function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}
export function clock(total: number): string {
  const safe = Math.max(0, Math.floor(total));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}
export function when(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? 'Time unavailable'
    : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
}
export function languageName(code: string | undefined): string {
  const base = (code || '').toLowerCase().split(/[-_]/)[0];
  return ({ hi: 'Hindi', en: 'English', hinglish: 'Hinglish' } as Record<string, string>)[base] || code || 'Unknown';
}
export function isDevanagari(text: string | null | undefined): boolean {
  return Boolean(text && /[ऀ-ॿ]/.test(text));
}
export function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function reportText(data: ScreeningResponse, sample: boolean): string {
  const band = displayBand(data);
  return [
    sample ? 'SAMPLE — DEMONSTRATION ONLY' : null,
    'SatyaCheck screening report',
    `Session: ${data.session_id}`,
    `Received: ${when(data.timestamp)}`,
    `Result: ${BANDS[band].label}`,
    `Trust score: ${band === 'insufficient' ? 'not given (insufficient speech)' : `${Math.round(data.fusion.trust_score)}/100, not a probability`}`,
    `Audio SHA-256: ${sample ? 'sample digest' : data.audio_sha256 || 'not supplied'}`,
    '',
    'Findings',
    ...signals(data).map(s => `- ${s.name}: ${s.finding} (risk ${pct(s.risk)}, weight ${pct(s.weight)}, flag ${s.flag.mark})`),
    '',
    'Evidence',
    ...(data.fusion.reason_codes.length
      ? data.fusion.reason_codes.map(r => `- ${r.explanation}\n  Observed ${r.value}; threshold ${r.threshold || 'not supplied'}; source ${r.citation_title || 'not supplied'} ${r.citation_url || ''}`.trimEnd())
      : ['- None returned']),
    '',
    'Transcript (automatic; may contain errors)',
    data.transcript.text || 'Not available',
    '',
    'Recommended actions',
    ...(data.fusion.recommended_actions.length ? data.fusion.recommended_actions.map(a => `- ${a}`) : ['- Verify through a number you already trust.']),
    '',
    'This is a screening summary, not an official complaint or a determination of fraud.',
  ].filter(line => line !== null).join('\n');
}
