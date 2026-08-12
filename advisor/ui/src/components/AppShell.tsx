import { Moon, Plus, Sun } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { NewRoDialog } from "@/components/NewRoDialog";
import { OfflineBanner } from "@/components/OfflineBanner";
import { TechNotifications } from "@/components/TechNotifications";
import { useTheme } from "@/hooks/useTheme";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import carroMarkOnDark from "@/assets/carro-mark-512-on-dark.png";
import carroWordmark from "@/assets/carro-wordmark.png";
import carroWordmarkOnDark from "@/assets/carro-wordmark-on-dark.png";

const links = [
  { to: "/", label: "Desk pool", end: true },
  { to: "/calendar", label: "Calendar" },
  { to: "/plans", label: "Plans" },
  { to: "/orders", label: "Orders" },
  { to: "/parts", label: "Parts" },
  { to: "/messages", label: "Messages" },
  { to: "/timecards", label: "Time cards" },
  { to: "/efficiency", label: "Efficiency" },
  { to: "/reports", label: "Reports" },
  { to: "/history", label: "History" },
  { to: "/people", label: "Staff" },
  { to: "/admin", label: "Admin" },
  { to: "/settings", label: "Config" },
];

type PresenceRow = {
  advisor_id: string;
  name: string;
  status: "at_desk" | "away" | string;
  working_privilege?: boolean;
  on_job_ro?: string;
  on_job_item?: string;
  is_me?: boolean;
};

const PRESENCE_MS = 25_000;

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
  const [newRoOpen, setNewRoOpen] = useState(false);
  const [online, setOnline] = useState<PresenceRow[]>([]);

  const refreshPresence = useCallback(async () => {
    if (!advisorName) {
      setOnline([]);
      return;
    }
    try {
      await api.advisorPresenceHeartbeat().catch(() => undefined);
      const r = await api.listAdvisorPresence();
      setOnline(r.advisors || []);
    } catch {
      /* presence is best-effort */
    }
  }, [advisorName]);

  useEffect(() => {
    if (!advisorName) {
      setOnline([]);
      return;
    }
    void refreshPresence();
    const id = window.setInterval(() => void refreshPresence(), PRESENCE_MS);
    return () => window.clearInterval(id);
  }, [advisorName, refreshPresence]);

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
            <Button type="button" size="sm" onClick={() => setNewRoOpen(true)}>
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
        {advisorName ? (
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-5 pb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              Online advisors
            </span>
            {online.length === 0 ? (
              <span className="text-xs text-muted">Just you (or shop presence offline)</span>
            ) : (
              online.map((row) => {
                const away = row.status === "away";
                return (
                  <span
                    key={row.advisor_id}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs",
                      away
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-100"
                        : "border-border bg-surface text-muted",
                    )}
                    title={
                      away && row.on_job_ro
                        ? `On ${row.on_job_ro}${row.on_job_item ? ` / ${row.on_job_item}` : ""}`
                        : "At desk"
                    }
                  >
                    <span className="font-medium text-fg">
                      {row.name || row.advisor_id}
                      {row.is_me ? " (you)" : ""}
                    </span>
                    <span>{away ? "Away" : "At desk"}</span>
                  </span>
                );
              })
            )}
          </div>
        ) : null}
      </header>
      <OfflineBanner />
      <main className="mx-auto max-w-6xl px-5 py-6">
        <Outlet />
      </main>
      <NewRoDialog open={newRoOpen} onClose={() => setNewRoOpen(false)} />
    </div>
  );
}
