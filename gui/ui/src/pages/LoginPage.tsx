import { useEffect, useState, type FormEvent } from "react";
import { api, type Technician } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTheme } from "@/hooks/useTheme";
import { Moon, Sun } from "lucide-react";

export function LoginPage({ onAuthed }: { onAuthed: (name: string) => void }) {
  const { theme, toggle } = useTheme();
  const [techs, setTechs] = useState<Technician[]>([]);
  const [techId, setTechId] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .listTechs()
      .then((r) => {
        setTechs(r.technicians);
        if (r.technicians[0]) setTechId(r.technicians[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const r = await api.login(techId, pin);
      onAuthed(r.technician.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
      <form
        onSubmit={submit}
        className="w-full max-w-md animate-[fadeIn_0.35s_ease] rounded-2xl border border-border bg-surface p-8 shadow-sm"
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
            <Label htmlFor="pin">PIN</Label>
            <Input
              id="pin"
              type="password"
              inputMode="numeric"
              maxLength={4}
              pattern="\d{4}"
              placeholder="••••"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
              autoFocus
            />
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button className="w-full" disabled={loading || !techId || pin.length !== 4}>
            {loading ? "Checking…" : "Continue"}
          </Button>
        </div>
      </form>
      <style>{`@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
