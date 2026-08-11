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

export type Advisor = {
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
  oem_part_number?: string;
  manufacturer?: string;
  brand?: string;
  supplier?: string;
  status: string;
  requested_at?: string;
  ordered_at?: string;
  received_at?: string;
  wrong_note?: string;
  wrong_count?: number;
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
  merge_snapshot?: {
    at?: string;
    reason?: string;
    target_id?: string;
    source_ids?: string[];
    target_before?: { concern?: string; notes?: string; private_notes?: string };
    sources?: WorkItem[];
  };
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
  oem_part_number?: string;
  manufacturer?: string;
  brand?: string;
  supplier?: string;
  status: string;
  requested_at?: string;
  ordered_at?: string;
  received_at?: string;
  wrong_note?: string;
  wrong_count?: number;
  updated_at?: string;
  vin?: string;
};

export type PartsUsageRow = {
  part_number: string;
  manufacturer: string;
  brand?: string;
  description: string;
  use_count: number;
  ro_count: number;
  last_used_at?: string;
  year?: number;
  month?: number;
};

export type PartSuggestion = {
  part_number: string;
  manufacturer: string;
  brand?: string;
  description: string;
  use_count?: number;
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
  assigned_to_id?: string;
  assigned_to_name?: string;
  manufacturer?: string;
  idle_since?: string;
  idle_hours?: number;
  idle_threshold_hours?: number;
  queue_lane?: string;
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
  canceled_at?: string;
  no_call_no_show_at?: string;
  waiting_since?: string;
  parts_requested_at?: string;
  parts_requested_by?: string;
  approval_requested_at?: string;
  approval_requested_by?: string;
  waiter?: boolean;
  urgent?: boolean;
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
  kind?: string;
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
  photos?: Array<{
    id?: string;
    filename?: string;
    relpath?: string;
    tag?: string;
    notes?: string;
    found_issue_id?: string;
  }>;
  updated?: string;
};

