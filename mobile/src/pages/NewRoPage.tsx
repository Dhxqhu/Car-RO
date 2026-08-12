import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function NewRoPage() {
  const nav = useNavigate();
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [phone, setPhone] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [complaint, setComplaint] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const o = await api.createRo({
        first_name: first,
        last_name: last,
        phone,
        year,
        make,
        model,
        vin,
        plate,
        complaint,
      });
      nav(`/ro/${o.id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create RO");
      setBusy(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={onSubmit}>
      <h1 className="font-display text-xl">New repair order</h1>
      <Label>Customer</Label>
      <div className="grid grid-cols-2 gap-2">
        <Input value={first} onChange={(e) => setFirst(e.target.value)} placeholder="First" />
        <Input value={last} onChange={(e) => setLast(e.target.value)} placeholder="Last" />
      </div>
      <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" type="tel" />
      <Label>Vehicle</Label>
      <div className="grid grid-cols-3 gap-2">
        <Input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Year" />
        <Input value={make} onChange={(e) => setMake(e.target.value)} placeholder="Make" />
        <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model" />
      </div>
      <Input value={vin} onChange={(e) => setVin(e.target.value)} placeholder="VIN" />
      <Input value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="Plate" />
      <Label>Complaint</Label>
      <Textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} rows={3} />
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <Button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create RO"}
      </Button>
    </form>
  );
}
