import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { CallerMetadata, OperatingMode, ReasonCode, ThreatLabel, TrustBand } from '../types/contracts';
import { wsUrl } from '../lib/api';
import { accessToken, authEnabled } from '../lib/auth';

/**
 * The live verdict feed, `/api/ws/live` (docs/LIVE_FEED.md, schema_version 1).
 *
 * Exotel phone calls stream from Exotel straight to the backend; this page never touches call
 * audio, it only watches verdicts arrive. One feed carries every call, grouped by session_id.
 * The feed is live only: nothing is replayed after a reconnect.
 */
export interface LiveVerdict {
  type: 'verdict';
  schema_version: number;
  session_id: string;
  window_index: number;
  is_final: boolean;
  escalated: boolean;
  timestamp: string;
  band: TrustBand;
  overlay_state: 'green' | 'amber' | 'red' | 'grey';
  trust_score: number;
  risk_score: number;
  mode: OperatingMode;
  signals: { identity: 'match' | 'mismatch' | 'unknown'; authenticity: 'synthetic' | 'bonafide' | 'unavailable'; intent_risk: number };
  reason_codes: ReasonCode[];
  transcript: string;
  language: string;
  caller_context: CallerMetadata | null;
  threat_label: ThreatLabel | null;
  recommended_actions: string[];
  vernacular_warning: string | null;
  window_trust_score?: number;
  window_band?: TrustBand;
}

export interface CallPoint { index: number; at: number; trust: number; window: number | null; band: TrustBand }

export interface CallState {
  sessionId: string;
  startedAt: number;
  updatedAt: number;
  latest: LiveVerdict;
  points: CallPoint[];
  escalations: number;
  final: boolean;
}

export type FeedStatus = 'connecting' | 'open' | 'reconnecting' | 'refused' | 'closed';

interface CallFeed {
  status: FeedStatus;
  calls: CallState[];
  needsToken: boolean;
  connect: (token?: string) => void;
  disconnect: () => void;
  clearEnded: () => void;
  soundOn: boolean;
  setSoundOn: (on: boolean) => void;
}

const CallFeedContext = createContext<CallFeed | null>(null);
const MAX_CALLS = 30;
const MAX_POINTS = 600;
const SCHEMA_VERSION = 1;

function isVerdict(value: unknown): value is LiveVerdict {
  const v = value as LiveVerdict;
  return !!v && v.type === 'verdict' && typeof v.session_id === 'string' && Number.isFinite(v.trust_score)
    && typeof v.band === 'string' && Array.isArray(v.reason_codes) && !!v.signals;
}

/** A short two-tone chime for an escalation. Only after the person turned sound on (autoplay rules). */
function chime(context: AudioContext | null) {
  if (!context) return;
  const now = context.currentTime;
  [880, 660].forEach((frequency, i) => {
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, now + i * 0.18);
    gain.gain.exponentialRampToValueAtTime(0.18, now + i * 0.18 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.16);
    osc.connect(gain).connect(context.destination);
    osc.start(now + i * 0.18);
    osc.stop(now + i * 0.18 + 0.18);
  });
}

