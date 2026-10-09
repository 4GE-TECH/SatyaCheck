import type { ScreeningResponse, EnrolledPerson, TrustBand } from './contracts';
export type Outcome<T> = { ok: true; data: T } | { ok: false; error: string };
export type Person = EnrolledPerson & { voiceprints?: { voiceprint_id: string; duration_s: number }[] };
export type Check = { result: ScreeningResponse; name: string; sample: boolean };

export async function request<T>(path: string, init: RequestInit = {}, timeout = 120000): Promise<Outcome<T>> {
  try {
    const signal = AbortSignal.any([AbortSignal.timeout(timeout), ...(init.signal ? [init.signal] : [])]);
    const response = await fetch(path, { ...init, signal });
    const data = await response.json().catch(() => null);
    if (!response.ok) return { ok: false, error: typeof data?.detail === 'string' ? data.detail : `The service could not complete this request (${response.status}). Please try again.` };
    if (data === null && response.status !== 204) return { ok: false, error: 'The service returned an unreadable response. Please try again.' };
    return { ok: true, data: data as T };
  } catch (error) {
    if (!init.signal?.aborted) console.warn('SatyaCheck service request failed', path, error);
    return { ok: false, error: init.signal?.aborted ? 'Request cancelled.' : 'The screening service is unavailable or took too long. Check the connection and try again.' };
  }
}

// Validate every nested field used by the interface. Incomplete evidence must
// never be rendered as a reassuring score or replaced with a sample result.
export function readResult(value: unknown): Outcome<ScreeningResponse> {
  const d = value as ScreeningResponse;
  const n = (v: unknown) => typeof v === 'number' && Number.isFinite(v);
  const t = (v: unknown) => typeof v === 'string';
  const f = (v: unknown) => n(v) && Number(v) >= 0 && Number(v) <= 1;
  const array = <T>(v: unknown, test: (item: T) => boolean): boolean => Array.isArray(v) && v.every(x => x != null && test(x));
  try {
    if (!d || !t(d.session_id) || !d.session_id || !t(d.timestamp) || !Number.isFinite(Date.parse(d.timestamp)) || !t(d.audio_sha256)
      || !n(d.processing_time_ms) || !d.quality || typeof d.quality.passed !== 'boolean'
      || ![d.quality.speech_duration_s, d.quality.snr_db, d.quality.min_speech_threshold_s, d.quality.min_snr_threshold_db].every(n)
      || (d.quality.reason != null && !t(d.quality.reason))
      || !['match','mismatch','unknown'].includes(d.speaker.verdict) || (d.speaker.matched_person_name != null && !t(d.speaker.matched_person_name))
      || !['identity_check','authority_check'].includes(d.fusion.mode) || !Object.keys(bands).includes(d.fusion.band)
      || !n(d.fusion.trust_score) || d.fusion.trust_score < 0 || d.fusion.trust_score > 100
      || ![d.fusion.identity_risk,d.fusion.authenticity_risk_effective,d.fusion.intent_risk,d.fusion.authenticity_risk].every(f)
      || !array<ScreeningResponse['fusion']['reason_codes'][number]>(d.fusion.reason_codes, r => t(r.code) && t(r.signal) && t(r.explanation) && t(r.value) && (r.threshold == null || t(r.threshold)) && (r.citation_title == null || t(r.citation_title)) && (r.citation_url == null || t(r.citation_url)))
      || !array<string>(d.fusion.recommended_actions, t)
      || (d.fusion.challenge_question != null && !t(d.fusion.challenge_question.question_text))
      || (d.fusion.vernacular_warning != null && !t(d.fusion.vernacular_warning))
      || !t(d.transcript.text) || !t(d.transcript.detected_language)
      || ![d.spoof.median_score,d.spoof.peak_score].every(f) || !n(d.spoof.max_synth_run_s)
      || !array<ScreeningResponse['spoof']['timeline'][number]>(d.spoof.timeline, s => n(s.start_s) && n(s.end_s) && s.start_s >= 0 && s.end_s >= s.start_s && f(s.score) && typeof s.is_synthetic === 'boolean')
      || (d.script.intent_summary != null && !t(d.script.intent_summary))
      || !array<ScreeningResponse['script']['incriminating_markers'][number]>(d.script.incriminating_markers, m => t(m.matched_text) && t(m.description))
      || !array<ScreeningResponse['script']['exculpatory_markers'][number]>(d.script.exculpatory_markers, m => t(m.matched_text) && t(m.description))) throw new Error('Incomplete screening evidence');
    return { ok: true, data: d };
  } catch (error) {
    console.warn('SatyaCheck rejected incomplete screening evidence', error);
    return { ok: false, error: 'The service returned incomplete evidence. No result is available. Please try again.' };
  }
}

export const bands: Record<TrustBand, { label: string; title: string; description: string; tone: string }> = {
  verified: { label: 'Voice verified', title: 'A familiar voice, recognised.', description: 'The voice matched an enrolled person. Still verify any unexpected request independently.', tone: 'positive' },
  caution: { label: 'Caution', title: 'Take a moment. Check the request.', description: 'Some signals deserve a closer look. Use a number you trust to confirm before acting.', tone: 'caution' },
  suspicious: { label: 'Suspicious signals', title: 'Something needs a second look.', description: 'Concerning patterns appeared in this recording. Verify independently before sharing money or information.', tone: 'danger' },
  high_risk: { label: 'High risk signals', title: 'Pause here. Verify independently.', description: 'Several signals raise concern. Avoid sending money or sharing codes while you verify the request.', tone: 'danger' },
  unverified: { label: 'Unverified caller', title: 'An unfamiliar voice. An open question.', description: 'No enrolled identity was verified. This is normal for genuine strangers and is not evidence of fraud on its own.', tone: 'neutral' },
  insufficient: { label: 'Insufficient audio', title: 'A little more clarity, please.', description: 'There is not enough clear speech to provide a score. Try a longer recording in a quieter place.', tone: 'neutral' },
};
export function bandFor(d: ScreeningResponse): TrustBand {
  if (!d.quality.passed || d.fusion.band === 'insufficient') return 'insufficient';
  if (d.fusion.band === 'verified' && (d.fusion.mode === 'authority_check' || d.speaker.verdict !== 'match')) return 'unverified';
  return d.fusion.band;
}
export function validateAudio(file: File): string | null {
  if (!file.size) return 'This audio file is empty. Choose another recording.';
  if (file.size > 50 * 1024 * 1024) return 'Choose a recording smaller than 50 MB.';
  if (!file.type.startsWith('audio/') && !/\.(wav|mp3|m4a|ogg|opus|webm|flac|aac|amr)$/i.test(file.name)) return 'Choose an audio file: WAV, MP3, M4A, OGG, OPUS, FLAC or AMR.';
  return null;
}
export function safeLink(value: string | null): string | null {
  try { const url = new URL(value || ''); return ['https:','http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
export function when(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }).format(date); }
export function time(seconds: number) { return `${Math.floor(seconds / 60).toString().padStart(2,'0')}:${Math.floor(seconds % 60).toString().padStart(2,'0')}`; }
