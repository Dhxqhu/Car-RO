import { Activity, Cable, FileText, Gauge, Info, ListTree } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

const tabs = [
  { to: "/scan", end: true, label: "Connect", icon: Cable },
  { to: "/scan/codes", label: "Codes", icon: ListTree },
  { to: "/scan/live", label: "Live data", icon: Activity },
  { to: "/scan/info", label: "Vehicle", icon: Info },
  { to: "/scan/saved", label: "Saved", icon: FileText },
  { to: "/scan/adapters", label: "Adapters", icon: Gauge },
];

export function ScanLayout() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
          Scanner
        </h1>
        <p className="mt-1 text-sm text-muted">
          obdscan workspace — ELM327 / GT327 DoIP. CLI stays fully supported.
        </p>
      </div>
      <nav className="flex flex-wrap gap-1 border-b border-border pb-px">
        {tabs.map(({ to, end, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "inline-flex items-center gap-2 rounded-t-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-b-2 border-accent text-accent"
                  : "text-muted hover:text-fg",
              )
            }
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
