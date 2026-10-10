import { useEffect, useRef, useState } from 'react';
import type {
  CoverageSpan, ScreeningResponse, SessionAuthenticity, StreamV2Alert, StreamV2Assessment, TrustBand,
} from '../types/contracts';
import { parseScreening, wsUrl } from '../lib/api';
import { accessToken } from '../lib/auth';
import { encodeWav, resample, rms } from '../lib/audio';

export type LivePhase = 'idle' | 'connecting' | 'listening' | 'finishing' | 'done' | 'error';

export interface LivePoint { at: number; trust: number | null; band: TrustBand }

const RATE = 16_000;
/** v2 sends raw 16 kHz int16 frames this often (the server accepts 250-500 ms). */
const FRAME_SECONDS = 0.5;
const MAX_SECONDS = 600;
/** Below this RMS a frame is digital silence: the microphone opened but hears nothing. */
const SILENCE = 0.0005;
const RECONNECT_DELAYS_MS = [1000, 2000, 4000];

const TAP = `class Tap extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('satya-tap',Tap);`;

function newSessionId(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : Math.random().toString(16).slice(2, 18);
  return `live_${random}`;
}

/** Float samples in [-1, 1) to little-endian int16 PCM, the v2 wire format. */
export function toInt16(samples: Float32Array): ArrayBuffer {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out.buffer;
}

export interface LiveOptions {
  /** "Who's calling?" — an enrolled contact's id the voice is checked against. A claim, not proof. */
  claimedPersonId?: string | null;
}

