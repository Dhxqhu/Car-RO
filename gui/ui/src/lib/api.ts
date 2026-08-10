/** Talk to the local Car-RO engine (proxied as /api in Vite / Tauri). */

function engineBase(): string {
  if (import.meta.env.VITE_ENGINE_URL) return import.meta.env.VITE_ENGINE_URL;
  // Tauri loads the UI from a custom protocol — talk to the local engine directly.
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    return "http://127.0.0.1:8788";
  }
  return "/api";
}

export type Technician = {
  id: string;
  name: string;
};

export type RepairOrder = {
  id: string;
  first_name: string;
  last_name: string;
  phone: string;
  year: string;
  make: string;
  model: string;
  vin: string;
  mileage: string;
  plate: string;
  complaint: string;
  tech_notes: string;
  technician_name: string;
  technician_id: string;
  status: string;
  obd_snapshot: string;
  photos: Array<Record<string, unknown>>;
  created: string;
  updated: string;
};

export type ConfigSnapshot = {
  config_file: string;
  shop_name: string;
  server_url: string;
  token_set: boolean;
  theme: string;
  textual_theme: string;
  logo_path: string;
  logo_status: string;
  local_keep: string | number;
  local_keep_resolved: number;
  local_keep_display: string;
  local_photo_keep: string | number;
  local_photo_keep_resolved: number;
  local_photo_keep_display: string;
  photos_dir: string;
  photos_inbox_dir: string;
  photos_provider: string;
  autosync_minutes: number;
  autosync?: {
    enabled: boolean;
    interval_minutes: number;
    running: boolean;
    last_run_at?: string | null;
    last_ok?: boolean | null;
    last_message?: string | null;
    last_error?: string | null;
    next_due_at?: string | null;
  };
  disk: { path: string; free_gb: number; total_gb: number };
  recommend: { local_keep: number; local_photo_keep: number };
  keep_presets: Array<{ label: string; value: string | number; detail: string }>;
  photo_keep_presets: Array<{ label: string; value: string | number; detail: string }>;
};

export type HistoryResult = {
  orders: RepairOrder[];
  matched_by: string;
  vin_query: string;
  name_query: string;
  remote_enabled: boolean;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${engineBase()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
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

export function photoUrl(roId: string, relpath: string): string {
  const name = relpath.split(/[/\\]/).pop() || relpath;
  return `${engineBase()}/ros/${encodeURIComponent(roId)}/photos/file/${encodeURIComponent(name)}`;
}

export const api = {
  health: () => req<{ ok: boolean; shop_name: string }>("/health"),
  listTechs: () => req<{ technicians: Technician[] }>("/technicians"),
  whoami: () => req<{ technician: Technician | null }>("/session"),
  login: (techId: string, pin: string) =>
    req<{ technician: Technician }>("/session/login", {
      method: "POST",
      body: JSON.stringify({ tech_id: techId, pin }),
    }),
  logout: () => req<{ ok: boolean }>("/session/logout", { method: "POST" }),
  listRos: (q = "") =>
    req<{ orders: RepairOrder[] }>(`/ros${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getRo: (id: string) => req<RepairOrder>(`/ros/${encodeURIComponent(id)}`),
  createRo: () => req<RepairOrder>("/ros", { method: "POST", body: "{}" }),
  saveRo: (order: RepairOrder) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(order.id)}`, {
      method: "PUT",
      body: JSON.stringify(order),
    }),
  deleteRo: (id: string) =>
    req<{ ok: boolean }>(`/ros/${encodeURIComponent(id)}`, { method: "DELETE" }),
  exportPdf: (id: string, opts?: { include_photos?: boolean }) => {
    const photos = opts?.include_photos !== false;
    const q = photos ? "" : "?include_photos=false";
    return req<{ path: string; include_photos?: boolean }>(
      `/ros/${encodeURIComponent(id)}/pdf${q}`,
      { method: "POST" },
    );
  },
  pullObd: (id: string) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(id)}/pull-obd`, { method: "POST" }),
  listPhotos: (id: string) =>
    req<{ photos: Array<Record<string, unknown>> }>(
      `/ros/${encodeURIComponent(id)}/photos`,
    ),
  uploadPhotos: (id: string, files: File[], tag: string, notes = "") => {
    const fd = new FormData();
    fd.append("tag", tag);
    fd.append("notes", notes);
    for (const f of files) fd.append("files", f);
    return req<RepairOrder>(`/ros/${encodeURIComponent(id)}/photos`, {
      method: "POST",
      body: fd,
    });
  },
  ingestInboxPhotos: (id: string, tag: string, notes = "") =>
    req<RepairOrder>(`/ros/${encodeURIComponent(id)}/photos/ingest`, {
      method: "POST",
      body: JSON.stringify({ tag, notes }),
    }),
  startPhoneUpload: (id: string, tag: string, mode: "phone" | "shortcut") =>
    req<{
      token: string;
      url: string;
      help_url: string;
      tag: string;
      mode: string;
      ttl_sec: number;
    }>(`/ros/${encodeURIComponent(id)}/photos/phone`, {
      method: "POST",
      body: JSON.stringify({ tag, mode }),
    }),
  refreshPhotos: (id: string) =>
    req<RepairOrder & { _local_files?: number }>(
      `/ros/${encodeURIComponent(id)}/photos/refresh`,
      { method: "POST" },
    ),
  history: (vin: string, name: string, excludeId?: string) => {
    const params = new URLSearchParams();
    if (vin.trim()) params.set("vin", vin.trim());
    if (name.trim()) params.set("name", name.trim());
    if (excludeId) params.set("exclude_id", excludeId);
    return req<HistoryResult>(`/history?${params.toString()}`);
  },
  historyPack: (
    vin: string,
    name: string,
    kind: "text" | "pdf" | "pdf-lite",
    excludeId?: string,
  ) =>
    req<{
      path: string;
      kind: string;
      count: number;
      estimated_pages?: number;
    }>("/history/pack", {
      method: "POST",
      body: JSON.stringify({
        vin,
        name,
        kind,
        exclude_id: excludeId || null,
      }),
    }),
  historyNewFrom: (priorId: string) =>
    req<RepairOrder>("/history/new-from", {
      method: "POST",
      body: JSON.stringify({ prior_id: priorId }),
    }),
  sync: () => req<{ ok: boolean; message: string }>("/sync", { method: "POST" }),
  getConfig: () => req<ConfigSnapshot>("/config"),
  setConfig: (body: Record<string, unknown>) =>
    req<{ ok: boolean } & ConfigSnapshot>("/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  generateToken: () =>
    req<{ ok: boolean; token: string } & ConfigSnapshot>("/config/generate-token", {
      method: "POST",
    }),
  applyDiskRecommendation: () =>
    req<{ ok: boolean } & ConfigSnapshot>("/config/apply-disk-recommendation", {
      method: "POST",
    }),
  addTech: (name: string, pin: string, adminPin: string) =>
    req<Technician>("/technicians", {
      method: "POST",
      body: JSON.stringify({ name, pin, admin_pin: adminPin }),
    }),
};
