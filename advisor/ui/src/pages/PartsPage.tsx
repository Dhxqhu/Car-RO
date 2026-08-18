import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type PartsSheetRow, type PartsUsageRow, type PartSupersession } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatShopTime } from "@/lib/utils";

const PART_STATUSES = [
  { value: "", label: "All open stages" },
  { value: "new_request", label: "Needed / requested" },
  { value: "ordered", label: "Ordered" },
  { value: "received", label: "Received" },
  { value: "received_wrong", label: "Received wrong" },
] as const;

type Supplier = { id: string; name: string };

type EditDraft = {
  description: string;
  part_number: string;
  oem_part_number: string;
  supplier: string;
  manufacturer: string;
  brand: string;
  superseded_by: string;
  supersedes: string;
};

function statusLabel(s: string): string {
  const hit = PART_STATUSES.find((p) => p.value === s);
  return hit?.label || s.replace(/_/g, " ");
}

function monthLabel(y: number, m: number): string {
  return `${y}-${String(m).padStart(2, "0")}`;
}

function isNeeded(row: PartsSheetRow): boolean {
  const s = (row.status || "").toLowerCase();
  return s === "new_request" || s === "received_wrong";
}

function rowKey(row: PartsSheetRow): string {
  return `${row.ro_id}-${row.work_item_id}-${row.part_id}`;
}

function draftFromRow(row: PartsSheetRow): EditDraft {
  return {
    description: row.description || "",
    part_number: row.part_number || "",
    oem_part_number: row.oem_part_number || "",
    supplier: row.supplier || "",
    manufacturer: row.manufacturer || row.make || "",
    brand: row.brand || "",
    superseded_by: row.superseded_by || "",
    supersedes: row.supersedes || "",
  };
}

function orderReady(d: EditDraft): boolean {
  return !!(d.part_number.trim() && d.supplier.trim());
}