export function useLiveSession() {
  const [phase, setPhaseState] = useState<LivePhase>('idle');
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [band, setBand] = useState<TrustBand | null>(null);
  const [alerts, setAlerts] = useState<StreamV2Alert[]>([]);
  const [committed, setCommitted] = useState('');
  const [tentative, setTentative] = useState('');
  const [coverage, setCoverage] = useState<CoverageSpan[]>([]);
  const [coverageDegraded, setCoverageDegraded] = useState(false);
  const [authenticity, setAuthenticity] = useState<SessionAuthenticity | null>(null);
  const [history, setHistory] = useState<LivePoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [sent, setSent] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [recording, setRecording] = useState<File | null>(null);

  const phaseRef = useRef<LivePhase>('idle');
  const socket = useRef<WebSocket | null>(null);
  const ready = useRef(false);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const pending = useRef<Float32Array[]>([]);
  const pendingLength = useRef(0);
  const captured = useRef<Float32Array[]>([]);
  const frames = useRef(0);
  const silentRun = useRef(0);
  const latest = useRef<ScreeningResponse | null>(null);
  const session = useRef('');
  const claim = useRef<string | null>(null);
  const started = useRef(0);
  const generation = useRef(0);
  const reconnects = useRef(0);
  const ticker = useRef<number | undefined>(undefined);
  const finishTimer = useRef<number | undefined>(undefined);

  function setPhase(next: LivePhase) {
    phaseRef.current = next;
    setPhaseState(next);
  }

  function releaseAudio() {
    window.clearInterval(ticker.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
    setAnalyser(null);
  }

  function closeSocket() {
    window.clearTimeout(finishTimer.current);
    const ws = socket.current;
    socket.current = null;
    ready.current = false;
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
  }

  function drain(): Float32Array {
    const out = new Float32Array(pendingLength.current);
    let offset = 0;
    for (const part of pending.current) { out.set(part, offset); offset += part.length; }
    pending.current = [];
    pendingLength.current = 0;
    return out;
  }

  function send(samples: Float32Array, rate: number) {
    const frame = resample(samples, rate, RATE);
    captured.current.push(frame);
    if (rms(frame) < SILENCE) {
      silentRun.current += 1;
      if (silentRun.current >= 6) {
        setWarning('No sound is reaching the microphone. A phone that is on the call cannot hear it. Use a second device near the speaker.');
      }
    } else {
      silentRun.current = 0;
      setWarning(current => (current?.startsWith('No sound') ? null : current));
    }
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !ready.current) return;
    ws.send(toInt16(frame));
    frames.current += 1;
    setSent(frames.current);
  }

  function buildRecording(): File | null {
    const total = captured.current.reduce((sum, part) => sum + part.length, 0);
    if (!total) return null;
    const all = new Float32Array(total);
    let offset = 0;
    for (const part of captured.current) { all.set(part, offset); offset += part.length; }
    return new File([encodeWav(all, RATE) as BlobPart], 'Live listening.wav', { type: 'audio/wav' });
  }

  function finish(id: number) {
    if (id !== generation.current) return;
    closeSocket();
    setRecording(buildRecording());
    if (latest.current) {
      setPhase('done');
    } else {
      setError('Listening ended before the service returned a result. Try again with a few seconds of speech.');
      setPhase('error');
    }
  }

  function onAssessment(message: StreamV2Assessment) {
    const next = parseScreening(message.current);
    latest.current = next;
    setResult(next);
    setBand(message.display_band);
    setAlerts(message.alerts);
    setCommitted(message.transcript_committed);
    setTentative(message.transcript_tentative);
    setCoverage(message.coverage);
    setCoverageDegraded(message.coverage_degraded);
    setAuthenticity(message.authenticity);
    setHistory(points => [...points, {
      at: (performance.now() - started.current) / 1000,
      trust: message.display_band === 'insufficient' ? null : next.fusion.trust_score,
      band: message.display_band,
    }]);
  }

  function onAlert(alert: StreamV2Alert) {
    setAlerts(list => [...list.filter(a => a.alert_id !== alert.alert_id), alert]);
  }

  /** Opens the v2 socket, signs in with the first message, resolves once the server is ready. */
  async function connect(id: number): Promise<void> {
    const token = await accessToken();
    const ws = await new Promise<WebSocket>((resolve, reject) => {
      const candidate = new WebSocket(wsUrl(`/api/ws/v2/screen/${encodeURIComponent(session.current)}`));
      candidate.binaryType = 'arraybuffer';
      const timeout = window.setTimeout(() => { candidate.close(); reject(new Error('Cannot reach the live screening service.')); }, 10_000);
      candidate.onopen = () => {
        candidate.send(JSON.stringify({
          type: 'start', token, client: 'web3', sample_rate: RATE, encoding: 's16le',
          caller_context: claim.current ? { claimed_identity: claim.current, channel_type: 'speakerphone' } : null,
        }));
      };
      candidate.onmessage = event => {
        let message: { type?: string; code?: string; detail?: string };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (message.type === 'ready') { window.clearTimeout(timeout); resolve(candidate); }
        else if (message.type === 'error') {
          window.clearTimeout(timeout);
          reject(new Error(message.code === 'busy' ? 'The screening service is busy. Try again in a minute.'
            : message.code === 'unauthorized' ? 'Your sign-in has expired. Sign in again to listen live.'
            : message.detail || 'The screening service refused this session.'));
        }
      };
      candidate.onerror = () => { window.clearTimeout(timeout); reject(new Error('Cannot reach the live screening service.')); };
    });
    if (id !== generation.current) { ws.close(); return; }
    socket.current = ws;
    ready.current = true;
    ws.onmessage = event => {
      if (id !== generation.current) return;
      let message: { type?: string; code?: string; detail?: string; is_final?: boolean };
      try { message = JSON.parse(String(event.data)); } catch { return; }
      try {
        if (message.type === 'assessment') {
          onAssessment(message as unknown as StreamV2Assessment);
          if (message.is_final) finish(id);
        } else if (message.type === 'alert') {
          onAlert(message as unknown as StreamV2Alert);
        } else if (message.type === 'error' && message.detail) {
          console.warn('SatyaCheck live: service error', message.code, message.detail);
          setWarning(`The service reported a problem: ${message.detail}`);
        }
      } catch (problem) {
        setWarning(problem instanceof Error ? problem.message : 'An update could not be read.');
      }
    };
    ws.onclose = () => {
      if (id !== generation.current || socket.current !== ws) return;
      socket.current = null;
      ready.current = false;
      if (phaseRef.current === 'finishing') { finish(id); return; }
      if (phaseRef.current === 'listening') void reconnect(id);
    };
  }

  async function reconnect(id: number) {
    const attempt = reconnects.current;
    if (attempt >= RECONNECT_DELAYS_MS.length) {
      releaseAudio();
      setRecording(buildRecording());
      setError('The connection to the screening service was lost. The last result is kept.');
      setPhase('error');
      return;
    }
    reconnects.current += 1;
    setWarning('Reconnecting to the screening service… audio during the gap is not screened.');
    await new Promise(resolve => window.setTimeout(resolve, RECONNECT_DELAYS_MS[attempt]));
    if (id !== generation.current || phaseRef.current !== 'listening') return;
    try {
      await connect(id);
      setWarning('Reconnected. A short stretch of audio was not screened.');
    } catch {
      void reconnect(id);
    }
  }

  async function start(options: LiveOptions = {}) {
    if (['connecting', 'listening', 'finishing'].includes(phaseRef.current)) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      setError('This browser cannot listen here. Use a secure connection, or upload a recording.');
      setPhase('error');
      return;
    }
    const id = ++generation.current;
    session.current = newSessionId();
    claim.current = options.claimedPersonId ?? null;
    latest.current = null;
    frames.current = 0;
    silentRun.current = 0;
    reconnects.current = 0;
    pending.current = [];
    pendingLength.current = 0;
    captured.current = [];
    setError(null); setWarning(null); setResult(null); setBand(null); setAlerts([]); setCommitted(''); setTentative('');
    setCoverage([]); setCoverageDegraded(false); setAuthenticity(null); setHistory([]); setElapsed(0); setSent(0);
    setRecording(null);
    setPhase('connecting');

    try {
      await connect(id);
    } catch (problem) {
      if (id !== generation.current) return;
      setError(problem instanceof Error ? problem.message : 'Cannot reach the live screening service.');
      setPhase('error');
      return;
    }
    if (id !== generation.current) return;

    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true },
      });
      if (id !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const audio = new AudioContext();
      context.current = audio;
      const moduleUrl = URL.createObjectURL(new Blob([TAP], { type: 'text/javascript' }));
      try { await audio.audioWorklet.addModule(moduleUrl); } finally { URL.revokeObjectURL(moduleUrl); }
      await audio.resume();
      if (id !== generation.current) { releaseAudio(); return; }
      const source = audio.createMediaStreamSource(media);
      const spectrum = audio.createAnalyser();
      spectrum.fftSize = 2048;
      spectrum.smoothingTimeConstant = 0.55;
      source.connect(spectrum);
      const tap = new AudioWorkletNode(audio, 'satya-tap');
      const mute = audio.createGain();
      mute.gain.value = 0;
      source.connect(tap).connect(mute).connect(audio.destination);
      const rate = audio.sampleRate;
      started.current = performance.now();
      tap.port.onmessage = (event: MessageEvent<Float32Array>) => {
        if (id !== generation.current || phaseRef.current !== 'listening') return;
        pending.current.push(event.data);
        pendingLength.current += event.data.length;
        if (pendingLength.current >= rate * FRAME_SECONDS) send(drain(), rate);
      };
      ticker.current = window.setInterval(() => {
        const seconds = Math.floor((performance.now() - started.current) / 1000);
        setElapsed(seconds);
        if (seconds >= MAX_SECONDS) stop();
      }, 250);
      setAnalyser(spectrum);
      setPhase('listening');
    } catch (problem) {
      if (id !== generation.current) return;
      releaseAudio();
      closeSocket();
      setError(problem instanceof DOMException && problem.name === 'NotAllowedError'
        ? 'Microphone access was denied. Allow it in your browser settings, or upload a recording.'
        : 'Could not open the microphone. Check that no other app is using it.');
      setPhase('error');
    }
  }

  function stop() {
    if (phaseRef.current !== 'listening') return;
    const id = generation.current;
    const rate = context.current?.sampleRate ?? RATE;
    setPhase('finishing');
    const rest = drain();
    releaseAudio();
    if (rest.length) send(rest, rate);
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'end' }));
    else { finish(id); return; }
    finishTimer.current = window.setTimeout(() => finish(id), 45_000);
  }

  function reset() {
    generation.current += 1;
    releaseAudio();
    closeSocket();
    latest.current = null;
    captured.current = [];
    setResult(null); setBand(null); setAlerts([]); setCommitted(''); setTentative(''); setCoverage([]);
    setCoverageDegraded(false); setAuthenticity(null); setHistory([]); setError(null); setWarning(null);
    setElapsed(0); setSent(0); setRecording(null);
    setPhase('idle');
  }

  useEffect(() => () => {
    generation.current += 1;
    window.clearInterval(ticker.current);
    window.clearTimeout(finishTimer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    void context.current?.close().catch(() => {});
    socket.current?.close();
  }, []);

  return {
    phase, result, band, alerts, committed, tentative, coverage, coverageDegraded, authenticity,
    history, error, warning, elapsed, sent, analyser, recording, sessionId: session.current, start, stop, reset,
  };
}
