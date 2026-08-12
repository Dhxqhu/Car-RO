import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Camera, Images } from "lucide-react";
import { CameraSheet } from "@/components/CameraSheet";
import { api, photoUrl, type RepairOrder } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn, customerLabel, formatStatus, vehicleLabel } from "@/lib/utils";

const PHOTO_TAGS = ["intake", "diag", "other"] as const;

export function RoPage() {
  const { id = "" } = useParams();
  const [order, setOrder] = useState<RepairOrder | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [photoTag, setPhotoTag] = useState<(typeof PHOTO_TAGS)[number]>("diag");
  const [cameraOpen, setCameraOpen] = useState(false);
  const libraryRef = useRef<HTMLInputElement | null>(null);

  async function load() {
    setError("");
    try {
      const o = await api.getRo(id);
      setOrder(o);
      const first = o.work_items?.[0];
      setNotes(first?.notes || o.tech_notes || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load RO");
    }
  }

  useEffect(() => {
    void load();
  }, [id]);

  async function saveNotes() {
    if (!order) return;
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const items = [...(order.work_items || [])];
      if (items[0]) items[0] = { ...items[0], notes };
      const saved = await api.putRo({
        ...order,
        tech_notes: notes,
        work_items: items,
      });
      setOrder(saved);
      setMsg("Saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFiles(files: File[]) {
    if (!order || !files.length) return;
    setBusy(true);
    setError("");
    setMsg("");
    try {
      for (const file of files) {
        await api.uploadPhoto(order.id, file, photoTag);
      }
      await load();
      setMsg(files.length === 1 ? "Photo added" : `${files.length} photos added`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (libraryRef.current) libraryRef.current.value = "";
    }
  }

  if (!order && !error) {
    return <p className="text-sm text-muted">Loading…</p>;
  }
  if (!order) {
    return <p className="text-sm text-danger">{error}</p>;
  }

  return (
    <div className="space-y-4">
      <Link to="/orders" className="text-sm text-accent">
        ← Orders
      </Link>
      <div>
        <h1 className="font-display text-xl">{customerLabel(order)}</h1>
        <p className="text-sm text-muted">{vehicleLabel(order)}</p>
        <p className="mt-1 text-xs text-muted">
          {order.id} · {formatStatus(order.status)}
          {order.current_tech_name ? ` · ${order.current_tech_name}` : ""}
        </p>
      </div>

      {order.vin || order.plate || order.phone ? (
        <div className="rounded-xl border border-border bg-surface px-4 py-3 text-sm">
          {order.vin ? <p>VIN {order.vin}</p> : null}
          {order.plate ? <p>Plate {order.plate}</p> : null}
          {order.phone ? <p>{order.phone}</p> : null}
        </div>
      ) : null}

      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Work</h2>
        {(order.work_items || []).length === 0 ? (
          <p className="text-sm text-muted">{order.complaint || "No work items yet."}</p>
        ) : (
          <ul className="space-y-2">
            {(order.work_items || []).map((w) => (
              <li key={w.id} className="rounded-xl border border-border bg-surface px-4 py-3">
                <p className="text-sm font-medium">{w.concern || "Work item"}</p>
                <p className="text-xs text-muted">{formatStatus(w.status)}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Notes</h2>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} />
        <Button disabled={busy} onClick={() => void saveNotes()}>
          Save notes
        </Button>
      </div>

      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          Photos{(order.photos || []).length ? ` · ${(order.photos || []).length}` : ""}
        </h2>
        <div className="flex gap-2">
          {PHOTO_TAGS.map((t) => (
            <button
              key={t}
              type="button"
              className={cn(
                "rounded-full border px-3 py-1 text-xs capitalize",
                photoTag === t
                  ? "border-accent bg-accent/15 font-semibold text-accent"
                  : "border-border bg-surface text-muted",
              )}
              onClick={() => setPhotoTag(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" disabled={busy} onClick={() => setCameraOpen(true)}>
            <Camera size={16} />
            Camera
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => libraryRef.current?.click()}
          >
            <Images size={16} />
            Library
          </Button>
        </div>
        <input
          ref={libraryRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => void uploadFiles(Array.from(e.target.files || []))}
        />
        {(order.photos || []).length === 0 ? (
          <p className="text-sm text-muted">No photos yet. Camera asks for access the first time.</p>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {(order.photos || []).map((p) => (
              <a
                key={p.id || p.relpath}
                href={photoUrl(order.id, p)}
                target="_blank"
                rel="noreferrer"
                className="block overflow-hidden rounded-lg border border-border"
              >
                <img
                  src={photoUrl(order.id, p)}
                  alt={p.filename || "photo"}
                  className="aspect-square w-full object-cover"
                />
              </a>
            ))}
          </div>
        )}
      </div>

      {cameraOpen ? (
        <CameraSheet
          onClose={() => setCameraOpen(false)}
          onCapture={(file) => {
            setCameraOpen(false);
            void uploadFiles([file]);
          }}
        />
      ) : null}

      {msg ? <p className="text-sm text-muted">{msg}</p> : null}
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </div>
  );
}
