import { useEffect, useState } from "react";
import { Bell, BellOff } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { httpsPwaUrl, isStandalone, pushBlockReason, subscribePush, unsubscribePush } from "@/lib/push";

export function NotifyButton() {
  const [subscribed, setSubscribed] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setHint(pushBlockReason());
    api
      .pushVapid()
      .then((r) => setSubscribed(!!r.subscribed))
      .catch(() => undefined);
  }, []);

  async function enable() {
    setBusy(true);
    setError("");
    try {
      const blocked = pushBlockReason();
      if (blocked) {
        setHint(blocked);
        setError(blocked);
        return;
      }
      const cfg = await api.pushVapid();
      const sub = await subscribePush(cfg.public_key);
      await api.pushSubscribe(sub);
      setSubscribed(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not enable notifications");
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setError("");
    try {
      const endpoint = await unsubscribePush();
      await api.pushUnsubscribe(endpoint);
      setSubscribed(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            {subscribed ? "Notifications on" : "Notifications"}
          </p>
          <p className="text-xs text-muted">
            {subscribed
              ? "Jobs, messages, and shop updates will alert this phone"
              : isStandalone()
                ? "Get a ping for your jobs and messages"
                : "Works after Add to Home Screen"}
          </p>
        </div>
        {subscribed ? (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void disable()}>
            <BellOff size={14} />
            Off
          </Button>
        ) : (
          <Button size="sm" disabled={busy} onClick={() => void enable()}>
            <Bell size={14} />
            Enable
          </Button>
        )}
      </div>
      {hint && !subscribed ? <p className="mt-2 text-xs text-muted">{hint}</p> : null}
      {!subscribed && httpsPwaUrl() ? (
        <a className="mt-2 block text-xs font-medium text-accent underline-offset-2 hover:underline" href={httpsPwaUrl()!}>
          Open HTTPS app
        </a>
      ) : null}
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  );
}
