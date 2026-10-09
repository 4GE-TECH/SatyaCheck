import { useEffect, useRef, useState } from 'react';
import type { ScreeningResponse } from '../types/contracts';
import { parseScreening } from '../api/client';
import { encodeWav, resample, rms, toBase64 } from '../lib/wav';
import { useWorkspace } from '../context/workspace-state';

export type LivePhase = 'idle' | 'connecting' | 'listening' | 'finishing' | 'done' | 'error';

const TARGET_RATE = 16_000;
const CHUNK_SECONDS = 3;
const MAX_SECONDS = 600;
/** Below this RMS a chunk is treated as digital silence: the stream opened but hears nothing. */
const SILENCE_RMS = 0.0005;

const TAP_SOURCE = `
class SatyaTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor('satya-tap', SatyaTap);
`;

function sessionId(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : Math.random().toString(16).slice(2, 18);
  return `live_${random}`;
}

function socketUrl(id: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ws/screen/${encodeURIComponent(id)}`;
}

export default function useLiveScreening() {
  const [phase, setPhase] = useState<LivePhase>('idle');
  const [data, setData] = useState<ScreeningResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [sent, setSent] = useState(0);
  const [received, setReceived] = useState(0);
  const { add } = useWorkspace();

  const socket = useRef<WebSocket | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const pending = useRef<Float32Array[]>([]);
  const pendingLength = useRef(0);
  const chunkIndex = useRef(0);
  const silentChunks = useRef(0);
  const latest = useRef<ScreeningResponse | null>(null);
  const levelRef = useRef(0);
  const ticker = useRef<number | undefined>(undefined);
  const finishTimer = useRef<number | undefined>(undefined);
  const finalChunk = useRef<number | null>(null);
  const finalAcknowledged = useRef(false);
  const lastAcceptedChunk = useRef(-1);
  const generation = useRef(0);
  const phaseRef = useRef<LivePhase>('idle');
  const sessionRef = useRef('');

  function move(next: LivePhase) {
    phaseRef.current = next;
    setPhase(next);
  }

  function releaseAudio() {
    window.clearInterval(ticker.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
    setLevel(0);
  }

  function closeSocket() {
    window.clearTimeout(finishTimer.current);
    const ws = socket.current;
    socket.current = null;
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
  }

  function takePending(): Float32Array {
    const out = new Float32Array(pendingLength.current);
    let offset = 0;
    for (const part of pending.current) {
      out.set(part, offset);
      offset += part.length;
    }
    pending.current = [];
    pendingLength.current = 0;
    return out;
  }

  function sendChunk(samples: Float32Array, rate: number, final: boolean) {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const audio = resample(samples, rate, TARGET_RATE);
    const silent = rms(audio) < SILENCE_RMS;
    if (silent && !final) {
      silentChunks.current += 1;
      if (silentChunks.current >= 2) {
        setWarning('No sound is reaching the microphone. If this device is on the call, it cannot hear it. Use a separate device near the speaker.');
      }
      return;
    }
    silentChunks.current = 0;
    setWarning(null);
    ws.send(JSON.stringify({
      type: 'audio_chunk',
      session_id: sessionRef.current,
      chunk_index: chunkIndex.current,
      audio_base64: toBase64(encodeWav(audio, TARGET_RATE)),
      is_final: final,
    }));
    if (final) finalChunk.current = chunkIndex.current;
    chunkIndex.current += 1;
    setSent(chunkIndex.current);
  }

  function complete(id: number) {
    if (id !== generation.current) return;
    closeSocket();
    const result = latest.current;
    if (result && finalAcknowledged.current) {
      add({ data: result, demo: false, name: 'Live listening' });
      move('done');
    } else {
      setError('The service did not confirm the final audio slice. The last result remains provisional and was not saved as a final report. Try listening again.');
      move('error');
    }
  }

  async function start() {
    if (phaseRef.current === 'connecting' || phaseRef.current === 'listening' || phaseRef.current === 'finishing') return;
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      setError('This browser cannot listen here. Use a secure connection or upload a recording instead.');
      move('error');
      return;
    }
    const id = ++generation.current;
    const session = sessionId();
    sessionRef.current = session;
    setError(null); setWarning(null); setData(null); setSeconds(0); setSent(0); setReceived(0);
    latest.current = null; chunkIndex.current = 0; silentChunks.current = 0;
    finalChunk.current = null; finalAcknowledged.current = false; levelRef.current = 0;
    lastAcceptedChunk.current = -1;
    pending.current = []; pendingLength.current = 0;
    move('connecting');

    try {
      const ws = await new Promise<WebSocket>((resolve, reject) => {
        const candidate = new WebSocket(socketUrl(session));
        socket.current = candidate;
        const timeout = window.setTimeout(() => { candidate.close(); reject(new Error('timeout')); }, 8000);
        candidate.onopen = () => { window.clearTimeout(timeout); resolve(candidate); };
        candidate.onerror = () => { window.clearTimeout(timeout); reject(new Error('socket')); };
        candidate.onclose = () => { window.clearTimeout(timeout); reject(new Error('closed')); };
      });
      if (id !== generation.current) { ws.close(); return; }
      socket.current = ws;
      ws.onmessage = event => {
        if (id !== generation.current) return;
        let message: { type?: string; detail?: string; session_id?: string; chunk_index?: number; response?: unknown };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (message.type === 'screening_update') {
          try {
            const result = parseScreening(message.response);
            if (message.session_id !== session || result.session_id !== session) {
              setWarning('An update did not match this listening session and was ignored.');
              return;
            }
            if (!Number.isInteger(message.chunk_index) || message.chunk_index! < 0 || message.chunk_index! >= chunkIndex.current || message.chunk_index! <= lastAcceptedChunk.current) return;
            lastAcceptedChunk.current = message.chunk_index!;
            latest.current = result;
            setData(result);
            setReceived(count => count + 1);
            if (finalChunk.current != null && message.chunk_index === finalChunk.current) finalAcknowledged.current = true;
          } catch (problem) {
            setWarning(problem instanceof Error ? problem.message : 'An update could not be read.');
          }
        } else if (message.type === 'error' && message.detail) {
          setWarning(`The service reported a problem: ${message.detail}`);
        }
      };
      ws.onclose = () => {
        if (id !== generation.current) return;
        if (phaseRef.current === 'finishing') { complete(id); return; }
        if (phaseRef.current === 'listening' || phaseRef.current === 'connecting') {
          generation.current += 1;
          releaseAudio();
          socket.current = null;
          setError('The connection to the screening service closed. The last provisional result is kept below.');
          move('error');
        }
      };
    } catch {
      if (id !== generation.current) return;
      closeSocket();
      setError('Cannot reach the live screening service. Check that it is running, or upload a recording instead.');
      move('error');
      return;
    }

    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true },
      });
      if (id !== generation.current || socket.current?.readyState !== WebSocket.OPEN) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const audio = new AudioContext();
      context.current = audio;
      const moduleUrl = URL.createObjectURL(new Blob([TAP_SOURCE], { type: 'text/javascript' }));
      try { await audio.audioWorklet.addModule(moduleUrl); } finally { URL.revokeObjectURL(moduleUrl); }
      if (id !== generation.current) { media.getTracks().forEach(track => track.stop()); void audio.close().catch(() => {}); return; }
      await audio.resume();
      if (id !== generation.current || socket.current?.readyState !== WebSocket.OPEN) { media.getTracks().forEach(track => track.stop()); void audio.close().catch(() => {}); return; }
      const source = audio.createMediaStreamSource(media);
      const tap = new AudioWorkletNode(audio, 'satya-tap');
      const mute = audio.createGain();
      mute.gain.value = 0;
      source.connect(tap).connect(mute).connect(audio.destination);
      const rate = audio.sampleRate;
      const began = performance.now();
      tap.port.onmessage = (event: MessageEvent<Float32Array>) => {
        if (id !== generation.current || phaseRef.current !== 'listening') return;
        const block = event.data;
        pending.current.push(block);
        pendingLength.current += block.length;
        levelRef.current = Math.max(levelRef.current * 0.9, rms(block));
        if (pendingLength.current >= rate * CHUNK_SECONDS) sendChunk(takePending(), rate, false);
      };
      ticker.current = window.setInterval(() => {
        setLevel(Math.min(1, levelRef.current * 8));
        const elapsed = Math.floor((performance.now() - began) / 1000);
        setSeconds(elapsed);
        if (elapsed >= MAX_SECONDS) stop();
      }, 120);
      move('listening');
    } catch (problem) {
      if (id !== generation.current) return;
      releaseAudio();
      closeSocket();
      setError(problem instanceof DOMException && problem.name === 'NotAllowedError'
        ? 'Microphone access was denied. Allow it in browser settings, or upload a recording.'
        : 'Could not open the microphone. Check that another app is not using it.');
      move('error');
    }
  }

  function stop() {
    if (phaseRef.current !== 'listening') return;
    const id = generation.current;
    const rate = context.current?.sampleRate ?? TARGET_RATE;
    move('finishing');
    const rest = takePending();
    releaseAudio();
    sendChunk(rest.length ? rest : new Float32Array(rate / 2), rate, true);
    finishTimer.current = window.setTimeout(() => complete(id), 45_000);
  }

  function reset() {
    generation.current += 1;
    releaseAudio();
    closeSocket();
    latest.current = null;
    finalChunk.current = null; finalAcknowledged.current = false;
    setData(null); setError(null); setWarning(null); setSeconds(0); setSent(0); setReceived(0);
    move('idle');
  }

  useEffect(() => () => {
    generation.current += 1;
    window.clearInterval(ticker.current);
    window.clearTimeout(finishTimer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    void context.current?.close().catch(() => {});
    socket.current?.close();
  }, []);

  return { phase, data, error, warning, seconds, level, sent, received, start, stop, reset };
}
