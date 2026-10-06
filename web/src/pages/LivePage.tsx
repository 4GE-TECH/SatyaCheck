import { useState } from "react";
import { KeyRound, Loader2, PhoneIncoming, Radio, RefreshCw, WifiOff } from "lucide-react";
import useLiveFeed, { type FeedStatus, type LiveCall } from "../hooks/useLiveFeed";
import LiveCallCard from "../components/LiveCallCard";
import { BAND_LABEL, DOT, knownState } from "../components/liveFeedDisplay";
import { LIVE_FEED_SCHEMA_VERSION } from "../types/liveFeed";

/** Calls as they are screened, from `/api/ws/live` (docs/LIVE_FEED.md). */

function FeedStatusBar({ status, onRetry }: { status: FeedStatus; onRetry: () => void }) {
  if (status.kind === "open") {
    const otherSchema =
      status.schemaVersion !== null && status.schemaVersion !== LIVE_FEED_SCHEMA_VERSION;
    return (
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] text-sm font-semibold text-[var(--text-primary)]">
          <Radio className="w-4 h-4 text-[var(--accent)]" aria-hidden />
          Live feed connected
        </div>
        {otherSchema && (
          <p className="text-sm text-[var(--warning-text)]">
            The backend sends feed version {status.schemaVersion}; this page was built for version{" "}
            {LIVE_FEED_SCHEMA_VERSION}. Some details may be missing.
          </p>
        )}
      </div>
    );
  }

  if (status.kind === "connecting") {
    return (
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] text-sm font-semibold text-[var(--text-secondary)]">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
        Connecting to the live feed…
      </div>
    );
  }

  if (status.kind === "retrying") {
    const unreachable = status.backendUp === false;
    return (
      <div className="p-4 rounded-xl bg-[var(--warning-bg)] border border-[var(--warning-border)] text-[var(--warning-text)] space-y-1">
        <div className="flex items-center gap-2 font-bold">
          <WifiOff className="w-4 h-4" aria-hidden />
          {unreachable ? "Cannot reach the backend" : "Live feed disconnected"} — retrying in {status.inSeconds}s
        </div>
        <p className="text-sm">
          {unreachable
            ? "Check SATYACHECK_BACKEND and that the backend and its tunnel are running. A quick tunnel gets a new address every time it restarts."
            : "Verdicts sent while disconnected are not replayed."}
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-[var(--danger-bg)] border border-[var(--danger-border)] text-[var(--danger-text)] space-y-2">
      <div className="flex items-center gap-2 font-bold">
        <KeyRound className="w-4 h-4" aria-hidden />
        The backend refused the live feed
      </div>
      <p className="text-sm">
        The backend is up, so the token is most likely missing or wrong. Restart the dashboard with the
        token from whoever runs the backend:{" "}
        <code className="font-mono">SATYACHECK_LIVE_TOKEN=… npm run dev</code>. A backend without the
        live feed looks the same.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--danger-border)] bg-transparent text-sm font-semibold text-[var(--danger-text)] cursor-pointer"
      >
        <RefreshCw className="w-4 h-4" aria-hidden /> Try again
      </button>
    </div>
  );
}

function CallList({
  calls,
  focusedId,
  onSelect,
}: {
  calls: LiveCall[];
  focusedId: string;
  onSelect: (sessionId: string) => void;
}) {
  return (
    <ul className="space-y-2">
      {calls.map((call) => {
        const v = call.latest;
        const focused = call.sessionId === focusedId;
        return (
          <li key={call.sessionId}>
            <button
              type="button"
              onClick={() => onSelect(call.sessionId)}
              aria-current={focused}
              className={`w-full text-left p-3 rounded-xl border cursor-pointer transition-colors bg-[var(--bg-primary)] ${
                focused ? "border-[var(--text-primary)]" : "border-[var(--border-default)] hover:bg-[var(--bg-secondary)]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full shrink-0 ${DOT[knownState(v.overlay_state)]}`} aria-hidden />
                <span className="font-mono font-semibold text-[var(--text-primary)] truncate">
                  {v.caller_context?.claimed_number || call.sessionId}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-[var(--text-muted)]">
                <span>
                  {BAND_LABEL[v.band] ?? v.band} · {v.is_final ? "ended" : "live"}
                </span>
                <span className="font-mono">
                  {new Date(call.firstSeen).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function LivePage() {
  const { status, calls, reconnect } = useLiveFeed();
  /** A call the viewer picked. Null means follow whichever call updated last. */
  const [pinnedId, setPinnedId] = useState<string | null>(null);

  const pinned = calls.find((c) => c.sessionId === pinnedId);
  const latest = calls.reduce<LiveCall | undefined>(
    (best, c) => (!best || c.lastSeen > best.lastSeen ? c : best),
    undefined,
  );
  const focused = pinned ?? latest;

  return (
    <div className="space-y-6 pb-12">
      <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-[var(--text-primary)]">Live calls</h1>
          <p className="text-base text-[var(--text-secondary)]">
            Verdicts from calls the backend is screening, as they happen.
          </p>
        </div>
        <FeedStatusBar status={status} onRetry={reconnect} />
      </header>

      {!focused ? (
        // Only promise a call while the feed can actually deliver one; otherwise the
        // status bar above says what is wrong.
        (status.kind === "open" || status.kind === "connecting") && (
        <div className="sec-card p-10 sm:p-14 text-center space-y-3 max-w-2xl mx-auto">
          <PhoneIncoming className="w-12 h-12 mx-auto text-[var(--text-muted)]" aria-hidden />
          <h2 className="text-2xl sm:text-3xl font-bold text-[var(--text-primary)]">Waiting for a call</h2>
          <p className="text-lg text-[var(--text-secondary)]">
            Verdicts appear here a few seconds after a call starts. Earlier verdicts are not replayed, so
            keep this page open before the call begins.
          </p>
        </div>
        )
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] gap-6 items-start">
          <LiveCallCard call={focused} />
          <aside className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-[var(--text-primary)]">Calls on this feed</h2>
              {pinned && (
                <button
                  type="button"
                  onClick={() => setPinnedId(null)}
                  className="text-sm font-semibold text-[var(--accent)] bg-transparent border-none cursor-pointer"
                >
                  Follow the latest
                </button>
              )}
            </div>
            <CallList calls={calls} focusedId={focused.sessionId} onSelect={setPinnedId} />
          </aside>
        </div>
      )}
    </div>
  );
}
