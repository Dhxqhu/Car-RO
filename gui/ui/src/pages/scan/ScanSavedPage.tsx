import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { obdApi, type SavedReport } from "@/lib/obdApi";

export function ScanSavedPage() {
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [dir, setDir] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    obdApi
      .saved()
      .then((r) => {
        setReports(r.reports);
        setDir(r.dir);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  const open = async (name: string) => {
    setErr(null);
    try {
      const r = await obdApi.savedReport(name);
      setPreview(r.text);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Read-only view of Documents/Saved Codes — same reports Car-RO uses to autofill ROs.
      </ScaffoldNote>
      {dir ? <p className="font-mono text-xs text-muted">{dir}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {reports.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
          No saved DTC reports yet.
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {reports.map((r) => (
            <li key={r.name} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <div>
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-muted">
                  {new Date(r.mtime * 1000).toLocaleString()} · {r.size} bytes
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => void open(r.name)}>
                View
              </Button>
            </li>
          ))}
        </ul>
      )}
      {preview ? (
        <pre className="max-h-80 overflow-auto rounded-xl border border-border bg-surface p-4 text-xs leading-relaxed">
          {preview}
        </pre>
      ) : null}
    </div>
  );
}
