export type Person = {
  id: string;
  name: string;
  role: "technician" | "advisor" | string;
  working_privilege?: boolean;
};

export type Session = {
  ok?: boolean;
  kind?: string;
  role?: string;
  id?: string;
  name?: string;
  token?: string;
  technician?: { id: string; name: string } | null;
  advisor?: { id: string; name: string } | null;
};

export type WorkItem = {
  id: string;
  concern?: string;
  notes?: string;
  status?: string;
  kind?: string;
  assigned_to_name?: string;
  worked_minutes?: number;
};

export type PhotoMeta = {
  id?: string;
  filename?: string;
  relpath?: string;
  tag?: string;
  notes?: string;
  volume?: string;
};

export type RepairOrder = {
  id: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  year?: string;
  make?: string;
  model?: string;
  vin?: string;
  mileage?: string;
  plate?: string;
  complaint?: string;
  tech_notes?: string;
  status?: string;
  assigned_to_name?: string;
  current_tech_name?: string;
  photos?: PhotoMeta[];
  work_items?: WorkItem[];
  found_issues?: Array<{ id: string; description?: string; status?: string }>;
  created?: string;
  updated?: string;
};

export type ShopMessage = {
  id: number;
  body: string;
  from_id: string;
  from_name: string;
  from_role: string;
  to_id: string;
  to_name: string;
  to_role: string;
  ro_id?: string;
  read_at?: string;
  at?: string;
};

export type AssignedJob = {
  ro_id?: string;
  id?: string;
  customer?: string;
  vehicle?: string;
  status?: string;
  concern?: string;
  item_status?: string;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TOKEN_KEY = "carro-pwa-token";

export function getStoredToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setStoredToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  headers.set("Accept", "application/json");
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getStoredToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const r = await fetch(path, { ...init, headers, credentials: "include" });
  if (r.status === 401 || r.status === 403) {
    if (path !== "/session" && path !== "/session/login") {
      /* caller handles logout */
    }
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail || "Request failed", r.status);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const api = {
  people: () => req<{ people: Person[]; empty: boolean }>("/people"),
  login: (id: string, pin: string) =>
    req<Session>("/session/login", { method: "POST", body: JSON.stringify({ id, pin }) }),
  session: () => req<Session>("/session"),
  logout: () => req<{ ok: boolean }>("/session/logout", { method: "POST" }),
  listRos: (q = "") =>
    req<RepairOrder[]>(`/ros${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getRo: (id: string) => req<RepairOrder>(`/ros/${encodeURIComponent(id)}`),
  putRo: (order: RepairOrder) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(order.id)}`, {
      method: "PUT",
      body: JSON.stringify({
        ...order,
        _base_updated: order.updated || "",
      }),
    }),
  createRo: (body: Partial<RepairOrder>) =>
    req<RepairOrder>("/ros", { method: "POST", body: JSON.stringify(body) }),
  assigned: (techId: string) =>
    req<{
      mine?: AssignedJob[];
      jobs?: AssignedJob[];
      orders?: AssignedJob[];
      source?: string;
    }>(`/assigned?tech_id=${encodeURIComponent(techId)}`),
  recent: (minutes = 24 * 60) =>
    req<{ orders: RepairOrder[]; count: number }>(`/advisor/recent?minutes=${minutes}`),
  messages: (forId: string) =>
    req<{ messages: ShopMessage[]; unread: number }>(
      `/messages?for_id=${encodeURIComponent(forId)}`,
    ),
  sendMessage: (body: Record<string, string>) =>
    req<{ ok: boolean; message: ShopMessage }>("/messages", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  markRead: (id: number, forId: string) =>
    req(`/messages/${id}/read`, {
      method: "POST",
      body: JSON.stringify({ for_id: forId }),
    }),
  myShift: (techId: string) =>
    req<{ shift: { id: number; started_at?: string; ended_at?: string } | null }>(
      `/shifts/mine?tech_id=${encodeURIComponent(techId)}`,
    ),
  startShift: (techId: string, techName: string) =>
    req("/shifts/start", {
      method: "POST",
      body: JSON.stringify({ tech_id: techId, tech_name: techName }),
    }),
  endShift: (techId: string) =>
    req("/shifts/end", {
      method: "POST",
      body: JSON.stringify({ tech_id: techId }),
    }),
  parts: (q: string) =>
    req<{ parts: Array<Record<string, string>>; count: number }>(
      `/parts?q=${encodeURIComponent(q)}&limit=80`,
    ),
  uploadPhoto: async (roId: string, file: File, tag = "other") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("tag", tag);
    return req<PhotoMeta>(`/ros/${encodeURIComponent(roId)}/photos`, {
      method: "POST",
      body: fd,
    });
  },
  pushVapid: () =>
    req<{ ok: boolean; public_key: string; subscribed: boolean }>("/push/vapid"),
  pushSubscribe: (sub: PushSubscriptionJSON) =>
    req<{ ok: boolean }>("/push/subscribe", {
      method: "POST",
      body: JSON.stringify(sub),
    }),
  pushUnsubscribe: (endpoint?: string) =>
    req<{ ok: boolean }>("/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint: endpoint || "" }),
    }),
};

export function photoUrl(roId: string, photo: PhotoMeta): string {
  const rel = photo.relpath || photo.filename || "";
  const vol = photo.volume ? `?volume=${encodeURIComponent(photo.volume)}` : "";
  return `/ros/${encodeURIComponent(roId)}/photos/${encodeURIComponent(rel)}${vol}`;
}
