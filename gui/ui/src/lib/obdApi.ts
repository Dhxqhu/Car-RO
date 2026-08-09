/** Talk to the local OBD engine routes (`/obd/*` on the same process as Car-RO). */

function engineBase(): string {
  if (import.meta.env.VITE_ENGINE_URL) return import.meta.env.VITE_ENGINE_URL;
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    return "http://127.0.0.1:8788";
  }
  return "/api";
}

export type ObdSession = {
  connected: boolean;
  port: string | null;
  baud: number | null;
  adapter_label: string | null;
  protocol: string | null;
  vin: string | null;
};

export type ObdAdapter = Record<string, unknown> & {
  id?: string;
  label?: string;
  port?: string;
  baud?: number;
  transport?: string;
};

export type SavedReport = {
  name: string;
  path: string;
  mtime: number;
  size: number;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${engineBase()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = j.detail || JSON.stringify(j);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const obdApi = {
  health: () =>
    req<{
      ok: boolean;
      obdscan_root: string | null;
      obdscan_found: boolean;
      wired: boolean;
      session: ObdSession;
    }>("/obd/health"),
  session: () => req<{ session: ObdSession }>("/obd/session"),
  adapters: () =>
    req<{
      path: string;
      default_id: string | null;
      adapters: ObdAdapter[];
      note?: string;
    }>("/obd/adapters"),
  connect: (body: { port?: string; baud?: number; adapter_id?: string } = {}) =>
    req<{ session: ObdSession }>("/obd/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  disconnect: () =>
    req<{ ok: boolean; session: ObdSession }>("/obd/disconnect", { method: "POST" }),
  vehicle: () =>
    req<{
      source: string | null;
      vehicle: Record<string, unknown> | null;
      note?: string;
    }>("/obd/vehicle"),
  codes: () => req<{ codes: unknown[] }>("/obd/codes"),
  clearCodes: () => req<{ ok: boolean }>("/obd/codes/clear", { method: "POST" }),
  live: (pids: string[] = []) =>
    req<{ values: Record<string, unknown> }>(
      `/obd/live${pids.length ? `?pids=${encodeURIComponent(pids.join(","))}` : ""}`,
    ),
  saved: () => req<{ dir: string; reports: SavedReport[] }>("/obd/saved"),
  savedReport: (name: string) =>
    req<{ name: string; path: string; text: string }>(
      `/obd/saved/${encodeURIComponent(name)}`,
    ),
  save: () => req<{ path: string }>("/obd/save", { method: "POST" }),
};
