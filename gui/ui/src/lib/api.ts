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

export type WorkItemTimeEntry = {
  minutes: number;
  tech_id?: string;
  tech_name?: string;
  at?: string;
  note?: string;
  source?: string;
};

export type WorkItemPart = {
  id: string;
  description: string;
  part_number?: string;
  manufacturer?: string;
  status: string;
  requested_at?: string;
  ordered_at?: string;
  received_at?: string;
  wrong_note?: string;
  updated_at?: string;
};

export type WorkItem = {
  id: string;
  concern: string;
  notes: string;
  private_notes?: string;
  item_type?: string;
  status: string;
  priority?: number;
  assigned_to_id?: string;
  assigned_to_name?: string;
  assigned_at?: string;
  created_by?: string;
  created_by_id?: string;
  created_by_role?: string;
  notes_by?: string;
  notes_by_id?: string;
  notes_by_role?: string;
  worked_minutes?: number;
  time_log?: WorkItemTimeEntry[];
  worked_first_at?: string;
  worked_last_at?: string;
  timer_started_at?: string;
  timer_tech_id?: string;
  timer_tech_name?: string;
  stage_entered_at?: string;
  stage_totals?: {
    waiting_parts_minutes?: number;
    waiting_customer_minutes?: number;
    in_progress_calendar_minutes?: number;
    open_minutes?: number;
  };
  stage_log?: Array<{
    stage: string;
    started_at?: string;
    ended_at?: string;
    minutes?: number;
  }>;
  downtime_minutes?: number;
  downtime_log?: Array<{
    reason: string;
    started_at?: string;
    ended_at?: string;
    minutes?: number;
  }>;
  downtime_started_at?: string;
  downtime_reason?: string;
  updated_by?: string;
  updated_by_role?: string;
  created?: string;
  updated?: string;
  linked_photo_ids?: string[];
  parts?: WorkItemPart[];
};

export type PartsSheetRow = {
  ro_id: string;
  work_item_id: string;
  item_type?: string;
  concern?: string;
  customer?: string;
  vehicle?: string;
  make?: string;
  part_id: string;
  description: string;
  part_number?: string;
  manufacturer?: string;
  status: string;
  requested_at?: string;
  ordered_at?: string;
  received_at?: string;
  wrong_note?: string;
  updated_at?: string;
};

export type IdleNudge = {
  kind: "ro" | "work_item" | "part" | string;
  ro_id: string;
  work_item_id?: string;
  part_id?: string;
  status?: string;
  item_type?: string;
  summary?: string;
  customer?: string;
  vehicle?: string;
  assigned_to_name?: string;
  manufacturer?: string;
  idle_since?: string;
  idle_hours?: number;
  fingerprint: string;
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
  current_item_id?: string;
  started_at?: string;
  done_at?: string;
  billed_out_at?: string;
  waiting_since?: string;
  parts_requested_at?: string;
  parts_requested_by?: string;
  approval_requested_at?: string;
  approval_requested_by?: string;
  status: string;
  obd_snapshot: string;
  photos: Array<Record<string, unknown>>;
  work_items?: WorkItem[];
  found_issues?: FoundIssue[];
  created: string;
  updated: string;
};

export type FoundIssue = {
  id: string;
  description: string;
  notes?: string;
  status: string;
  decline_reason?: string;
  found_by?: string;
  found_by_id?: string;
  found_at?: string;
  resolved_by?: string;
  resolved_by_id?: string;
  resolved_at?: string;
  work_item_id?: string;
  source_work_item_id?: string;
  compose_downtime_minutes?: number;
  updated?: string;
};

export type FoundIssueSummary = {
  id: string;
  ro_id: string;
  description: string;
  status: string;
  found_by?: string;
  found_by_id?: string;
  found_at?: string;
  source_work_item_id?: string;
  customer: string;
  vehicle: string;
  vin?: string;
};

