import { ClipboardList, Home, MessageSquare, Plus, Wrench } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

const tabs = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/orders", label: "Orders", icon: ClipboardList },
  { to: "/messages", label: "Msgs", icon: MessageSquare },
  { to: "/parts", label: "Parts", icon: Wrench },
];

export function AppShell({
  name,
  role,
  onExit,
}: {
  name: string;
  role: string;
  onExit: () => void;
}) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-lg flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div>
          <p className="font-display text-lg leading-none">Car-RO</p>
          <p className="mt-0.5 text-xs text-muted">
            {name}
            {role === "advisor" ? " · advisor" : " · tech"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {role === "advisor" ? (
            <NavLink
              to="/new"
              className="inline-flex h-9 items-center gap-1 rounded-lg bg-accent px-3 text-xs font-medium text-accent-fg"
            >
              <Plus size={14} />
              New
            </NavLink>
          ) : null}
          <button type="button" className="text-xs text-muted" onClick={onExit}>
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 px-4 pb-24 pt-4">
        <Outlet />
      </main>
      <nav className="fixed inset-x-0 bottom-0 mx-auto max-w-lg border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
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
