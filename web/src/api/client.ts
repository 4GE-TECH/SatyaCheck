import type { EnrolledPerson, ScreeningResponse } from '../types/contracts';

export interface PersonRecord extends EnrolledPerson {
  voiceprints?: { voiceprint_id: string; duration_s: number }[];
}

export async function request(path: string, options: RequestInit = {}, timeout = 120_000): Promise<Response> {
  const signal = AbortSignal.any([AbortSignal.timeout(timeout), ...(options.signal ? [options.signal] : [])]);
  let response: Response;
  try { response = await fetch(path, { ...options, signal }); }
  catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error(signal.aborted ? 'The check is taking longer than expected. Please try again.' : 'Cannot reach the screening service. Check the connection and try again.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    throw new Error(detail || (response.status === 404 ? 'This saved check could not be found.' : `The request could not be completed (${response.status}). Please try again.`));
  }
  return response;
}
export async function getPeople(signal?: AbortSignal): Promise<PersonRecord[]> {
  const data: unknown = await (await request('/api/persons', { signal }, 12_000)).json();
  if (!Array.isArray(data) || data.some(p => !p || typeof p.person_id !== 'string' || typeof p.name !== 'string')) throw new Error('The contact list could not be read. Please try again.');
  return data;
}
export async function deletePerson(id: string): Promise<void> {
  await request(`/api/persons/${encodeURIComponent(id)}`, { method: 'DELETE' }, 12_000);
}
export function parseScreening(data: unknown): ScreeningResponse {
  const d = data as ScreeningResponse;
  const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
  const fraction = (value: unknown) => finite(value) && value >= 0 && value <= 1;
  const text = (value: unknown): value is string => typeof value === 'string';
  const optionalText = (value: unknown) => value == null || text(value);
  const entries = <T>(value: unknown, valid: (entry: T) => boolean): boolean => Array.isArray(value) && value.every(entry => entry != null && valid(entry));
  if (!d || typeof d.session_id !== 'string' || !d.quality || !d.fusion || !d.speaker || !d.spoof || !d.script || !d.transcript
    || !d.session_id.trim() || !text(d.timestamp) || !Number.isFinite(Date.parse(d.timestamp))
    || !optionalText(d.audio_sha256) || !finite(d.processing_time_ms)
    || typeof d.quality.passed !== 'boolean' || !optionalText(d.quality.reason)
    || ![d.quality.speech_duration_s, d.quality.snr_db, d.quality.min_speech_threshold_s, d.quality.min_snr_threshold_db].every(finite)
    || !['match', 'mismatch', 'unknown'].includes(d.speaker.verdict) || !optionalText(d.speaker.matched_person_name)
    || typeof d.speaker.is_replay !== 'boolean'
    || !['identity_check', 'authority_check'].includes(d.fusion.mode)
    || !['verified', 'caution', 'suspicious', 'high_risk', 'unverified', 'insufficient'].includes(d.fusion.band)
    || !finite(d.fusion.trust_score) || d.fusion.trust_score < 0 || d.fusion.trust_score > 100
    || ![d.fusion.identity_risk, d.fusion.authenticity_risk, d.fusion.authenticity_risk_effective, d.fusion.intent_risk].every(fraction)
    || !d.fusion.weights_used || ![d.fusion.weights_used.asv_weight, d.fusion.weights_used.cm_weight, d.fusion.weights_used.text_weight].every(fraction)
    || !entries<ScreeningResponse['fusion']['reason_codes'][number]>(d.fusion.reason_codes, r => text(r.code) && text(r.signal) && text(r.value) && text(r.explanation) && text(r.severity) && optionalText(r.threshold) && optionalText(r.citation_title) && optionalText(r.citation_url))
    || !entries<string>(d.fusion.recommended_actions, text)
    || !optionalText(d.fusion.vernacular_warning) || (d.fusion.challenge_question != null && !text(d.fusion.challenge_question.question_text))
    || typeof d.spoof.is_synthetic !== 'boolean' || ![d.spoof.median_score, d.spoof.peak_score].every(fraction) || !finite(d.spoof.max_synth_run_s)
    || !entries<ScreeningResponse['spoof']['timeline'][number]>(d.spoof.timeline, s => finite(s.start_s) && s.start_s >= 0 && finite(s.end_s) && s.end_s >= s.start_s && fraction(s.score) && typeof s.is_synthetic === 'boolean')
    || !text(d.transcript.text) || !text(d.transcript.detected_language)
    || !optionalText(d.script.intent_summary)
    || !entries<ScreeningResponse['script']['playbooks'][number]>(d.script.playbooks, p => text(p.playbook_id) && text(p.title) && text(p.source_agency) && text(p.source_url) && finite(p.similarity_score))
    || !entries<ScreeningResponse['script']['incriminating_markers'][number]>(d.script.incriminating_markers, m => text(m.matched_text) && text(m.description) && text(m.category))
    || !entries<ScreeningResponse['script']['exculpatory_markers'][number]>(d.script.exculpatory_markers, m => text(m.matched_text) && text(m.description) && text(m.category)))
    throw new Error('The service returned an incomplete result. No verdict is available; please try again.');
  return d;
}
export async function getScreening(id: string, signal?: AbortSignal) {
  return parseScreening(await (await request(`/api/screen/${encodeURIComponent(id)}`, { signal }, 15_000)).json());
}
export function audioError(file: File): string | null {
  if (!file.size) return 'This recording is empty. Choose another audio file.';
  if (file.size > 50 * 1024 * 1024) return 'Choose an audio file smaller than 50 MB.';
  if (!file.type.startsWith('audio/') && !/\.(wav|mp3|ogg|opus|webm|m4a|flac|aac|amr|mp4)$/i.test(file.name)) return 'Choose a supported audio recording, such as WAV, MP3, M4A or OGG.';
  return null;
}

