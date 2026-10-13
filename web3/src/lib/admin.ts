import { useEffect, useRef, useState } from 'react';
import type { ScreeningResponse, TrustBand } from '../types/contracts';
import { parseScreening, request, wsUrl } from './api';
import { accessToken } from './auth';

/**
 * The admin console's API (server/admin_router.py). Every account's calls, read-only, for
 * accounts listed in the server's ADMIN_USER_IDS. The server logs every view.
 */

export interface Who { user_id: string | null; username: string | null; display_name: string | null }

export function whoLabel(who: Who | null | undefined): string {
  if (!who?.user_id) return 'Unknown account';
  if (who.username) return `@${who.username}`;
  return `Account ${who.user_id.slice(0, 8)}…`;
}

export interface Overview {
  calls: { ringing: number; active: number };
  live_sessions: number | null;
  max_live_sessions: number | null;
  screenings_24h: number;
  bands_24h: Record<string, number>;
  accounts_with_calls: number;
  accounts_with_username: number;
  device: string | null;
  ready: boolean | null;
  problems: string[];
  webrtc_enabled: boolean;
}

/** What a listener is being shown about one voice right now (the bounded WebRTC packet). */
export interface VoiceState {
  rev: number;
  display_band: TrustBand;
  trust_score: number | null;
  mode: string | null;
  screening_available: boolean;
  reason: string | null;
  reasons: { code: string; explanation: string }[];
  alerts: { alert_id: string; band: TrustBand; at_s: number; resolved: boolean; evidence: string | null }[];
  coverage: { screened_s: number; unscreened_s: number; degraded: boolean } | null;
  transcript_tail: string;
}

export interface LiveCall {
  call_id: string;
  status: 'ringing' | 'active';
  age_s: number;
  in_call_s: number | null;
  caller: Who;
  callee: Who;
  screening: boolean;
  voices: { session_id: string; speaker_id: string; listener_id: string; state: VoiceState | null }[];
}

export interface CallRow {
  session_id: string;
  created_at: string | null;
  status: string;
  channel_type: string | null;
  owner: Who;
  band?: TrustBand | null;
  trust_score?: number | null;
  mode?: string | null;
  transcript_preview?: string;
}

export interface CallDetail {
  session_id: string;
  owner: Who;
  channel_type: string | null;
  status: string;
  created_at: string | null;
  response: ScreeningResponse | null;
  timeline: { chunk_index: number; is_final: boolean; at: string | null; band: TrustBand | null; trust_score: number | null }[];
}

export interface UserRow extends Who {
  calls: number;
  enrolled_voices: number;
  connections: number;
  last_call_at: string | null;
  admin: boolean;
}

/** null when this account is signed in but is not an admin (403). Throws on other failures. */
export async function adminMe(signal?: AbortSignal): Promise<{ user_id: string } | null> {
  try {
    return await (await request('/api/admin/me', { signal }, 12_000)).json();
  } catch (problem) {
    if (problem instanceof Error && /administrators/.test(problem.message)) return null;
    throw problem;
  }
}

export async function getOverview(signal?: AbortSignal): Promise<Overview> {
  return (await request('/api/admin/overview', { signal }, 12_000)).json();
}

export async function getLiveCalls(signal?: AbortSignal): Promise<LiveCall[]> {
  return (await (await request('/api/admin/calls/live', { signal }, 8_000)).json()).calls ?? [];
}

export async function getCalls(params: { cursor?: string | null; owner?: string | null; channel?: string | null; limit?: number },
  signal?: AbortSignal): Promise<{ items: CallRow[]; nextCursor: string | null }> {
  const q = new URLSearchParams({ limit: String(params.limit ?? 30) });
  if (params.cursor) q.set('cursor', params.cursor);
  if (params.owner) q.set('owner', params.owner);
  if (params.channel) q.set('channel', params.channel);
  const data = await (await request(`/api/admin/screenings?${q}`, { signal }, 15_000)).json();
  if (!Array.isArray(data?.items)) throw new Error('The call list could not be read. Please try again.');
  return { items: data.items, nextCursor: data.next_cursor ?? null };
}

