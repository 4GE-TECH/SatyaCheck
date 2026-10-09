import type { ScreeningResponse, TrustBand } from '../types/contracts';

export type Tone = 'success' | 'warning' | 'danger' | 'neutral';

export const bands: Record<TrustBand, { label: string; title: string; tone: Tone; description: string }> = {
  verified: {
    label: 'Voice verified',
    title: 'A familiar voice.',
    tone: 'success',
    description: 'The voice matches an enrolled person. Still verify unexpected requests independently.',
  },
  caution: {
    label: 'Caution',
    title: 'Take a moment to verify.',
    tone: 'warning',
    description: 'Some signals deserve a closer look. Confirm the request before acting.',
  },
  suspicious: {
    label: 'Suspicious signals',
    title: 'Check before you act.',
    tone: 'danger',
    description: 'The analysis found concerning signals. Use a trusted contact method to verify the request.',
  },
  high_risk: {
    label: 'High risk signals',
    title: 'Pause. Verify independently.',
    tone: 'danger',
    description: 'Several signals raise concern. Avoid sharing money or sensitive information while you verify.',
  },
  unverified: {
    label: 'Unverified',
    title: 'This voice is not verified.',
    tone: 'neutral',
    description: 'No enrolled identity was confirmed. An unfamiliar caller is not, by itself, a sign of fraud.',
  },
  insufficient: {
    label: 'Insufficient audio',
    title: 'Not enough speech to report.',
    tone: 'neutral',
    description: 'There is not enough usable speech for a reliable check. Try a longer, clearer recording.',
  },
};

/** The band shown to people. Unknown speakers and authority checks never display as verified. */
export function displayBand(data: ScreeningResponse): TrustBand {
  if (!data.quality.passed || data.fusion.band === 'insufficient') return 'insufficient';
  if (data.fusion.band === 'verified' && (data.fusion.mode === 'authority_check' || data.speaker.verdict !== 'match')) {
    return 'unverified';
  }
  return Object.hasOwn(bands, data.fusion.band) ? data.fusion.band : 'unverified';
}

/**
 * Trust-score reference intervals. Mirrors config.BAND_THRESHOLDS on risk
 * (0.15 / 0.40 / 0.65) through trust = (1 - risk) * 100.
 */
export const trustIntervals: { from: number; to: number; tone: Tone; label: string }[] = [
  { from: 0, to: 35, tone: 'danger', label: 'High risk' },
  { from: 35, to: 60, tone: 'danger', label: 'Suspicious' },
  { from: 60, to: 85, tone: 'warning', label: 'Caution' },
  { from: 85, to: 100, tone: 'success', label: 'Verified' },
];

export function reportIntervals(data: ScreeningResponse) {
  return data.fusion.mode === 'authority_check' || data.speaker.verdict !== 'match'
    ? [{ from: 0, to: 100, tone: 'neutral' as const, label: 'Identity unverified' }]
    : trustIntervals;
}

export type Flag = { mark: 'H' | 'L' | 'OK' | '—'; tone: Tone; label: string };

const flags = {
  high: { mark: 'H', tone: 'danger', label: 'Concern' },
  ok: { mark: 'OK', tone: 'success', label: 'Within expected' },
  none: { mark: '—', tone: 'neutral', label: 'Not assessed' },
  low: { mark: 'L', tone: 'warning', label: 'Below minimum' },
} satisfies Record<string, Flag>;

export interface SignalRow {
  key: 'identity' | 'authenticity' | 'intent';
  test: string;
  question: string;
  result: string;
  detail: string;
  risk: number | null;
  weight: number;
  flag: Flag;
  reference?: { observed: string; threshold: string; interval: { value: number; threshold: number } | null };
}

