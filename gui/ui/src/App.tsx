import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/LoginPage";
import { RoEditorPage } from "@/pages/RoEditorPage";
import { RoListPage } from "@/pages/RoListPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TechsPage } from "@/pages/TechsPage";
import { ScanAdaptersPage } from "@/pages/scan/ScanAdaptersPage";
import { ScanCodesPage } from "@/pages/scan/ScanCodesPage";
import { ScanConnectPage } from "@/pages/scan/ScanConnectPage";
import { ScanInfoPage } from "@/pages/scan/ScanInfoPage";
import { ScanLayout } from "@/pages/scan/ScanLayout";
import { ScanLivePage } from "@/pages/scan/ScanLivePage";
import { ScanSavedPage } from "@/pages/scan/ScanSavedPage";

export default function App() {
  const [techName, setTechName] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api
      .whoami()
      .then((r) => setTechName(r.technician?.name ?? null))
      .catch(() => setTechName(null))
      .finally(() => setReady(true));
  }, []);

  if (!ready) {
    return (
      <ThemeProvider>
        <div className="flex min-h-screen items-center justify-center text-muted">Loading…</div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <BrowserRouter>
        {!techName ? (
          <LoginPage onAuthed={(name) => setTechName(name)} />
        ) : (
          <Routes>
            <Route element={<AppShell techName={techName} />}>
              <Route index element={<RoListPage />} />
              <Route path="ro/:id" element={<RoEditorPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="techs" element={<TechsPage />} />
              <Route path="scan" element={<ScanLayout />}>
                <Route index element={<ScanConnectPage />} />
                <Route path="codes" element={<ScanCodesPage />} />
                <Route path="live" element={<ScanLivePage />} />
                <Route path="info" element={<ScanInfoPage />} />
                <Route path="saved" element={<ScanSavedPage />} />
                <Route path="adapters" element={<ScanAdaptersPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}
