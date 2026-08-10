import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/LoginPage";
import { RoEditorPage } from "@/pages/RoEditorPage";
import { AssignedWorkPage } from "@/pages/AssignedWorkPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { PartsPage } from "@/pages/PartsPage";
import { MessagesPage } from "@/pages/MessagesPage";
import { PeoplePage } from "@/pages/PeoplePage";
import { WeeklyReportsPage } from "@/pages/WeeklyReportsPage";
import { EfficiencyPage } from "@/pages/EfficiencyPage";
import { AdminPage } from "@/pages/AdminPage";

export default function App() {
  const [advisorName, setAdvisorName] = useState<string | null>(null);
  const [advisorId, setAdvisorId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    document.title = "Car-RO · Advisor Desk";
    api
      .advisorWhoami()
      .then((r) => {
        if (r.advisor?.name) {
          setAdvisorName(r.advisor.name);
          setAdvisorId(r.advisor.id || null);
        }
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  function enterAdvisor(name: string, id?: string) {
    setAdvisorName(name);
    setAdvisorId(id || null);
  }

  function exitToLogin() {
    setAdvisorName(null);
    setAdvisorId(null);
    void api.advisorLogout().catch(() => undefined);
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
        {!advisorName ? (
          <LoginPage onAuthed={enterAdvisor} />
        ) : (
          <Routes>
            <Route
              element={
                <AppShell
                  advisorName={advisorName}
                  advisorId={advisorId ?? undefined}
                  onExit={exitToLogin}
                />
              }
            >
              <Route index element={<AssignedWorkPage />} />
              <Route path="ro/:id" element={<RoEditorPage />} />
              <Route path="parts" element={<PartsPage />} />
              <Route path="messages" element={<MessagesPage />} />
              <Route path="efficiency" element={<EfficiencyPage />} />
              <Route path="reports" element={<WeeklyReportsPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="people" element={<PeoplePage />} />
              <Route path="admin" element={<AdminPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}
