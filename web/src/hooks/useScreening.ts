import { useState, useRef, useEffect } from 'react';
import type { ScreeningResponse } from '../types/contracts';
import type { MockScenario } from '../api/mock';
import { request, parseScreening, audioError } from '../api/client';
import { useWorkspace } from '../context/workspace-state';
export default function useScreening() {
  const [data, setData] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [name, setName] = useState('');
  const controller = useRef<AbortController | null>(null);
  const { add } = useWorkspace();
  useEffect(() => () => controller.current?.abort(), []);
  function clear() { controller.current?.abort(); controller.current = null; setData(null); setLoading(false); setError(null); setDemo(false); }
  async function screenFile(file: File) {
    if (controller.current) return;
    const problem = audioError(file); if (problem) { setError(problem); return; }
    const active = new AbortController(); controller.current = active;
    setLoading(true); setError(null); setData(null); setDemo(false); setName(file.name);
    try {
      const body = new FormData(); body.append('file', file); body.append('channel_type', 'upload');
      const result = parseScreening(await (await request('/api/screen', { method: 'POST', body, signal: active.signal })).json());
      if (active.signal.aborted) return;
      setData(result); add({ data: result, demo: false, name: file.name });
    } catch (error) { if (!active.signal.aborted) setError(error instanceof Error ? error.message : 'The audio could not be checked. Please try again.'); }
    finally { if (controller.current === active) { controller.current = null; setLoading(false); } }
  }
  async function screenMock(scenario: MockScenario) {
    if (controller.current) return;
    const active = new AbortController(); controller.current = active;
    setLoading(true); setError(null);
    try {
      const { getMockFixture } = await import('../api/mock');
      if (active.signal.aborted) return;
      const result = getMockFixture(scenario);
      setData(result); setDemo(true); setName('Sample result');
      add({ data: result, demo: true, name: 'Sample result' });
    } catch { if (!active.signal.aborted) setError('Could not load the sample. Please try again.'); }
    finally { if (controller.current === active) { controller.current = null; setLoading(false); } }
  }
  return { data, loading, error, demo, name, screenFile, screenMock, clear };
}
