import type { EnrolledPerson, ScreeningResponse } from '../types/contracts';

export interface PersonRecord extends EnrolledPerson {
  voiceprints?: { voiceprint_id: string; duration_s: number }[];
}

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const AUDIO_EXTENSIONS = /\.(wav|mp3|ogg|opus|webm|m4a|flac|aac|amr|mp4)$/i;

/** fetch with a timeout, caller abort, and the server's own error explanation surfaced. */
export async function request(path: string, options: RequestInit = {}, timeout = 120_000): Promise<Response> {
  const signal = AbortSignal.any([AbortSignal.timeout(timeout), ...(options.signal ? [options.signal] : [])]);
  let response: Response;
  try {
    response = await fetch(path, { ...options, signal });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error(signal.aborted
      ? 'The service is taking longer than expected. Please try again.'
      : 'Cannot reach the screening service. Check that it is running, then try again.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    throw new Error(detail || (response.status === 404
      ? 'That report could not be found on this service.'
      : `The request could not be completed (${response.status}). Please try again.`));
  }
  return response;
}

/** Rejects anything that is not a complete ScreeningResponse, so a malformed reply never becomes a verdict. */
export function parseScreening(data: unknown): ScreeningResponse {
  const d = data as ScreeningResponse;
  if (!d || typeof d.session_id !== 'string' || !d.quality || !d.fusion || !d.speaker || !d.spoof || !d.script || !d.transcript
    || !Number.isFinite(d.fusion.trust_score) || !Array.isArray(d.fusion.reason_codes)
    || !Array.isArray(d.fusion.recommended_actions) || !Array.isArray(d.spoof.timeline)
    || !Array.isArray(d.script.incriminating_markers) || !Array.isArray(d.script.exculpatory_markers)) {
    throw new Error('The service returned an incomplete result. No verdict is available; please try again.');
  }
  return d;
}

export function audioError(file: File): string | null {
  if (!file.size) return 'This recording is empty. Choose another audio file.';
  if (file.size > MAX_UPLOAD_BYTES) return 'Choose an audio file smaller than 50 MB.';
  if (!file.type.startsWith('audio/') && !AUDIO_EXTENSIONS.test(file.name)) {
    return 'Choose a supported recording, such as WAV, MP3, M4A or OGG.';
  }
  return null;
}

export async function screenFile(file: File, signal: AbortSignal): Promise<ScreeningResponse> {
  const body = new FormData();
  body.append('file', file);
  body.append('channel_type', 'upload');
  return parseScreening(await (await request('/api/screen', { method: 'POST', body, signal })).json());
}

export async function getScreening(id: string, signal?: AbortSignal): Promise<ScreeningResponse> {
  return parseScreening(await (await request(`/api/screen/${encodeURIComponent(id)}`, { signal }, 15_000)).json());
}

export async function getPeople(signal?: AbortSignal): Promise<PersonRecord[]> {
  const data: unknown = await (await request('/api/persons', { signal }, 12_000)).json();
  if (!Array.isArray(data) || data.some(p => !p || typeof p.person_id !== 'string' || typeof p.name !== 'string')) {
    throw new Error('The list of known voices could not be read. Please try again.');
  }
  return data;
}

export interface EnrollInput {
  name: string;
  relation: string;
  phone?: string;
  file: File;
  personId?: string | null;
  secret?: { question: string; answer: string } | null;
}

/** Enrollment succeeds only when the service confirms a stored voiceprint, never on status code alone. */
export async function enroll(input: EnrollInput, signal: AbortSignal): Promise<PersonRecord> {
  const body = new FormData();
  body.append('name', input.name);
  body.append('relation', input.relation);
  body.append('file', input.file);
  if (input.phone) body.append('phone_number', input.phone);
  if (input.personId) body.append('person_id', input.personId);
  if (input.secret) body.append('shared_secrets', JSON.stringify([input.secret]));
  const person = await (await request('/api/enroll', { method: 'POST', body, signal })).json() as PersonRecord;
  if (!person?.person_id || !Array.isArray(person.voiceprints) || !person.voiceprints.length) {
    throw new Error('The service did not confirm a saved voiceprint. Retry with a longer, clearer recording.');
  }
  return person;
}

export async function deletePerson(id: string): Promise<void> {
  await request(`/api/persons/${encodeURIComponent(id)}`, { method: 'DELETE' }, 12_000);
}

export type Health = 'checking' | 'online' | 'offline';

export async function checkHealth(signal: AbortSignal): Promise<Exclude<Health, 'checking'>> {
  try {
    const response = await fetch('/api/health', { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) });
    return response.ok ? 'online' : 'offline';
  } catch {
    return 'offline';
  }
}

export async function downloadReportPdf(sessionId: string): Promise<void> {
  const response = await request(`/api/report/${encodeURIComponent(sessionId)}/pdf`);
  if (!response.headers.get('content-type')?.includes('application/pdf')) {
    throw new Error('The service did not return a PDF. Use Print instead.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `satyacheck-${sessionId}.pdf`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
