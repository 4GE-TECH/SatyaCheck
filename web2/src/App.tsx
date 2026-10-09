import { Component, Suspense, createElement, lazy, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { MotionConfig, motion } from 'motion/react';
import { ArrowUpRight, AudioLines, CircleHelp, FileText, RefreshCw, Users } from 'lucide-react';
import { LabContext } from './lib/store';
import type { Check } from './lib/api';
import Home from './pages/Home';
import { Reports, ReportRoute } from './pages/Reports';
const Voices = lazy(() => import('./pages/Voices'));
const Guide = lazy(() => import('./pages/Guide'));

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error('SatyaCheck observatory interface failure', error); }
  render() { return this.state.failed ? <main className="fatal"><h1>This view couldn’t open.</h1><p>No new result is available. Reload to try again.</p><button className="button ivory" onClick={() => location.reload()}>Reload SatyaCheck</button></main> : this.props.children; }
}
function Shell() {
  const location = useLocation(); const previous = useRef(location.pathname);
  const [health, setHealth] = useState<'connecting'|'online'|'offline'>('connecting'); const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setHealth('connecting');
    fetch('/api/health', { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]) }).then(response => { if (!controller.signal.aborted) setHealth(response.ok ? 'online' : 'offline'); }).catch(() => { if (!controller.signal.aborted) setHealth('offline'); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    document.title = `${location.pathname.startsWith('/voices') ? 'Known voices' : location.pathname.startsWith('/reports') ? 'Reports' : location.pathname === '/guide' ? 'Safety guide' : 'Listen beyond the familiar'} · SatyaCheck`;
    if (previous.current !== location.pathname) { window.scrollTo({ top: 0, behavior: 'instant' }); document.getElementById('main')?.focus({ preventScroll: true }); previous.current = location.pathname; }
  }, [location.pathname]);
  return <><a className="skip-link" href="#main">Skip to content</a><header className="site-header"><Link className="brand" to="/" aria-label="SatyaCheck home"><img src="/brand/logo.jpg" alt="" width="32" height="32"/><span>SatyaCheck<span className="brand-period">.</span></span></Link><nav className="primary-nav" aria-label="Main">{[{to:'/',label:'Check audio',icon:AudioLines},{to:'/voices',label:'Known voices',icon:Users},{to:'/reports',label:'Reports',icon:FileText}].map(item => <NavLink end={item.to === '/'} to={item.to} key={item.to}>{({isActive}) => <><span className="nav-symbol">{createElement(item.icon,{size:18})}</span><span>{item.label}</span>{isActive && <motion.span className="nav-active" layoutId="nav-active" transition={{type:'spring',stiffness:380,damping:34}}/>}</>}</NavLink>)}</nav><div className="header-tools"><button className={`service-state ${health}`} onClick={() => setRetry(n=>n+1)} disabled={health === 'connecting'} aria-label={`Service ${health}. Retry connection`}><i/><span>{health === 'connecting' ? 'Connecting' : health === 'online' ? 'Service online' : 'Service offline'}</span>{health === 'offline' && <RefreshCw size={12}/>}</button><Link className="icon-button guide-link" to="/guide" aria-label="Safety guide"><CircleHelp size={19}/></Link></div></header>
    <main id="main" tabIndex={-1} className="main"><Suspense fallback={<div className="page-loading" role="status">Opening your workspace…</div>}><Routes><Route path="/" element={<Home/>}/><Route path="/voices" element={<Voices/>}/><Route path="/reports" element={<Reports/>}/><Route path="/reports/:id" element={<ReportRoute/>}/><Route path="/guide" element={<Guide/>}/><Route path="*" element={<div className="fatal"><h1>That page isn’t here.</h1><Link to="/" className="button ivory">Back to the listening desk</Link></div>}/></Routes></Suspense></main>
    <footer className="site-footer"><Link to="/" className="footer-brand">SatyaCheck.</Link><p>More context. Better questions.<br/>A moment to make your own call.</p><div><Link to="/guide">A guide to your results<ArrowUpRight size={15}/></Link><a href="tel:1930">Cybercrime helpline · 1930<ArrowUpRight size={15}/></a></div><span>Hindi · English · Hinglish</span></footer></>;
}
export default function App() {
  const [checks,setChecks] = useState<Check[]>([]);
  const save = useCallback((check: Check) => setChecks(current => [check,...current.filter(c => c.result.session_id !== check.result.session_id)]),[]);
  return <Boundary><MotionConfig reducedMotion="user"><LabContext.Provider value={{checks,save}}><BrowserRouter><Shell/></BrowserRouter></LabContext.Provider></MotionConfig></Boundary>;
}
