import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Moon, Sun } from "lucide-react";
import { api, setStoredToken, type Person } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const PIN_LEN = 4;

export function LoginPage({
  onAuthed,
}: {
  onAuthed: (name: string, id: string, role: string) => void;
}) {
  const { theme, toggle } = useTheme();
  const [people, setPeople] = useState<Person[]>([]);
  const [personId, setPersonId] = useState("");
  const [digits, setDigits] = useState<string[]>(() => Array(PIN_LEN).fill(""));
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);
  const pin = digits.join("");

  useEffect(() => {
    api
      .people()
      .then((r) => {
        setPeople(r.people || []);
        setEmpty(!!r.empty || !(r.people || []).length);
        if (r.people?.[0]) setPersonId(r.people[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!empty) inputsRef.current[0]?.focus();
  }, [empty, people]);

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
      const s = await api.login(personId, pin);
      if (s.token) setStoredToken(s.token);
      onAuthed(s.name || "", s.id || personId, s.kind || s.role || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setDigits(Array(PIN_LEN).fill(""));
      focusAt(0);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col overflow-x-hidden px-5 pb-8 pt-[max(2.5rem,env(safe-area-inset-top))]">
      <div className="flex items-center justify-between">
        <p className="font-display text-2xl font-medium tracking-tight">Car-RO</p>
        <Button variant="ghost" size="icon" type="button" onClick={toggle} aria-label="Theme">
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </Button>
      </div>
      <p className="mt-1 text-sm text-muted">Shop phone — lighter than the bay PC.</p>

      {empty ? (
        <p className="mt-10 rounded-xl border border-border bg-surface p-4 text-sm text-muted">
          No staff on the shop server yet. Sync a bay PC first, then come back.
        </p>
      ) : (
        <form className="mt-8 flex flex-1 flex-col gap-5" onSubmit={onSubmit}>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Who</p>
            <div className="grid gap-2">
              {people.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPersonId(p.id)}
                  className={cn(
                    "flex items-center justify-between rounded-xl border px-4 py-3 text-left",
                    personId === p.id
                      ? "border-accent bg-accent/10"
                      : "border-border bg-surface",
                  )}
                >
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs capitalize text-muted">
                    {p.role === "technician" ? "Tech" : "Advisor"}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">PIN</p>
            <div className="mx-auto grid w-full max-w-[13.5rem] grid-cols-4 gap-2">
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => {
                    inputsRef.current[i] = el;
                  }}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={1}
                  size={1}
                  value={d}
                  onChange={(e) => setDigitAt(i, e.target.value)}
                  onKeyDown={(e) => onKeyDown(i, e)}
                  onFocus={(e) => e.target.select()}
                  className="pin-box rounded-xl border border-border bg-surface font-semibold"
                  aria-label={`PIN digit ${i + 1}`}
                />
              ))}
            </div>
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}

          <Button type="submit" disabled={loading || pin.length !== PIN_LEN || !personId}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      )}
    </div>
  );
}
