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

export type DtcRow = { type: string; code: string; description: string };

export type PidInfo = { name: string; pid: string; unit: string; custom: boolean };

export type ProfileSummary = {
  id: string;
  label: string;
  pid_count: number;
  makes: string;
  years: string;
  active: boolean;
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
      lock?: {
        held: boolean;
        stale?: boolean;
        pid?: number;
        owner?: string;
        port?: string;
        path?: string;
        alive?: boolean;
      };
    }>("/obd/health"),
  session: () => req<{ session: ObdSession }>("/obd/session"),
  adapters: () =>
    req<{
      path: string;
      default_id: string | null;
      adapters: ObdAdapter[];
      note?: string;
    }>("/obd/adapters"),
  setDefaultAdapter: (adapter_id: string) =>
    req<{ ok: boolean; default_id: string }>("/obd/adapters/default", {
      method: "PUT",
      body: JSON.stringify({ adapter_id }),
    }),
  upsertAdapter: (body: {
    id: string;
    label?: string;
    port?: string;
    baud?: number;
    transport?: string;
    notes?: string;
    make_default?: boolean;
  }) =>
    req<{ ok: boolean; id: string; default_id?: string }>("/obd/adapters", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  discoverAdapters: () =>
    req<{
      usb: { path: string; detail: string }[];
      bluetooth: { addr: string; name: string; paired: string }[];
      note?: string;
    }>("/obd/adapters/discover"),
  autosetupUsb: (port?: string) =>
    req<{
      ok: boolean;
      adapter_id?: string;
      port?: string;
      baud?: number;
      banner?: string;
      message?: string;
      tried?: { path: string; elm: boolean; baud?: number; banner?: string }[];
    }>("/obd/adapters/autosetup/usb", {
      method: "POST",
      body: JSON.stringify(port ? { port } : {}),
    }),
  autosetupBluetooth: (body: { bt_addr?: string; rfcomm?: number; scan_seconds?: number } = {}) =>
    req<{
      ok: boolean;
      adapter_id?: string;
      bt_addr?: string;
      name?: string;
      port?: string;
      baud?: number;
      banner?: string;
      elm_ok?: boolean;
      message?: string;
      warning?: string | null;
      error?: string;
      devices?: { addr: string; name: string }[];
    }>("/obd/adapters/autosetup/bluetooth", {
      method: "POST",
      body: JSON.stringify(body),
    }),
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
  vehicleLive: () =>
    req<{
      source: string;
      vehicle: Record<string, unknown>;
      raw: Record<string, string>;
    }>("/obd/vehicle/live", { method: "POST" }),
  codes: (force = false) =>
    req<{ ok: boolean; ecu_alive?: boolean; codes: DtcRow[]; note?: string }>(
      `/obd/codes${force ? "?force=true" : ""}`,
    ),
  clearCodes: () =>
    req<{ ok: boolean; response: string }>("/obd/codes/clear", { method: "POST" }),
  lookup: (codes: string) =>
    req<{
      results: { code: string; description: string; found?: boolean }[];
      db_size: number;
    }>(`/obd/lookup?codes=${encodeURIComponent(codes.trim())}`),
  live: (pids: string[] = []) =>
    req<{
      pids: string[];
      values: Record<string, { value: string | null; unit: string; error?: string; raw?: string }>;
    }>(`/obd/live${pids.length ? `?pids=${encodeURIComponent(pids.join(","))}` : ""}`),
  configureLive: (pids: string[]) =>
    req<{ pids: string[]; unknown: string[] }>("/obd/live", {
      method: "POST",
      body: JSON.stringify({ pids }),
    }),
  pids: () =>
    req<{ pids: PidInfo[]; selected: string[]; active_profile: string }>("/obd/pids"),
  readiness: () =>
    req<{
      ok: boolean;
      mil?: boolean;
      dtc_count?: number;
      ignition?: string;
      monitors: { name: string; status: string }[];
      raw?: string;
    }>("/obd/readiness"),
  freeze: () =>
    req<{
      dtc_raw: string;
      frame: string;
      samples: { name: string; pid: string; value: string }[];
    }>("/obd/freeze"),
  rawHelp: () =>
    req<{
      at: { command: string; description: string }[];
      obd: { command: string; description: string }[];
      pids: { command: string; description: string }[];
    }>("/obd/raw/help"),
  raw: (command: string, wait = 1.5) =>
    req<{ command: string; response: string }>("/obd/raw", {
      method: "POST",
      body: JSON.stringify({ command, wait }),
    }),
  saved: () => req<{ dir: string; reports: SavedReport[] }>("/obd/saved"),
  savedReport: (name: string) =>
    req<{ name: string; path: string; text: string }>(
      `/obd/saved/${encodeURIComponent(name)}`,
    ),
  save: (force = false) =>
    req<{
      ok: boolean;
      path: string | null;
      codes?: DtcRow[];
      note?: string;
    }>(`/obd/save${force ? "?force=true" : ""}`, { method: "POST" }),

  profiles: () =>
    req<{ path: string; active_id: string; profiles: ProfileSummary[] }>("/obd/profiles"),
  selectProfile: (profile_id: string) =>
    req<{ ok: boolean; active_id: string }>("/obd/profiles/select", {
      method: "POST",
      body: JSON.stringify({ profile_id }),
    }),
  createProfile: (body: {
    id: string;
    label?: string;
    makes?: string[];
    notes?: string;
    activate?: boolean;
  }) =>
    req<{ ok: boolean; profile: { id: string; label: string } }>("/obd/profiles", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProfile: (id: string) =>
    req<{ ok: boolean; active_id: string }>(`/obd/profiles/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  activePids: () =>
    req<{ active_id: string; pids: Record<string, Record<string, unknown>> }>(
      "/obd/profiles/active/pids",
    ),
  setActivePid: (body: {
    name: string;
    pid: string;
    unit?: string;
    formula?: string;
    mult?: number;
    offset?: number;
    wide?: boolean;
    note?: string;
  }) =>
    req<{ ok: boolean; pids: Record<string, unknown> }>("/obd/profiles/active/pids", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  removeActivePid: (name: string) =>
    req<{ ok: boolean }>(`/obd/profiles/active/pids/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  doipStatus: () =>
    req<{
      ok: boolean;
      has_doip: boolean;
      obdscan_found: boolean;
      obdscan_root: string | null;
      hint: string | null;
      note?: string;
    }>("/obd/doip/status"),
  doipPacks: () => req<{ packs: DoipPackSummary[] }>("/obd/doip/packs"),
  doipPack: (id: string) =>
    req<DoipPackDetail>(`/obd/doip/packs/${encodeURIComponent(id)}`),
  doipDiscover: (timeout = 5) =>
    req<{ vehicles: DoipVehicle[]; note?: string }>("/obd/doip/discover", {
      method: "POST",
      body: JSON.stringify({ timeout }),
    }),
  doipProbe: (body: { pack: string; ip: string; max_addresses?: number }) =>
    req<{
      pack: string;
      ip: string;
      results: DoipProbeRow[];
      alive: DoipProbeRow[];
    }>("/obd/doip/probe", { method: "POST", body: JSON.stringify(body) }),
  doipDids: (body: { pack: string; ip: string; la: string }) =>
    req<{
      pack: string;
      ip: string;
      la: string;
      session: string;
      dids: { id: string; value: string }[];
    }>("/obd/doip/dids", { method: "POST", body: JSON.stringify(body) }),
  doipDtcs: (body: { pack: string; ip: string; la: string }) =>
    req<{
      ok: boolean;
      pack: string;
      ip: string;
      la: string;
      codes: string[];
      error?: string;
    }>("/obd/doip/dtcs", { method: "POST", body: JSON.stringify(body) }),
  doipClearDtcs: (body: { pack: string; ip: string; la: string }) =>
    req<{
      ok: boolean;
      pack: string;
      ip: string;
      la: string;
      message: string;
    }>("/obd/doip/dtcs/clear", { method: "POST", body: JSON.stringify(body) }),
};

export type DoipPackSummary = {
  id: string;
  name: string;
  description: string;
  maturity: string;
  module_count: number;
  did_count: number;
  transports: string[];
  ip_hints: string[];
  gateway_addresses: string[];
  default_doip_port: number;
  tester_address: string;
};

export type DoipPackDetail = DoipPackSummary & {
  modules: {
    address: string;
    name: string;
    addressing: string;
    description: string;
  }[];
  dids: { did: string; name: string; description: string }[];
};

export type DoipVehicle = {
  ip: string;
  la: string;
  la_int: number;
  vin: string;
};

export type DoipProbeRow = {
  la: string;
  la_int: number;
  name: string;
  status: string;
  alive: boolean;
};
