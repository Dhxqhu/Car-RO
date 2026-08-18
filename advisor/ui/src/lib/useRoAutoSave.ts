import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_DEBOUNCE_MS = 2500;

export type RoAutoSaveStatus = "idle" | "pending" | "saving" | "saved";

export function useRoAutoSave(options: {
  roId: string | undefined;
  enabled?: boolean;
  debounceMs?: number;
  dirtyRef: React.MutableRefObject<boolean>;
  /** True while manual save or other blocking work is in progress. */
  busyRef: React.MutableRefObject<boolean>;
  /** Changes whenever editable fields change — drives debounce scheduling. */
  watchKey: string;
  onSave: () => Promise<void>;
  onError: (message: string) => void;
}): { status: RoAutoSaveStatus; autoSaving: boolean; lastSavedAt: Date | null } {
  const {
    roId,
    enabled = true,
    debounceMs = DEFAULT_DEBOUNCE_MS,
    dirtyRef,
    busyRef,
    watchKey,
    onSave,
    onError,
  } = options;

  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const [status, setStatus] = useState<RoAutoSaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [autoSaving, setAutoSaving] = useState(false);
  const autoSavingRef = useRef(false);
  autoSavingRef.current = autoSaving;
  const timerRef = useRef<number | null>(null);

  const performSave = useCallback(async () => {
    if (!roId || !dirtyRef.current || busyRef.current || autoSavingRef.current) return;
    setAutoSaving(true);
    setStatus("saving");
    try {
      await onSaveRef.current();
      if (!dirtyRef.current) {
        setLastSavedAt(new Date());
        setStatus("saved");
      } else {
        setStatus("pending");
      }
    } catch (e) {
      setStatus("pending");
      onErrorRef.current(e instanceof Error ? e.message : "Auto-save failed");
    } finally {
      setAutoSaving(false);
    }
  }, [roId, dirtyRef, busyRef]);

  useEffect(() => {
    if (!enabled || !roId) {
      setStatus("idle");
      return;
    }
    if (!dirtyRef.current) {
      setStatus(lastSavedAt ? "saved" : "idle");
      return;
    }
    setStatus("pending");
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      void performSave();
    }, debounceMs);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [watchKey, enabled, roId, debounceMs, performSave, dirtyRef, lastSavedAt]);

  useEffect(() => {
    if (!enabled) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [enabled, dirtyRef]);

  return { status, autoSaving, lastSavedAt };
}

export function formatAutoSaveTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
