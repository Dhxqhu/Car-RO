import { ObdApiError } from "@/lib/obdApi";

/** OS-aware tips from the engine when ports / adapters are not found. */

export function ConnectionHints({
  title = "Common fixes",
  hints,
  platform,
}: {
  title?: string;
  hints: string[];
  platform?: string | null;
}) {
  if (!hints.length) return null;
  const os =
    platform === "windows" ? "Windows" : platform === "linux" ? "Linux" : platform || null;
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3 text-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {title}
        {os ? <span className="ml-2 normal-case text-muted">({os} host)</span> : null}
      </div>
      <ul className="mt-2 list-disc space-y-1.5 pl-4 text-muted">
        {hints.map((h) => (
          <li key={h} className="text-fg/90">
            {h}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Pull message + OS hints from ObdApiError or a plain Error. */
export function parseApiError(err: unknown): { message: string; hints: string[] } {
  if (err instanceof ObdApiError) {
    return { message: err.message, hints: err.hints };
  }
  if (err instanceof Error) {
    return { message: err.message, hints: [] };
  }
  return { message: String(err), hints: [] };
}
