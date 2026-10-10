import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, ArrowUpRight, Broadcast, ChatCircleText, FileAudio, Fingerprint, Microphone, Pause, Play, Stop, UploadSimple, Waveform, X,
} from '@phosphor-icons/react';
import { useWorkspace, type Source } from '../../app/workspace';
import { audioError, screenFile } from '../../lib/api';
import { decodeFile, peaks } from '../../lib/audio';
import { BANDS, clock, displayBand, when } from '../../lib/verdict';
import { EASE, ScrollTrigger, SplitText, gsap, reducedMotion, useGSAP } from '../../lib/motion';
import { useRecorder } from '../../hooks/useRecorder';
import VoiceField from '../../components/VoiceField';
import InlineWave from '../../components/InlineWave';
import { ambient } from '../../components/AmbientField';
import { Button, ButtonLink, Notice, ToneChip } from '../../components/ui';
import { CallerPicker } from '../../components/CallerPicker';
import SignalAccordion from './SignalAccordion';
import { SAMPLES } from './samples';
import { ADVISORIES } from './advisories';

type Mode = 'upload' | 'record';

const SAMPLE_BAND = { green: 'verified', red: 'high_risk', caution: 'caution', suspicious: 'suspicious', unverified: 'unverified', insufficient: 'insufficient' } as const;

