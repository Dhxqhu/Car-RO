import { useEffect, useState, type ReactNode } from "react";
import { api, type ConfigSnapshot } from "@/lib/api";
import {
  DEFAULT_NOTIFY_PREFS,
  loadNotifyPrefs,
  saveNotifyPrefs,
  type NotifyPrefs,
} from "@/lib/notifyPrefs";
import { playNotifyChime, unlockNotifySound } from "@/lib/notifySound";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const emptyCfg = (): ConfigSnapshot => ({
  config_file: "",
  shop_name: "",
  server_url: "",
  token_set: false,
  theme: "",
  textual_theme: "ansi-dark",
  logo_path: "",
  logo_status: "",
  local_keep: "auto",
  local_keep_resolved: 0,
  local_keep_display: "",
  local_photo_keep: "auto",
  local_photo_keep_resolved: 0,
  local_photo_keep_display: "",
  local_billed_keep: 20,
  local_parts_received_keep_hours: 24,
  idle_nudge_hours: 24,
  photos_dir: "",
  photos_inbox_dir: "",
  photos_provider: "local",
  autosync_minutes: 15,
  pa_inspection_types: true,
  disk: { path: "", free_gb: 0, total_gb: 0 },
  recommend: { local_keep: 0, local_photo_keep: 0 },
  keep_presets: [],
  photo_keep_presets: [],
});

