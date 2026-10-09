import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowDown, ArrowRight, ArrowUpRight, AudioLines, Fingerprint, MessageCircle, Play, ShieldQuestion, Users, LoaderCircle } from 'lucide-react';
import AudioPicker from '../components/AudioPicker';
import SignalSculpture from '../components/SignalSculpture';
import { Button, ErrorNote, Reveal, ease } from '../components/UI';
import { request, readResult, validateAudio, bandFor, bands, when } from '../lib/api';
import { samples, sampleCheck } from '../lib/samples';
import { useLab } from '../lib/store';
import type { TrustBand } from '../lib/contracts';

const signals = [
  { name: 'Identity', icon: Fingerprint, short: 'The person behind the voice.', title: 'Familiar is a feeling. A match is evidence.', body: 'Compare the caller’s voice with people you have enrolled. A stranger stays unverified—not suspicious simply for being unknown.', detail: 'Enrolled voices · Match, mismatch or unknown', link: 'Build your circle', route: '/voices' },
  { name: 'Authenticity', icon: AudioLines, short: 'The way the voice was made.', title: 'A voice can change halfway through a call.', body: 'We examine the recording in segments, including short bursts of synthetic speech. An automated voice alone is not a reason to flag a call.', detail: 'Median · Peak · Longest synthetic run', link: 'Understand the evidence', route: '/guide' },
  { name: 'Intent', icon: MessageCircle, short: 'The request beneath the words.', title: 'Listen to what they ask you to do.', body: 'Pressure, secrecy and urgent payment demands raise concern. An invitation to call back or check with someone else lowers it.', detail: 'Hindi · English · Hinglish', link: 'Read the safety guide', route: '/guide' },
];
export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [signal, setSignal] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const { checks, save } = useLab(); const navigate = useNavigate(); const reduced = useReducedMotion();
  useEffect(() => () => controller.current?.abort(), []);
  function openSample(band: TrustBand) { const check = sampleCheck(band); save(check); navigate(`/reports/${encodeURIComponent(check.result.session_id)}`); }
  async function analyze() {
    if (!file || controller.current || capturing) return;
    const problem = validateAudio(file); if (problem) { setError(problem); return; }
    const active = new AbortController(); controller.current = active; setBusy(true); setError('');
    const data = new FormData(); data.append('file', file); data.append('channel_type', 'upload');
    const response = await request<unknown>('/api/screen', { method: 'POST', body: data, signal: active.signal });
    if (active.signal.aborted) return;
    const parsed = response.ok ? readResult(response.data) : response;
    controller.current = null; setBusy(false);
    if (!parsed.ok) { setError(parsed.error); return; }
    save({ result: parsed.data, name: file.name, sample: false }); navigate(`/reports/${encodeURIComponent(parsed.data.session_id)}`);
  }
  function cancel() { controller.current?.abort(); controller.current = null; setBusy(false); }
  const chosen = signals[signal];
  return <div className="home">
    <section className="hero" aria-labelledby="home-heading">
      <div className="hero-copy"><Reveal><p className="eyebrow"><span className="small-orbit"/>Listen beyond the familiar</p></Reveal><Reveal delay={.07}><h1 id="home-heading">Familiar voice.<br/><span>Look closer.</span></h1></Reveal><Reveal delay={.14}><p className="hero-description">A voice can be copied. Your trust shouldn’t be.<br className="desktop-break"/> Check the identity, authenticity and intent behind a call.</p><a href="#audio-console" className="hero-jump">Let’s hear the evidence <ArrowDown size={17}/></a></Reveal></div>
      <SignalSculpture/>
      <div className="hero-bottom"><span>Made for real conversations.</span><span>Hindi <i/> English <i/> Hinglish</span></div>
    </section>
    <Reveal delay={.12} className="console-reveal">
      <section className="audio-console" id="audio-console" aria-labelledby="console-heading">
        <div className="console-top"><h2 id="console-heading"><AudioLines size={18}/>Your listening desk</h2><span>Only use audio you have permission to check.</span></div>
        <div className="console-grid"><div className="console-input">
          {busy ? <div className="analysis-state" role="status"><div className="analysis-orbits" aria-hidden="true"><i/><i/><i/><AudioLines size={36}/></div><h3>Listening to the whole picture.</h3><p>Three independent signals are being checked together.</p><div className="analysis-branches">{signals.map(s => <span key={s.name}><LoaderCircle className="spinner" size={13}/>{s.name}</span>)}</div><Button variant="ghost" onClick={cancel}>Cancel check</Button></div>
          : <><AudioPicker file={file} onFile={setFile} onBusy={setCapturing}/>{file && <div className="analyze-action"><p>A score with evidence.<br/>Never a verdict without context.</p><Button onClick={analyze} disabled={capturing}>Analyze recording<ArrowRight size={18}/></Button></div>}</>}
          {error && <ErrorNote>{error}</ErrorNote>}
        </div><aside className="sample-list" aria-labelledby="samples-heading"><p className="eyebrow" id="samples-heading">Or take a closer look</p><p className="sample-caption">Explore a sample. No audio is analysed.</p>{samples.map(sample => <button className="sample-row" key={sample.band} disabled={busy || capturing} onClick={() => openSample(sample.band)}><span className="sample-play"><Play size={14} fill="currentColor"/></span><span><strong>{sample.name}</strong><small>{sample.lang} · Sample result</small></span><ArrowUpRight size={17}/></button>)}<details className="extra-samples"><summary>Explore more result states</summary><div>{(['caution','suspicious','insufficient'] as const).map(band => <button disabled={busy || capturing} key={band} onClick={() => openSample(band)}>{bands[band].label}<ArrowRight size={14}/></button>)}</div></details></aside></div>
      </section>
    </Reveal>
    <section className="signal-section" aria-labelledby="signal-heading"><Reveal><div className="section-heading"><div><p className="eyebrow">Beyond a single score</p><h2 id="signal-heading">Trust needs<br/><span>more than one signal.</span></h2></div><p>One voice. Three independent perspectives.<br/>Every finding has a reason you can inspect.</p></div></Reveal>
      <div className="signal-workbench"><div className="signal-selector" role="tablist" aria-label="Explore the signals">{signals.map((s,i) => <button key={s.name} id={`signal-tab-${i}`} role="tab" aria-selected={signal === i} aria-controls="signal-detail" tabIndex={signal === i ? 0 : -1} onKeyDown={e => { if (['ArrowDown','ArrowRight','ArrowUp','ArrowLeft','Home','End'].includes(e.key)) { e.preventDefault(); const next = e.key === 'Home' ? 0 : e.key === 'End' ? 2 : (i + (['ArrowUp','ArrowLeft'].includes(e.key) ? 2 : 1)) % 3; setSignal(next); document.getElementById(`signal-tab-${next}`)?.focus(); } }} onClick={() => setSignal(i)}>
        {signal === i && <motion.span className="signal-selection" layoutId="signal-selection" transition={{ type: 'spring', stiffness: 350, damping: 35 }}/>}<s.icon size={26} strokeWidth={1.4}/><span><strong>{s.name}</strong><small>{s.short}</small></span><ArrowRight size={20}/></button>)}</div>
        <div className="signal-detail" role="tabpanel" id="signal-detail" aria-labelledby={`signal-tab-${signal}`}><AnimatePresence mode="wait" initial={false}><motion.div key={signal} initial={{ opacity: 0, transform: reduced ? 'none' : 'translateY(8px)' }} animate={{ opacity: 1, transform: 'translateY(0)' }} exit={{ opacity: 0 }} transition={{ duration: .18, ease }}><chosen.icon size={50} strokeWidth={.85}/><h3>{chosen.title}</h3><p>{chosen.body}</p><span className="signal-detail-meta">{chosen.detail}</span><Link className="text-link" to={chosen.route}>{chosen.link}<ArrowUpRight size={16}/></Link></motion.div></AnimatePresence></div>
      </div>
    </section>
    {checks.length > 0 && <section className="recent-checks"><div className="section-line"><h2>Your recent checks</h2><Link to="/reports" className="text-link">All session reports<ArrowRight size={16}/></Link></div>{checks.slice(0,3).map(check => <Link to={`/reports/${encodeURIComponent(check.result.session_id)}`} className="recent-row" key={check.result.session_id}><span className={`status-dot ${bands[bandFor(check.result)].tone}`}/><strong>{check.name}</strong><span>{check.sample ? 'Sample' : when(check.result.timestamp)}</span><span>{bands[bandFor(check.result)].label}</span><ArrowUpRight size={18}/></Link>)}</section>}
    <Reveal><section className="family-invitation"><span className="family-symbol"><Users size={38} strokeWidth={1}/></span><div><p className="eyebrow">A little preparation goes a long way</p><h2>Make familiar voices<br/>more than a feeling.</h2><p>Enroll someone you know, with their permission.<br/>Give your next check a voice to compare.</p><Link className="button ivory" to="/voices">Build your circle<ArrowUpRight size={18}/></Link></div><div className="family-visual" aria-hidden="true"><span>Aa</span><span>मा</span><span>पा</span><i/></div></section></Reveal>
    <div className="honesty-note"><ShieldQuestion size={20}/><p>A screening aid, not a determination of fraud. An unfamiliar voice is not automatically a suspicious one.</p></div>
  </div>;
}
