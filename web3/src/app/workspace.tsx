import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { ScreeningResponse } from '../types/contracts';
import { checkHealth, type Health } from '../lib/api';

export type Source = 'upload' | 'clip' | 'live' | 'sample' | 'saved';

/** One completed check, held in memory for this page session only. */
export interface CheckRecord {
  data: ScreeningResponse;
  name: string;
  source: Source;
  /** The audio itself, when this session produced it, so the report can draw and replay it. */
  audio?: File | null;
}

type Theme = 'dark' | 'light';

interface Workspace {
  records: CheckRecord[];
  addRecord: (record: CheckRecord) => void;
  findRecord: (sessionId: string) => CheckRecord | undefined;
  theme: Theme;
  toggleTheme: () => void;
  health: Health;
  recheckHealth: () => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
}

const WorkspaceContext = createContext<Workspace | null>(null);
const LIGHT_QUERY = '(prefers-color-scheme: light)';

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [records, setRecords] = useState<CheckRecord[]>([]);
  const [theme, setTheme] = useState<Theme>(() => (window.matchMedia(LIGHT_QUERY).matches ? 'light' : 'dark'));
  const [health, setHealth] = useState<Health>('checking');
  const [healthTick, setHealthTick] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const chosenTheme = useRef(false);

  useEffect(() => {
    const media = window.matchMedia(LIGHT_QUERY);
    const follow = (event: MediaQueryListEvent) => { if (!chosenTheme.current) setTheme(event.matches ? 'light' : 'dark'); };
    media.addEventListener('change', follow);
    return () => media.removeEventListener('change', follow);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#07081a' : '#f4f5fb');
  }, [theme]);

  useEffect(() => {
    const controller = new AbortController();
    checkHealth(controller.signal).then(result => { if (!controller.signal.aborted) setHealth(result); });
    const timer = window.setInterval(() => {
      checkHealth(controller.signal).then(result => { if (!controller.signal.aborted) setHealth(result); });
    }, 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [healthTick]);

  const addRecord = useCallback((record: CheckRecord) => {
    setRecords(previous => [record, ...previous.filter(r => r.data.session_id !== record.data.session_id)].slice(0, 40));
  }, []);
  const findRecord = useCallback((id: string) => records.find(r => r.data.session_id === id), [records]);
  const toggleTheme = useCallback(() => {
    chosenTheme.current = true;
    setTheme(current => (current === 'dark' ? 'light' : 'dark'));
  }, []);
  const recheckHealth = useCallback(() => { setHealth('checking'); setHealthTick(n => n + 1); }, []);

  const value = useMemo<Workspace>(() => ({
    records, addRecord, findRecord, theme, toggleTheme, health, recheckHealth, paletteOpen, setPaletteOpen,
  }), [records, addRecord, findRecord, theme, toggleTheme, health, recheckHealth, paletteOpen]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): Workspace {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error('WorkspaceProvider is missing.');
  return value;
}