export function CallFeedProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<FeedStatus>('connecting');
  const [calls, setCalls] = useState<Map<string, CallState>>(() => new Map());
  const [needsToken, setNeedsToken] = useState(false);
  const [soundOn, setSoundOnState] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const token = useRef('');
  const wanted = useRef(true);
  const retry = useRef(0);
  const timer = useRef<number | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const sound = useRef(false);

  const handle = useCallback((verdict: LiveVerdict) => {
    if (verdict.escalated && sound.current) chime(audio.current);
    setCalls(previous => {
      const next = new Map(previous);
      const now = Date.now();
      const existing = next.get(verdict.session_id);
      const startedAt = existing?.startedAt ?? now;
      const point: CallPoint = {
        index: verdict.window_index,
        at: (now - startedAt) / 1000,
        trust: verdict.trust_score,
        window: Number.isFinite(verdict.window_trust_score) ? verdict.window_trust_score! : null,
        band: verdict.window_band ?? verdict.band,
      };
      next.set(verdict.session_id, {
        sessionId: verdict.session_id,
        startedAt,
        updatedAt: now,
        latest: verdict,
        points: [...(existing?.points ?? []), point].slice(-MAX_POINTS),
        escalations: (existing?.escalations ?? 0) + (verdict.escalated ? 1 : 0),
        final: verdict.is_final || (existing?.final ?? false),
      });
      if (next.size > MAX_CALLS) {
        const oldest = [...next.values()].sort((a, b) => a.updatedAt - b.updatedAt)[0];
        next.delete(oldest.sessionId);
      }
      return next;
    });
  }, []);

  const open = useCallback(() => {
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null; }
    socket.current?.close();
    const query = token.current ? `?token=${encodeURIComponent(token.current)}` : '';
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl(`/api/ws/live${query}`));
    } catch {
      setStatus('closed');
      return;
    }
    socket.current = ws;
    setStatus(retry.current ? 'reconnecting' : 'connecting');

    ws.onopen = () => {
      retry.current = 0;
      setStatus('open');
      setNeedsToken(false);
      // Signed in: the first message names the account, so the feed carries only its calls.
      // Without sign-in the server's dev mode reads silence as the dev account.
      if (authEnabled) {
        void accessToken().then(signedIn => {
          if (signedIn && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'auth', token: signedIn }));
        });
      }
    };
    ws.onmessage = event => {
      let message: unknown;
      try { message = JSON.parse(String(event.data)); } catch { return; }
      const type = (message as { type?: string })?.type;
      if (type === 'hello') {
        const version = (message as { schema_version?: number }).schema_version;
        if (version !== SCHEMA_VERSION) console.warn(`Live feed schema ${version}; this dashboard reads ${SCHEMA_VERSION}.`);
        return;
      }
      if (isVerdict(message)) handle(message);
    };
    ws.onclose = event => {
      if (socket.current !== ws) return;
      socket.current = null;
      if (event.code === 1008) {
        // Wrong or missing token: retrying with the same token can never succeed.
        setStatus('refused');
        setNeedsToken(true);
        return;
      }
      if (!wanted.current) { setStatus('closed'); return; }
      retry.current += 1;
      setStatus('reconnecting');
      const delay = Math.min(15_000, 600 * 2 ** Math.min(retry.current, 5));
      timer.current = window.setTimeout(open, delay);
    };
  }, [handle]);

  useEffect(() => {
    wanted.current = true;
    open();
    return () => {
      wanted.current = false;
      if (timer.current) window.clearTimeout(timer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, [open]);

  const connect = useCallback((nextToken?: string) => {
    if (nextToken !== undefined) token.current = nextToken.trim();
    wanted.current = true;
    retry.current = 0;
    open();
  }, [open]);

  const disconnect = useCallback(() => {
    wanted.current = false;
    if (timer.current) window.clearTimeout(timer.current);
    socket.current?.close();
    socket.current = null;
    setStatus('closed');
  }, []);

  const clearEnded = useCallback(() => {
    setCalls(previous => new Map([...previous].filter(([, call]) => !call.final)));
  }, []);

  const setSoundOn = useCallback((on: boolean) => {
    sound.current = on;
    setSoundOnState(on);
    if (on && !audio.current) {
      try { audio.current = new AudioContext(); } catch { audio.current = null; }
    }
    if (on) void audio.current?.resume();
  }, []);

  const value = useMemo<CallFeed>(() => ({
    status,
    calls: [...calls.values()].sort((a, b) => Number(a.final) - Number(b.final) || b.updatedAt - a.updatedAt),
    needsToken,
    connect,
    disconnect,
    clearEnded,
    soundOn,
    setSoundOn,
  }), [status, calls, needsToken, connect, disconnect, clearEnded, soundOn, setSoundOn]);

  return <CallFeedContext.Provider value={value}>{children}</CallFeedContext.Provider>;
}

export function useCallFeed(): CallFeed {
  const value = useContext(CallFeedContext);
  if (!value) throw new Error('CallFeedProvider is missing.');
  return value;
}
