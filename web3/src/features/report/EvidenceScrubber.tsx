import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Pause, Play } from '@phosphor-icons/react';
import type { ScreeningResponse } from '../../types/contracts';
import type { Evidence } from '../../hooks/useEvidence';
import SpectrogramCanvas from '../../components/SpectrogramCanvas';
import { SYNTH_THRESHOLD, clock, evidenceDuration, identityText, isDevanagari, markPhrases, pct, trustedMatch } from '../../lib/verdict';

interface Props {
  data: ScreeningResponse;
  evidence: Evidence;
}

/**
 * The recording, second by second. Every lane shares one time axis and one cursor:
 * spectrogram (when the audio is in this session), synthetic-speech score, speech, identity.
 */
export default function EvidenceScrubber({ data, evidence }: Props) {
  const audio = useRef<HTMLAudioElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [dragging, setDragging] = useState(false);
  const duration = Math.max(evidence.duration || 0, evidenceDuration(data)) || 0;
  const segments = useMemo(() => [...data.spoof.timeline].sort((a, b) => a.start_s - b.start_s), [data]);
  const speech = data.transcript.segments.length
    ? data.transcript.segments
    : data.transcript.text && duration ? [{ start_s: 0, end_s: duration, text: data.transcript.text, language: null }] : [];
  const canPlay = Boolean(evidence.url) && evidence.status !== 'unavailable';

  useEffect(() => {
    const node = audio.current;
    if (!node) return;
    let frame = 0;
    const follow = () => { setCursor(node.currentTime); frame = requestAnimationFrame(follow); };
    const onPlay = () => { setPlaying(true); frame = requestAnimationFrame(follow); };
    const onPause = () => { setPlaying(false); cancelAnimationFrame(frame); };
    node.addEventListener('play', onPlay);
    node.addEventListener('pause', onPause);
    node.addEventListener('ended', onPause);
    return () => {
      cancelAnimationFrame(frame);
      node.removeEventListener('play', onPlay);
      node.removeEventListener('pause', onPause);
      node.removeEventListener('ended', onPause);
    };
  }, [evidence.url]);

  if (!duration) {
    return <p className="empty-line">No time-aligned evidence was returned for this recording.</p>;
  }

  const at = cursor ?? 0;
  // Segments overlap; the one drawn at a moment is the latest to have started.
  const segmentAt = segments.findLast(s => at >= s.start_s && at < s.end_s) ?? null;
  const speechAt = speech.find(s => at >= s.start_s && at < s.end_s) ?? null;
  const pos = (t: number) => `${Math.max(0, Math.min(100, (t / duration) * 100))}%`;
  const ticks = niceTicks(duration);

  function seekTo(time: number) {
    const t = Math.max(0, Math.min(duration, time));
    setCursor(t);
    if (audio.current && canPlay) audio.current.currentTime = Math.min(t, audio.current.duration || t);
  }
  function fromPointer(event: ReactPointerEvent) {
    const rect = track.current!.getBoundingClientRect();
    seekTo(((event.clientX - rect.left) / rect.width) * duration);
  }
  function toggle() {
    const node = audio.current;
    if (!node) return;
    if (node.paused) void node.play(); else node.pause();
  }

  return (
    <div className="scrubber">
      <div className="scrubber-bar">
        {canPlay && (
          <button type="button" className="play" onClick={toggle} aria-label={playing ? 'Pause recording' : 'Play recording'}>
            {playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}
          </button>
        )}
        <span className="num scrubber-time">{clock(at)} <span className="muted">/ {clock(duration)}</span></span>
        <span className="scrubber-readout" aria-live="off">
          {segmentAt ? (
            <>Synthetic score <b className="num">{pct(segmentAt.score)}</b> · {segmentAt.is_synthetic ? <b className="t-danger">synthetic</b> : 'natural'}</>
          ) : cursor == null ? 'Drag across the lanes to inspect any moment' : 'No segment score here'}
        </span>
        {canPlay && <audio ref={audio} src={evidence.url!} preload="metadata" />}
      </div>

      <div
        ref={track}
        className={`lanes${dragging ? ' is-dragging' : ''}`}
        role="slider"
        tabIndex={0}
        aria-label="Evidence timeline"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration * 10) / 10}
        aria-valuenow={Math.round(at * 10) / 10}
        aria-valuetext={`${clock(at)}${segmentAt ? `, synthetic score ${pct(segmentAt.score)}` : ''}${speechAt ? `, ${speechAt.text}` : ''}`}
        onPointerDown={event => { track.current!.setPointerCapture(event.pointerId); setDragging(true); fromPointer(event); }}
        onPointerMove={event => { if (dragging) fromPointer(event); }}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
        onKeyDown={event => {
          if (event.key === 'ArrowRight') { event.preventDefault(); seekTo(at + 0.5); }
          if (event.key === 'ArrowLeft') { event.preventDefault(); seekTo(at - 0.5); }
          if (event.key === 'Home') { event.preventDefault(); seekTo(0); }
          if (event.key === 'End') { event.preventDefault(); seekTo(duration); }
          if (event.key === ' ' && canPlay) { event.preventDefault(); toggle(); }
        }}
      >
        <div className={`lane lane-spectrum${evidence.status === 'none' ? ' is-empty' : ''}`}>
          <span className="lane-label">Sound</span>
          <div className="lane-body">
            {evidence.spectrogram ? (
              <>
                <SpectrogramCanvas spectrogram={evidence.spectrogram} label="Spectrogram of the recording, 60 Hz to 8 kHz" />
                <span className="freq freq-top" aria-hidden="true">8 kHz</span>
                <span className="freq freq-bottom" aria-hidden="true">60 Hz</span>
              </>
            ) : evidence.status === 'loading' ? (
              <div className="lane-note shimmer-bg">Drawing the spectrogram…</div>
            ) : evidence.status === 'unavailable' ? (
              <div className="lane-note">This browser can’t decode this format for drawing. The service analysed it normally.</div>
            ) : (
              <div className="lane-note">The audio isn’t kept with saved reports or samples, so only the analysis is shown.</div>
            )}
          </div>
        </div>

        <div className="lane lane-synth">
          <span className="lane-label">Synthetic</span>
          <div className="lane-body">
            <span className="synth-threshold" style={{ bottom: `${SYNTH_THRESHOLD * 100}%` }} aria-hidden="true"><span>{pct(SYNTH_THRESHOLD)} threshold</span></span>
            {segments.map((segment, i) => {
              const next = segments[i + 1];
              const end = next ? Math.min(next.start_s, segment.end_s) : segment.end_s;
              return (
                <span
                  key={i}
                  className={`synth-bar${segment.is_synthetic ? ' is-synth' : ''}${segmentAt === segment ? ' is-current' : ''}`}
                  style={{ left: pos(segment.start_s), width: `calc(${pos(end - segment.start_s)} - 2px)`, height: `${Math.max(6, segment.score * 100)}%` }}
                />
              );
            })}
            {!segments.length && <div className="lane-note">No segment scores returned.</div>}
          </div>
        </div>

        <div className="lane lane-speech">
          <span className="lane-label">Speech</span>
          <div className="lane-body">
            {speech.map((segment, i) => {
              const runs = markPhrases(segment.text, data);
              const kind = runs.some(r => r.kind === 'concern') ? 'concern' : runs.some(r => r.kind === 'reassure') ? 'reassure' : '';
              return (
                <span
                  key={i}
                  className={`speech-block ${kind}${speechAt === segment ? ' is-current' : ''}`}
                  style={{ left: pos(segment.start_s), width: `calc(${pos(segment.end_s - segment.start_s)} - 3px)` }}
                  lang={isDevanagari(segment.text) ? 'hi' : undefined}
                >
                  {segment.text}
                </span>
              );
            })}
          </div>
        </div>

        <div className="lane lane-identity">
          <span className="lane-label">Identity</span>
          <div className="lane-body">
            <span className={`identity-band v-${data.speaker.verdict === 'match' && !trustedMatch(data) ? 'unknown' : data.speaker.verdict}`}>
              {identityText(data)}
            </span>
          </div>
        </div>

        <div className="lane lane-axis" aria-hidden="true">
          <span className="lane-label" />
          <div className="lane-body">
            {ticks.map(t => <span key={t} className="tick num" style={{ left: pos(t) }}>{t}s</span>)}
          </div>
        </div>

        {cursor != null && <span className="playhead" style={{ left: `calc(var(--lane-label) + (100% - var(--lane-label)) * ${at / duration})` }} aria-hidden="true" />}
      </div>

      <p className="caption-line" aria-live="polite">
        {speechAt ? <>“<span lang={isDevanagari(speechAt.text) ? 'hi' : undefined}>{speechAt.text}</span>”</> : <span className="muted">Bars show each segment’s synthetic score. The dashed line marks the synthetic threshold.</span>}
      </p>
    </div>
  );
}

function niceTicks(duration: number): number[] {
  const step = duration <= 12 ? 2 : duration <= 30 ? 5 : duration <= 90 ? 15 : 30;
  const out: number[] = [];
  for (let t = 0; t <= duration + 0.001; t += step) out.push(Math.round(t));
  return out;
}
