import { Cable, Moon, Sun } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { OfflineBanner } from "@/components/OfflineBanner";
import { TechNotifications } from "@/components/TechNotifications";
import { TechShiftControls } from "@/components/TechShiftControls";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import carroMarkOnDark from "@/assets/carro-mark-512-on-dark.png";
import carroWordmark from "@/assets/carro-wordmark.png";
import carroWordmarkOnDark from "@/assets/carro-wordmark-on-dark.png";

const workspaces = [
  {
    to: "/",
    label: "Orders",
    match: (p: string) =>
      p === "/" ||
      p.startsWith("/ro") ||
      p.startsWith("/assigned") ||
      p.startsWith("/parts") ||
      p.startsWith("/history") ||
      p.startsWith("/messages") ||
      p.startsWith("/settings") ||
      p.startsWith("/techs") ||
      p.startsWith("/admin"),
  },
  { to: "/scan", label: "Scanner", match: (p: string) => p.startsWith("/scan") },
];

const orderLinks = [
  { to: "/", label: "Orders", end: true },
  { to: "/assigned", label: "Assigned" },
  { to: "/parts", label: "Parts" },
  { to: "/messages", label: "Messages" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Config" },
  { to: "/techs", label: "Technicians" },
  { to: "/admin", label: "Admin" },
];

export function AppShell({
  variant = "full",
  techName,
  techId,
  scannerOnly = false,
  onExit,
}: {
  variant?: "full" | "scanner";
  techName?: string;
  techId?: string;
  scannerOnly?: boolean;
  onExit?: () => void;
}) {
  const { theme, toggle } = useTheme();
  const { pathname } = useLocation();
  const inScan = pathname.startsWith("/scan");
  const scannerShell = variant === "scanner";
  const dark = theme === "dark";

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border/80 bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div className="flex items-center gap-3">
            {scannerShell ? (
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-sm ring-1 ring-black/10 dark:ring-white/15">
                <Cable className="h-4 w-4" />
              </div>
            ) : (
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
            )}
            <div>
              {scannerShell ? (
                <div className="font-[family-name:var(--font-display)] text-lg font-semibold leading-none tracking-tight">
                  obdscan
                </div>
              ) : (
                <img
                  src={dark ? carroWordmarkOnDark : carroWordmark}
                  alt="Car-RO"
                  className="h-7 w-auto max-w-[9.5rem] object-contain object-left"
                  draggable={false}
                />
              )}
              <div className="mt-1 text-xs text-muted">
                {scannerShell
                  ? scannerOnly
                    ? "Scanner only"
                    : "Scanner · no technician login"
                  : techName
                    ? `Logged in as ${techName}`
                    : null}
              </div>
            </div>
            {!scannerShell ? (
              <div
                className="ml-2 flex rounded-lg border border-border bg-surface p-0.5"
                role="tablist"
                aria-label="Workspace"
              >
                {workspaces.map((w) => {
                  const active = w.match(pathname);
                  return (
                    <NavLink
                      key={w.to}
                      to={w.to}
                      role="tab"
                      aria-selected={active}
                      className={cn(
                        "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                        active ? "bg-accent text-accent-fg" : "text-muted hover:text-fg",
                      )}
                    >
                      {w.label}
                    </NavLink>
                  );
                })}
              </div>
            ) : null}
          </div>
          <nav className="flex items-center gap-1">
            {!scannerShell && !inScan
              ? orderLinks.map((l) => (
                  <NavLink
                    key={l.to}
                    to={l.to}
                    end={l.end}
                    className={({ isActive }) =>
                      cn(
                        "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive ? "bg-accent/15 text-accent" : "text-muted hover:text-fg",
                      )
                    }
                  >
                    {l.label}
                  </NavLink>
                ))
              : null}
            {!scannerShell && techName ? (
              <>
                <TechShiftControls techId={techId} />
                <TechNotifications techName={techName} techId={techId} />
              </>
            ) : null}
            {onExit ? (
              <Button variant="ghost" onClick={onExit}>
                {scannerShell ? "Exit to login" : "Log out"}
              </Button>
            ) : null}
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </nav>
        </div>
      </header>
      {!scannerShell ? <OfflineBanner /> : null}
      <main className="mx-auto max-w-6xl px-5 py-8">
        <Outlet />
      </main>
    </div>
  );
}
