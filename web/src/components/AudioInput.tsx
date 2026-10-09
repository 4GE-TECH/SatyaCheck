import { useEffect, useRef, useState } from 'react';
import { Upload, Mic, FileAudio, X, Square } from 'lucide-react';
import { audioError } from '../api/client';
import { useRecorder } from '../hooks/useRecorder';
import { Button, Notice } from './Primitives';
import { formatTime } from '../lib/presentation';

interface Props {
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
  enrollment?: boolean;
  onBusyChange?: (busy: boolean) => void;
}

/** Upload or record a clip. Used by both the check requisition and enrollment. */
export default function AudioInput({ file, onFile, disabled = false, enrollment = false, onBusyChange }: Props) {
  const [mode, setMode] = useState<'upload' | 'record'>('upload');
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const player = useRef<HTMLAudioElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const recorder = useRecorder(choose);
  const busy = recorder.recording || recorder.starting;

  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => {
    if (!file || !player.current) return;
    const url = URL.createObjectURL(file);
    player.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function choose(next: File) {
    const problem = audioError(next);
    setError(problem);
    if (!problem) onFile(next);
  }

  if (file) {
    return (
      <div className="audio-input">
        <div className="selected-audio">
          <div className="file-row">
            <span className="file-icon" aria-hidden="true"><FileAudio size={22} /></span>
            <div className="file-meta">
              <strong className="truncate" title={file.name}>{file.name}</strong>
              <span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready</span>
            </div>
            <button type="button" className="icon-button" disabled={disabled} onClick={() => onFile(null)} aria-label="Remove selected audio">
              <X size={18} />
            </button>
          </div>
          <audio ref={player} controls preload="metadata" aria-label="Preview selected recording" />
        </div>
        {error && <Notice tone="danger">{error}</Notice>}
      </div>
    );
  }

  return (
    <div className="audio-input">
      <div className="segmented" role="group" aria-label="Audio source">
        {(['upload', 'record'] as const).map(value => (
          <button
            type="button"
            key={value}
            aria-pressed={mode === value}
            disabled={disabled || busy}
            onClick={() => { setMode(value); setError(null); }}
          >
            {value === 'upload' ? <Upload size={16} aria-hidden="true" /> : <Mic size={16} aria-hidden="true" />}
            {value === 'upload' ? 'Upload a file' : 'Record a clip'}
          </button>
        ))}
      </div>

      {mode === 'upload' ? (
        <div
          className={`drop-zone${dragging ? ' dragging' : ''}`}
          onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={event => {
            event.preventDefault();
            setDragging(false);
            if (!disabled && event.dataTransfer.files[0]) choose(event.dataTransfer.files[0]);
          }}
        >
          <FileAudio size={28} strokeWidth={1.6} aria-hidden="true" className="zone-icon" />
          <p className="zone-title">Drop a recording or voice note here</p>
          <Button type="button" disabled={disabled} onClick={() => input.current?.click()}>
            <Upload size={16} aria-hidden="true" />Choose audio file
          </Button>
          <span className="zone-hint">WAV, MP3, M4A, OGG, OPUS, FLAC or AMR · up to 50 MB</span>
          <input
            ref={input}
            type="file"
            aria-hidden="true"
            tabIndex={-1}
            className="visually-hidden"
            accept="audio/*,.wav,.mp3,.ogg,.opus,.webm,.m4a,.flac,.amr"
            disabled={disabled}
            onChange={event => {
              const selected = event.target.files?.[0];
              if (selected) choose(selected);
              event.target.value = '';
            }}
          />
        </div>
      ) : (
        <div className={`record-zone${recorder.recording ? ' recording' : ''}`}>
          <div className="record-status">
            <span className="rec-dot" aria-hidden="true" />
            <span className="rec-time" aria-live="off">{formatTime(recorder.seconds)}</span>
            <meter min={0} max={1} value={recorder.level} aria-label="Microphone sound level" />
          </div>
          <p className="zone-title">
            {recorder.recording ? 'Recording from this microphone' : enrollment ? 'Record about 30 seconds of natural speech' : 'Record a clip from a device near the speaker'}
          </p>
          <div className="button-row">
            {recorder.recording ? (
              <Button type="button" variant="danger" onClick={recorder.stop}><Square size={15} aria-hidden="true" />Stop and use clip</Button>
            ) : (
              <Button type="button" variant="secondary" busy={recorder.starting} disabled={disabled} onClick={recorder.start}>
                <Mic size={16} aria-hidden="true" />Start recording
              </Button>
            )}
            {busy && <Button type="button" variant="quiet" onClick={recorder.cancel}>Cancel</Button>}
          </div>
          {recorder.recording && recorder.seconds > 2 && recorder.level < 0.015 && (
            <span className="zone-hint warn">Very quiet. Move closer and speak normally.</span>
          )}
          <span className="zone-hint">{enrollment ? 'A quiet room works best. At least 15 seconds of speech is required.' : 'Up to 2 minutes. A phone in a call cannot record that call.'}</span>
        </div>
      )}
      {(error || recorder.error) && <Notice tone="danger">{error || recorder.error}</Notice>}
    </div>
  );
}
