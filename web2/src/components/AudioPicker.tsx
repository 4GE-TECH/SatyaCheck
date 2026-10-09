import { useEffect, useRef, useState } from 'react';
import { AudioLines, FileAudio, Mic, Square, Upload, X, ArrowRight } from 'lucide-react';
import { useCapture } from '../lib/useCapture';
import { time, validateAudio } from '../lib/api';
import { Button, ErrorNote } from './UI';

export default function AudioPicker({ file, onFile, enrollment = false, disabled = false, onBusy }: { file: File | null; onFile: (file: File | null) => void; enrollment?: boolean; disabled?: boolean; onBusy?: (busy: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<'upload'|'record'>('upload');
  const [error, setError] = useState('');
  const [drag, setDrag] = useState(false);
  const [url, setUrl] = useState('');
  const capture = useCapture(choose);
  const capturing = capture.state !== 'idle';
  useEffect(() => { onBusy?.(capturing); }, [capturing, onBusy]);
  useEffect(() => { if (!file) { setUrl(''); return; } const next = URL.createObjectURL(file); setUrl(next); return () => URL.revokeObjectURL(next); }, [file]);
  function choose(next: File) { const problem = validateAudio(next); setError(problem || ''); if (!problem) onFile(next); }
  return <div className="audio-picker">
    <input className="sr-only" ref={input} type="file" tabIndex={-1} aria-label="Audio recording" accept="audio/*,.wav,.mp3,.m4a,.ogg,.opus,.webm,.flac,.amr" disabled={disabled || capturing} onChange={e => { const chosen = e.target.files?.[0]; if (chosen) choose(chosen); e.target.value = ''; }}/>
    {file ? <div className="chosen-audio"><div className="chosen-file"><span className="file-symbol"><FileAudio size={27}/></span><div><span className="eyebrow">Ready to check</span><strong title={file.name}>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(2)} MB</small></div><button className="icon-button" disabled={disabled} onClick={() => onFile(null)} aria-label="Remove recording"><X size={18}/></button></div><audio src={url} controls preload="metadata" aria-label="Preview recording"/></div>
    : mode === 'upload' ? <div className={`upload-stage ${drag ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); if (!disabled) setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={event => { event.preventDefault(); setDrag(false); if (!disabled && event.dataTransfer.files[0]) choose(event.dataTransfer.files[0]); }}>
      <div className="upload-emblem" aria-hidden="true"><AudioLines size={35} strokeWidth={1.4}/><span/><span/></div>
      <div className="upload-copy"><h3>{enrollment ? 'A voice worth recognising.' : 'Bring the conversation into focus.'}</h3><p>Drop a recording or voice note here.</p><div className="picker-actions"><Button disabled={disabled} onClick={() => input.current?.click()}><Upload size={17}/>Upload recording<ArrowRight size={16}/></Button><Button disabled={disabled} variant="outline" onClick={() => { setError(''); setMode('record'); }}><Mic size={17}/>Record nearby</Button></div><small>WAV, MP3, M4A, OGG, OPUS, FLAC, AMR · Up to 50 MB</small></div>
    </div> : <div className="record-stage">
      <div className="record-readout"><span className={capturing ? 'record-dot active' : 'record-dot'}/><strong>{time(capture.seconds)}</strong><span>{capture.state === 'opening' ? 'Opening microphone…' : capturing ? 'Listening nearby' : 'Microphone ready'}</span></div>
      <meter min={0} max={1} value={capture.level} aria-label="Microphone amplitude"/>
      <p>{enrollment ? 'Speak naturally for about 60 seconds. Use a quiet room.' : 'Use a second device near a call on speaker. A phone in a cellular call cannot record that call.'}</p>
      <div className="picker-actions">{capturing ? <Button onClick={capture.stop} disabled={capture.state === 'opening'}><Square size={16}/>Stop and use recording</Button> : <Button onClick={capture.start} disabled={disabled}><Mic size={17}/>Start recording</Button>}<Button variant="ghost" onClick={() => { capture.cancel(); setMode('upload'); }}> {capturing ? 'Cancel recording' : 'Back to upload'}</Button></div>
      {capturing && capture.seconds > 2 && capture.level < .015 && <span className="quiet-note" role="status">Very quiet. Move closer to the speaker.</span>}
    </div>}
    {(error || (mode === 'record' && capture.error)) && <ErrorNote>{mode === 'record' ? capture.error || error : error}</ErrorNote>}
  </div>;
}
