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

export type WorkItem = {
  id: string;
  concern: string;
  notes: string;
  status: string;
  priority?: number;
  assigned_to_id?: string;
  assigned_to_name?: string;
  created_by?: string;
  updated_by?: string;
  created_by_role?: string;
  updated_by_role?: string;
  created?: string;
  updated?: string;
  linked_photo_ids?: string[];
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
  assigned_to_id?: string;
  assigned_to_name?: string;
  assigned_at?: string;
  current_tech_id?: string;
  current_tech_name?: string;
  current_since?: string;
  status: string;
  obd_snapshot: string;
  photos: Array<Record<string, unknown>>;
  work_items?: WorkItem[];
  created: string;
  updated: string;
};

export type AssignedOrderSummary = {
  id: string;
  customer: string;
  vehicle: string;
  vin: string;
  status: string;
  assigned_to_id: string;
  assigned_to_name: string;
  assigned_at: string;
  current_tech_id?: string;
  current_tech_name?: string;
  current_since?: string;
  updated: string;
  work_items: Array<{
    id: string;
    concern: string;
    status: string;
    assigned_to_id: string;
    assigned_to_name: string;
  }>;
};

export type NowWorkingEntry = {
  tech_id: string;
  tech_name: string;
  since: string;
  order: AssignedOrderSummary;
  is_me?: boolean;
};

export type AssignedBoard = {
  mine: AssignedOrderSummary[];
  by_tech: Array<{
    id: string;
    name: string;
    orders: AssignedOrderSummary[];
    current?: AssignedOrderSummary | null;
  }>;
  unassigned: AssignedOrderSummary[];
  now_working?: NowWorkingEntry[];
  my_current?: AssignedOrderSummary | null;
  tech_id?: string;
  tech_name?: string;
  source?: string;
};

export type RoEvent = {
  id?: number | string;
  type: string;
  ro_id: string;
  item_id?: string;
  actor?: string;
  actor_id?: string | null;
  at: string;
  summary?: string;
  payload?: { actor_id?: string; [key: string]: unknown };
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
  exportPdf: (id: string, opts?: { include_photos?: boolean; open_viewer?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.include_photos === false) params.set("include_photos", "false");
    if (opts?.open_viewer) params.set("open_viewer", "true");
    const q = params.toString() ? `?${params}` : "";
    return req<{
      path: string;
      include_photos?: boolean;
      opened?: boolean;
      viewer?: string | null;
      view_url?: string;
    }>(`/ros/${encodeURIComponent(id)}/pdf${q}`, { method: "POST" });
  },
  openPdf: (id: string, opts?: { include_photos?: boolean }) => {
    const photos = opts?.include_photos !== false;
    const q = photos ? "" : "?include_photos=false";
    return req<{
      path: string;
      opened?: boolean;
      viewer?: string | null;
      view_url?: string;
    }>(`/ros/${encodeURIComponent(id)}/pdf/open${q}`, { method: "POST" });
  },
  pdfViewUrl: (id: string, include_photos = true) => {
    const q = include_photos ? "" : "?include_photos=false";
    return `${engineBase()}/ros/${encodeURIComponent(id)}/pdf/file${q}`;
  },
  openFile: (path: string) =>
    req<{ path: string; opened?: boolean; viewer?: string | null }>("/files/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
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
  upsertWorkItem: (
    roId: string,
    body: {
      id?: string;
      concern?: string;
      notes?: string;
      status?: string;
      priority?: number;
      assigned_to_id?: string;
      assigned_to_name?: string;
    },
  ) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/work-items`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteWorkItem: (roId: string, itemId: string) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}`,
      { method: "DELETE" },
    ),
  assignedBoard: () => req<AssignedBoard>("/assigned"),
  assignRo: (
    roId: string,
    body: { assigned_to_id?: string; assigned_to_name?: string; status?: string },
  ) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/assign`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  setCurrentTask: (roId: string, active = true) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/current`, {
      method: "POST",
      body: JSON.stringify({ active }),
    }),
  listEvents: (opts?: {
    since?: string;
    since_id?: number;
    limit?: number;
    ro_id?: string;
    exclude_actor?: string;
    exclude_actor_id?: string;
    /** Engine default true — omit own events. Set false only for admin/debug. */
    exclude_self?: boolean;
  }) => {
    const params = new URLSearchParams();
    if (opts?.since) params.set("since", opts.since);
    if (opts?.since_id) params.set("since_id", String(opts.since_id));
    if (opts?.ro_id) params.set("ro_id", opts.ro_id);
    if (opts?.exclude_actor) params.set("exclude_actor", opts.exclude_actor);
    if (opts?.exclude_actor_id) params.set("exclude_actor_id", opts.exclude_actor_id);
    if (opts?.exclude_self === false) params.set("exclude_self", "false");
    params.set("limit", String(opts?.limit ?? 50));
    return req<{ events: RoEvent[]; note?: string }>(`/events?${params.toString()}`);
  },
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
