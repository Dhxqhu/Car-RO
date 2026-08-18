import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/hooks/useTheme";
import { api, setStoredToken } from "@/lib/api";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { MessagesPage } from "@/pages/MessagesPage";
import { NewRoPage } from "@/pages/NewRoPage";
import { OrdersPage } from "@/pages/OrdersPage";
import { PartsPage } from "@/pages/PartsPage";
import { RoPage } from "@/pages/RoPage";

export default function App() {
  const [name, setName] = useState<string | null>(null);
  const [id, setId] = useState("");
  const [role, setRole] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    document.title = "Car-RO";
    api
      .session()
      .then((s) => {
        if (s.kind === "technician" || s.kind === "advisor") {
          setName(s.name || "");
          setId(s.id || "");
          setRole(s.kind);
        }
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  function enter(n: string, personId: string, r: string) {
    setName(n);
    setId(personId);
    setRole(r === "advisor" ? "advisor" : "technician");
  }

  function exit() {
    void api.logout().catch(() => undefined);
    setStoredToken("");
    setName(null);
    setId("");
    setRole("");
  }

  if (!ready) {
    return (
      <ThemeProvider>
        <div className="flex min-h-dvh items-center justify-center text-muted">Loading…</div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <BrowserRouter>
        {!name ? (
          <LoginPage onAuthed={enter} />
        ) : (
          <Routes>
            <Route element={<AppShell name={name} id={id} role={role} onExit={exit} />}>
              <Route index element={<HomePage id={id} name={name} role={role} />} />
              <Route path="orders" element={<OrdersPage />} />
              <Route path="ro/:id" element={<RoPage id={id} name={name} role={role} />} />
              <Route path="messages" element={<MessagesPage id={id} name={name} role={role} />} />
              <Route path="parts" element={<PartsPage />} />
              {role === "advisor" ? <Route path="new" element={<NewRoPage />} /> : null}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}
