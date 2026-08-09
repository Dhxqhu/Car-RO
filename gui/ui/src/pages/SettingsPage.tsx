import { useEffect, useState, type ReactNode } from "react";
import { api, type ConfigSnapshot } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
  photos_dir: "",
  photos_inbox_dir: "",
  photos_provider: "local",
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
  const [photosDir, setPhotosDir] = useState("");
  const [inboxDir, setInboxDir] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [generatedToken, setGeneratedToken] = useState("");

  function applySnapshot(c: ConfigSnapshot) {
    setCfg(c);
    setShop(c.shop_name);
    setServerUrl(c.server_url);
    setTextualTheme(c.textual_theme || "ansi-dark");
    setLogoPath(c.logo_path);
    setPhotosDir(c.photos_dir);
    setInboxDir(c.photos_inbox_dir);
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

  useEffect(() => {
    api
      .getConfig()
      .then(applySnapshot)
      .catch((e: Error) => setErr(e.message));
  }, []);

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
      const body: Record<string, unknown> = {
        shop_name: shop,
        server_url: serverUrl,
        textual_theme: textualTheme,
        logo_path: logoPath,
        local_keep: keepValue(localKeep, localKeepCustom),
        local_photo_keep: keepValue(photoKeep, photoKeepCustom),
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
            placeholder="http://homebaseserver:8787"
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
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">
          Local cache keep
        </h2>
        <p className="text-sm text-muted">
          How many recent ROs (and photo files) stay on this machine. Older ones prune on sync;
          the server still has them when configured.
        </p>
        <Field label={`Local RO keep — now ${cfg.local_keep_display || "…"}`}>
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
        <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Photos paths</h2>
        <Field label="Photos directory">
          <Input value={photosDir} onChange={(e) => setPhotosDir(e.target.value)} />
        </Field>
        <Field label="Inbox directory">
          <Input value={inboxDir} onChange={(e) => setInboxDir(e.target.value)} />
        </Field>
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
