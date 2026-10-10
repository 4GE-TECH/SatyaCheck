import { Component, StrictMode, Suspense, lazy, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import '@fontsource-variable/noto-sans-devanagari';
import './styles/base.css';
import './styles/ui.css';
import './styles/shell.css';
import './styles/pages.css';
import './styles/report.css';
import './styles/calls.css';
import './lib/motion';
import { WorkspaceProvider } from './app/workspace';
import { CallFeedProvider } from './app/callFeed';
import Shell from './app/Shell';
import AuthGate from './app/AuthGate';
import CheckPage from './features/check/CheckPage';
import { ButtonLink } from './components/ui';

const ReportPage = lazy(() => import('./features/report/ReportPage'));
const ReportsPage = lazy(() => import('./features/report/ReportsPage'));
const LivePage = lazy(() => import('./features/live/LivePage'));
const CallsPage = lazy(() => import('./features/calls/CallsPage'));
const VoicesPage = lazy(() => import('./features/voices/VoicesPage'));
const HelpPage = lazy(() => import('./features/help/HelpPage'));

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error('SatyaCheck interface error', error); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fallback">
        <h1>Something went wrong on this screen.</h1>
        <p>No result has been changed. Reload to continue.</p>
        <button className="btn btn-primary btn-md" type="button" onClick={() => window.location.reload()}>Reload SatyaCheck</button>
      </main>
    );
  }
}

function NotFound() {
  return (
    <div className="page fallback">
      <h1>This page doesn’t exist.</h1>
      <p>The address may be mistyped, or the page may have moved.</p>
      <ButtonLink to="/" variant="primary">Check a recording</ButtonLink>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Boundary>
        <WorkspaceProvider>
          <CallFeedProvider>
          <BrowserRouter>
            <AuthGate>
            <Shell>
              <Suspense fallback={<div className="page-loading" role="status">Loading…</div>}>
                <Routes>
                  <Route path="/" element={<CheckPage />} />
                  <Route path="/live" element={<LivePage />} />
                  <Route path="/calls" element={<CallsPage />} />
                  <Route path="/voices" element={<VoicesPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/report/:id" element={<ReportPage />} />
                  <Route path="/help" element={<HelpPage />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </Shell>
            </AuthGate>
          </BrowserRouter>
          </CallFeedProvider>
        </WorkspaceProvider>
    </Boundary>
  </StrictMode>,
);
