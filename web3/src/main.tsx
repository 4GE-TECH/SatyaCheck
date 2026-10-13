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
import './styles/admin.css';
import './lib/motion';
import { WorkspaceProvider } from './app/workspace';
import { CallFeedProvider } from './app/callFeed';
import Shell from './app/Shell';
import AdminGate from './app/AdminGate';
import OverviewPage from './features/admin/OverviewPage';
import { ButtonLink } from './components/ui';

// The admin console. The earlier user pages are still in src/features (unrouted) and on the
// archive/web3-user-dashboard branch: see web3/ARCHIVE.md to bring them back.
const LiveCallsPage = lazy(() => import('./features/admin/LiveCallsPage'));
const CallHistoryPage = lazy(() => import('./features/admin/CallHistoryPage'));
const CallDetailPage = lazy(() => import('./features/admin/CallDetailPage'));
const UsersPage = lazy(() => import('./features/admin/UsersPage'));

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
      <ButtonLink to="/" variant="primary">Go to the overview</ButtonLink>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Boundary>
        <WorkspaceProvider>
          <CallFeedProvider>
          <BrowserRouter>
            <AdminGate>
            <Shell>
              <Suspense fallback={<div className="page-loading" role="status">Loading…</div>}>
                <Routes>
                  <Route path="/" element={<OverviewPage />} />
                  <Route path="/live" element={<LiveCallsPage />} />
                  <Route path="/calls" element={<CallHistoryPage />} />
                  <Route path="/calls/:id" element={<CallDetailPage />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </Shell>
            </AdminGate>
          </BrowserRouter>
          </CallFeedProvider>
        </WorkspaceProvider>
    </Boundary>
  </StrictMode>,
);
