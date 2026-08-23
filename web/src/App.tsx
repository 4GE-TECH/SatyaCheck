import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/Layout";
import ScreenPage from "./pages/ScreenPage";
import EnrollPage from "./pages/EnrollPage";
import ReportPage from "./pages/ReportPage";

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<ScreenPage />} />
            <Route path="/enroll" element={<EnrollPage />} />
            <Route path="/report" element={<ReportPage />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </ThemeProvider>
  );
}
