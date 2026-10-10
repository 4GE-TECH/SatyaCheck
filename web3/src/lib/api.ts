import type { EnrolledPerson, IncidentReportPacket, ScreeningResponse } from '../types/contracts';
import { accessToken, authEnabled, signOut } from './auth';

/**
 * Where the backend lives. Empty means same origin: the Vite dev server proxies `/api`
 * (set SATYACHECK_BACKEND for the proxy target). A build that talks to a remote backend
 * directly sets VITE_SATYACHECK_BACKEND, and that backend must list this origin in
 * SATYACHECK_CORS_ORIGINS.
 */
const BACKEND = (import.meta.env?.VITE_SATYACHECK_BACKEND ?? '').replace(/\/+$/, '');

export function apiUrl(path: string): string {
  return `${BACKEND}${path}`;
}

/** WebSocket URL for an /api path: https becomes wss, http becomes ws. */
export function wsUrl(path: string): string {
  const base = BACKEND || window.location.origin;
  return `${base.replace(/^http/, 'ws')}${path}`;
}

export interface PersonRecord extends EnrolledPerson {
  /** Summaries only: the service never returns voice vectors or answer hashes. */
  voiceprints?: { voiceprint_id: string; condition?: string; duration_s: number; model_version?: string }[];
  phone_numbers?: string[];
  aliases?: string[];
}

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const AUDIO_EXTENSIONS = /\.(wav|mp3|ogg|opus|webm|m4a|flac|aac|amr|mp4)$/i;

/** fetch with a timeout, caller abort, and the server's own error explanation surfaced. */
export async function request(path: string, options: RequestInit = {}, timeout = 120_000): Promise<Response> {
  const signal = AbortSignal.any([AbortSignal.timeout(timeout), ...(options.signal ? [options.signal] : [])]);
  const token = await accessToken();
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...options, headers, signal });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error(signal.aborted
      ? 'The service is taking longer than expected. Please try again.'
      : 'Cannot reach the screening service. Check that it is running, then try again.');
  }
  if (response.status === 401) {
    if (authEnabled) void signOut();
    throw new Error('Your sign-in has expired. Sign in again to continue.');
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

export async function screenFile(file: File, signal: AbortSignal, claimedPersonId?: string | null): Promise<ScreeningResponse> {
  const body = new FormData();
  body.append('file', file);
  body.append('channel_type', 'upload');
  // "Who's calling?": a medium-trust claim the voice is checked against, never proof.
  if (claimedPersonId) body.append('claimed_identity', claimedPersonId);
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
  /** The person being enrolled agreed to voiceprint storage. A voiceprint is biometric data. */
  consent: boolean;
  /** Extra numbers they call from, and what callers call them ("Papa"). Hints, never proof. */
  phoneNumbers?: string[];
  aliases?: string[];
}

/** Enrollment succeeds only when the service confirms a stored voiceprint, never on status code alone. */
export async function enroll(input: EnrollInput, signal: AbortSignal): Promise<PersonRecord> {
  const body = new FormData();
  body.append('name', input.name);
  body.append('relation', input.relation);
  body.append('file', input.file);
  body.append('consent', String(input.consent));
  if (input.phone) body.append('phone_number', input.phone);
  if (input.personId) body.append('person_id', input.personId);
  if (input.secret) body.append('shared_secrets', JSON.stringify([input.secret]));
  for (const number of input.phoneNumbers ?? []) if (number.trim()) body.append('phone_numbers', number.trim());
  for (const alias of input.aliases ?? []) if (alias.trim()) body.append('aliases', alias.trim());
  const person = await (await request('/api/enroll', { method: 'POST', body, signal })).json() as PersonRecord;
  if (!person?.person_id || !Array.isArray(person.voiceprints) || !person.voiceprints.length) {
    throw new Error('The service did not confirm a saved voiceprint. Retry with a longer, clearer recording.');
  }
  return person;
}

export interface ScreeningListItem {
  session_id: string;
  created_at: string;
  status: string;
  channel_type: string | null;
  band: string | null;
  trust_score: number | null;
}

/** This account's screened calls, newest first. Pass the returned cursor for the next page. */
export async function listScreenings(cursor?: string | null, limit = 20, signal?: AbortSignal):
  Promise<{ items: ScreeningListItem[]; nextCursor: string | null }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  const data = await (await request(`/api/screen?${params}`, { signal }, 12_000)).json() as
    { items?: ScreeningListItem[]; next_cursor?: string | null };
  if (!Array.isArray(data?.items)) throw new Error('The list of reports could not be read. Please try again.');
  return { items: data.items, nextCursor: data.next_cursor ?? null };
}

/** Deletes the contact and their stored voiceprint. Resolves to whether a voiceprint file was removed. */
export async function deletePerson(id: string): Promise<{ voiceprintDeleted: boolean | null }> {
  const response = await request(`/api/persons/${encodeURIComponent(id)}`, { method: 'DELETE' }, 12_000);
  const body = await response.json().catch(() => null) as { voiceprint_deleted?: boolean } | null;
  return { voiceprintDeleted: typeof body?.voiceprint_deleted === 'boolean' ? body.voiceprint_deleted : null };
}

export type Health = 'checking' | 'online' | 'offline';

export interface HealthDetail {
  status: Exclude<Health, 'checking'>;
  /** False when the intent branch is running on keyword markers only (scam-pattern search is down). */
  retrievalAvailable: boolean | null;
  retrievalReason: string | null;
  realSpoof: boolean | null;
}

export async function checkHealth(signal: AbortSignal): Promise<HealthDetail> {
  const offline: HealthDetail = { status: 'offline', retrievalAvailable: null, retrievalReason: null, realSpoof: null };
  try {
    const response = await fetch(apiUrl('/api/health'), { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) });
    if (!response.ok) return offline;
    const body = await response.json().catch(() => ({})) as Record<string, unknown>;
    return {
      status: 'online',
      retrievalAvailable: typeof body.nlp_retrieval_available === 'boolean' ? body.nlp_retrieval_available : null,
      retrievalReason: typeof body.nlp_retrieval_reason === 'string' ? body.nlp_retrieval_reason : null,
      realSpoof: typeof body.use_real_spoof === 'boolean' ? body.use_real_spoof : null,
    };
  } catch {
    return offline;
  }
}

/** The incident report packet, including the tamper-evident log anchor when the call raised an alert. */
export async function getReportPacket(sessionId: string, signal?: AbortSignal): Promise<IncidentReportPacket | null> {
  try {
    const data = await (await request(`/api/report/${encodeURIComponent(sessionId)}`, { signal }, 15_000)).json();
    return data && typeof data === 'object' ? data as IncidentReportPacket : null;
  } catch {
    return null;
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
