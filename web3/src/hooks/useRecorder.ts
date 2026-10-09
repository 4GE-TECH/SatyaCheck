import { useEffect, useRef, useState } from 'react';

const MAX_SECONDS = 120;

/** Records a clip with MediaRecorder. Rejects clips that captured no audible sound. */
export function useRecorder(onClip: (file: File, seconds: number) => void) {
  const [state, setState] = useState<'idle' | 'starting' | 'recording'>('idle');
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const generation = useRef(0);
  const callback = useRef(onClip);
  useEffect(() => { callback.current = onClip; }, [onClip]);

  function release() {
    window.clearInterval(timer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
  }

  function stop() {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }

  function cancel() {
    generation.current++;
    stop();
    release();
    setState('idle');
    setLevel(0);
  }

  useEffect(() => () => {
    generation.current++;
    if (recorder.current?.state === 'recording') recorder.current.stop();
    window.clearInterval(timer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    void context.current?.close().catch(() => {});
  }, []);

  async function start() {
    if (state !== 'idle') return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('This browser cannot record here. Use a secure connection, or upload a file instead.');
      return;
    }
    const id = ++generation.current;
    setState('starting'); setError(null); setSeconds(0);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
      if (id !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const audio = new AudioContext();
      context.current = audio;
      await audio.resume();
      const analyser = audio.createAnalyser();
      analyser.fftSize = 1024;
      audio.createMediaStreamSource(media).connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const active = new MediaRecorder(media, mimeType ? { mimeType } : undefined);
      recorder.current = active;
      const parts: Blob[] = [];
      let loudest = 0;
      const began = performance.now();
      active.ondataavailable = event => { if (event.data.size) parts.push(event.data); };
      active.onerror = () => {
        if (id !== generation.current) return;
        generation.current++;
        release(); setState('idle');
        setError('The microphone stopped unexpectedly. Please record again.');
      };
      active.onstop = () => {
        if (id !== generation.current) return;
        release(); setState('idle'); setLevel(0);
        // A stream that opens is not a stream that hears anything: check amplitude, not length.
        if (loudest < 0.002) {
          setError('No sound was captured. Check the microphone. A phone that is on a call cannot hear that call.');
          return;
        }
        const type = active.mimeType || 'audio/webm';
        const extension = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
        const length = Math.round((performance.now() - began) / 1000);
        callback.current(new File(parts, `Clip ${new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}.${extension}`, { type }), length);
      };
      active.start(250);
      setState('recording');
      timer.current = window.setInterval(() => {
        analyser.getFloatTimeDomainData(buffer);
        let total = 0;
        for (const sample of buffer) total += sample * sample;
        const rms = Math.sqrt(total / buffer.length);
        loudest = Math.max(loudest, rms);
        setLevel(Math.min(1, rms * 8));
        const elapsed = Math.floor((performance.now() - began) / 1000);
        setSeconds(elapsed);
        if (elapsed >= MAX_SECONDS) stop();
      }, 80);
    } catch (problem) {
      if (id !== generation.current) return;
      release(); setState('idle');
      setError(problem instanceof DOMException && problem.name === 'NotAllowedError'
        ? 'Microphone access was denied. Allow it in your browser settings, or upload a file.'
        : 'Could not open the microphone. Check that no other app is using it.');
    }
  }

  return { state, seconds, level, error, start, stop, cancel, maxSeconds: MAX_SECONDS };
}
