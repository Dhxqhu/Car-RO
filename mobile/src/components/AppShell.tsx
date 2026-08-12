import { ClipboardList, Home, MessageSquare, Plus, Wrench } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { NotifyBell } from "@/components/NotifyBell";
import { cn } from "@/lib/utils";

const tabs = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/orders", label: "Orders", icon: ClipboardList },
  { to: "/messages", label: "Msgs", icon: MessageSquare },
  { to: "/parts", label: "Parts", icon: Wrench },
];

export function AppShell({
  name,
  id,
  role,
  onExit,
}: {
  name: string;
  id: string;
  role: string;
  onExit: () => void;
}) {
  const { pathname } = useLocation();
  const flush = pathname === "/messages";

  return (
    <div className="mx-auto flex h-dvh max-w-lg flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div>
          <p className="font-display text-lg leading-none">Car-RO</p>
          <p className="mt-0.5 text-xs text-muted">
            {name}
            {role === "advisor" ? " · advisor" : " · tech"}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {role === "advisor" ? (
            <NavLink
              to="/new"
              className="inline-flex h-9 items-center gap-1 rounded-lg bg-accent px-3 text-xs font-medium text-accent-fg"
            >
              <Plus size={14} />
              New
            </NavLink>
          ) : null}
          <NotifyBell id={id} name={name} role={role} />
          <button type="button" className="px-1 text-xs text-muted" onClick={onExit}>
            Sign out
          </button>
        </div>
      </header>
      <main
        className={cn(
          "flex min-h-0 flex-1 flex-col",
          flush ? "overflow-hidden" : "overflow-y-auto px-4 pt-4",
        )}
      >
        <Outlet />
      </main>
      <nav className="shrink-0 border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)]">
        <div className="grid grid-cols-4">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-0.5 py-2 text-[11px]",
                  isActive ? "text-accent" : "text-muted",
                )
              }
            >
              <t.icon size={20} />
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