export function SettingsPage() {
  const [cfg, setCfg] = useState<ConfigSnapshot>(emptyCfg());
  const [shop, setShop] = useState("");
  const [serverUrl, setServerUrl] = useState("");
  const [token, setToken] = useState("");
  const [textualTheme, setTextualTheme] = useState("ansi-dark");
  const [logoPath, setLogoPath] = useState("");
  const [localKeep, setLocalKeep] = useState<string>("auto");
  const [localKeepCustom, setLocalKeepCustom] = useState("");
  const [photoKeep, setPhotoKeep] = useState<string>("auto");
  const [photoKeepCustom, setPhotoKeepCustom] = useState("");
  const [billedKeep, setBilledKeep] = useState("20");
  const [partsKeepHours, setPartsKeepHours] = useState("24");
  const [idleNudgeHours, setIdleNudgeHours] = useState("24");
  const [photosDir, setPhotosDir] = useState("");
  const [inboxDir, setInboxDir] = useState("");
  const [autosyncMinutes, setAutosyncMinutes] = useState("15");
  const [paInspectionTypes, setPaInspectionTypes] = useState(true);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [generatedToken, setGeneratedToken] = useState("");
  const [notify, setNotify] = useState<NotifyPrefs>(() => loadNotifyPrefs());
  const [bugTitle, setBugTitle] = useState("");
  const [bugDescription, setBugDescription] = useState("");
  const [bugSteps, setBugSteps] = useState("");
  const [bugSeverity, setBugSeverity] = useState("medium");
  const [bugBusy, setBugBusy] = useState(false);
  const [recentBugs, setRecentBugs] = useState<
    Array<{
      id: string;
      title: string;
      severity: string;
      created_at: string;
      synced?: boolean;
      sync_error?: string;
    }>
  >([]);

  function setNotifyPref<K extends keyof NotifyPrefs>(key: K, value: NotifyPrefs[K]) {
    unlockNotifySound();
    const next = saveNotifyPrefs({ [key]: value });
    setNotify(next);
    if (key === "sound" && value) playNotifyChime("message", { force: true });
  }

  function applySnapshot(c: ConfigSnapshot) {
    setCfg(c);
    setShop(c.shop_name);
    setServerUrl(c.server_url);
    setTextualTheme(c.textual_theme || "ansi-dark");
    setLogoPath(c.logo_path);
    setPhotosDir(c.photos_dir);
    setInboxDir(c.photos_inbox_dir);
    setAutosyncMinutes(String(c.autosync_minutes ?? 0));
    setPaInspectionTypes(c.pa_inspection_types !== false);
    setBilledKeep(String(c.local_billed_keep ?? 20));
    setPartsKeepHours(String(c.local_parts_received_keep_hours ?? 24));
    setIdleNudgeHours(String(c.idle_nudge_hours ?? 24));
    const lk = String(c.local_keep);
    const presetVals = new Set(
      c.keep_presets.map((p) => String(p.value)).filter((v) => v !== "custom"),
    );
    if (presetVals.has(lk) || lk === "auto") {
      setLocalKeep(lk);
      setLocalKeepCustom("");
    } else {
      setLocalKeep("custom");
      setLocalKeepCustom(lk);
    }
    const pk = String(c.local_photo_keep);
    const photoPresetVals = new Set(
      c.photo_keep_presets.map((p) => String(p.value)).filter((v) => v !== "custom"),
    );
    if (photoPresetVals.has(pk) || pk === "auto" || pk === "match") {
      setPhotoKeep(pk);
      setPhotoKeepCustom("");
    } else {
      setPhotoKeep("custom");
      setPhotoKeepCustom(pk);
    }
  }

  async function refreshBugReports() {
    try {
      const r = await api.listBugReports(20);
      setRecentBugs(r.reports || []);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    api
      .getConfig()
      .then(applySnapshot)
      .catch((e: Error) => setErr(e.message));
    void refreshBugReports();
  }, []);

  async function submitBug() {
    setBugBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.submitBugReport({
        title: bugTitle,
        description: bugDescription,
        steps: bugSteps,
        severity: bugSeverity,
        client: "tech",
      });
      const sync = r.report.sync_status || (r.report.synced ? "synced" : "skipped");
      setMsg(
        sync === "synced"
          ? `Bug report saved and synced to shop (${r.report.id}).`
          : sync.startsWith("error:")
            ? `Bug report saved locally (${r.report.id}). Shop sync failed.`
            : `Bug report saved locally (${r.report.id}). Shop server not configured.`,
      );
      setBugTitle("");
      setBugDescription("");
      setBugSteps("");
      setBugSeverity("medium");
      await refreshBugReports();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not submit bug report");
    } finally {
      setBugBusy(false);
    }
  }

  function keepValue(mode: string, custom: string): string | number {
    if (mode === "custom") {
      const n = parseInt(custom, 10);
      if (Number.isNaN(n)) throw new Error("Custom keep must be a number");
      return n;
    }
    return mode;
  }

  async function save() {
    setErr("");
    setMsg("");
    setGeneratedToken("");
    try {
      const mins = parseInt(autosyncMinutes, 10);
      if (Number.isNaN(mins) || mins < 0) {
        throw new Error("Autosync minutes must be 0 (off) or a positive number");
      }
      const billed = parseInt(billedKeep, 10);
      if (Number.isNaN(billed) || billed < 0) {
        throw new Error("Billed-out keep must be 0 or a positive number");
      }
      const partsHours = parseFloat(partsKeepHours);
      if (Number.isNaN(partsHours) || partsHours < 0) {
        throw new Error("Received parts keep hours must be 0 or positive");
      }
      const idleHours = parseFloat(idleNudgeHours);
      if (Number.isNaN(idleHours) || idleHours < 0) {
        throw new Error("Idle nudge hours must be 0 (off) or positive");
      }
      const body: Record<string, unknown> = {
        shop_name: shop,
        server_url: serverUrl,
        textual_theme: textualTheme,
        logo_path: logoPath,
        local_keep: keepValue(localKeep, localKeepCustom),
        local_photo_keep: keepValue(photoKeep, photoKeepCustom),
        local_billed_keep: billed,
        local_parts_received_keep_hours: partsHours,
        idle_nudge_hours: idleHours,
        autosync_minutes: mins,
        pa_inspection_types: paInspectionTypes,
        photos_dir: photosDir,
        photos_inbox_dir: inboxDir,
      };
      if (token.trim()) body.token = token.trim();
      const next = await api.setConfig(body);
      applySnapshot(next);
      setToken("");
      setMsg("Saved — same file the CLI uses.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    }
  }

  async function genToken() {
    setErr("");
    setMsg("");
    try {
      const next = await api.generateToken();
      applySnapshot(next);
      setGeneratedToken(next.token);
      setMsg("Generated and saved a new API token.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Token generate failed");
    }
  }

  async function applyDisk() {
    setErr("");
    setMsg("");
    try {
      const next = await api.applyDiskRecommendation();
      applySnapshot(next);
      setMsg(
        `Set local keep + photo keep to auto (→ ${next.local_keep_resolved} ROs / ${next.local_photo_keep_resolved} with photos).`,
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
          Configuration
        </h1>
        <p className="mt-1 text-sm text-muted">
          Same menu as CLI <code className="text-fg">carro config</code>
          {cfg.config_file ? (
            <>
              {" "}
              · <span className="break-all">{cfg.config_file}</span>
            </>
          ) : null}
        </p>
        {cfg.disk.path ? (
          <p className="mt-1 text-xs text-muted">
            Disk {cfg.disk.free_gb} GB free of {cfg.disk.total_gb} GB on {cfg.disk.path}
          </p>
        ) : null}
      </div>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Shop & server</h2>
        <Field label="Shop name">
          <Input value={shop} onChange={(e) => setShop(e.target.value)} />
        </Field>
        <Field label="Server URL (empty = local only)">
          <Input
            placeholder="http://shop-server:8787"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
          />
        </Field>
        <Field
          label={
            cfg.token_set
              ? "API token (set — leave blank to keep)"
              : "API token"
          }
        >
          <Input
            type="password"
            placeholder={cfg.token_set ? "••••••••" : "Paste token"}
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" onClick={() => void genToken()}>
            Generate new token
          </Button>
        </div>
        {generatedToken ? (
          <p className="break-all rounded-lg bg-border/30 p-3 font-mono text-xs">{generatedToken}</p>
        ) : null}
        <Field label="Shop logo path (PDF)">
          <Input
            placeholder="/path/to/logo.png"
            value={logoPath}
            onChange={(e) => setLogoPath(e.target.value)}
          />
          {cfg.logo_status ? (
            <p className="mt-1 text-xs text-muted">{cfg.logo_status}</p>
          ) : null}
        </Field>
        <Field label="Textual theme (CLI forms)">
          <Input
            placeholder="ansi-dark"
            value={textualTheme}
            onChange={(e) => setTextualTheme(e.target.value)}
          />
        </Field>
        <Field label="Autosync interval (minutes, 0 = off)">
          <Input
            type="number"
            min={0}
            step={1}
            placeholder="15"
            value={autosyncMinutes}
            onChange={(e) => setAutosyncMinutes(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">
            While the engine is open, push dirty local ROs to the shop server on this timer
            (default 15). Skips work when nothing is pending; backs off if the server is
            unreachable. 0 turns the timer off — pending edits still retry every few minutes.
          </p>
          {cfg.autosync ? (
            <p className="mt-1 text-xs text-muted">
              Status:{" "}
              {cfg.autosync.enabled
                ? `on · every ${cfg.autosync.interval_minutes} min`
                : "off"}
              {cfg.autosync.last_run_at
                ? ` · last ${cfg.autosync.last_ok === false ? "failed" : "ok"} ${cfg.autosync.last_run_at}`
                : ""}
              {cfg.autosync.last_error ? ` · ${cfg.autosync.last_error}` : ""}
            </p>
          ) : null}
        </Field>
        <Field label="PA inspection types (SI/IM, SI only)">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--accent)]"
              checked={paInspectionTypes}
              onChange={(e) => setPaInspectionTypes(e.target.checked)}
            />
            Show SI/IM and SI only in work-item pickers
          </label>
          <p className="mt-1 text-xs text-muted">
            Pennsylvania safety / emissions inspection names. Leave on for PA shops; turn
            off elsewhere. Existing SI/IM jobs still display normally.
          </p>
        </Field>
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Local cache keep
        </h2>
        <p className="text-sm text-muted">
          Active jobs stay under local RO keep; billed-out jobs have their own limit (default 20).
          Older closed work stays on the shop server — use Orders → Server search or History when a
          repeat customer needs prior context.
        </p>
        <Field label={`Local RO keep (active) — now ${cfg.local_keep_display || "…"}`}>
          <select
            className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
            value={localKeep}
            onChange={(e) => setLocalKeep(e.target.value)}
          >
            {cfg.keep_presets.map((p) => (
              <option key={p.label} value={String(p.value)}>
                {p.label}
                {p.value !== "custom" && p.value !== "auto" ? ` = ${p.value}` : ""} — {p.detail}
              </option>
            ))}
          </select>
          {localKeep === "custom" ? (
            <Input
              className="mt-2"
              type="number"
              min={0}
              placeholder="Number of ROs"
              value={localKeepCustom}
              onChange={(e) => setLocalKeepCustom(e.target.value)}
            />
          ) : null}
        </Field>
        <Field label={`Local billed-out keep — now ${cfg.local_billed_keep ?? 20}`}>
          <Input
            type="number"
            min={0}
            step={1}
            value={billedKeep}
            onChange={(e) => setBilledKeep(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">
            Newest closed ROs kept on this bay after sync. Use server search for older history.
          </p>
        </Field>
        <Field
          label={`Received parts keep (hours) — now ${cfg.local_parts_received_keep_hours ?? 24}`}
        >
          <Input
            type="number"
            min={0}
            step={1}
            value={partsKeepHours}
            onChange={(e) => setPartsKeepHours(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">
            After a part is marked received, keep it on the local RO this long after sync, then strip
            it from the bay cache (server still has the full RO).
          </p>
        </Field>
        <Field label={`Idle nudge (hours) — now ${cfg.idle_nudge_hours ?? 24} (0 = off)`}>
          <Input
            type="number"
            min={0}
            step={1}
            value={idleNudgeHours}
            onChange={(e) => setIdleNudgeHours(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">
            Bell badge when a work item (open / in progress / waiting parts) or part (new request /
            ordered) has had no activity this long. Helps catch forgotten jobs.
          </p>
        </Field>
        <Field label={`Local photo keep — now ${cfg.local_photo_keep_display || "…"}`}>
          <select
            className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
            value={photoKeep}
            onChange={(e) => setPhotoKeep(e.target.value)}
          >
            {cfg.photo_keep_presets.map((p) => (
              <option key={p.label} value={String(p.value)}>
                {p.label}
                {p.value !== "custom" && p.value !== "auto" && p.value !== "match"
                  ? ` = ${p.value}`
                  : ""}{" "}
                — {p.detail}
              </option>
            ))}
          </select>
          {photoKeep === "custom" ? (
            <Input
              className="mt-2"
              type="number"
              min={0}
              placeholder="ROs with local photos"
              value={photoKeepCustom}
              onChange={(e) => setPhotoKeepCustom(e.target.value)}
            />
          ) : null}
        </Field>
        <Button type="button" variant="secondary" onClick={() => void applyDisk()}>
          Apply disk recommendation (auto / auto → {cfg.recommend.local_keep} /{" "}
          {cfg.recommend.local_photo_keep})
        </Button>
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
              Notifications
            </h2>
            <p className="mt-1 text-sm text-muted">
              Everything is <span className="text-fg">on by default</span>. Turn off only what you
              don’t want on this PC. The bell only shows work assigned to you. Idle threshold still
              comes from shop config above.
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            className="shrink-0"
            onClick={() => {
              unlockNotifySound();
              const next = saveNotifyPrefs({ ...DEFAULT_NOTIFY_PREFS });
              setNotify(next);
              setMsg("Notification settings reset — all on.");
            }}
          >
            Reset all on
          </Button>
        </div>
        <NotifyToggle
          label="Notification sound"
          detail="Chime when something new arrives (browser may require a click first)."
          checked={notify.sound}
          onChange={(v) => setNotifyPref("sound", v)}
        />
        <NotifyToggle
          label="Team updates"
          detail="Status changes, assignments, photos, and other RO activity from others."
          checked={notify.teamUpdates}
          onChange={(v) => setNotifyPref("teamUpdates", v)}
        />
        <NotifyToggle
          label="Shop messages"
          detail="Person-to-person messages addressed to you."
          checked={notify.shopMessages}
          onChange={(v) => setNotifyPref("shopMessages", v)}
        />
        <NotifyToggle
          label="Idle nudges"
          detail="Needs attention when work items or parts sit idle past the hours above."
          checked={notify.idleNudges}
          onChange={(v) => setNotifyPref("idleNudges", v)}
        />
        <NotifyToggle
          label="Waiter & urgent"
          detail="When an RO is flagged waiter or urgent."
          checked={notify.waiterUrgent}
          onChange={(v) => setNotifyPref("waiterUrgent", v)}
        />
        <NotifyToggle
          label="Day start / day end"
          detail="Punch clock day start and day end from techs."
          checked={notify.punches}
          onChange={(v) => setNotifyPref("punches", v)}
        />
        <NotifyToggle
          label="Next-day requests"
          detail="Next-day requested, approved, or declined."
          checked={notify.nextDay}
          onChange={(v) => setNotifyPref("nextDay", v)}
        />
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Photos paths</h2>
        <Field label="Photos directory">
          <Input value={photosDir} onChange={(e) => setPhotosDir(e.target.value)} />
        </Field>
        <Field label="Inbox directory">
          <Input value={inboxDir} onChange={(e) => setInboxDir(e.target.value)} />
        </Field>
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Bug report</h2>
          <p className="mt-1 text-sm text-muted">
            Document a problem on this bay. Saved locally and pushed to the shop server when online.
            App version, shop name, and who you are are attached automatically — never the API token.
          </p>
        </div>
        <Field label="Title">
          <Input
            value={bugTitle}
            onChange={(e) => setBugTitle(e.target.value)}
            placeholder="Short summary"
          />
        </Field>
        <Field label="Severity">
          <select
            className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
            value={bugSeverity}
            onChange={(e) => setBugSeverity(e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </Field>
        <Field label="What happened">
          <textarea
            className="min-h-[6rem] w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm"
            value={bugDescription}
            onChange={(e) => setBugDescription(e.target.value)}
            placeholder="What you expected vs what you saw"
          />
        </Field>
        <Field label="Steps to reproduce (optional)">
          <textarea
            className="min-h-[4rem] w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm"
            value={bugSteps}
            onChange={(e) => setBugSteps(e.target.value)}
            placeholder="1. … 2. …"
          />
        </Field>
        <Button
          type="button"
          disabled={bugBusy || !bugTitle.trim() || !bugDescription.trim()}
          onClick={() => void submitBug()}
        >
          {bugBusy ? "Submitting…" : "Submit bug report"}
        </Button>
        {recentBugs.length ? (
          <div className="space-y-2 border-t border-border pt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
              Recent on this bay
            </h3>
            <ul className="space-y-2">
              {recentBugs.map((r) => (
                <li key={r.id} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  <div className="font-medium">
                    {r.title}{" "}
                    <span className="text-xs font-normal uppercase text-muted">{r.severity}</span>
                  </div>
                  <div className="text-xs text-muted">
                    {r.created_at}
                    {r.synced
                      ? " · synced to shop"
                      : r.sync_error
                        ? ` · local only (${r.sync_error})`
                        : " · local only"}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {msg ? <p className="text-sm text-accent">{msg}</p> : null}
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      <Button onClick={() => void save()}>Save configuration</Button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function NotifyToggle({
  label,
  detail,
  checked,
  onChange,
}: {
  label: string;
  detail: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border/60 px-3 py-2.5 hover:bg-border/20">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-[var(--accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="min-w-0">
        <span className={cn("block text-sm font-medium", !checked && "text-muted")}>{label}</span>
        <span className="mt-0.5 block text-xs text-muted">{detail}</span>
      </span>
    </label>
  );
}