/** Itemized job on the Assigned board (work item + car context). */
export type AssignedJobSummary = {
  id: string;
  ro_id: string;
  item_id: string;
  concern: string;
  item_status: string;
  item_type?: string;
  customer: string;
  vehicle: string;
  vin: string;
  ro_status: string;
  assigned_to_id?: string;
  assigned_to_name?: string;
  assigned_at?: string;
  worked_minutes?: number;
  worked_first_at?: string;
  worked_last_at?: string;
  timer_started_at?: string;
  timer_tech_name?: string;
  stage_entered_at?: string;
  stage_totals?: Record<string, number>;
  waiting_parts_minutes?: number;
  waiting_customer_minutes?: number;
  stage_live_minutes?: number;
  downtime_minutes?: number;
  is_current?: boolean;
  current_tech_id?: string;
  current_tech_name?: string;
  current_since?: string;
  updated?: string;
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
  current_item_id?: string;
  started_at?: string;
  done_at?: string;
  billed_out_at?: string;
  waiting_since?: string;
  parts_requested_at?: string;
  parts_requested_by?: string;
  approval_requested_at?: string;
  approval_requested_by?: string;
  worked_minutes?: number;
  created?: string;
  updated: string;
  work_items: Array<{
    id: string;
    concern: string;
    status: string;
    assigned_to_id: string;
    assigned_to_name: string;
    created_by?: string;
    created_by_role?: string;
    notes_by?: string;
    worked_minutes?: number;
    worked_first_at?: string;
    worked_last_at?: string;
    timer_started_at?: string;
  }>;
};

export type NowWorkingEntry = {
  tech_id: string;
  tech_name: string;
  since: string;
  item_id?: string;
  order: AssignedOrderSummary;
  job?: AssignedJobSummary;
  is_me?: boolean;
};