function PartEditForm({
  draft,
  setDraft,
  suppliers,
  busy,
  onSave,
  onCancel,
  onAddSupplier,
  saveLabel = "Save details",
}: {
  draft: EditDraft;
  setDraft: (d: EditDraft) => void;
  suppliers: Supplier[];
  busy: boolean;
  onSave: () => void;
  onCancel: () => void;
  onAddSupplier: () => void;
  saveLabel?: string;
}) {
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-border/80 bg-bg/40 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label>Description</Label>
          <Input
            className="mt-1"
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
        </div>
        <div>
          <Label>Actual part number</Label>
          <Input
            className="mt-1"
            value={draft.part_number}
            onChange={(e) => setDraft({ ...draft, part_number: e.target.value })}
            placeholder="Ordered / stock PN"
          />
        </div>
        <div>
          <Label>OEM part number</Label>
          <Input
            className="mt-1"
            value={draft.oem_part_number}
            onChange={(e) => setDraft({ ...draft, oem_part_number: e.target.value })}
          />
        </div>
        <div className="sm:col-span-2">
          <Label>Supplier</Label>
          <div className="mt-1 flex flex-wrap gap-2">
            <select
              className="flex h-10 min-w-[12rem] flex-1 rounded-lg border border-border bg-bg px-3 text-sm"
              value={draft.supplier}
              onChange={(e) => setDraft({ ...draft, supplier: e.target.value })}
            >
              <option value="">Choose supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.name}>
                  {s.name}
                </option>
              ))}
              {draft.supplier && !suppliers.some((s) => s.name === draft.supplier) ? (
                <option value={draft.supplier}>{draft.supplier} (not in list)</option>
              ) : null}
            </select>
            <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onAddSupplier}>
              Add supplier
            </Button>
          </div>
        </div>
        <div>
          <Label>Brand / cross</Label>
          <Input
            className="mt-1"
            value={draft.brand}
            onChange={(e) => setDraft({ ...draft, brand: e.target.value })}
          />
        </div>
        <div>
          <Label>Manufacturer</Label>
          <Input
            className="mt-1"
            value={draft.manufacturer}
            onChange={(e) => setDraft({ ...draft, manufacturer: e.target.value })}
          />
        </div>
        <div>
          <Label>Superseded by</Label>
          <Input
            className="mt-1"
            value={draft.superseded_by}
            onChange={(e) => setDraft({ ...draft, superseded_by: e.target.value })}
            placeholder="Current PN if this number is old"
          />
        </div>
        <div>
          <Label>This replaces</Label>
          <Input
            className="mt-1"
            value={draft.supersedes}
            onChange={(e) => setDraft({ ...draft, supersedes: e.target.value })}
            placeholder="Old PN this line replaces"
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={busy || !draft.description.trim()} onClick={onSave}>
          {saveLabel}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function PartRow({
  row,
  busy,
  suppliers,
  editing,
  draft,
  setDraft,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onStatus,
  onAddSupplier,
  orderMode,
}: {
  row: PartsSheetRow;
  busy: boolean;
  suppliers: Supplier[];
  editing: boolean;
  draft: EditDraft | null;
  setDraft: (d: EditDraft) => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onStatus: (row: PartsSheetRow, next: string) => void;
  onAddSupplier: () => void;
  orderMode: boolean;
}) {
  const wrongN = Number(row.wrong_count) || 0;
  return (
    <li className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium">
            {row.description || "—"}{" "}
            <span className="font-mono text-xs text-muted">
              {row.part_id} · {statusLabel(row.status)}
            </span>
            {wrongN > 0 ? (
              <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                Wrong ×{wrongN}
              </span>
            ) : null}
            {row.superseded_by ? (
              <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                Superseded → {row.superseded_by}
              </span>
            ) : row.supersedes ? (
              <span className="ml-2 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-200">
                Replaces {row.supersedes}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-muted">
            {row.part_number ? `Actual ${row.part_number}` : "Actual PN —"}
            {row.oem_part_number ? ` · OEM ${row.oem_part_number}` : ""}
            {row.supplier ? ` · ${row.supplier}` : ""}
            {row.brand ? ` · ${row.brand}` : ""}
            {row.manufacturer || row.make ? ` · ${row.manufacturer || row.make}` : ""}
          </p>
          <p className="mt-1 text-sm text-muted">
            <Link className="text-accent hover:underline" to={`/ro/${row.ro_id}`}>
              {row.ro_id}
            </Link>
            {row.work_item_id ? ` / ${row.work_item_id}` : ""}
            {row.vehicle ? ` · ${row.vehicle}` : ""}
            {row.customer ? ` · ${row.customer}` : ""}
          </p>
          {row.concern ? <p className="mt-1 text-xs text-muted">{row.concern}</p> : null}
          {row.wrong_note ? (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Wrong: {row.wrong_note}</p>
          ) : null}
          <p className="mt-1 text-xs text-muted">
            {row.requested_at ? `asked ${formatShopTime(row.requested_at)}` : ""}
            {row.ordered_at ? ` · ordered ${formatShopTime(row.ordered_at)}` : ""}
            {row.received_at ? ` · received ${formatShopTime(row.received_at)}` : ""}
          </p>
        </div>
        {!editing ? (
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onEdit}>
              Edit
            </Button>
            {isNeeded(row) ? (
              <Button type="button" size="sm" disabled={busy} onClick={() => onStatus(row, "ordered")}>
                Mark ordered
              </Button>
            ) : null}
            {isNeeded(row) || row.status === "ordered" ? (
              <Button type="button" size="sm" disabled={busy} onClick={() => onStatus(row, "received")}>
                Mark received
              </Button>
            ) : null}
            {row.status !== "received_wrong" ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => onStatus(row, "received_wrong")}
              >
                Wrong part
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {editing && draft ? (
        <PartEditForm
          draft={draft}
          setDraft={setDraft}
          suppliers={suppliers}
          busy={busy}
          onSave={onSaveEdit}
          onCancel={onCancelEdit}
          onAddSupplier={onAddSupplier}
          saveLabel={orderMode ? "Save & mark ordered" : "Save details"}
        />
      ) : null}
    </li>
  );
}

function PartSection({
  title,
  empty,
  rows,
  busy,
  suppliers,
  editingKey,
  draft,
  setDraft,
  orderModeKey,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onStatus,
  onAddSupplier,
  accent = true,
}: {
  title: string;
  empty: string;
  rows: PartsSheetRow[];
  busy: boolean;
  suppliers: Supplier[];
  editingKey: string | null;
  draft: EditDraft | null;
  setDraft: (d: EditDraft) => void;
  orderModeKey: string | null;
  onEdit: (row: PartsSheetRow, forOrder: boolean) => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onStatus: (row: PartsSheetRow, next: string) => void;
  onAddSupplier: () => void;
  accent?: boolean;
}) {
  return (
    <section className="space-y-3">
      <h2
        className={`text-xs font-semibold uppercase tracking-wide ${
          accent ? "text-accent" : "text-muted"
        }`}
      >
        {title}
        {rows.length ? ` · ${rows.length}` : ""}
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <PartRow
                key={key}
                row={row}
                busy={busy}
                suppliers={suppliers}
                editing={editingKey === key}
                draft={editingKey === key ? draft : null}
                setDraft={setDraft}
                onEdit={() => onEdit(row, false)}
                onCancelEdit={onCancelEdit}
                onSaveEdit={onSaveEdit}
                onStatus={onStatus}
                onAddSupplier={onAddSupplier}
                orderMode={orderModeKey === key}
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function PartsPage() {
  const now = new Date();
  const [tab, setTab] = useState<"sheet" | "usage">("sheet");
  const [rows, setRows] = useState<PartsSheetRow[]>([]);
  const [usage, setUsage] = useState<PartsUsageRow[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [partNumber, setPartNumber] = useState("");
  const [roId, setRoId] = useState("");
  const [q, setQ] = useState("");
  const [includeReceived, setIncludeReceived] = useState(true);
  const [usageYear, setUsageYear] = useState(now.getFullYear());
  const [usageMonth, setUsageMonth] = useState(now.getMonth() + 1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [orderModeKey, setOrderModeKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [editingRow, setEditingRow] = useState<PartsSheetRow | null>(null);
  const [newSupplierName, setNewSupplierName] = useState("");
  const [supersessions, setSupersessions] = useState<PartSupersession[]>([]);
  const [oldPn, setOldPn] = useState("");
  const [newPn, setNewPn] = useState("");

  const loadSuppliers = useCallback(async () => {
    try {
      const r = await api.listSuppliers();
      setSuppliers(r.suppliers || []);
    } catch {
      setSuppliers([]);
    }
  }, []);

  const loadSupersessions = useCallback(async () => {
    try {
      const r = await api.listPartSupersessions();
      setSupersessions(r.links || []);
    } catch {
      setSupersessions([]);
    }
  }, []);

  const loadSheet = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.listParts({
        status: status || undefined,
        manufacturer: manufacturer || undefined,
        part_number: partNumber || undefined,
        ro_id: roId || undefined,
        q: q || undefined,
        include_received: includeReceived || status === "received",
        source: "auto",
      });
      setRows(r.parts || []);
      setSource(r.source || "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load parts");
    } finally {
      setBusy(false);
    }
  }, [status, manufacturer, partNumber, roId, q, includeReceived]);

  const loadUsage = useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.partsUsage({ year: usageYear, month: usageMonth, limit: 100 });
      setUsage(r.usage || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load usage (shop server required)");
      setUsage([]);
    } finally {
      setBusy(false);
    }
  }, [usageYear, usageMonth]);

  useEffect(() => {
    void loadSuppliers();
    void loadSupersessions();
  }, [loadSuppliers, loadSupersessions]);

  useEffect(() => {
    if (tab === "sheet") void loadSheet();
    else void loadUsage();
  }, [tab, loadSheet, loadUsage]);

  function beginEdit(row: PartsSheetRow, forOrder: boolean) {
    const key = rowKey(row);
    setEditingKey(key);
    setOrderModeKey(forOrder ? key : null);
    setEditingRow(row);
    setDraft(draftFromRow(row));
  }

  function cancelEdit() {
    setEditingKey(null);
    setOrderModeKey(null);
    setEditingRow(null);
    setDraft(null);
  }

  async function saveEdit() {
    if (!editingRow || !draft) return;
    if (!draft.description.trim()) {
      setErr("Description required");
      return;
    }
    const forOrder = orderModeKey === rowKey(editingRow);
    if (forOrder && !orderReady(draft)) {
      setErr("Actual part number and supplier are required to mark ordered");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.patchPart(editingRow.ro_id, editingRow.work_item_id, editingRow.part_id, {
        description: draft.description,
        part_number: draft.part_number,
        oem_part_number: draft.oem_part_number,
        supplier: draft.supplier,
        manufacturer: draft.manufacturer,
        brand: draft.brand,
        superseded_by: draft.superseded_by,
        supersedes: draft.supersedes,
        ...(forOrder ? { status: "ordered" } : {}),
      });
      setMsg(
        forOrder
          ? `${editingRow.part_id} saved and marked ordered`
          : `${editingRow.part_id} details saved`,
      );
      cancelEdit();
      await loadSheet();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function setStatusFor(row: PartsSheetRow, next: string) {
    if (next === "ordered") {
      const d = draftFromRow(row);
      if (!orderReady(d)) {
        beginEdit(row, true);
        setMsg("Fill actual part number and supplier, then Save & mark ordered.");
        return;
      }
    }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      let wrong_note = "";
      if (next === "received_wrong") {
        wrong_note =
          window.prompt("What was wrong with the part?", "Received wrong part") ||
          "Received wrong part";
      }
      await api.patchPart(row.ro_id, row.work_item_id, row.part_id, {
        status: next,
        wrong_note,
      });
      const hint =
        next === "received"
          ? " (work item returns to unassigned when all parts are in)"
          : next === "received_wrong"
            ? " (wrong count +1 · re-ordered)"
            : "";
      setMsg(`${row.part_id} → ${statusLabel(next)}${hint}`);
      await loadSheet();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function addSupplierInline() {
    const name =
      (draft?.supplier && !suppliers.some((s) => s.name === draft.supplier)
        ? ""
        : "") ||
      window.prompt("New supplier name", newSupplierName || "") ||
      "";
    const clean = name.trim();
    if (!clean) return;
    setBusy(true);
    setErr("");
    try {
      const entry = await api.addSupplier(clean);
      await loadSuppliers();
      if (draft) setDraft({ ...draft, supplier: entry.name });
      setMsg(`Supplier added: ${entry.name}`);
      setNewSupplierName("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add supplier");
    } finally {
      setBusy(false);
    }
  }

  async function addSupplierFromManage() {
    const clean = newSupplierName.trim();
    if (!clean) return;
    setBusy(true);
    setErr("");
    try {
      const entry = await api.addSupplier(clean);
      setNewSupplierName("");
      await loadSuppliers();
      setMsg(`Supplier added: ${entry.name}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add supplier");
    } finally {
      setBusy(false);
    }
  }

  async function removeSupplier(id: string, name: string) {
    if (!window.confirm(`Remove supplier “${name}” from the list?`)) return;
    setBusy(true);
    setErr("");
    try {
      await api.deleteSupplier(id);
      await loadSuppliers();
      setMsg(`Removed ${name}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove supplier");
    } finally {
      setBusy(false);
    }
  }

  async function addSupersession() {
    const old_number = oldPn.trim();
    const new_number = newPn.trim();
    if (!old_number || !new_number) return;
    setBusy(true);
    setErr("");
    try {
      await api.addPartSupersession({ old_number, new_number });
      setOldPn("");
      setNewPn("");
      await loadSupersessions();
      setMsg(`${old_number} → ${new_number}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add supersession");
    } finally {
      setBusy(false);
    }
  }

  async function removeSupersession(id: string, label: string) {
    if (!window.confirm(`Remove supersession ${label}?`)) return;
    setBusy(true);
    setErr("");
    try {
      await api.deletePartSupersession(id);
      await loadSupersessions();
      setMsg(`Removed ${label}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove supersession");
    } finally {
      setBusy(false);
    }
  }

  function drillUsage(u: PartsUsageRow) {
    setTab("sheet");
    setPartNumber(u.part_number || "");
    setManufacturer(u.manufacturer || "");
    setIncludeReceived(true);
    setStatus("");
    setMsg(
      `Showing ROs for ${u.description || u.part_number || "part"} (${u.use_count} uses / ${u.ro_count} ROs)`,
    );
  }

  const boards = useMemo(() => {
    const needed: PartsSheetRow[] = [];
    const ordered: PartsSheetRow[] = [];
    const received: PartsSheetRow[] = [];
    for (const row of rows) {
      const s = (row.status || "").toLowerCase();
      if (s === "ordered") ordered.push(row);
      else if (s === "received") received.push(row);
      else needed.push(row);
    }
    return { needed, ordered, received };
  }, [rows]);

  const useBoard = !status;
  const sectionProps = {
    busy,
    suppliers,
    editingKey,
    draft,
    setDraft: (d: EditDraft) => setDraft(d),
    orderModeKey,
    onEdit: beginEdit,
    onCancelEdit: cancelEdit,
    onSaveEdit: () => void saveEdit(),
    onStatus: (row: PartsSheetRow, next: string) => void setStatusFor(row, next),
    onAddSupplier: () => void addSupplierInline(),
  };

  let sheetBody: ReactNode;
  if (!rows.length) {
    sheetBody = <p className="text-sm text-muted">{busy ? "Loading…" : "No matching parts."}</p>;
  } else if (useBoard) {
    sheetBody = (
      <div className="space-y-8">
        <PartSection
          title="Needed / requested"
          empty="No parts waiting to be ordered."
          rows={boards.needed}
          accent
          {...sectionProps}
        />
        <PartSection
          title="Ordered"
          empty="Nothing currently on order."
          rows={boards.ordered}
          {...sectionProps}
        />
        {includeReceived ? (
          <PartSection
            title="Received"
            empty="No recently received parts in this view."
            rows={boards.received}
            accent={false}
            {...sectionProps}
          />
        ) : null}
      </div>
    );
  } else {
    sheetBody = (
      <ul className="space-y-3">
        {rows.map((row) => {
          const key = rowKey(row);
          return (
            <PartRow
              key={key}
              row={row}
              busy={busy}
              suppliers={suppliers}
              editing={editingKey === key}
              draft={editingKey === key ? draft : null}
              setDraft={(d) => setDraft(d)}
              onEdit={() => beginEdit(row, false)}
              onCancelEdit={cancelEdit}
              onSaveEdit={() => void saveEdit()}
              onStatus={(r, next) => void setStatusFor(r, next)}
              onAddSupplier={() => void addSupplierInline()}
              orderMode={orderModeKey === key}
            />
          );
        })}
      </ul>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">Parts</h1>
        <p className="mt-1 text-sm text-muted">
          Fill actual PN, OEM PN, and supplier when ordering. Mark superseded numbers so lookup
          fills the current PN. Suppliers stay uniform via the shared list below.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={tab === "sheet" ? "default" : "secondary"}
          onClick={() => setTab("sheet")}
        >
          Order board
        </Button>
        <Button
          type="button"
          size="sm"
          variant={tab === "usage" ? "default" : "secondary"}
          onClick={() => setTab("usage")}
        >
          Monthly usage
        </Button>
      </div>

      {err ? <p className="text-sm text-red-600 dark:text-red-400">{err}</p> : null}
      {msg ? <p className="text-sm text-muted">{msg}</p> : null}

      {tab === "usage" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface p-4">
            <div>
              <Label>Year</Label>
              <Input
                className="mt-1 w-28"
                type="number"
                value={usageYear}
                onChange={(e) => setUsageYear(Number(e.target.value) || now.getFullYear())}
              />
            </div>
            <div>
              <Label>Month</Label>
              <Input
                className="mt-1 w-20"
                type="number"
                min={1}
                max={12}
                value={usageMonth}
                onChange={(e) => setUsageMonth(Number(e.target.value) || 1)}
              />
            </div>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void loadUsage()}>
              Refresh
            </Button>
            <p className="text-xs text-muted">
              {monthLabel(usageYear, usageMonth)} · ranked by how often the part was documented
            </p>
          </div>
          {!usage.length ? (
            <p className="text-sm text-muted">{busy ? "Loading…" : "No parts usage in this month."}</p>
          ) : (
            <ul className="space-y-2">
              {usage.map((u) => (
                <li
                  key={`${u.part_number}|${u.manufacturer}|${u.brand || ""}|${u.description}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3"
                >
                  <div>
                    <div className="font-medium">{u.description || u.part_number || "—"}</div>
                    <p className="text-sm text-muted">
                      {u.brand ? `${u.brand} · ` : ""}
                      {u.manufacturer || "—"}
                      {u.part_number ? ` · PN ${u.part_number}` : ""}
                      {` · ${u.use_count} uses · ${u.ro_count} RO(s)`}
                      {u.last_used_at ? ` · last ${formatShopTime(u.last_used_at)}` : ""}
                    </p>
                  </div>
                  <Button type="button" size="sm" variant="secondary" onClick={() => drillUsage(u)}>
                    Show ROs
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <>
          <section className="space-y-3 rounded-2xl border border-border bg-surface p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Suppliers
              {suppliers.length ? ` · ${suppliers.length}` : ""}
            </h2>
            <div className="flex flex-wrap gap-2">
              <Input
                className="max-w-xs"
                value={newSupplierName}
                onChange={(e) => setNewSupplierName(e.target.value)}
                placeholder="New supplier name"
              />
              <Button
                type="button"
                size="sm"
                disabled={busy || !newSupplierName.trim()}
                onClick={() => void addSupplierFromManage()}
              >
                Add
              </Button>
            </div>
            {suppliers.length === 0 ? (
              <p className="text-sm text-muted">No suppliers yet — add NAPA, dealership, etc.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {suppliers.map((s) => (
                  <li
                    key={s.id}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-2.5 py-1 text-sm"
                  >
                    {s.name}
                    <button
                      type="button"
                      className="text-xs text-muted hover:text-danger"
                      disabled={busy}
                      onClick={() => void removeSupplier(s.id, s.name)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3 rounded-2xl border border-border bg-surface p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Superseded numbers
              {supersessions.length ? ` · ${supersessions.length}` : ""}
            </h2>
            <p className="text-xs text-muted">
              Old PN → current PN. Searching an old number on an RO fills the replacement.
            </p>
            <div className="flex flex-wrap gap-2">
              <Input
                className="max-w-[10rem]"
                value={oldPn}
                onChange={(e) => setOldPn(e.target.value)}
                placeholder="Old PN"
              />
              <Input
                className="max-w-[10rem]"
                value={newPn}
                onChange={(e) => setNewPn(e.target.value)}
                placeholder="Current PN"
              />
              <Button
                type="button"
                size="sm"
                disabled={busy || !oldPn.trim() || !newPn.trim()}
                onClick={() => void addSupersession()}
              >
                Link
              </Button>
            </div>
            {supersessions.length === 0 ? (
              <p className="text-sm text-muted">No supersessions yet — e.g. 5W30-OLD → 5W30-NEW.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {supersessions.map((s) => (
                  <li
                    key={s.id}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-2.5 py-1 font-mono text-sm"
                  >
                    {s.old_number} → {s.new_number}
                    <button
                      type="button"
                      className="text-xs text-muted hover:text-danger"
                      disabled={busy}
                      onClick={() => void removeSupersession(s.id, `${s.old_number} → ${s.new_number}`)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="grid gap-3 rounded-2xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <Label>Status filter</Label>
              <select
                className="mt-1 flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                {PART_STATUSES.map((s) => (
                  <option key={s.label} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Manufacturer contains</Label>
              <Input
                className="mt-1"
                value={manufacturer}
                onChange={(e) => setManufacturer(e.target.value)}
                placeholder="Ford"
              />
            </div>
            <div>
              <Label>Part number contains</Label>
              <Input
                className="mt-1"
                value={partNumber}
                onChange={(e) => setPartNumber(e.target.value)}
              />
            </div>
            <div>
              <Label>RO id</Label>
              <Input className="mt-1" value={roId} onChange={(e) => setRoId(e.target.value)} />
            </div>
            <div>
              <Label>Search (description / PN / OEM / supplier)</Label>
              <Input
                className="mt-1"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="oil filter"
              />
            </div>
            <div className="flex items-end gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeReceived}
                  onChange={(e) => setIncludeReceived(e.target.checked)}
                />
                Show received
              </label>
              <Button type="button" variant="secondary" disabled={busy} onClick={() => void loadSheet()}>
                Refresh
              </Button>
            </div>
            {source ? (
              <p className="text-xs text-muted sm:col-span-2 lg:col-span-3">Source: {source}</p>
            ) : null}
          </section>

          {sheetBody}
        </>
      )}
    </div>
  );
}
