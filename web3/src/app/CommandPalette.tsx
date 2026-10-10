import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import { useNavigate } from 'react-router-dom';
import { EASE, gsap, reducedMotion } from '../lib/motion';
import { Broadcast, FileText, Files, Flask, Lifebuoy, MagnifyingGlass, MoonStars, PhoneCall, UsersThree, Waveform, type IconProps } from '@phosphor-icons/react';
import { useWorkspace } from './workspace';
import { BANDS, displayBand } from '../lib/verdict';
import { SAMPLES } from '../features/check/samples';
import { Kbd } from '../components/ui';

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon: ComponentType<IconProps>;
  run: () => void;
}

export default function CommandPalette() {
  const { paletteOpen, setPaletteOpen, records, toggleTheme, addRecord } = useWorkspace();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => navigate(to);
    return [
      { id: 'check', label: 'Check a recording', group: 'Go to', icon: Waveform, run: go('/') },
      { id: 'live', label: 'Listen live', group: 'Go to', icon: Broadcast, run: go('/live') },
      { id: 'calls', label: 'Phone calls', hint: 'Exotel calls as they happen', group: 'Go to', icon: PhoneCall, run: go('/calls') },
      { id: 'voices', label: 'Known voices', group: 'Go to', icon: UsersThree, run: go('/voices') },
      { id: 'reports', label: 'Reports', group: 'Go to', icon: Files, run: go('/reports') },
      { id: 'help', label: 'How to read a report', group: 'Go to', icon: Lifebuoy, run: go('/help') },
      { id: 'theme', label: 'Switch theme', group: 'Settings', icon: MoonStars, run: toggleTheme },
      ...records.slice(0, 6).map(record => ({
        id: `r-${record.data.session_id}`,
        label: record.name,
        hint: BANDS[displayBand(record.data)].label,
        group: 'Reports this session',
        icon: FileText,
        run: go(`/report/${encodeURIComponent(record.data.session_id)}`),
      })),
      ...SAMPLES.map(sample => ({
        id: `s-${sample.scenario}`,
        label: `Sample: ${sample.label}`,
        hint: sample.story,
        group: 'Labelled samples',
        icon: Flask,
        run: () => {
          void sample.load().then(data => {
            addRecord({ data, name: `Sample · ${sample.label}`, source: 'sample' });
            navigate(`/report/${encodeURIComponent(data.session_id)}`);
          });
        },
      })),
    ];
  }, [records, navigate, toggleTheme, addRecord]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? commands.filter(c => `${c.label} ${c.hint ?? ''} ${c.group}`.toLowerCase().includes(q)) : commands;
  }, [commands, query]);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (paletteOpen && !node.open) {
      node.showModal();
      queueMicrotask(() => { setQuery(''); setIndex(0); input.current?.focus(); });
      if (!reducedMotion()) {
        gsap.fromTo(node.querySelector('.palette-card'), { y: -12, scale: 0.97, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: 0.32, ease: EASE.out });
        gsap.fromTo(node.querySelectorAll('.palette-item'), { x: -6 }, { x: 0, duration: 0.4, stagger: 0.015, ease: EASE.out });
      }
    } else if (!paletteOpen && node.open) {
      node.close();
    }
  }, [paletteOpen]);

  function run(command: Command | undefined) {
    if (!command) return;
    setPaletteOpen(false);
    command.run();
  }

  let lastGroup = '';
  return (
    <dialog
      ref={dialog}
      className="palette"
      aria-label="Command menu"
      onClose={() => setPaletteOpen(false)}
      onClick={event => { if (event.target === dialog.current) setPaletteOpen(false); }}
    >
      {paletteOpen && (
          <div className="palette-card">
            <div className="palette-search">
              <MagnifyingGlass size={20} weight="bold" aria-hidden="true" />
              <input
                ref={input}
                value={query}
                onChange={event => { setQuery(event.target.value); setIndex(0); }}
                onKeyDown={event => {
                  if (event.key === 'ArrowDown') { event.preventDefault(); setIndex(i => Math.min(visible.length - 1, i + 1)); }
                  if (event.key === 'ArrowUp') { event.preventDefault(); setIndex(i => Math.max(0, i - 1)); }
                  if (event.key === 'Enter') { event.preventDefault(); run(visible[index]); }
                }}
                placeholder="Search pages, reports and samples"
                aria-label="Search commands"
                role="combobox"
                aria-expanded="true"
                aria-controls="palette-list"
                aria-activedescendant={visible[index] ? `cmd-${visible[index].id}` : undefined}
              />
              <Kbd>Esc</Kbd>
            </div>
            <ul id="palette-list" role="listbox" className="palette-list">
              {visible.length === 0 && <li className="palette-empty">Nothing matches “{query}”.</li>}
              {visible.map((command, i) => {
                const header = command.group !== lastGroup ? command.group : null;
                lastGroup = command.group;
                const Icon = command.icon;
                return (
                  <li key={command.id} role="presentation">
                    {header && <div className="palette-group" role="presentation">{header}</div>}
                    <div
                      id={`cmd-${command.id}`}
                      role="option"
                      aria-selected={i === index}
                      className="palette-item"
                      onMouseMove={() => setIndex(i)}
                      onClick={() => run(command)}
                    >
                      <Icon size={18} aria-hidden="true" />
                      <span className="ellipsis">{command.label}</span>
                      {command.hint && <span className="palette-hint ellipsis">{command.hint}</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
    </dialog>
  );
}
