import { Moon, Plus, Sun } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { TechNotifications } from "@/components/TechNotifications";
import { useTheme } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import carroMarkOnDark from "@/assets/carro-mark-512-on-dark.png";
import carroWordmark from "@/assets/carro-wordmark.png";
import carroWordmarkOnDark from "@/assets/carro-wordmark-on-dark.png";

const links = [
  { to: "/", label: "Desk pool", end: true },
  { to: "/parts", label: "Parts" },
  { to: "/messages", label: "Messages" },
  { to: "/efficiency", label: "Efficiency" },
  { to: "/reports", label: "Reports" },
  { to: "/history", label: "History" },
  { to: "/people", label: "People" },
  { to: "/admin", label: "Admin" },
  { to: "/settings", label: "Config" },
];

export function AppShell({
  advisorName,
  advisorId,
  onExit,
}: {
  advisorName?: string;
  advisorId?: string;
  onExit?: () => void;
}) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const nav = useNavigate();
  const [creating, setCreating] = useState(false);

  async function newRo() {
    setCreating(true);
    try {
      const o = await api.createRo();
      nav(`/ro/${o.id}`);
    } catch {
      /* ignore — engine will surface on next action */
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border/80 bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-accent p-1 shadow-sm ring-1 ring-black/10 dark:ring-white/15">
              <img
                src={carroMarkOnDark}
                alt=""
                width={28}
                height={28}
                className="h-7 w-7 object-contain"
                draggable={false}
              />
            </div>
            <div>
              <img
                src={dark ? carroWordmarkOnDark : carroWordmark}
                alt="Car-RO"
                className="h-5 w-auto"
                draggable={false}
              />
              <p className="mt-0.5 text-xs text-muted">Advisor desk</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" disabled={creating} onClick={() => void newRo()}>
              <Plus className="h-4 w-4" />
              New RO
            </Button>
            {advisorName ? (
              <span className="text-sm text-muted">
                {advisorName}
                {advisorId ? (
                  <span className="ml-1 font-mono text-xs opacity-70">{advisorId}</span>
                ) : null}
              </span>
            ) : null}
            {advisorName ? (
              <TechNotifications techName={advisorName} techId={advisorId} />
            ) : null}
            <Button type="button" size="sm" variant="ghost" onClick={() => toggle()}>
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            {onExit ? (
              <Button type="button" size="sm" variant="secondary" onClick={onExit}>
                Log out
              </Button>
            ) : null}
          </div>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-5 pb-2">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                cn(
                  "rounded-lg px-3 py-1.5 text-sm whitespace-nowrap",
                  isActive ? "bg-accent text-accent-fg" : "text-muted hover:bg-border/40",
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-6">
        <Outlet />
      </main>
    </div>
  );
}
