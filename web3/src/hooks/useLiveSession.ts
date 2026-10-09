import { useEffect, useRef, useState } from 'react';
import type { ScreeningResponse, TrustBand } from '../types/contracts';
import { parseScreening } from '../lib/api';
import { displayBand } from '../lib/verdict';
import { encodeWav, resample, rms, toBase64 } from '../lib/audio';

export type LivePhase = 'idle' | 'connecting' | 'listening' | 'finishing' | 'done' | 'error';

export interface LivePoint { at: number; trust: number | null; band: TrustBand }

const RATE = 16_000;
const SLICE_SECONDS = 3;
const MAX_SECONDS = 600;
/** Below this RMS a slice is digital silence: the microphone opened but hears nothing. */
const SILENCE = 0.0005;

const TAP = `class Tap extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('satya-tap',Tap);`;

function newSessionId(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : Math.random().toString(16).slice(2, 18);
  return `live_${random}`;
}

export function useLiveSession() {
  const [phase, setPhaseState] = useState<LivePhase>('idle');
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [history, setHistory] = useState<LivePoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [sent, setSent] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [recording, setRecording] = useState<File | null>(null);

  const phaseRef = useRef<LivePhase>('idle');
  const socket = useRef<WebSocket | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const pending = useRef<Float32Array[]>([]);
  const pendingLength = useRef(0);
  const captured = useRef<Float32Array[]>([]);
  const chunk = useRef(0);
  const silentRun = useRef(0);
  const latest = useRef<ScreeningResponse | null>(null);
  const session = useRef('');
  const started = useRef(0);
  const generation = useRef(0);
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

  function send(samples: Float32Array, rate: number, final: boolean) {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const slice = resample(samples, rate, RATE);
    captured.current.push(slice);
    if (rms(slice) < SILENCE && !final) {
      silentRun.current += 1;
      if (silentRun.current >= 2) {
        console.warn(`SatyaCheck live: ${silentRun.current} silent slices skipped`);
        setWarning('No sound is reaching the microphone. A phone that is on the call cannot hear it. Use a second device near the speaker.');
      }
      return;
    }
    silentRun.current = 0;
    setWarning(null);
    ws.send(JSON.stringify({
      type: 'audio_chunk',
      session_id: session.current,
      chunk_index: chunk.current,
      audio_base64: toBase64(encodeWav(slice, RATE)),
      is_final: final,
    }));
    chunk.current += 1;
    setSent(chunk.current);
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

  async function start() {
    if (['connecting', 'listening', 'finishing'].includes(phaseRef.current)) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      setError('This browser cannot listen here. Use a secure connection, or upload a recording.');
      setPhase('error');
      return;
    }
    const id = ++generation.current;
    session.current = newSessionId();
    latest.current = null;
    chunk.current = 0;
    silentRun.current = 0;
    pending.current = [];
    pendingLength.current = 0;
    captured.current = [];
    setError(null); setWarning(null); setResult(null); setHistory([]); setElapsed(0); setSent(0); setRecording(null);
    setPhase('connecting');

    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = await new Promise<WebSocket>((resolve, reject) => {
        const candidate = new WebSocket(`${protocol}//${window.location.host}/api/ws/screen/${encodeURIComponent(session.current)}`);
        const timeout = window.setTimeout(() => { candidate.close(); reject(new Error('timeout')); }, 8000);
        candidate.onopen = () => { window.clearTimeout(timeout); resolve(candidate); };
        candidate.onerror = () => { window.clearTimeout(timeout); reject(new Error('socket')); };
      });
      if (id !== generation.current) { ws.close(); return; }
      socket.current = ws;
      ws.onmessage = event => {
        if (id !== generation.current) return;
        let message: { type?: string; detail?: string; response?: unknown };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (message.type === 'screening_update') {
          try {
            const next = parseScreening(message.response);
            latest.current = next;
            setResult(next);
            const band = displayBand(next);
            setHistory(points => [...points, {
              at: (performance.now() - started.current) / 1000,
              trust: band === 'insufficient' ? null : next.fusion.trust_score,
              band,
            }]);
          } catch (problem) {
            setWarning(problem instanceof Error ? problem.message : 'An update could not be read.');
          }
        } else if (message.type === 'error' && message.detail) {
          console.warn('SatyaCheck live: service error', message.detail);
          setWarning(`The service reported a problem: ${message.detail}`);
        }
      };
      ws.onclose = () => {
        if (id !== generation.current) return;
        if (phaseRef.current === 'finishing') { finish(id); return; }
        if (phaseRef.current === 'listening') {
          releaseAudio();
          socket.current = null;
          setRecording(buildRecording());
          setError('The connection to the screening service closed. The last provisional result is kept.');
          setPhase('error');
        }
      };
    } catch {
      if (id !== generation.current) return;
      setError('Cannot reach the live screening service. Check that it is running, or upload a recording instead.');
      setPhase('error');
      return;
    }

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
        if (pendingLength.current >= rate * SLICE_SECONDS) send(drain(), rate, false);
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
    send(rest.length ? rest : new Float32Array(Math.round(rate / 2)), rate, true);
    finishTimer.current = window.setTimeout(() => finish(id), 45_000);
  }

  function reset() {
    generation.current += 1;
    releaseAudio();
    closeSocket();
    latest.current = null;
    captured.current = [];
    setResult(null); setHistory([]); setError(null); setWarning(null); setElapsed(0); setSent(0); setRecording(null);
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

  return { phase, result, history, error, warning, elapsed, sent, analyser, recording, sessionId: session.current, start, stop, reset };
}
