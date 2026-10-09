import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FileAudio, Radio, Square, Info, Fingerprint, AudioLines, MessageSquareText, FileText } from 'lucide-react';
import useScreening from '../hooks/useScreening';
import useLiveScreening from '../hooks/useLiveScreening';
import { useWorkspace } from '../context/workspace-state';
import { Button, Notice, EmptyState, BandBadge } from '../components/Primitives';
import VoiceHero from '../components/VoiceHero';
import AudioInput from '../components/AudioInput';
import ResultView from '../components/ResultView';
import ReportSheet from '../components/ReportSheet';
import { bands, displayBand, date, formatTime } from '../lib/presentation';
import type { MockScenario } from '../api/mock';

const examples: { scenario: MockScenario; label: string }[] = [
  { scenario: 'green', label: 'Verified voice' },
  { scenario: 'caution', label: 'Caution' },
  { scenario: 'suspicious', label: 'Suspicious signals' },
  { scenario: 'red', label: 'High risk signals' },
  { scenario: 'unverified', label: 'Unverified caller' },
  { scenario: 'insufficient', label: 'Insufficient audio' },
];

const measures = [
  { test: 'Identity', icon: Fingerprint, question: 'Who is speaking?', reference: 'Compared with your known voices. An unfamiliar voice stays neutral.' },
  { test: 'Authenticity', icon: AudioLines, question: 'Does it sound synthetic?', reference: 'Signs of generated speech, considered alongside the caller’s request.' },
  { test: 'Intent', icon: MessageSquareText, question: 'What is being asked?', reference: 'Pressure and secrecy raise concern. An invitation to verify lowers it.' },
];

