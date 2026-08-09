import { useEffect, useState } from "react";
import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { obdApi } from "@/lib/obdApi";

export function ScanRawPage() {
  const [command, setCommand] = useState("010C");
  const [response, setResponse] = useState("");
  const [help, setHelp] = useState<{
    at: { command: string; description: string }[];
    obd: { command: string; description: string }[];
    pids: { command: string; description: string }[];
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void obdApi
      .rawHelp()
      .then(setHelp)
      .catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Raw AT / OBD command (obdscan menu 14). Requires an active ELM connection.
      </ScaffoldNote>

      <div className="flex flex-wrap gap-2">
        <Input
          className="max-w-xs font-mono"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          spellCheck={false}
        />
        <Button
          disabled={busy}
          onClick={() =>
            void (async () => {
              setBusy(true);
              setErr(null);
              try {
                const r = await obdApi.raw(command);
                setResponse(r.response || "(empty)");
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            })()
          }
        >
          Send
        </Button>
      </div>

      {err ? <p className="text-sm text-danger">{err}</p> : null}

      {response ? (
        <pre className="max-h-64 overflow-auto rounded-xl border border-border bg-surface p-4 text-xs leading-relaxed">
          {response}
        </pre>
      ) : null}

      {help ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <HelpList title="AT commands" rows={help.at} onPick={setCommand} />
          <HelpList title="OBD shortcuts" rows={help.obd} onPick={setCommand} />
          <div className="lg:col-span-2">
            <HelpList title="Mode 01 PIDs (sample)" rows={help.pids} onPick={setCommand} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function HelpList({
  title,
  rows,
  onPick,
}: {
  title: string;
  rows: { command: string; description: string }[];
  onPick: (c: string) => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{title}</div>
      <ul className="mt-2 max-h-56 space-y-1 overflow-auto text-xs">
        {rows.map((r) => (
          <li key={`${r.command}-${r.description}`}>
            <button
              type="button"
              className="text-left hover:text-accent"
              onClick={() => onPick(r.command)}
            >
              <span className="font-mono text-fg">{r.command}</span>{" "}
              <span className="text-muted">{r.description}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
