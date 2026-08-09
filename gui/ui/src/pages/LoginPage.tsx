import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ClipboardEvent } from "react";
import { Cable, Moon, Sun } from "lucide-react";
import { api, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const PIN_LEN = 4;

export function LoginPage({
  onAuthed,
  onOpenScanner,
}: {
  onAuthed: (name: string) => void;
  onOpenScanner: () => void;
}) {
  const { theme, toggle } = useTheme();
  const [techs, setTechs] = useState<Technician[]>([]);
  const [techId, setTechId] = useState("");
  const [digits, setDigits] = useState<string[]>(() => Array(PIN_LEN).fill(""));
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);
  const pin = digits.join("");

  useEffect(() => {
    api
      .listTechs()
      .then((r) => {
        setTechs(r.technicians);
        if (r.technicians[0]) setTechId(r.technicians[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    inputsRef.current[0]?.focus();
  }, []);

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
        if (next[index]) {
          next[index] = "";
        } else if (index > 0) {
          next[index - 1] = "";
          queueMicrotask(() => focusAt(index - 1));
        }
        return next;
      });
      return;
    }
    if (e.key === "ArrowLeft" && index > 0) {
      e.preventDefault();
      focusAt(index - 1);
    }
    if (e.key === "ArrowRight" && index < PIN_LEN - 1) {
      e.preventDefault();
      focusAt(index + 1);
    }
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    const raw = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, PIN_LEN);
    if (!raw) return;
    const next = Array(PIN_LEN).fill("");
    for (let i = 0; i < raw.length; i++) next[i] = raw[i];
    setDigits(next);
    focusAt(Math.min(raw.length, PIN_LEN - 1));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pin.length !== PIN_LEN) return;
    setLoading(true);
    setError("");
    try {
      const r = await api.login(techId, pin);
      onAuthed(r.technician.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setDigits(Array(PIN_LEN).fill(""));
      queueMicrotask(() => focusAt(0));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-4"
        onClick={toggle}
        aria-label="Toggle theme"
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </Button>
      <div className="w-full max-w-md animate-[fadeIn_0.35s_ease] space-y-4">
        <form
          onSubmit={submit}
          className="rounded-2xl border border-border bg-surface p-8 shadow-sm"
        >
          <p className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Car-RO
          </p>
          <p className="mt-2 text-sm text-muted">
            Pick your name and enter your 4-digit PIN to stamp repair orders.
          </p>

          <div className="mt-8 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="tech">Technician</Label>
              <select
                id="tech"
                className="flex h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
                value={techId}
                onChange={(e) => setTechId(e.target.value)}
              >
                {techs.length === 0 ? (
                  <option value="">No technicians — set up via CLI first</option>
                ) : (
                  techs.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))
                )}
              </select>
            </div>
            <div className="space-y-2">
              <Label id="pin-label">PIN</Label>
              <div
                className="flex justify-center gap-2"
                role="group"
                aria-labelledby="pin-label"
              >
                {digits.map((digit, i) => (
                  <input
                    key={i}
                    ref={(el) => {
                      inputsRef.current[i] = el;
                    }}
                    type="password"
                    inputMode="numeric"
                    autoComplete={i === 0 ? "one-time-code" : "off"}
                    maxLength={1}
                    aria-label={`PIN digit ${i + 1}`}
                    value={digit}
                    onChange={(e) => setDigitAt(i, e.target.value)}
                    onKeyDown={(e) => onKeyDown(i, e)}
                    onPaste={onPaste}
                    onFocus={(e) => e.target.select()}
                    className={cn(
                      "h-14 w-14 rounded-xl border border-border bg-bg text-center font-mono text-2xl text-fg",
                      "outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/30",
                    )}
                  />
                ))}
              </div>
            </div>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <Button className="w-full" disabled={loading || !techId || pin.length !== PIN_LEN}>
              {loading ? "Checking…" : "Continue"}
            </Button>
          </div>
        </form>

        <div className="rounded-2xl border border-dashed border-border bg-surface/60 p-6">
          <p className="text-sm font-medium">Just need the scan tool?</p>
          <p className="mt-1 text-sm text-muted">
            Open Scanner without a PIN. Orders and tech settings stay locked until you log in.
          </p>
          <Button
            type="button"
            variant="secondary"
            className="mt-4 w-full"
            onClick={onOpenScanner}
          >
            <Cable className="h-4 w-4" />
            Open Scanner
          </Button>
        </div>
      </div>
      <style>{`@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