export default function CheckPage() {
  const navigate = useNavigate();
  const { addRecord, records } = useWorkspace();
  const [mode, setMode] = useState<Mode>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<Source>('upload');
  const [waveform, setWaveform] = useState<Float32Array | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [claim, setClaim] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const preview = useRef<HTMLAudioElement>(null);
  const page = useRef<HTMLDivElement>(null);
  const decodeId = useRef(0);
  const recorder = useRecorder(clip => choose(clip, 'clip'));

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => { ambient.level = recorder.state === 'recording' ? recorder.level : 0; }, [recorder.level, recorder.state]);
  useEffect(() => () => { ambient.level = 0; }, []);

  useGSAP(() => {
    if (reducedMotion()) return;
    // Headline: lines rise out of a mask. Text is real text throughout; SplitText reverts after.
    const split = SplitText.create('.hero-title', { type: 'lines', mask: 'lines', autoSplit: true, onSplit: self =>
      gsap.from(self.lines, { yPercent: 105, duration: 1.1, stagger: 0.09, ease: EASE.out }),
    });
    gsap.from('.hero-lede', { y: 16, duration: 0.9, delay: 0.25, ease: EASE.out });
    gsap.from('.composer', { y: 28, scale: 0.985, duration: 1.1, delay: 0.1, ease: EASE.out });

    // The principle statement brightens word by word as it scrolls through.
    const statement = SplitText.create('.principle-text', { type: 'words' });
    gsap.fromTo(statement.words, { opacity: 0.16 }, {
      opacity: 1, stagger: 0.08, ease: 'none',
      scrollTrigger: { trigger: '.principle', start: 'top 75%', end: 'bottom 55%', scrub: true },
    });

    // Samples stack: each card pins and the next one slides over it.
    const cards = gsap.utils.toArray<HTMLElement>('.stack-card');
    if (window.matchMedia('(min-width: 900px)').matches) {
      cards.forEach((card, i) => {
        if (i === cards.length - 1) return;
        gsap.to(card, {
          scale: 0.94 - (cards.length - i) * 0.005, filter: 'brightness(0.7)', ease: 'none',
          scrollTrigger: { trigger: cards[i + 1], start: 'top bottom', end: 'top 30%', scrub: true },
        });
      });
    }

    // The advisory marquee drifts continuously; hover or focus pauses it.
    const track = page.current?.querySelector<HTMLElement>('.marquee-track');
    if (track) {
      const loop = gsap.to(track, { xPercent: -50, duration: 60, ease: 'none', repeat: -1 });
      const pause = () => loop.pause();
      const resume = () => loop.resume();
      track.addEventListener('pointerenter', pause);
      track.addEventListener('pointerleave', resume);
      track.addEventListener('focusin', pause);
      track.addEventListener('focusout', resume);
    }
    ScrollTrigger.refresh();
    return () => { split.revert(); statement.revert(); };
  }, { scope: page });

  function choose(next: File, from: Source) {
    const problem = audioError(next);
    if (problem) { setError(problem); return; }
    const id = ++decodeId.current;
    setError(null);
    setFile(next);
    setSource(from);
    setWaveform(null);
    setDuration(null);
    setPlaying(false);
    setPreviewUrl(URL.createObjectURL(next));
    void decodeFile(next).then(audio => {
      if (!audio || id !== decodeId.current) return;
      setWaveform(peaks(audio.samples, 220));
      setDuration(audio.duration);
    });
  }

  function clear() {
    controller.current?.abort();
    decodeId.current++;
    setFile(null); setWaveform(null); setDuration(null); setError(null); setPreviewUrl(null); setPlaying(false);
  }

  async function check() {
    if (!file || checking) return;
    const active = new AbortController();
    controller.current = active;
    setChecking(true);
    setError(null);
    preview.current?.pause();
    try {
      const data = await screenFile(file, active.signal, claim);
      if (active.signal.aborted) return;
      addRecord({ data, name: file.name, source, audio: file });
      navigate(`/report/${encodeURIComponent(data.session_id)}`);
    } catch (problem) {
      if (!active.signal.aborted) setError(problem instanceof Error ? problem.message : 'The recording could not be checked. Please try again.');
    } finally {
      if (controller.current === active) { controller.current = null; setChecking(false); }
    }
  }

  async function openSample(index: number) {
    const sample = SAMPLES[index];
    const data = await sample.load();
    addRecord({ data, name: `Sample · ${sample.label}`, source: 'sample' });
    navigate(`/report/${encodeURIComponent(data.session_id)}`);
  }

  const recording = recorder.state !== 'idle';
  const stage = checking ? 'checking' : file ? 'ready' : recording ? 'recording' : mode;

  return (
    <div className="page check-page" ref={page}>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title" className="hero-title">
            Is this voice <InlineWave /> really who it says it is?
          </h1>
          <p className="hero-lede">Drop in a call recording or voice note. SatyaCheck checks who is speaking, whether the voice is synthetic and what is being asked, then tells you what to do next.</p>
        </div>

        <div className="bezel composer-bezel">
          <div
            className={`composer state-${stage}${dragging ? ' is-dragging' : ''}`}
            onDragOver={event => { event.preventDefault(); if (!checking && !recording) setDragging(true); }}
            onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
            onDrop={event => {
              event.preventDefault();
              setDragging(false);
              const dropped = event.dataTransfer.files[0];
              if (dropped && !checking && !recording) choose(dropped, 'upload');
            }}
          >
            <div className="composer-top">
              <div className="segmented" role="group" aria-label="How to add audio">
                {(['upload', 'record'] as const).map(value => (
                  <button key={value} type="button" aria-pressed={mode === value && !file} disabled={checking || recording} onClick={() => { clear(); setMode(value); }}>
                    {value === 'upload' ? <UploadSimple size={16} weight="light" aria-hidden="true" /> : <Microphone size={16} weight="light" aria-hidden="true" />}
                    {value === 'upload' ? 'Upload' : 'Record a clip'}
                  </button>
                ))}
              </div>
              <Link to="/live" className="live-link"><Broadcast size={18} weight="light" aria-hidden="true" />Listen to a live call<ArrowUpRight size={14} weight="bold" aria-hidden="true" /></Link>
            </div>

            <div className="stage">
              <VoiceField level={recorder.level} waveform={waveform} scanning={checking} />
              {stage === 'upload' && (
                <div className="stage-content">
                  <span className="stage-icon"><FileAudio size={26} weight="light" aria-hidden="true" /></span>
                  <p className="stage-title">{dragging ? 'Let go to add this recording' : 'Drop a recording or voice note'}</p>
                  <Button onClick={() => picker.current?.click()}><UploadSimple size={17} weight="light" aria-hidden="true" />Choose audio file</Button>
                  <span className="stage-hint">WAV, MP3, M4A, OGG, OPUS, FLAC or AMR, up to 50 MB</span>
                </div>
              )}
              {stage === 'record' && (
                <div className="stage-content">
                  <button type="button" className="rec-button" onClick={recorder.start} disabled={recorder.state === 'starting'} aria-label="Start recording">
                    <Microphone size={30} weight="fill" aria-hidden="true" />
                  </button>
                  <p className="stage-title">Record from a device near the speaker</p>
                  <span className="stage-hint">Up to 2 minutes. A phone that is on the call cannot record that call.</span>
                </div>
              )}
              {stage === 'recording' && (
                <div className="stage-content">
                  <span className="rec-live"><span className="rec-dot" aria-hidden="true" />Recording</span>
                  <p className="stage-clock num" aria-live="off">{clock(recorder.seconds)}</p>
                  <div className="row-gap">
                    <Button variant="danger" onClick={recorder.stop}><Stop size={16} weight="fill" aria-hidden="true" />Stop and use clip</Button>
                    <Button variant="ghost" onClick={recorder.cancel}>Cancel</Button>
                  </div>
                  {recorder.seconds > 2 && recorder.level < 0.015 && <span className="stage-hint warn">Very quiet. Move closer to the speaker.</span>}
                </div>
              )}
              {stage === 'ready' && file && (
                <div className="stage-content stage-file">
                  <div className="file-chip">
                    <button type="button" className="play" onClick={() => { const a = preview.current; if (a) { if (a.paused) void a.play(); else a.pause(); } }} aria-label={playing ? 'Pause preview' : 'Play preview'}>
                      {playing ? <Pause size={16} weight="fill" /> : <Play size={16} weight="fill" />}
                    </button>
                    <div className="file-meta">
                      <strong className="ellipsis" title={file.name}>{file.name}</strong>
                      <span className="num">{duration ? clock(duration) : '—:—'} · {(file.size / 1024 / 1024).toFixed(2)} MB</span>
                    </div>
                    <button type="button" className="icon-btn" onClick={clear} aria-label="Remove this recording"><X size={16} weight="bold" /></button>
                  </div>
                  {previewUrl && <audio ref={preview} src={previewUrl} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} preload="metadata" aria-label="Preview of the selected recording" />}
                </div>
              )}
              {stage === 'checking' && (
                <div className="stage-content stage-checking" role="status" aria-live="polite">
                  <p className="stage-title">Listening to {file?.name}</p>
                  <ul className="checking-rows">
                    <li><Fingerprint size={18} weight="light" aria-hidden="true" />Comparing with known voices</li>
                    <li><Waveform size={18} weight="light" aria-hidden="true" />Scoring each moment for synthetic speech</li>
                    <li><ChatCircleText size={18} weight="light" aria-hidden="true" />Reading what is being asked</li>
                  </ul>
                  <Button variant="ghost" size="sm" onClick={() => controller.current?.abort()}>Cancel</Button>
                </div>
              )}
              <input
                ref={picker}
                type="file"
                className="sr-only"
                tabIndex={-1}
                aria-hidden="true"
                accept="audio/*,.wav,.mp3,.ogg,.opus,.webm,.m4a,.flac,.amr"
                onChange={event => { const picked = event.target.files?.[0]; if (picked) choose(picked, 'upload'); event.target.value = ''; }}
              />
            </div>

            {(error || recorder.error) && <div className="composer-error"><Notice tone="danger">{error || recorder.error}</Notice></div>}

            {file && <div className="composer-claim"><CallerPicker value={claim} onChange={setClaim} disabled={checking} /></div>}

            <div className="composer-foot">
              <p>Only check recordings you have permission to use. Audio goes to your configured screening service.</p>
              <Button variant="primary" size="lg" disabled={!file || recording} busy={checking} onClick={check} trail={<ArrowRight size={16} weight="bold" />}>
                {checking ? 'Checking…' : 'Check this recording'}
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="chapter" aria-labelledby="signals-title">
        <div className="chapter-head">
          <h2 id="signals-title">Three questions, answered together</h2>
          <p>Each is checked on its own, then combined into one trust score with the evidence behind it.</p>
        </div>
        <SignalAccordion />
      </section>

      <section className="principle" aria-label="The principle">
        <p className="principle-text">A real emergency asks you to check. A scam asks you not to. SatyaCheck listens for both, and never calls anyone a fraud.</p>
      </section>

      <section className="chapter marquee-chapter" aria-labelledby="patterns-title">
        <div className="chapter-head">
          <h2 id="patterns-title">Recognises patterns from published advisories</h2>
          <p>When a call resembles a documented scam, the report cites the advisory it matched.</p>
        </div>
        <div className="marquee" aria-label="Advisories in the pattern library">
          <ul className="marquee-track">
            {[...ADVISORIES, ...ADVISORIES].map((advisory, i) => (
              <li key={i} aria-hidden={i >= ADVISORIES.length || undefined}>
                <strong>{advisory.title}</strong>
                <span>{advisory.agency}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="chapter" aria-labelledby="samples-title">
        <div className="chapter-head">
          <h2 id="samples-title">See it on six labelled samples</h2>
          <p>Demonstrations of each result type. They never describe your own audio.</p>
        </div>
        <ol className="stack">
          {SAMPLES.map((sample, i) => {
            const band = BANDS[SAMPLE_BAND[sample.scenario]];
            return (
              <li key={sample.scenario} className={`stack-card tone-${band.tone}`} style={{ top: `${110 + i * 14}px` }}>
                <div className="stack-text">
                  <ToneChip tone={band.tone}>{band.label}</ToneChip>
                  <h3>{sample.label}</h3>
                  <p>{sample.story}.</p>
                </div>
                <p className="stack-headline">{band.headline}</p>
                <Button onClick={() => void openSample(i)} disabled={checking || recording} trail={<ArrowRight size={14} weight="bold" />}>
                  Open sample
                </Button>
              </li>
            );
          })}
        </ol>
      </section>

      <section className="finale" aria-labelledby="finale-title">
        <h2 id="finale-title">When a call feels wrong, check before you act.</h2>
        <div className="finale-actions">
          <Button variant="primary" size="lg" onClick={() => { window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' }); page.current?.querySelector<HTMLButtonElement>('.composer .stage button')?.focus({ preventScroll: true }); }} trail={<ArrowRight size={16} weight="bold" />}>
            Check a recording
          </Button>
          <ButtonLink to="/live" size="lg" trail={<Broadcast size={16} weight="light" />}>Listen live</ButtonLink>
        </div>
        {records.length > 0 && (
          <ul className="session-strip" aria-label="Reports this session">
            {records.slice(0, 4).map(record => {
              const band = displayBand(record.data);
              return (
                <li key={record.data.session_id}>
                  <Link to={`/report/${encodeURIComponent(record.data.session_id)}`}>
                    <span className="ellipsis">{record.name}</span>
                    <span className="muted">{record.source === 'sample' ? 'Sample' : when(record.data.timestamp)}</span>
                    <ToneChip tone={BANDS[band].tone}>{BANDS[band].label}</ToneChip>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