export function signalRows(data: ScreeningResponse): SignalRow[] {
  const { fusion, speaker, spoof, script } = data;
  const authority = fusion.mode === 'authority_check';
  const identityResult = speaker.verdict === 'match'
    ? `Match${speaker.matched_person_name ? ` · ${speaker.matched_person_name}` : ''}`
    : speaker.verdict === 'mismatch' ? 'Differs from the claimed voice' : 'No enrolled match';
  const incriminating = script.incriminating_markers.length;
  const reassuring = script.exculpatory_markers.length;
  const authenticityConcern = fusion.reason_codes.some(r => r.signal === 'authenticity' && ['high', 'critical'].includes(r.severity));
  const rows: SignalRow[] = [
    {
      key: 'identity',
      test: 'Identity',
      question: 'Who is speaking?',
      result: identityResult,
      detail: authority
        ? 'Authority check: identity abstains and is treated as neutral.'
        : `Compared with enrolled voices${speaker.is_replay ? ' · possible replayed recording' : ''}.`,
      risk: fusion.identity_risk,
      weight: fusion.weights_used.asv_weight,
      flag: speaker.verdict === 'mismatch' ? flags.high : speaker.verdict === 'match' ? flags.ok : flags.none,
    },
    {
      key: 'authenticity',
      test: 'Authenticity',
      question: 'Does it sound synthetic?',
      result: !spoof.timeline.length
        ? 'No segment evidence'
        : spoof.is_synthetic ? `Synthetic signal · ${number(spoof.max_synth_run_s, ' s')} longest run` : 'No sustained synthetic signal',
      detail: Math.abs(fusion.authenticity_risk - fusion.authenticity_risk_effective) > 0.005
        ? `Weighed against intent: ${percent(fusion.authenticity_risk)} raw, ${percent(fusion.authenticity_risk_effective)} counted.`
        : 'Synthetic speech counts in proportion to what is being asked.',
      risk: fusion.authenticity_risk_effective,
      weight: fusion.weights_used.cm_weight,
      flag: !spoof.timeline.length ? flags.none : authenticityConcern ? flags.high : spoof.is_synthetic
        ? { mark: '—', tone: 'neutral', label: 'Synthetic property detected; concern depends on intent' } : flags.ok,
    },
    {
      key: 'intent',
      test: 'Intent',
      question: 'What is being asked?',
      result: script.intent_summary
        || (incriminating ? `${incriminating} concerning ${plural(incriminating, 'phrase')}` : 'No concerning phrases'),
      detail: `${incriminating} concerning · ${reassuring} reassuring ${plural(reassuring, 'phrase')}.`,
      risk: fusion.intent_risk,
      weight: fusion.weights_used.text_weight,
      flag: incriminating ? flags.high : reassuring ? flags.ok : flags.none,
    },
  ];
  return rows.map(row => {
    const reason = fusion.reason_codes.find(r => r.signal === row.key && r.threshold);
    const observed = reason?.value.match(/(\d+(?:\.\d+)?)\s*%/);
    const threshold = reason?.threshold?.match(/^\s*[<>≤≥=]+\s*(\d+(?:\.\d+)?)\s*%\s*$/);
    const value = observed ? Number(observed[1]) : NaN;
    const limit = threshold ? Number(threshold[1]) : NaN;
    return { ...row, reference: reason ? {
      observed: reason.value,
      threshold: reason.threshold!,
      interval: value >= 0 && value <= 100 && limit >= 0 && limit <= 100 ? { value, threshold: limit } : null,
    } : undefined };
  });
}

export function qualityRows(data: ScreeningResponse) {
  const { quality } = data;
  return [
    {
      test: 'Usable speech',
      result: number(quality.speech_duration_s, ' s'),
      reference: `≥ ${number(quality.min_speech_threshold_s, ' s')}`,
      flag: quality.speech_duration_s >= quality.min_speech_threshold_s ? flags.ok : flags.low,
    },
    {
      test: 'Signal-to-noise',
      result: number(quality.snr_db, ' dB'),
      reference: `≥ ${number(quality.min_snr_threshold_db, ' dB')}`,
      flag: quality.snr_db >= quality.min_snr_threshold_db ? flags.ok : flags.low,
    },
  ] satisfies { test: string; result: string; reference: string; flag: Flag }[];
}

/** Splits a transcript into plain and highlighted runs for each matched marker phrase. */
export function highlightTranscript(data: ScreeningResponse): { text: string; kind?: 'concern' | 'reassure'; note?: string }[] {
  const text = data.transcript.text;
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
  const runs: { text: string; kind?: 'concern' | 'reassure'; note?: string }[] = [];
  let cursor = 0;
  for (const f of found) {
    if (f.start > cursor) runs.push({ text: text.slice(cursor, f.start) });
    runs.push({ text: text.slice(f.start, f.end), kind: f.kind, note: f.note });
    cursor = f.end;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor) });
  return runs;
}

export function number(value: number | undefined, suffix = '', digits = 1): string {
  return Number.isFinite(value) ? `${value!.toFixed(digits)}${suffix}` : 'Unavailable';
}

export function percent(value: number | null | undefined): string {
  return Number.isFinite(value) ? `${Math.round(Math.max(0, Math.min(1, value!)) * 100)}` : '—';
}

export function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}

export function date(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? 'Time unavailable'
    : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
}

export function language(code: string | undefined): string {
  if (!code) return 'Unknown';
  const base = code.toLowerCase().split(/[-_]/)[0];
  return ({ hi: 'Hindi', en: 'English', hinglish: 'Hinglish' } as Record<string, string>)[base] || code;
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

export function isDevanagari(text: string | null | undefined): boolean {
  return Boolean(text && /[ऀ-ॿ]/.test(text));
}

export function formatTime(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