export default function ScreenPage() {
  const screening = useScreening();
  const live = useLiveScreening();
  const { records } = useWorkspace();
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [source, setSource] = useState<'file' | 'live'>('file');
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);
  function navigateTabs(event: KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 'file' : event.key === 'End' ? 'live' : source === 'file' ? 'live' : 'file';
    setSource(next);
    document.getElementById(`tab-${next}`)?.focus();
  }

  /** Keeps a playable URL for the chosen file, so the report can scrub it against the authenticity strip. */
  function chooseFile(next: File | null) {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = next ? URL.createObjectURL(next) : null;
    setAudioUrl(urlRef.current);
    setFile(next);
  }
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);

  if (screening.data) {
    return (
      <ResultView
        data={screening.data}
        demo={screening.demo}
        name={screening.name}
        audioUrl={screening.demo ? null : audioUrl}
        onReset={() => { screening.clear(); chooseFile(null); }}
      />
    );
  }
  if (live.phase === 'done' && live.data) {
    return <ResultView data={live.data} name="Live listening" status="final" onReset={live.reset} />;
  }

  const liveActive = live.phase === 'connecting' || live.phase === 'listening' || live.phase === 'finishing';
  const busy = screening.loading || recording || liveActive;

  return (
    <div className="page-stack">
      <VoiceHero />

      <div className="screen-grid">
        <section className="panel requisition" aria-labelledby="requisition-heading">
          <div className="panel-head">
            <div><span className="section-kicker">Start here</span><h2 id="requisition-heading">New check</h2></div>
            <div className="tabs source-tabs" data-source={source} role="tablist" aria-label="How to provide audio">
              <button
                type="button" role="tab" id="tab-file" aria-controls="panel-file"
                aria-selected={source === 'file'} disabled={busy}
                tabIndex={source === 'file' ? 0 : -1} onKeyDown={navigateTabs}
                onClick={() => setSource('file')}
              >
                <FileAudio size={16} aria-hidden="true" />Recording
              </button>
              <button
                type="button" role="tab" id="tab-live" aria-controls="panel-live"
                aria-selected={source === 'live'} disabled={busy}
                tabIndex={source === 'live' ? 0 : -1} onKeyDown={navigateTabs}
                onClick={() => setSource('live')}
              >
                <Radio size={16} aria-hidden="true" />Listen live
              </button>
            </div>
          </div>

          {source === 'file' ? (
            <div role="tabpanel" id="panel-file" aria-labelledby="tab-file" className="panel-body">
              {screening.loading ? (
                <div className="processing" role="status" aria-live="polite">
                  <div className="processing-rows" aria-hidden="true">
                    {measures.map(m => <span key={m.test}><b>{m.test}</b><i /></span>)}
                  </div>
                  <p className="processing-title">Checking {screening.name || 'the recording'}…</p>
                  <p className="processing-note">Identity, authenticity and intent run together. This usually takes a few seconds on a local service.</p>
                  <Button variant="secondary" onClick={screening.clear}>Cancel check</Button>
                </div>
              ) : (
                <>
                  <AudioInput file={file} onFile={chooseFile} onBusyChange={setRecording} />
                  <div className="panel-foot">
                    <p>Only check recordings you have permission to use.</p>
                    <Button disabled={!file || recording} onClick={() => file && screening.screenFile(file)}>
                      Check audio<ArrowRight size={17} aria-hidden="true" />
                    </Button>
                  </div>
                </>
              )}
              {screening.error && <Notice tone="danger">{screening.error}</Notice>}
            </div>
          ) : (
            <div role="tabpanel" id="panel-live" aria-labelledby="tab-live" className="panel-body">
              <LivePanel live={live} />
            </div>
          )}
        </section>

        <aside className="measures" aria-labelledby="measures-heading">
          <div><span className="section-kicker">The evidence behind a check</span><h2 id="measures-heading">Three signals.<br /> One clearer picture.</h2></div>
          <div className="signal-list">
            {measures.map(({ icon: Icon, ...m }) => (
              <div className="signal-item" key={m.test}>
                <span className="signal-icon"><Icon size={23} strokeWidth={1.5} aria-hidden="true" /></span>
                <div><h3>{m.test}</h3><p>{m.reference}</p></div>
              </div>
            ))}
          </div>
          <p className="measures-foot">
            The three are combined into a trust score from 0 to 100 and a labelled result. Every finding cites its evidence.
          </p>
          <Link to="/enroll" className="text-link">Enroll a familiar voice<ArrowRight size={16} aria-hidden="true" /></Link>
        </aside>
      </div>

      {live.data && live.phase !== 'done' && (
        <section aria-label="Provisional live report" className="live-report">
          <ReportSheet data={live.data} status={live.phase === 'error' ? 'interrupted' : 'provisional'} name="Live listening" />
        </section>
      )}

      <section className="panel recent-panel" aria-labelledby="recent-heading">
        <div className="panel-head">
          <div>
            <h2 id="recent-heading">Reports this session</h2>
            <p className="panel-sub">Kept in memory while this page is open. Refreshing clears the list.</p>
          </div>
          <Link to="/report" className="text-link">View reports<ArrowRight size={16} aria-hidden="true" /></Link>
        </div>
        {records.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th scope="col">Recording</th><th scope="col">Received</th><th scope="col">Result</th><th scope="col" className="col-num">Trust</th></tr>
              </thead>
              <tbody>
                {records.map(record => {
                  const band = displayBand(record.data);
                  return (
                    <tr key={record.data.session_id}>
                      <th scope="row">
                        <Link className="row-link" to={`/report?session=${encodeURIComponent(record.data.session_id)}`}>
                          <span className="truncate">{record.name}</span>
                        </Link>
                      </th>
                      <td>{record.demo ? 'Sample data' : date(record.data.timestamp)}</td>
                      <td><BandBadge tone={bands[band].tone}>{bands[band].label}</BandBadge></td>
                      <td className="col-num">{band === 'insufficient' ? '—' : Math.round(record.data.fusion.trust_score)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={<FileText size={24} />} title="No reports yet">
            <p>Each check you run appears here, ready to reopen, copy or print.</p>
          </EmptyState>
        )}
      </section>

      <details className="demo-tools">
        <summary>Explore sample results</summary>
        <p>Labelled demonstrations of each result type. They do not check your audio.</p>
        <div className="button-row">
          {examples.map(example => (
            <Button key={example.scenario} variant="secondary" disabled={busy} onClick={() => screening.screenMock(example.scenario)}>
              {example.label}
            </Button>
          ))}
        </div>
      </details>
    </div>
  );
}

function LivePanel({ live }: { live: ReturnType<typeof useLiveScreening> }) {
  const band = live.data ? displayBand(live.data) : null;
  if (live.phase === 'idle' || live.phase === 'error') {
    return (
      <div className="live-idle">
        <p className="zone-title">Listen to a call from a second device</p>
        <ol className="live-steps">
          <li>Put the call on speaker.</li>
          <li>Place this device close to it.</li>
          <li>Start listening. The report updates every few seconds.</li>
        </ol>
        <div className="capture-note">
          <Info size={18} aria-hidden="true" />
          <p>The phone that is on the call cannot hear its own call. Android gives it silence. Listen from a different device.</p>
        </div>
        {live.error && <Notice tone="danger">{live.error}</Notice>}
        <div className="panel-foot">
          <p>Only listen to calls you are part of, with permission.</p>
          <Button onClick={live.start}><Radio size={17} aria-hidden="true" />Start listening</Button>
        </div>
      </div>
    );
  }
  return (
    <div className={`live-console phase-${live.phase}`} role="status" aria-live="polite">
      <div className="live-readout">
        <div className="live-time">
          <span className="rec-dot" aria-hidden="true" />
          <strong>{formatTime(live.seconds)}</strong>
          <span>{live.phase === 'connecting' ? 'Connecting…' : live.phase === 'finishing' ? 'Finishing the report…' : 'Listening'}</span>
        </div>
        <meter min={0} max={1} value={live.level} aria-label="Microphone sound level" />
        <dl className="live-counts">
          <div><dt>Slices sent</dt><dd>{live.sent}</dd></div>
          <div><dt>Updates</dt><dd>{live.received}</dd></div>
          <div>
            <dt>Current result</dt>
            <dd>{band ? <BandBadge tone={bands[band].tone}>{bands[band].label}</BandBadge> : 'Waiting for speech'}</dd>
          </div>
        </dl>
      </div>
      {live.warning && <Notice tone="warning">{live.warning}</Notice>}
      <div className="panel-foot">
        <p>Warnings only escalate during a session. A later calm stretch does not erase an earlier concern.</p>
        <Button variant="danger" onClick={live.stop} disabled={live.phase !== 'listening'} busy={live.phase === 'finishing'}>
          {live.phase !== 'finishing' && <Square size={15} aria-hidden="true" />}Stop and finalise
        </Button>
      </div>
      <Button variant="quiet" onClick={live.reset}>Discard session</Button>
    </div>
  );
}
