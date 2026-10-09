import { Component, Suspense, lazy, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { WorkspaceProvider } from './context/WorkspaceContext';
import Layout from './components/Layout';
import ScreenPage from './pages/ScreenPage';

const EnrollPage = lazy(() => import('./pages/EnrollPage'));
const ReportPage = lazy(() => import('./pages/ReportPage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error('SatyaCheck interface error', error); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="recovery">
        <h1>This view could not load.</h1>
        <p>No new result is available. Reload the page to try again.</p>
        <button className="button button-primary" onClick={() => window.location.reload()}>Reload SatyaCheck</button>
      </main>
    );
  }
}

function NotFound() {
  return (
    <div className="page-stack not-found">
      <h1>Page not found</h1>
      <p>This address does not match a page in SatyaCheck.</p>
      <Link className="button button-primary" to="/">Check audio</Link>
    </div>
  );
}

export default function App() {
  return (
    <Boundary>
      <ThemeProvider>
        <WorkspaceProvider>
          <BrowserRouter>
            <Layout>
              <Suspense fallback={<div className="page-loading" role="status">Loading…</div>}>
                <Routes>
                  <Route path="/" element={<ScreenPage />} />
                  <Route path="/enroll" element={<EnrollPage />} />
                  <Route path="/report" element={<ReportPage />} />
                  <Route path="/help" element={<HelpPage />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </Layout>
          </BrowserRouter>
        </WorkspaceProvider>
      </ThemeProvider>
    </Boundary>
  );
}
