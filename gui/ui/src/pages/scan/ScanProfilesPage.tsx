import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { obdApi, type ProfileSummary } from "@/lib/obdApi";

export function ScanProfilesPage() {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [activeId, setActiveId] = useState("");
  const [path, setPath] = useState("");
  const [pids, setPids] = useState<Record<string, Record<string, unknown>>>({});
  const [newId, setNewId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [pidName, setPidName] = useState("");
  const [pidHex, setPidHex] = useState("");
  const [pidUnit, setPidUnit] = useState("");
  const [pidFormula, setPidFormula] = useState("raw");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    const pr = await obdApi.profiles();
    setProfiles(pr.profiles);
    setActiveId(pr.active_id);
    setPath(pr.path);
    if (pr.active_id) {
      const ap = await obdApi.activePids();
      setPids(ap.pids);
    } else {
      setPids({});
    }
  };

  useEffect(() => {
    void refresh().catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Custom PIDs / RE profiles (obdscan menu 9). Stored in{" "}
        <code className="text-fg">~/.config/obdscan/pid_profiles.json</code> — shared with the CLI.
      </ScaffoldNote>
      {path ? <p className="font-mono text-xs text-muted">{path}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Create profile
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Input
            placeholder="id (e.g. ford)"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            className="max-w-[10rem]"
          />
          <Input
            placeholder="label"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="max-w-[12rem]"
          />
          <Button
            onClick={() =>
              void (async () => {
                setErr(null);
                try {
                  await obdApi.createProfile({
                    id: newId,
                    label: newLabel || newId,
                    makes: [newId],
                    activate: true,
                  });
                  setNewId("");
                  setNewLabel("");
                  setMsg("Profile created");
                  await refresh();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                }
              })()
            }
          >
            Create
          </Button>
        </div>
      </div>

      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {profiles.length === 0 ? (
          <li className="px-4 py-8 text-center text-sm text-muted">No profiles yet.</li>
        ) : (
          profiles.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <div>
                <div className="font-medium">
                  {p.label}{" "}
                  {p.active ? <span className="text-xs text-accent">active</span> : null}
                </div>
                <div className="text-xs text-muted">
                  {p.id} · {p.pid_count} PIDs · {p.makes || "—"} · {p.years || "—"}
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={p.active}
                  onClick={() =>
                    void (async () => {
                      await obdApi.selectProfile(p.id);
                      setMsg(`Active: ${p.id}`);
                      await refresh();
                    })().catch((e: Error) => setErr(e.message))
                  }
                >
                  Activate
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (!window.confirm(`Delete profile ${p.id}?`)) return;
                    void (async () => {
                      await obdApi.deleteProfile(p.id);
                      await refresh();
                    })().catch((e: Error) => setErr(e.message));
                  }}
                >
                  Delete
                </Button>
              </div>
            </li>
          ))
        )}
      </ul>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">
          Custom PIDs on active profile {activeId ? `(${activeId})` : ""}
        </div>
        {!activeId ? (
          <p className="mt-2 text-sm text-muted">Select or create a profile first.</p>
        ) : (
          <>
            <div className="mt-3 grid gap-2 sm:grid-cols-4">
              <Input placeholder="NAME" value={pidName} onChange={(e) => setPidName(e.target.value)} />
              <Input
                placeholder="Mode 01 hex (2 chars, e.g. 0C)"
                value={pidHex}
                onChange={(e) => setPidHex(e.target.value)}
              />
              <Input placeholder="unit" value={pidUnit} onChange={(e) => setPidUnit(e.target.value)} />
              <Input
                placeholder="formula"
                value={pidFormula}
                onChange={(e) => setPidFormula(e.target.value)}
              />
            </div>
            <Button
              className="mt-2"
              size="sm"
              onClick={() =>
                void (async () => {
                  setErr(null);
                  try {
                    await obdApi.setActivePid({
                      name: pidName,
                      pid: pidHex,
                      unit: pidUnit,
                      formula: pidFormula,
                    });
                    setPidName("");
                    setPidHex("");
                    setMsg("PID saved");
                    await refresh();
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : String(e));
                  }
                })()
              }
            >
              Add / update PID
            </Button>
            <ul className="mt-3 space-y-1 text-sm">
              {Object.entries(pids).map(([name, spec]) => (
                <li key={name} className="flex justify-between gap-2 font-mono text-xs">
                  <span>
                    {name} · {String(spec.pid)} · {String(spec.formula || "raw")} ·{" "}
                    {String(spec.unit || "")}
                  </span>
                  <button
                    type="button"
                    className="text-danger hover:underline"
                    onClick={() =>
                      void (async () => {
                        await obdApi.removeActivePid(name);
                        await refresh();
                      })().catch((e: Error) => setErr(e.message))
                    }
                  >
                    remove
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
