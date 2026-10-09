import { useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, Link, useLocation } from 'react-router-dom';
import { Moon, Sun, RefreshCw, Phone, AudioLines, UsersRound, FileText, CircleHelp, ArrowUpRight, Languages } from 'lucide-react';
import { Brand } from './Primitives';
import { useTheme } from '../context/theme-state';

const links = [
  { to: '/', label: 'Check audio', icon: AudioLines },
  { to: '/enroll', label: 'Known voices', icon: UsersRound },
  { to: '/report', label: 'Reports', icon: FileText },
  { to: '/help', label: 'Help', icon: CircleHelp },
];

type Health = 'checking' | 'online' | 'offline';

const healthLabel: Record<Health, string> = {
  checking: 'Connecting',
  online: 'Service online',
  offline: 'Service offline',
};

export default function Layout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  const previousPath = useRef(pathname);
  const [health, setHealth] = useState<Health>('checking');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]) })
      .then(response => { if (!controller.signal.aborted) setHealth(response.ok ? 'online' : 'offline'); })
      .catch(() => { if (!controller.signal.aborted) setHealth('offline'); });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    const current = links.find(link => link.to === pathname)?.label;
    document.title = current ? `${current} · SatyaCheck` : 'SatyaCheck';
    if (previousPath.current !== pathname) {
      window.scrollTo({ top: 0, behavior: 'instant' });
      document.getElementById('main-content')?.focus({ preventScroll: true });
      previousPath.current = pathname;
    }
  }, [pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="letterhead">
        <div className="letterhead-inner">
          <Link to="/" className="brand-link" aria-label="SatyaCheck home"><Brand /></Link>
          <span className="nav-caption">Your workspace</span>
          <nav aria-label="Main" className="main-nav">
            {links.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <Icon size={20} strokeWidth={1.7} aria-hidden="true" /><span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-note">
            <span className="sidebar-note-line" />
            <p>A moment to pause.<br />A reason to verify.</p>
            <span>When a call feels urgent, call back on a number you know.</span>
            <Link to="/help">Know your next step<ArrowUpRight size={15} aria-hidden="true" /></Link>
          </div>
          <div className="letterhead-actions">
            <button
              type="button"
              className={`connection ${health}`}
              onClick={() => { setHealth('checking'); setRetry(n => n + 1); }}
              disabled={health === 'checking'}
              aria-label={`${healthLabel[health]}. Check the connection again`}
            >
              <span className="status-dot" aria-hidden="true" />
              <span className="connection-text">{healthLabel[health]}</span>
              {health === 'offline' && <RefreshCw size={14} aria-hidden="true" />}
            </button>
            <button
              type="button"
              className="icon-button on-letterhead"
              aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
              onClick={toggleTheme}
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </div>
      </header>
      <div className="workspace-topbar">
        <span>Workspace <span aria-hidden="true">/</span> <strong>{links.find(link => link.to === pathname)?.label || 'SatyaCheck'}</strong></span>
        <span className="workspace-languages"><Languages size={16} aria-hidden="true" />Hindi · English · Hinglish</span>
      </div>
      <main id="main-content" tabIndex={-1} className="workspace"><div key={pathname} className="route-view">{children}</div></main>
      <footer className="workspace-footer">
        <span>A screening aid, not a determination of fraud. Reads Hindi, English and Hinglish.</span>
        <a href="tel:1930"><Phone size={14} aria-hidden="true" />Cybercrime helpline 1930</a>
      </footer>
    </div>
  );
}
