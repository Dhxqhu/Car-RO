import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { detectScannerOnlyBoot, persistMode, type AppMode } from "@/lib/sessionMode";
import { LoginPage } from "@/pages/LoginPage";
import { RoEditorPage } from "@/pages/RoEditorPage";
import { RoListPage } from "@/pages/RoListPage";
import { AssignedWorkPage } from "@/pages/AssignedWorkPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { PartsPage } from "@/pages/PartsPage";
import { MessagesPage } from "@/pages/MessagesPage";
import { TechsPage } from "@/pages/TechsPage";
import { AdminPage } from "@/pages/AdminPage";
import { ScanAdaptersPage } from "@/pages/scan/ScanAdaptersPage";
import { ScanCodesPage } from "@/pages/scan/ScanCodesPage";
import { ScanConnectPage } from "@/pages/scan/ScanConnectPage";
import { ScanDoipPage } from "@/pages/scan/ScanDoipPage";
import { ScanInfoPage } from "@/pages/scan/ScanInfoPage";
import { ScanLayout } from "@/pages/scan/ScanLayout";
import { ScanLibrariesPage } from "@/pages/scan/ScanLibrariesPage";
import { ScanLivePage } from "@/pages/scan/ScanLivePage";
import { ScanProfilesPage } from "@/pages/scan/ScanProfilesPage";
import { ScanRawPage } from "@/pages/scan/ScanRawPage";
import { ScanSavedPage } from "@/pages/scan/ScanSavedPage";

function scanRoutes(): ReactNode {
  return (
    <Route path="scan" element={<ScanLayout />}>
      <Route index element={<ScanConnectPage />} />
      <Route path="codes" element={<ScanCodesPage />} />
      <Route path="live" element={<ScanLivePage />} />
      <Route path="info" element={<ScanInfoPage />} />
      <Route path="profiles" element={<ScanProfilesPage />} />
      <Route path="doip" element={<ScanDoipPage />} />
      <Route path="libraries" element={<ScanLibrariesPage />} />
      <Route path="raw" element={<ScanRawPage />} />
      <Route path="saved" element={<ScanSavedPage />} />
      <Route path="adapters" element={<ScanAdaptersPage />} />
    </Route>
  );
}

export default function App() {
  const scannerOnly = detectScannerOnlyBoot();
  const [mode, setMode] = useState<AppMode>(scannerOnly ? "scanner" : "login");
  const [techName, setTechName] = useState<string | null>(null);
  const [techId, setTechId] = useState<string | null>(null);
  const [ready, setReady] = useState(scannerOnly);

  useEffect(() => {
    if (scannerOnly) {
      document.title = "obdscan";
      setReady(true);
      return;
    }
    document.title = "Car-RO · Orders & Scanner";
    api
      .whoami()
      .then((r) => {
        if (r.technician?.name) {
          setTechName(r.technician.name);
          setTechId(r.technician.id || null);
          setMode("tech");
          persistMode("tech");
        }
      })
      .catch(() => {
        /* stay on login */
      })
      .finally(() => setReady(true));
  }, [scannerOnly]);

  function enterTech(name: string, id?: string) {
    setTechName(name);
    setTechId(id || null);
    setMode("tech");
    persistMode("tech");
  }

  function enterScanner() {
    setTechName(null);
    setMode("scanner");
    persistMode("scanner");
    document.title = scannerOnly ? "obdscan" : "Car-RO · Scanner";
  }

  function exitToLogin() {
    if (scannerOnly) return;
    setTechName(null);
    setTechId(null);
    setMode("login");
    persistMode("login");
    document.title = "Car-RO · Orders & Scanner";
    void api.logout().catch(() => undefined);
  }

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
        {mode === "login" ? (
          <LoginPage onAuthed={enterTech} onOpenScanner={enterScanner} />
        ) : mode === "scanner" ? (
          <Routes>
            <Route
              element={
                <AppShell
                  variant="scanner"
                  scannerOnly={scannerOnly}
                  onExit={scannerOnly ? undefined : exitToLogin}
                />
              }
            >
              {scanRoutes()}
              <Route path="*" element={<Navigate to="/scan" replace />} />
            </Route>
          </Routes>
        ) : (
          <Routes>
            <Route
              element={
                <AppShell
                  variant="full"
                  techName={techName ?? undefined}
                  techId={techId ?? undefined}
                  onExit={exitToLogin}
                />
              }
            >
              <Route index element={<RoListPage />} />
              <Route path="ro/:id" element={<RoEditorPage />} />
              <Route path="assigned" element={<AssignedWorkPage />} />
              <Route path="parts" element={<PartsPage />} />
              <Route path="messages" element={<MessagesPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="techs" element={<TechsPage />} />
              <Route path="admin" element={<AdminPage />} />
              {scanRoutes()}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}