export type FoundIssueSummary = {
  id: string;
  ro_id: string;
  description: string;
  status: string;
  kind?: string;
  found_by?: string;
  found_by_id?: string;
  found_at?: string;
  source_work_item_id?: string;
  photo_count?: number;
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
  waiter?: boolean;
  urgent?: boolean;
  queue_lane?: string;
  pending_queue_lane?: string;
  queue_day?: string;
  due_eod?: boolean;
  next_day_request?: {
    status?: string;
    at?: string;
    by?: string;
    by_id?: string;
    note?: string;
    read_at?: string;
  };
  assigned_to_id?: string;
  assigned_to_name?: string;
  assigned_at?: string;
  wait_requested_by?: string;
  wait_requested_by_id?: string;
  wait_kind?: string;
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
  canceled_at?: string;
  no_call_no_show_at?: string;
  waiting_since?: string;
  parts_requested_at?: string;
  parts_requested_by?: string;
  approval_requested_at?: string;
  approval_requested_by?: string;
  waiter?: boolean;
  urgent?: boolean;
  worked_minutes?: number;
  tech_worked?: Array<{ tech_id?: string; tech_name: string; minutes: number }>;
  items_total?: number;
  items_done?: number;
  items_declined?: number;
  items_open?: number;
  open_concerns?: string[];
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
  mine_daily?: AssignedJobSummary[];
  mine_next_day?: AssignedJobSummary[];
  mine_long_term?: AssignedJobSummary[];
  next_day?: AssignedJobSummary[];
  long_term?: AssignedJobSummary[];
  daily_by_tech?: Array<{
    id: string;
    name: string;
    jobs: AssignedJobSummary[];
  }>;
  defer_requests?: AssignedJobSummary[];
  waiting_parts?: AssignedJobSummary[];
  waiting_customer?: AssignedJobSummary[];
  found_issues_pending?: FoundIssueSummary[];
  ready_to_bill?: AssignedOrderSummary[];
  waiting_other_items?: AssignedOrderSummary[];
  billed_out?: AssignedOrderSummary[];
  canceled?: AssignedOrderSummary[];
  no_call_no_show?: AssignedOrderSummary[];
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

export type MessagePerson = {
  id: string;
  name: string;
  role: "technician" | "advisor";
};

export type ShopMessage = {
  id: number;
  at: string;
  body: string;
  from_id: string;
  from_name: string;
  from_role: string;
  to_id: string;
  to_name: string;
  to_role: string;
  ro_id?: string;
  work_item_id?: string;
  reply_to?: number | null;
  read_at?: string | null;
  delivered_at?: string | null;
  last_notified_at?: string;
  renotify_count?: number;
};

export type TechShift = {
  id: number;
  tech_id: string;
  tech_name: string;
  day: string;
  started_at: string;
  ended_at?: string | null;
};

export type WeeklyTechDay = {
  job_minutes: number;
  presence_minutes: number;
};

export type WeeklyTechJob = {
  ro_id: string;
  item_id: string;
  concern: string;
  minutes: number;
  vehicle: string;
  customer: string;
};

export type WeeklyTechRow = {
  tech_id: string;
  tech_name: string;
  job_minutes: number;
  presence_minutes: number;
  days: Record<string, WeeklyTechDay>;
  jobs: WeeklyTechJob[];
};

export type WeeklyTechReport = {
  week_start: string;
  week_end: string;
  generated_at: string;
  techs: WeeklyTechRow[];
  shop_job_minutes: number;
  shop_presence_minutes: number;
};

export type WeeklyReportSnapshot = {
  week_start: string;
  week_end: string;
  payload: WeeklyTechReport;
  created_at: string;
  updated_at: string;
  created_by: string;
  created_by_id: string;
};

export type WeeklyReportMeta = {
  week_start: string;
  week_end: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  created_by_id: string;
};

export type EfficiencyReason = {
  reason: string;
  label: string;
  minutes: number;
};

export type EfficiencyDay = {
  job_minutes: number;
  presence_minutes: number;
  downtime_minutes: number;
  ot_minutes: number;
  baseline_minutes: number;
};

export type EfficiencyTechRow = {
  tech_id: string;
  tech_name: string;
  baseline_minutes: number;
  job_minutes: number;
  presence_minutes: number;
  utilized_minutes: number;
  downtime_minutes: number;
  attributed_downtime_minutes: number;
  unaccounted_minutes: number;
  ot_minutes: number;
  worked_vs_clocked_rate: number;
  utilized_rate: number;
  baseline_fill: number;
  downtime_by_reason: EfficiencyReason[];
  days: Record<string, EfficiencyDay>;
  jobs: WeeklyTechJob[];
};

export type EfficiencyShop = {
  baseline_minutes: number;
  job_minutes: number;
  presence_minutes: number;
  utilized_minutes: number;
  downtime_minutes: number;
  ot_minutes: number;
  techs_present: number;
  worked_vs_clocked_rate: number;
  utilized_rate: number;
  baseline_fill: number;
  downtime_by_reason: EfficiencyReason[];
};

export type EfficiencyReport = {
  week_start: string;
  week_end: string;
  generated_at: string;
  baseline_day_minutes: number;
  baseline_week_minutes: number;
  techs: EfficiencyTechRow[];
  shop: EfficiencyShop;
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
  remote_ok?: boolean;
  note?: string;
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
    let detail: unknown = r.statusText;
    try {
      const j = await r.json();
      detail = j.detail ?? j;
    } catch {
      /* ignore */
    }
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "detail" in detail
          ? String((detail as { detail?: unknown }).detail || "Request failed")
          : "Request failed";
    throw new ApiError(message, r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

/** Tech GUI always identifies as technician when both sessions exist on one engine. */
const MSG_AS_ROLE = "technician";

function msgReq<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  headers.set("X-Carro-As-Role", MSG_AS_ROLE);
  const join = path.includes("?") ? "&" : "?";
  const withRole = path.includes("as_role=")
    ? path
    : `${path}${join}as_role=${encodeURIComponent(MSG_AS_ROLE)}`;
  return req<T>(withRole, { ...init, headers });
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isObdVinMismatch(
  err: unknown,
): err is ApiError & {
  body: {
    mismatch: true;
    ro_vin?: string;
    pulled_vin?: string;
    detail?: string;
    pulled?: { vin?: string; year?: string; make?: string; obd_snapshot?: string };
  };
} {
  if (!(err instanceof ApiError) || err.status !== 409) return false;
  const d = err.body;
  if (!d || typeof d !== "object") return false;
  const body = d as Record<string, unknown>;
  // FastAPI wraps dict detail as the detail value itself
  if (body.mismatch === true) return true;
  return false;
}

export function photoUrl(roId: string, relpath: string): string {
  const name = relpath.split(/[/\\]/).pop() || relpath;
  return `${engineBase()}/ros/${encodeURIComponent(roId)}/photos/file/${encodeURIComponent(name)}`;
}

export const api = {
  health: () => req<{ ok: boolean; shop_name: string }>("/health"),
  listTechs: () => req<{ technicians: Technician[] }>("/technicians"),
  whoami: () => req<{ technician: Technician | null; role?: string | null }>("/session"),
  login: (techId: string, pin: string) =>
    req<{ technician: Technician; role?: string }>("/session/login", {
      method: "POST",
      body: JSON.stringify({ tech_id: techId, pin }),
    }),
  logout: () => req<{ ok: boolean }>("/session/logout", { method: "POST" }),
  bootstrapTechnician: (body: {
    name: string;
    pin: string;
    admin_pin: string;
    set_admin?: boolean;
  }) =>
    req<{ technician: Technician; has_admin_pin: boolean; role?: string }>(
      "/bootstrap/technician",
      { method: "POST", body: JSON.stringify(body) },
    ),
  listAdvisors: () =>
    req<{ advisors: Advisor[]; has_admin_pin: boolean; empty: boolean }>("/advisors"),
  advisorWhoami: () =>
    req<{
      advisor: Advisor | null;
      role?: string | null;
      has_admin_pin?: boolean;
    }>("/advisor/session"),
  advisorLogin: (advisorId: string, pin: string) =>
    req<{ advisor: Advisor; role?: string }>("/advisor/session/login", {
      method: "POST",
      body: JSON.stringify({ advisor_id: advisorId, pin }),
    }),
  advisorLogout: () =>
    req<{ ok: boolean }>("/advisor/session/logout", { method: "POST" }),
  bootstrapAdvisor: (body: {
    name: string;
    pin: string;
    admin_pin: string;
    set_admin?: boolean;
  }) =>
    req<{ advisor: Advisor; has_admin_pin: boolean; role?: string }>(
      "/bootstrap/advisor",
      { method: "POST", body: JSON.stringify(body) },
    ),
  addAdvisor: (name: string, pin: string, adminPin?: string) =>
    req<Advisor>("/advisors", {
      method: "POST",
      body: JSON.stringify({
        name,
        pin,
        ...(adminPin ? { admin_pin: adminPin } : {}),
      }),
    }),
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
  createRo: () =>
    req<RepairOrder>("/ros", {
      method: "POST",
      body: JSON.stringify({ prefer_actor: "tech" }),
    }),
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
  pullObd: (id: string, opts?: { force?: boolean }) =>
    req<RepairOrder & { obd_vin_mismatch_forced?: boolean; pulled_vin?: string }>(
      `/ros/${encodeURIComponent(id)}/pull-obd`,
      {
        method: "POST",
        body: JSON.stringify({ force: Boolean(opts?.force) }),
      },
    ),
  listPhotos: (id: string) =>
    req<{ photos: Array<Record<string, unknown>> }>(
      `/ros/${encodeURIComponent(id)}/photos`,
    ),
  uploadPhotos: (
    id: string,
    files: File[],
    tag: string,
    notes = "",
    foundIssueId = "",
  ) => {
    const fd = new FormData();
    fd.append("tag", tag);
    fd.append("notes", notes);
    if (foundIssueId) fd.append("found_issue_id", foundIssueId);
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
      body: JSON.stringify({ prior_id: priorId, prefer_actor: "tech" }),
    }),
  sync: () =>
    req<{
      ok: boolean;
      message: string;
      pending?: { pending_total?: number };
    }>("/sync", { method: "POST" }),
  syncStatus: () =>
    req<{
      ok: boolean;
      pending?: { pending_total?: number };
      server_configured?: boolean;
    }>("/sync/status"),
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
  mergeWorkItems: (
    roId: string,
    targetId: string,
    sourceIds: string[],
    reason: string,
  ) =>
    req<RepairOrder & { merged_into?: string; merged_sources?: string[] }>(
      `/ros/${encodeURIComponent(roId)}/work-items/merge`,
      {
        method: "POST",
        body: JSON.stringify({
          target_id: targetId,
          source_ids: sourceIds,
          reason,
        }),
      },
    ),
  unmergeWorkItem: (roId: string, itemId: string) =>
    req<RepairOrder & { unmerged_sources?: string[] }>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/unmerge`,
      { method: "POST", body: "{}" },
    ),
  listParts: (opts?: {
    status?: string;
    manufacturer?: string;
    part_number?: string;
    ro_id?: string;
    q?: string;
    include_received?: boolean;
    source?: "auto" | "local" | "server";
  }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.manufacturer) params.set("manufacturer", opts.manufacturer);
    if (opts?.part_number) params.set("part_number", opts.part_number);
    if (opts?.ro_id) params.set("ro_id", opts.ro_id);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.include_received) params.set("include_received", "true");
    if (opts?.source) params.set("source", opts.source);
    const q = params.toString();
    return req<{ parts: PartsSheetRow[]; count: number; source?: string }>(
      `/parts${q ? `?${q}` : ""}`,
    );
  },
  partsUsage: (opts?: { year?: number; month?: number; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.year) params.set("year", String(opts.year));
    if (opts?.month) params.set("month", String(opts.month));
    if (opts?.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return req<{
      usage: PartsUsageRow[];
      count: number;
      year: number;
      month: number;
    }>(`/parts/usage${q ? `?${q}` : ""}`);
  },
  partsSuggest: (q = "", limit = 25) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    params.set("limit", String(limit));
    return req<{ suggestions: PartSuggestion[]; count: number; source?: string }>(
      `/parts/suggest?${params.toString()}`,
    );
  },
  addPart: (
    roId: string,
    itemId: string,
    body: {
      description: string;
      part_number?: string;
      oem_part_number?: string;
      manufacturer?: string | null;
      brand?: string;
      supplier?: string;
    },
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
      oem_part_number?: string;
      manufacturer?: string;
      brand?: string;
      supplier?: string;
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
    body: {
      assigned_to_id?: string;
      assigned_to_name?: string;
      item_id?: string | null;
      status?: string;
      due_eod?: boolean | null;
    },
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
      | "canceled"
      | "no_call_no_show"
      | "reopen"
      | "waiting_parts"
      | "request_parts"
      | "item_waiting_parts"
      | "waiting_customer"
      | "request_approval"
      | "item_waiting_customer"
      | "item_release_wait"
      | "item_return_to_requester",
    itemId?: string,
  ) =>
    msgReq<RepairOrder>(`/ros/${encodeURIComponent(roId)}/queue`, {
      method: "POST",
      body: JSON.stringify({ action, item_id: itemId || null }),
    }),
  setRoFlags: (roId: string, flags: { waiter?: boolean; urgent?: boolean }) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(roId)}/flags`, {
      method: "POST",
      body: JSON.stringify(flags),
    }),
  setWorkItemQueueLane: (
    roId: string,
    itemId: string,
    lane: "daily" | "next_day" | "long_term",
    approveRequest = false,
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/queue`,
      {
        method: "POST",
        body: JSON.stringify({ lane, approve_request: approveRequest }),
      },
    ),
  requestNextDay: (roId: string, itemId: string, note = "") =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/queue/request-next-day`,
      {
        method: "POST",
        body: JSON.stringify({ note }),
      },
    ),
  decideNextDayRequest: (roId: string, itemId: string, approve: boolean) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/queue/request-decision`,
      {
        method: "POST",
        body: JSON.stringify({ approve }),
      },
    ),
  markNextDayRequestRead: (roId: string, itemId: string) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/queue/request-read`,
      { method: "POST", body: "{}" },
    ),
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
      status?: "draft" | "pending";
    },
  ) =>
    req<RepairOrder & { created_found_issue_id?: string }>(
      `/ros/${encodeURIComponent(roId)}/found-issues`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  updateFoundIssue: (
    roId: string,
    fiId: string,
    body: { description?: string; notes?: string },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/found-issues/${encodeURIComponent(fiId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  submitFoundIssues: (roId: string, ids?: string[]) =>
    req<
      RepairOrder & {
        submitted_found_issue_ids?: string[];
        submitted_count?: number;
      }
    >(`/ros/${encodeURIComponent(roId)}/found-issues/submit`, {
      method: "POST",
      body: JSON.stringify({ ids: ids || [] }),
    }),
  approveFoundIssue: (roId: string, fiId: string, itemType = "repair") =>
    msgReq<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/found-issues/${encodeURIComponent(fiId)}/approve`,
      {
        method: "POST",
        body: JSON.stringify({ item_type: itemType }),
      },
    ),
  declineFoundIssue: (roId: string, fiId: string, reason = "customer_declined") =>
    msgReq<RepairOrder>(
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
  listMessagePeople: () =>
    msgReq<{
      people: MessagePerson[];
      me?: { id: string; role: string };
      server_required?: boolean;
    }>("/messages/people"),
  listMessages: (opts?: { unread?: boolean; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.unread) params.set("unread", "true");
    params.set("limit", String(opts?.limit ?? 100));
    const q = params.toString();
    return msgReq<{ messages: ShopMessage[]; unread: number }>(`/messages?${q}`);
  },
  listSentMessages: (opts?: { limit?: number }) => {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 100));
    return msgReq<{ messages: ShopMessage[] }>(`/messages/sent?${params.toString()}`);
  },
  listMessageThread: (withId: string, opts?: { limit?: number }) => {
    const params = new URLSearchParams();
    params.set("with_id", withId);
    params.set("limit", String(opts?.limit ?? 200));
    return msgReq<{
      messages: ShopMessage[];
      me: { id: string; name: string; role: string };
      with_id: string;
    }>(`/messages/thread?${params.toString()}`);
  },
  sendMessage: (body: {
    body: string;
    to_id: string;
    to_role: "technician" | "advisor";
    to_name?: string;
    ro_id?: string;
    work_item_id?: string;
    reply_to?: number | null;
  }) =>
    msgReq<{ ok: boolean; message: ShopMessage }>("/messages", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  markMessageRead: (messageId: number) =>
    msgReq<{ ok: boolean; message: ShopMessage }>(`/messages/${messageId}/read`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  markMessagesDelivered: (ids: number[]) =>
    msgReq<{ ok: boolean; messages: ShopMessage[]; count: number }>("/messages/delivered", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  renotifyMessage: (messageId: number) =>
    msgReq<{ ok: boolean; message: ShopMessage }>(`/messages/${messageId}/renotify`, {
      method: "POST",
      body: "{}",
    }),
  shiftMine: () => req<{ shift: TechShift | null }>("/shifts/mine"),
  shiftsActive: () => req<{ shifts: TechShift[] }>("/shifts/active"),
  listShifts: (opts?: {
    tech_id?: string;
    day_from?: string;
    day_to?: string;
    limit?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.tech_id) params.set("tech_id", opts.tech_id);
    if (opts?.day_from) params.set("day_from", opts.day_from);
    if (opts?.day_to) params.set("day_to", opts.day_to);
    params.set("limit", String(opts?.limit ?? 200));
    return req<{ shifts: TechShift[] }>(`/shifts?${params.toString()}`);
  },
  shiftStart: (opts?: {
    tech_id?: string;
    tech_name?: string;
    started_at?: string;
    day?: string;
  }) =>
    req<{ ok: boolean; shift: TechShift }>("/shifts/start", {
      method: "POST",
      body: JSON.stringify(opts || {}),
    }),
  shiftEnd: (opts?: {
    tech_id?: string;
    shift_id?: number;
    ended_at?: string;
  }) =>
    req<{ ok: boolean; shift: TechShift }>("/shifts/end", {
      method: "POST",
      body: JSON.stringify(opts || {}),
    }),
  updateShift: (
    shiftId: number,
    body: {
      started_at?: string | null;
      ended_at?: string | null;
      clear_end?: boolean;
      day?: string | null;
      admin_pin?: string;
    },
  ) =>
    req<{ ok: boolean; shift: TechShift }>(`/shifts/${shiftId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteShift: (shiftId: number) =>
    req<{ ok: boolean; id: number }>(`/shifts/${shiftId}`, {
      method: "DELETE",
    }),
  weeklyReport: (weekStart?: string) => {
    const q = weekStart
      ? `?week_start=${encodeURIComponent(weekStart)}`
      : "";
    return req<{
      live: WeeklyTechReport;
      snapshot: WeeklyReportSnapshot | null;
      week_start: string;
    }>(`/reports/weekly${q}`);
  },
  weeklyReportArchive: (limit = 52) =>
    req<{ weeks: WeeklyReportMeta[]; server_required?: boolean }>(
      `/reports/weekly/archive?limit=${limit}`,
    ),
  saveWeeklyReport: (weekStart: string) =>
    req<{ ok: boolean; snapshot: WeeklyReportSnapshot }>(
      `/reports/weekly/${encodeURIComponent(weekStart)}`,
      { method: "PUT", body: "{}" },
    ),
  efficiencyReport: (weekStart?: string) => {
    const q = weekStart
      ? `?week_start=${encodeURIComponent(weekStart)}`
      : "";
    return req<{ report: EfficiencyReport; week_start: string }>(
      `/reports/efficiency${q}`,
    );
  },
  listIdleNotifications: (opts?: { assignee_id?: string; desk?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.assignee_id) params.set("assignee_id", opts.assignee_id);
    if (opts?.desk) params.set("desk", "1");
    const q = params.toString();
    return req<{
      idle: IdleNudge[];
      count: number;
      idle_nudge_hours: number;
      enabled: boolean;
    }>(`/notifications/idle${q ? `?${q}` : ""}`);
  },
  getConfig: () => req<ConfigSnapshot>("/config"),
  setConfig: (body: Record<string, unknown>) =>
    req<{ ok: boolean } & ConfigSnapshot>("/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  submitBugReport: (body: {
    title: string;
    description: string;
    severity?: string;
    steps?: string;
    client?: string;
  }) =>
    req<{
      ok: boolean;
      report: {
        id: string;
        title: string;
        severity: string;
        created_at: string;
        synced?: boolean;
        sync_status?: string;
        sync_error?: string;
      };
    }>("/bug-reports", { method: "POST", body: JSON.stringify(body) }),
  listBugReports: (limit = 30) =>
    req<{
      reports: Array<{
        id: string;
        title: string;
        description?: string;
        severity: string;
        created_at: string;
        synced?: boolean;
        sync_status?: string;
        sync_error?: string;
        reporter_name?: string;
        client?: string;
      }>;
      count: number;
    }>(`/bug-reports?limit=${limit}`),
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
  adminRemoveTech: (techId: string, adminPin?: string) =>
    req<{ ok: boolean }>(`/admin/technicians/${encodeURIComponent(techId)}`, {
      method: "DELETE",
      body: JSON.stringify(adminPin ? { admin_pin: adminPin } : {}),
    }),
  adminResetAdvisorPin: (advisorId: string, newPin: string) =>
    req<{ ok: boolean }>(`/admin/advisors/${encodeURIComponent(advisorId)}/reset-pin`, {
      method: "POST",
      body: JSON.stringify({ advisor_id: advisorId, new_pin: newPin }),
    }),
  adminRenameAdvisor: (advisorId: string, name: string) =>
    req<{ ok: boolean }>(`/admin/advisors/${encodeURIComponent(advisorId)}/rename`, {
      method: "POST",
      body: JSON.stringify({ advisor_id: advisorId, name }),
    }),
  adminRemoveAdvisor: (advisorId: string, adminPin?: string) =>
    req<{ ok: boolean }>(`/admin/advisors/${encodeURIComponent(advisorId)}`, {
      method: "DELETE",
      body: JSON.stringify(adminPin ? { admin_pin: adminPin } : {}),
    }),
  adminWorkItemTime: (
    roId: string,
    itemId: string,
    body: {
      action: "set" | "add" | "clear";
      minutes?: number;
      note?: string;
      admin_pin?: string;
    },
  ) =>
    req<RepairOrder>(
      `/ros/${encodeURIComponent(roId)}/work-items/${encodeURIComponent(itemId)}/time/admin`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
