import { useEffect, useRef, useState } from 'react';
import { Check, Copy, Download, Printer } from 'lucide-react';
import type { ScreeningResponse } from '../types/contracts';
import { request } from '../api/client';
import { reportText } from '../lib/report';
import { Button, Notice } from './Primitives';

export default function ReportActions({ data, demo }: { data: ScreeningResponse; demo: boolean }) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [problem, setProblem] = useState('');
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    setProblem('');
    try {
      await navigator.clipboard.writeText(reportText(data, demo));
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setProblem('Clipboard access is unavailable here. Use Print / save PDF instead.');
    }
  }

  async function download() {
    if (demo || downloading) return;
    setDownloading(true);
    setProblem('');
    try {
      const response = await request(`/api/report/${encodeURIComponent(data.session_id)}/pdf`);
      if (!response.headers.get('content-type')?.includes('application/pdf')) {
        throw new Error('The service did not return a PDF. Use Print / save PDF instead.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `satyacheck-${data.session_id}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'Could not download the report. Use Print / save PDF.');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="report-actions">
      <div className="button-row">
        <Button variant="secondary" onClick={copy}>
          {copied ? <Check size={17} aria-hidden="true" /> : <Copy size={17} aria-hidden="true" />}
          {copied ? 'Copied' : 'Copy summary'}
        </Button>
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer size={17} aria-hidden="true" />Print / save PDF
        </Button>
        {!demo && (
          <Button variant="secondary" busy={downloading} onClick={download}>
            {!downloading && <Download size={17} aria-hidden="true" />}Service PDF
          </Button>
        )}
      </div>
      {problem && <Notice tone="danger">{problem}</Notice>}
      <span className="visually-hidden" role="status">{copied ? 'Summary copied to clipboard' : ''}</span>
    </div>
  );
}
