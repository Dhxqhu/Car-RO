import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { detectScannerOnlyBoot, persistMode, type AppMode } from "@/lib/sessionMode";
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

function scanRoutes(): ReactNode {
  return (
    <Route path="scan" element={<ScanLayout />}>
      <Route index element={<ScanConnectPage />} />
      <Route path="codes" element={<ScanCodesPage />} />
      <Route path="live" element={<ScanLivePage />} />
      <Route path="info" element={<ScanInfoPage />} />
      <Route path="saved" element={<ScanSavedPage />} />
      <Route path="adapters" element={<ScanAdaptersPage />} />
    </Route>
  );
}

export default function App() {
  const scannerOnly = detectScannerOnlyBoot();
  const [mode, setMode] = useState<AppMode>(scannerOnly ? "scanner" : "login");
  const [techName, setTechName] = useState<string | null>(null);
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
          setMode("tech");
          persistMode("tech");
        }
      })
      .catch(() => {
        /* stay on login */
      })
      .finally(() => setReady(true));
  }, [scannerOnly]);

  function enterTech(name: string) {
    setTechName(name);
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
                  onExit={exitToLogin}
                />
              }
            >
              <Route index element={<RoListPage />} />
              <Route path="ro/:id" element={<RoEditorPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="techs" element={<TechsPage />} />
              {scanRoutes()}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}
