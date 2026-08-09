import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SettingsPage() {
  const [shop, setShop] = useState("");
  const [serverUrl, setServerUrl] = useState("");
  const [token, setToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .getConfig()
      .then((c) => {
        setShop(c.shop_name);
        setServerUrl(c.server_url);
        setTokenSet(c.token_set);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  async function save() {
    setErr("");
    setMsg("");
    try {
      const body: Record<string, string> = {
        shop_name: shop,
        server_url: serverUrl,
      };
      if (token.trim()) body.token = token.trim();
      await api.setConfig(body);
      setMsg("Saved");
      setToken("");
      setTokenSet(Boolean(token.trim()) || tokenSet);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Same config as the CLI (`~/.config/carro/config.toml`).
        </p>
      </div>
      <div className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        <div className="space-y-2">
          <Label>Shop name</Label>
          <Input value={shop} onChange={(e) => setShop(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Server URL</Label>
          <Input
            placeholder="http://homebaseserver:8787"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>API token {tokenSet ? "(set — leave blank to keep)" : ""}</Label>
          <Input
            type="password"
            placeholder={tokenSet ? "••••••••" : "Paste token"}
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </div>
        {msg ? <p className="text-sm text-accent">{msg}</p> : null}
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        <Button onClick={() => void save()}>Save settings</Button>
      </div>
    </div>
  );
}
