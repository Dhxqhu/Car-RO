import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { formatStatus } from "@/lib/utils";

type PartRow = {
  ro_id?: string;
  description?: string;
  part_number?: string;
  status?: string;
  manufacturer?: string;
  superseded_by?: string;
  supersedes?: string;
};

export function PartsPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<PartRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = window.setTimeout(() => {
      api
        .parts(q)
        .then((r) => setRows((r.parts || []) as PartRow[]))
        .catch((e: Error) => setError(e.message));
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-3">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Part number or description" />
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No parts match.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((p, i) => (
            <li key={`${p.ro_id}-${p.part_number}-${i}`} className="rounded-xl border border-border bg-surface px-4 py-3">
              <p className="font-medium">{p.description || p.part_number || "Part"}</p>
              <p className="text-xs text-muted">
                {[p.part_number, p.manufacturer, formatStatus(p.status)].filter(Boolean).join(" · ")}
                {p.superseded_by ? ` · superseded → ${p.superseded_by}` : ""}
                {p.supersedes && !p.superseded_by ? ` · replaces ${p.supersedes}` : ""}
              </p>
              {p.ro_id ? (
                <Link to={`/ro/${p.ro_id}`} className="mt-1 inline-block text-xs text-accent">
                  {p.ro_id}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
