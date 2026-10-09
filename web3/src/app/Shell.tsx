import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Broadcast, Files, Lifebuoy, MagnifyingGlass, Moon, Phone, Sun, UsersThree, Waveform, ArrowClockwise } from '@phosphor-icons/react';
import { useWorkspace } from './workspace';
import CommandPalette from './CommandPalette';
import AmbientField from '../components/AmbientField';
import { EASE, gsap, reducedMotion } from '../lib/motion';

export const NAV = [
  { to: '/', label: 'Check', icon: Waveform },
  { to: '/live', label: 'Live', icon: Broadcast },
  { to: '/voices', label: 'Voices', icon: UsersThree },
  { to: '/reports', label: 'Reports', icon: Files },
  { to: '/help', label: 'Help', icon: Lifebuoy },
] as const;

const PAGE_TITLE: Record<string, string> = { '/live': 'Listen live', '/voices': 'Known voices', '/reports': 'Reports', '/help': 'Help' };
const HEALTH_LABEL = { checking: 'Connecting', online: 'Service online', offline: 'Service offline' } as const;
const PROXIMITY = 110;

function isActive(pathname: string, to: string) {
  if (to === '/') return pathname === '/';
  if (to === '/reports') return pathname.startsWith('/report');
  return pathname.startsWith(to);
}

export default function Shell({ children }: { children: ReactNode }) {
  const { theme, toggleTheme, health, recheckHealth, setPaletteOpen } = useWorkspace();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const view = useRef<HTMLDivElement>(null);
  const nav = useRef<HTMLElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    document.title = pathname.startsWith('/report/') ? 'Report · SatyaCheck' : PAGE_TITLE[pathname] ? `${PAGE_TITLE[pathname]} · SatyaCheck` : 'SatyaCheck';
  }, [pathname]);

  // Route change: the new page rises in under a thin reading sweep. Content is never hidden;
  // only position and a short sweep animate, so captures and assistive tech see it at once.
  useLayoutEffect(() => {
    if (firstRender.current) { firstRender.current = false; return; }
    window.scrollTo({ top: 0 });
    main.current?.focus({ preventScroll: true });
    if (reducedMotion() || !view.current) return;
    const tl = gsap.timeline();
    tl.fromTo(view.current, { y: 18 }, { y: 0, duration: 0.7, ease: EASE.out })
      .fromTo('.route-sweep', { scaleX: 0, opacity: 1, transformOrigin: '0% 50%' }, { scaleX: 1, duration: 0.45, ease: EASE.inOut }, 0)
      .to('.route-sweep', { opacity: 0, duration: 0.35 }, 0.4);
    return () => { tl.kill(); };
  }, [pathname]);

  // The active indicator lives inside the active link, so CSS keeps it aligned at any font or
  // width. Navigation runs as a view transition, so the browser glides the named pill between links.

  // Proximity springs: items near the pointer lift and grow slightly, like a dock.
  useEffect(() => {
    const host = nav.current;
    if (!host || reducedMotion() || !window.matchMedia('(pointer: fine)').matches) return;
    const items = Array.from(host.querySelectorAll<HTMLElement>('.nav-link'));
    const springs = items.map(item => ({
      y: gsap.quickTo(item, 'y', { duration: 0.5, ease: 'elastic.out(1, 0.55)' }),
      scaleX: gsap.quickTo(item, 'scaleX', { duration: 0.5, ease: 'elastic.out(1, 0.55)' }),
      scaleY: gsap.quickTo(item, 'scaleY', { duration: 0.5, ease: 'elastic.out(1, 0.55)' }),
    }));
    const onMove = (event: PointerEvent) => {
      items.forEach((item, i) => {
        const rect = item.getBoundingClientRect();
        const distance = Math.abs(event.clientX - (rect.left + rect.width / 2));
        const t = Math.max(0, 1 - distance / PROXIMITY);
        const influence = t * t * (3 - 2 * t);
        springs[i].y(influence * 2.5);
        springs[i].scaleX(1 + influence * 0.07);
        springs[i].scaleY(1 + influence * 0.07);
      });
    };
    const onLeave = () => springs.forEach(s => { s.y(0); s.scaleX(1); s.scaleY(1); });
    host.addEventListener('pointermove', onMove);
    host.addEventListener('pointerleave', onLeave);
    return () => { host.removeEventListener('pointermove', onMove); host.removeEventListener('pointerleave', onLeave); };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setPaletteOpen]);

  return (
    <div className="shell">
      <AmbientField />
      <div className="grain" aria-hidden="true" />
      <a className="skip" href="#main">Skip to content</a>

      <header className="island-wrap">
        <div className="island">
          <Link to="/" className="brand" aria-label="SatyaCheck, go to Check">
            <img src="/brand/satyacheck-logo.jpg" alt="" width="30" height="30" />
            <span>SatyaCheck</span>
          </Link>
          <nav ref={nav} className="nav" aria-label="Main">
            {NAV.map(({ to, label }) => {
              const active = isActive(pathname, to);
              return (
                <NavLink key={to} to={to} viewTransition className={`nav-link${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>
                  {active && <span className="nav-pill" aria-hidden="true" />}
                  <span className="nav-label">{label === 'Live' ? 'Listen live' : label}</span>
                </NavLink>
              );
            })}
          </nav>
          <div className="island-tools">
            <button type="button" className="tool-btn search" onClick={() => setPaletteOpen(true)} aria-label="Open command menu" aria-keyshortcuts="Control+K Meta+K">
              <MagnifyingGlass size={17} weight="light" aria-hidden="true" />
              <kbd className="kbd">Ctrl K</kbd>
            </button>
            <button
              type="button"
              className={`tool-btn health health-${health}`}
              onClick={recheckHealth}
              disabled={health === 'checking'}
              aria-label={`${HEALTH_LABEL[health]}. Check again`}
              title={`${HEALTH_LABEL[health]}. Click to check again.`}
            >
              <span className="health-dot" aria-hidden="true" />
              <span className="health-text">{HEALTH_LABEL[health]}</span>
              {health === 'offline' && <ArrowClockwise size={14} weight="bold" aria-hidden="true" />}
            </button>
            <button type="button" className="tool-btn" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
              {theme === 'dark' ? <Sun size={18} weight="light" /> : <Moon size={18} weight="light" />}
            </button>
          </div>
        </div>
        <span className="route-sweep" aria-hidden="true" />
      </header>

      <main id="main" ref={main} tabIndex={-1} className="main">
        <div ref={view} className="view">{children}</div>
      </main>

      <footer className="footer">
        <p>SatyaCheck is a screening aid. It gives evidence, never a verdict of fraud. It reads Hindi, English and Hinglish.</p>
        <a href="tel:1930"><Phone size={15} weight="light" aria-hidden="true" />Cybercrime helpline 1930</a>
      </footer>

      <nav className="tabbar" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = isActive(pathname, to);
          return (
            <NavLink key={to} to={to} className={`tab${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>
              <Icon size={22} weight={active ? 'fill' : 'light'} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          );
        })}
      </nav>

      <CommandPalette />
    </div>
  );
}
