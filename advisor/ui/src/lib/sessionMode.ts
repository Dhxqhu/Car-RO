/** App entry: full bay (tech PIN) vs Scanner without Orders. */

export type AppMode = "login" | "tech" | "scanner";

const STORAGE_KEY = "carro-app-mode";

/** True when launched as scanner-only (skip login, no Orders). */
export function detectScannerOnlyBoot(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  if (params.get("mode") === "scanner") return true;
  const env = (import.meta.env.VITE_CARRO_MODE as string | undefined)?.toLowerCase();
  if (env === "scanner") return true;
  return false;
}

export function readStoredMode(): AppMode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "tech" || v === "scanner" || v === "login") return v;
  } catch {
    /* ignore */
  }
  return null;
}

export function persistMode(mode: AppMode): void {
  try {
    if (mode === "login") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}
