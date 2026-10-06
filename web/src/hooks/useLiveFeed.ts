import { useCallback, useEffect, useState } from "react";
import type { LiveVerdict } from "../types/liveFeed";

/**
 * Subscribes to the backend's live verdict feed, `/api/ws/live` (docs/LIVE_FEED.md).
 *
 * The socket goes to this page's own origin; the Vite dev server forwards it to the
 * backend and adds the `?token=` (web/vite.config.ts), so the token never reaches the page.
 *
 * Live only: nothing is replayed, so verdicts sent while the socket was down are gone.
 * State lives in memory only — no browser storage (CLAUDE.md).
 */

/** Calls kept on screen. Older ones drop off; the backend keeps the reports. */
const MAX_CALLS = 20;
const MAX_RETRY_SECONDS = 10;

export type FeedStatus =
  | { kind: "connecting" }
  | { kind: "open"; schemaVersion: number | null }
  /** The socket dropped or never opened; another attempt is scheduled. */
  | { kind: "retrying"; inSeconds: number; backendUp: boolean | null }
  /**
   * The backend is up but refused the socket — in practice a missing or wrong token.
   * Not retried automatically: the dev server has to be restarted with the right one.
   */
  | { kind: "refused" };

export interface LiveCall {
  sessionId: string;
  /** Wall-clock ms when the first verdict arrived. */
  firstSeen: number;
  lastSeen: number;
  latest: LiveVerdict;
  /** One entry per scoring window, in order. The final verdict replaces a repeated index. */
  windows: LiveVerdict[];
}

function addVerdict(calls: LiveCall[], verdict: LiveVerdict): LiveCall[] {
  const now = Date.now();
  const i = calls.findIndex((c) => c.sessionId === verdict.session_id);
  if (i === -1) {
    const call: LiveCall = {
      sessionId: verdict.session_id,
      firstSeen: now,
      lastSeen: now,
      latest: verdict,
      windows: [verdict],
    };
    return [call, ...calls].slice(0, MAX_CALLS);
  }
  const old = calls[i];
  const last = old.windows[old.windows.length - 1];
  const windows =
    last && last.window_index === verdict.window_index
      ? [...old.windows.slice(0, -1), verdict]
      : [...old.windows, verdict];
  const updated: LiveCall = { ...old, lastSeen: now, latest: verdict, windows };
  return calls.map((c, j) => (j === i ? updated : c));
}

async function backendIsUp(): Promise<boolean> {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export default function useLiveFeed() {
  const [status, setStatus] = useState<FeedStatus>({ kind: "connecting" });
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const [generation, setGeneration] = useState(0);

  /** Start over after a refusal, once the dev server has the right token. */
  const reconnect = useCallback(() => setGeneration((g) => g + 1), []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;
    let stopped = false;

    const scheduleRetry = (backendUp: boolean | null) => {
      const delay = Math.min(MAX_RETRY_SECONDS, 2 ** attempt);
      attempt += 1;
      setStatus({ kind: "retrying", inSeconds: delay, backendUp });
      retryTimer = window.setTimeout(connect, delay * 1000);
    };

    function connect() {
      if (stopped) return;
      setStatus({ kind: "connecting" });
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${window.location.host}/api/ws/live`);
      socket = ws;
      let opened = false;

      ws.onopen = () => {
        opened = true;
        attempt = 0;
        setStatus({ kind: "open", schemaVersion: null });
      };

      ws.onmessage = (event) => {
        let msg: { type?: unknown; schema_version?: unknown };
        try {
          msg = JSON.parse(String(event.data));
        } catch {
          console.warn("live feed: ignoring a frame that is not JSON", event.data);
          return;
        }
        if (msg.type === "hello") {
          const version = typeof msg.schema_version === "number" ? msg.schema_version : null;
          setStatus({ kind: "open", schemaVersion: version });
        } else if (msg.type === "verdict") {
          setCalls((prev) => addVerdict(prev, msg as LiveVerdict));
        }
        // Any other type is ignored, as docs/LIVE_FEED.md asks.
      };

      ws.onclose = async (event) => {
        if (stopped) return;
        if (event.code === 1008) {
          console.warn("live feed: refused with 1008 (missing or wrong token)");
          setStatus({ kind: "refused" });
          return;
        }
        if (opened) {
          console.warn(`live feed: socket closed (code ${event.code}); reconnecting`);
          scheduleRetry(null);
          return;
        }
        // The handshake failed. The backend refuses a bad token before accepting, which
        // the browser reports as a generic failure, so ask the backend whether it is up:
        // if it is, the token is the likely cause.
        const up = await backendIsUp();
        if (stopped) return;
        if (up) {
          console.warn("live feed: backend is up but refused the socket; check SATYACHECK_LIVE_TOKEN");
          setStatus({ kind: "refused" });
        } else {
          console.warn("live feed: backend unreachable; retrying");
          scheduleRetry(false);
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [generation]);

  return { status, calls, reconnect };
}
