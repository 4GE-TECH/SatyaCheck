import { useEffect, useRef, useState } from 'react';

export function useRecorder(onRecorded: (file: File) => void) {
  const [recording, setRecording] = useState(false);
  const [starting, setStarting] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const generation = useRef(0);
  const callback = useRef(onRecorded);
  useEffect(() => { callback.current = onRecorded; }, [onRecorded]);
  function release() {
    window.clearInterval(timer.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    void audio.current?.close().catch(() => {});
    audio.current = null;
  }
  function stop() {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }
  function cancel() {
    generation.current++;
    stop(); release();
    setRecording(false); setStarting(false); setLevel(0);
  }
  useEffect(() => () => { generation.current++; if (recorder.current?.state === 'recording') recorder.current.stop(); release(); }, []);
  async function start() {
    if (starting || recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('This browser cannot record here. Use a secure connection or upload an audio file.'); return;
    }
    setStarting(true); setError(null); setSeconds(0);
    const id = ++generation.current;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
      if (id !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      const context = new AudioContext(); audio.current = context;
      await context.resume();
      if (id !== generation.current) { release(); return; }
      const analyser = context.createAnalyser(); analyser.fftSize = 1024;
      context.createMediaStreamSource(media).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const active = new MediaRecorder(media, mimeType ? { mimeType } : undefined);
      recorder.current = active;
      const parts: Blob[] = [];
      let peak = 0;
      const began = performance.now();
      active.ondataavailable = event => { if (event.data.size) parts.push(event.data); };
      active.onerror = () => {
        if (id !== generation.current) return;
        generation.current++; release(); setRecording(false); setStarting(false);
        setError('The microphone stopped unexpectedly. Please record again.');
      };
      active.onstop = () => {
        if (id !== generation.current) return;
        release(); setRecording(false); setLevel(0);
        if (peak < 0.002) { setError('No audible sound was captured. Check your microphone or use a separate device if you are on a call.'); return; }
        const type = active.mimeType || 'audio/webm';
        const extension = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
        callback.current(new File(parts, `recording-${Date.now()}.${extension}`, { type }));
      };
      active.start(250); setStarting(false); setRecording(true);
      timer.current = window.setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((total, sample) => total + sample * sample, 0) / samples.length);
        peak = Math.max(peak, rms); setLevel(Math.min(1, rms * 8));
        const elapsed = Math.floor((performance.now() - began) / 1000);
        setSeconds(elapsed);
        if (elapsed >= 120) stop();
      }, 100);
    } catch (error) {
      if (id !== generation.current) return;
      release(); setStarting(false); setRecording(false);
      setError(error instanceof DOMException && error.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in browser settings, or upload a recording.' : 'Could not open the microphone. Check that another app is not using it.');
    }
  }
  return { recording, starting, seconds, level, error, start, stop, cancel };
}