export async function getCallDetail(sessionId: string, signal?: AbortSignal): Promise<CallDetail> {
  const data = await (await request(`/api/admin/screenings/${encodeURIComponent(sessionId)}`, { signal }, 15_000)).json();
  return { ...data, response: data.response ? parseScreening(data.response) : null };
}

export async function getUsers(signal?: AbortSignal): Promise<UserRow[]> {
  return (await (await request('/api/admin/users', { signal }, 12_000)).json()).users ?? [];
}

/** One verdict from the admin live feed: the documented live-feed message plus its account. */
export interface FeedVerdict {
  type: 'verdict';
  session_id: string;
  owner_id: string | null;
  window_index: number;
  is_final: boolean;
  band: TrustBand;
  trust_score: number;
  mode: string;
  transcript: string;
  language: string;
  signals: { identity: string; authenticity: string; intent_risk: number };
  reason_codes: { code: string; explanation: string; severity: string }[];
  received_at: number;
}

export type FeedStatus = 'connecting' | 'open' | 'reconnecting' | 'refused';

/** How long a session that has gone quiet stays on the live page. */
const KEEP_MS = 10 * 60 * 1000;

/**
 * Every verdict from every account, as it happens (/api/admin/ws/live). Keeps the latest
 * verdict per session; sessions quiet for ten minutes drop off. Signs in with the first
 * message, never the URL. Reconnects with backoff; a refusal (not an admin) does not retry.
 */
export function useAdminFeed(): { sessions: FeedVerdict[]; status: FeedStatus } {
  const [sessions, setSessions] = useState<Map<string, FeedVerdict>>(new Map());
  const [status, setStatus] = useState<FeedStatus>('connecting');
  const retry = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let stopped = false;

    async function open() {
      setStatus(retry.current ? 'reconnecting' : 'connecting');
      const token = await accessToken();
      if (stopped) return;
      const ws = new WebSocket(wsUrl('/api/admin/ws/live'));
      socket = ws;
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
      ws.onmessage = event => {
        let message: Omit<Partial<FeedVerdict>, 'type'> & { type?: string };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (message.type === 'hello') { retry.current = 0; setStatus('open'); return; }
        if (message.type !== 'verdict' || typeof message.session_id !== 'string') return;
        const verdict = { ...message, received_at: Date.now() } as FeedVerdict;
        setSessions(prev => {
          const next = new Map(prev);
          next.set(verdict.session_id, verdict);
          for (const [id, v] of next) if (Date.now() - v.received_at > KEEP_MS) next.delete(id);
          return next;
        });
      };
      ws.onclose = event => {
        if (stopped || socket !== ws) return;
        if (event.code === 1008) { setStatus('refused'); return; }
        retry.current += 1;
        setStatus('reconnecting');
        timer = window.setTimeout(() => void open(), Math.min(15_000, 600 * 2 ** Math.min(retry.current, 5)));
      };
    }

    void open();
    return () => { stopped = true; window.clearTimeout(timer); socket?.close(); };
  }, []);

  return { sessions: [...sessions.values()].sort((a, b) => b.received_at - a.received_at), status };
}

/** "rtc_<call>_caller" -> { callId, role } for app-to-app calls; null for other sessions. */
export function rtcSession(sessionId: string): { callId: string; role: 'caller' | 'callee' } | null {
  const m = /^rtc_([0-9a-f]+)_(caller|callee)$/.exec(sessionId);
  return m ? { callId: m[1], role: m[2] as 'caller' | 'callee' } : null;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export const CHANNELS: Record<string, string> = {
  webrtc: 'App call', app_ws: 'App stream', speakerphone: 'Live listening', upload: 'Upload',
  telephony: 'Phone line', exotel: 'Phone line', whatsapp: 'WhatsApp', voicemail: 'Voicemail',
};
