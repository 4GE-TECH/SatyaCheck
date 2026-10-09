import { useEffect, useRef, useState } from 'react';

export function useCapture(onClip: (file: File) => void) {
  const [state, setState] = useState<'idle'|'opening'|'recording'>('idle');
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState('');
  const resources = useRef<{ stream?: MediaStream; context?: AudioContext; recorder?: MediaRecorder; timer?: number }>({});
  const epoch = useRef(0);
  const pending = useRef(false);
  const callback = useRef(onClip);
  callback.current = onClip;
  function release() {
    const r = resources.current;
    clearInterval(r.timer);
    r.stream?.getTracks().forEach(track => track.stop());
    if (r.context?.state !== 'closed') void r.context?.close().catch(error => console.warn('Audio cleanup failed', error));
    resources.current = {};
    pending.current = false;
  }
  function stop() { if (resources.current.recorder?.state === 'recording') resources.current.recorder.stop(); }
  function cancel() { epoch.current++; stop(); release(); setState('idle'); setLevel(0); }
  useEffect(() => () => { epoch.current++; if (resources.current.recorder?.state === 'recording') resources.current.recorder.stop(); release(); }, []);
  async function start() {
    if (pending.current) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Recording needs HTTPS or localhost and a supported browser. You can upload an audio file instead.'); return; }
    pending.current = true;
    const token = ++epoch.current;
    setError(''); setState('opening'); setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
      if (token !== epoch.current) { stream.getTracks().forEach(t => t.stop()); return; }
      resources.current.stream = stream;
      const context = new AudioContext(); resources.current.context = context;
      await context.resume();
      if (token !== epoch.current) return;
      const analyser = context.createAnalyser(); analyser.fftSize = 1024;
      context.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const mimeType = ['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      resources.current.recorder = recorder;
      const chunks: Blob[] = []; let loudest = 0; const startTime = performance.now();
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => {
        if (token !== epoch.current) return;
        console.warn('Microphone recording interrupted'); epoch.current++; release(); setState('idle'); setError('The microphone stopped unexpectedly. Try recording again.');
      };
      recorder.onstop = () => {
        if (token !== epoch.current) return;
        release(); setState('idle'); setLevel(0);
        if (loudest < .002) { console.warn('Capture rejected: no audible amplitude'); setError('No audible speech was captured. Check the microphone, or use a second device if you are on a call.'); return; }
        const type = recorder.mimeType || 'audio/webm';
        const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
        const file = new File(chunks, `Nearby recording.${ext}`, { type });
        if (!file.size) { setError('The recording is empty. Please try again.'); return; }
        callback.current(file);
      };
      recorder.start(250); setState('recording');
      resources.current.timer = window.setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
        loudest = Math.max(loudest, rms); setLevel(Math.min(1, rms * 9));
        const elapsed = Math.floor((performance.now() - startTime) / 1000); setSeconds(elapsed);
        if (elapsed >= 90) stop();
      }, 120);
    } catch (problem) {
      if (token !== epoch.current) return;
      console.warn('Unable to open microphone', problem); release(); setState('idle');
      setError(problem instanceof DOMException && problem.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow access in your browser, or upload a recording.' : 'The microphone could not be opened. Close other recording apps and try again.');
    }
  }
  return { state, seconds, level, error, start, stop, cancel };
}
