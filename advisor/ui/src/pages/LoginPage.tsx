import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Moon, Sun } from "lucide-react";
import { api, type Advisor } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import carroWordmark from "@/assets/carro-wordmark.png";
import carroWordmarkOnDark from "@/assets/carro-wordmark-on-dark.png";

const PIN_LEN = 4;

export function LoginPage({ onAuthed }: { onAuthed: (name: string, id?: string) => void }) {
  const { theme, toggle } = useTheme();
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [advisorId, setAdvisorId] = useState("");
  const [digits, setDigits] = useState<string[]>(() => Array(PIN_LEN).fill(""));
  const [hasAdminPin, setHasAdminPin] = useState(true);
  const [empty, setEmpty] = useState(false);
  const [bootName, setBootName] = useState("");
  const [bootPin, setBootPin] = useState("");
  const [adminPin, setAdminPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);
  const pin = digits.join("");

  async function refreshRoster() {
    const r = await api.listAdvisors();
    setAdvisors(r.advisors || []);
    setHasAdminPin(!!r.has_admin_pin);
    setEmpty(!!r.empty || !(r.advisors || []).length);
    if (r.advisors?.[0]) setAdvisorId(r.advisors[0].id);
  }

  useEffect(() => {
    refreshRoster().catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!empty) inputsRef.current[0]?.focus();
  }, [empty, advisors]);

  function focusAt(i: number) {
    const el = inputsRef.current[Math.max(0, Math.min(PIN_LEN - 1, i))];
    el?.focus();
    el?.select();
  }

  function setDigitAt(index: number, value: string) {
    const d = value.replace(/\D/g, "").slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[index] = d;
      return next;
    });
    if (d && index < PIN_LEN - 1) focusAt(index + 1);
  }

  function onKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace") {
      e.preventDefault();
      setDigits((prev) => {
        const next = [...prev];
        if (next[index]) next[index] = "";
        else if (index > 0) {
          next[index - 1] = "";
          queueMicrotask(() => focusAt(index - 1));
        }
        return next;
      });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await api.advisorLogin(advisorId, pin);
      onAuthed(r.advisor.name, r.advisor.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setDigits(Array(PIN_LEN).fill(""));
      focusAt(0);
    } finally {
      setLoading(false);
    }
  }

  async function onBootstrap(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await api.bootstrapAdvisor({
        name: bootName,
        pin: bootPin,
        admin_pin: adminPin,
        set_admin: !hasAdminPin,
      });
      onAuthed(r.advisor.name, r.advisor.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center px-4">
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="absolute right-4 top-4"
        onClick={() => toggle()}
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </Button>
      <img
        src={theme === "dark" ? carroWordmarkOnDark : carroWordmark}
        alt="Car-RO"
        className="mb-2 h-8 w-auto"
        draggable={false}
      />
      <p className="mb-8 text-sm text-muted">Advisor desk</p>

      {empty ? (
        <form
          onSubmit={(e) => void onBootstrap(e)}
          className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-surface p-6"
        >
          <h1 className="text-lg font-semibold">Set up first advisor</h1>
          <p className="text-xs text-muted">
            {hasAdminPin
              ? "Enter the shop admin PIN, then create the first advisor."
              : "Set the global shop admin PIN, then create the first advisor."}
          </p>
          {!hasAdminPin ? (
            <div className="space-y-2">
              <Label>New admin PIN (4 digits)</Label>
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                value={adminPin}
                onChange={(e) => setAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
                required
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Admin PIN</Label>
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                value={adminPin}
                onChange={(e) => setAdminPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
                required
              />
            </div>
          )}
          <div className="space-y-2">
            <Label>Advisor name</Label>
            <Input value={bootName} onChange={(e) => setBootName(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label>Advisor login PIN</Label>
            <Input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={bootPin}
              onChange={(e) => setBootPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
              required
            />
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Creating…" : "Create advisor"}
          </Button>
        </form>
      ) : (
        <form
          onSubmit={(e) => void onSubmit(e)}
          className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-surface p-6"
        >
          <h1 className="text-lg font-semibold">Advisor login</h1>
          <div className="space-y-2">
            <Label>Advisor</Label>
            <select
              className="flex h-10 w-full rounded-lg border border-border bg-bg px-3 text-sm"
              value={advisorId}
              onChange={(e) => setAdvisorId(e.target.value)}
            >
              {advisors.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>PIN</Label>
            <div className="flex gap-2">
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => {
                    inputsRef.current[i] = el;
                  }}
                  className={cn(
                    "h-12 w-12 rounded-lg border border-border bg-bg text-center text-lg font-semibold",
                  )}
                  inputMode="numeric"
                  maxLength={1}
                  value={d}
                  onChange={(e) => setDigitAt(i, e.target.value)}
                  onKeyDown={(e) => onKeyDown(i, e)}
                />
              ))}
            </div>
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={loading || pin.length < PIN_LEN}>
            {loading ? "…" : "Log in"}
          </Button>
        </form>
      )}
    </div>
  );
}
