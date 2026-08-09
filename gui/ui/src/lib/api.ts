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
  exportPdf: (id: string) =>
    req<{ path: string }>(`/ros/${encodeURIComponent(id)}/pdf`, { method: "POST" }),
  pullObd: (id: string) =>
    req<RepairOrder>(`/ros/${encodeURIComponent(id)}/pull-obd`, { method: "POST" }),
  listPhotos: (id: string) =>
    req<{ photos: Array<Record<string, unknown>> }>(
      `/ros/${encodeURIComponent(id)}/photos`,
    ),
  sync: () => req<{ ok: boolean; message: string }>("/sync", { method: "POST" }),
  getConfig: () =>
    req<{
      shop_name: string;
      server_url: string;
      token_set: boolean;
      theme: string;
    }>("/config"),
  setConfig: (body: Record<string, string>) =>
    req<{ ok: boolean }>("/config", { method: "PUT", body: JSON.stringify(body) }),
  addTech: (name: string, pin: string, adminPin: string) =>
    req<Technician>("/technicians", {
      method: "POST",
      body: JSON.stringify({ name, pin, admin_pin: adminPin }),
    }),
};