export type AssignedBoard = {
  mine: AssignedJobSummary[];
  waiting_parts?: AssignedJobSummary[];
  waiting_customer?: AssignedJobSummary[];
  found_issues_pending?: FoundIssueSummary[];
  ready_to_bill?: AssignedOrderSummary[];
  billed_out?: AssignedOrderSummary[];
  by_tech: Array<{
    id: string;
    name: string;
    orders: AssignedOrderSummary[];
    jobs?: AssignedJobSummary[];
    current?: AssignedJobSummary | AssignedOrderSummary | null;
  }>;
  unassigned: AssignedJobSummary[];
  now_working?: NowWorkingEntry[];
  my_current?: AssignedJobSummary | null;
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
  local_billed_keep: number;
  local_parts_received_keep_hours: number;
  idle_nudge_hours: number;
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
  extendedSearch: (opts: {
    q?: string;
    name?: string;
    vin?: string;
    plate?: string;
    make?: string;
    model?: string;
    year?: string;
    status?: string;
  }) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) {
      if (typeof v === "string" && v.trim()) params.set(k, v.trim());
    }
    return req<{
      orders: RepairOrder[];
      remote_enabled: boolean;
      remote_only: number;
      sources: Record<string, string>;
    }>(`/ros/extended-search?${params.toString()}`);
  },
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
      private_notes?: string;
      item_type?: string;
      status?: string;
      priority?: number;
    },
  ) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/work-items`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listParts: (opts?: {
    status?: string;
    manufacturer?: string;
    part_number?: string;
    ro_id?: string;
    include_received?: boolean;
  }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.manufacturer) params.set("manufacturer", opts.manufacturer);
    if (opts?.part_number) params.set("part_number", opts.part_number);
    if (opts?.ro_id) params.set("ro_id", opts.ro_id);
    if (opts?.include_received) params.set("include_received", "true");
    const q = params.toString();
    return req<{ parts: PartsSheetRow[]; count: number }>(`/parts${q ? `?${q}` : ""}`);
  },
  addPart: (
    roId: string,
    itemId: string,
    body: { description: string; part_number?: string; manufacturer?: string | null },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/parts`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  patchPart: (
    roId: string,
    itemId: string,
    partId: string,
    body: {
      description?: string;
      part_number?: string;
      manufacturer?: string;
      status?: string;
      wrong_note?: string;
    },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/parts/${encodeURIComponent(partId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  deletePart: (roId: string, itemId: string, partId: string) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/parts/${encodeURIComponent(partId)}`,
      { method: "DELETE" },
    ),
  workItemTime: (
    roId: string,
    itemId: string,
    body: { action: "add" | "start" | "stop" | "checkpoint"; minutes?: number; note?: string },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/time`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
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
  setCurrentTask: (roId: string, active = true, itemId?: string) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/current`, {
      method: "POST",
      body: JSON.stringify({ active, item_id: itemId || null }),
    }),
  queueAction: (
    roId: string,
    action:
      | "add"
      | "remove"
      | "complete"
      | "complete_item"
      | "billed_out"
      | "reopen"
      | "waiting_parts"
      | "request_parts"
      | "item_waiting_parts"
      | "waiting_customer"
      | "request_approval"
      | "item_waiting_customer",
    itemId?: string,
  ) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/queue`, {
      method: "POST",
      body: JSON.stringify({ action, item_id: itemId || null }),
    }),
  beginFoundIssueCompose: (roId: string, itemId?: string) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/found-issues/compose`, {
      method: "POST",
      body: JSON.stringify({ item_id: itemId || null }),
    }),
  cancelFoundIssueCompose: (roId: string, itemId?: string) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/found-issues/compose/cancel`,
      {
        method: "POST",
        body: JSON.stringify({ item_id: itemId || null }),
      },
    ),
  createFoundIssue: (
    roId: string,
    body: {
      description: string;
      notes?: string;
      source_work_item_id?: string;
      finish_compose?: boolean;
    },
  ) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/found-issues`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  approveFoundIssue: (roId: string, fiId: string, itemType = "repair") =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/found-issues/${encodeURIComponent(fiId)}/approve`,
      {
        method: "POST",
        body: JSON.stringify({ item_type: itemType }),
      },
    ),
  declineFoundIssue: (roId: string, fiId: string, reason = "customer_declined") =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/found-issues/${encodeURIComponent(fiId)}/decline`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),
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
  listIdleNotifications: () =>
    req<{
      idle: IdleNudge[];
      count: number;
      idle_nudge_hours: number;
      enabled: boolean;
    }>("/notifications/idle"),
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
  addTech: (name: string, pin: string, adminPin?: string) =>
    req<Technician>("/technicians", {
      method: "POST",
      body: JSON.stringify({
        name,
        pin,
        ...(adminPin ? { admin_pin: adminPin } : {}),
      }),
    }),
  adminSession: () =>
    req<{ active: boolean; has_admin_pin: boolean }>("/admin/session"),
  adminUnlock: (adminPin: string) =>
    req<{ ok: boolean; active: boolean }>("/admin/unlock", {
      method: "POST",
      body: JSON.stringify({ admin_pin: adminPin }),
    }),
  adminLock: () => req<{ ok: boolean }>("/admin/lock", { method: "POST" }),
  adminChangePin: (adminPin: string, newPin: string) =>
    req<{ ok: boolean }>("/admin/change-pin", {
      method: "POST",
      body: JSON.stringify({ admin_pin: adminPin, new_pin: newPin }),
    }),
  adminResetTechPin: (techId: string, newPin: string) =>
    req<{ ok: boolean }>(`/admin/technicians/${encodeURIComponent(techId)}/reset-pin`, {
      method: "POST",
      body: JSON.stringify({ tech_id: techId, new_pin: newPin }),
    }),
  adminRenameTech: (techId: string, name: string) =>
    req<{ ok: boolean }>(`/admin/technicians/${encodeURIComponent(techId)}/rename`, {
      method: "POST",
      body: JSON.stringify({ tech_id: techId, name }),
    }),
  adminRemoveTech: (techId: string) =>
    req<{ ok: boolean }>(`/admin/technicians/${encodeURIComponent(techId)}`, {
      method: "DELETE",
    }),
  adminWorkItemTime: (
    roId: string,
    itemId: string,
    body: { action: "set" | "add" | "clear"; minutes?: number; note?: string },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/time/admin`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
