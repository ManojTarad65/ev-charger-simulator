"use client";
import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function CreateChargerDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState({
    charger_id: "SIM001",
    vendor: "Trodec",
    model: "AC_7KW",
    serial_number: "SIM123456",
    firmware_version: "1.0.0",
    number_of_connectors: 1,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.createCharger(form);
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Create Charger">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Charger ID" value={form.charger_id} onChange={(v) => setForm({ ...form, charger_id: v })} />
        <Field label="Vendor" value={form.vendor} onChange={(v) => setForm({ ...form, vendor: v })} />
        <Field label="Model" value={form.model} onChange={(v) => setForm({ ...form, model: v })} />
        <Field label="Serial Number" value={form.serial_number} onChange={(v) => setForm({ ...form, serial_number: v })} />
        <Field label="Firmware" value={form.firmware_version} onChange={(v) => setForm({ ...form, firmware_version: v })} />
        <Field
          label="Connectors"
          type="number"
          value={String(form.number_of_connectors)}
          onChange={(v) => setForm({ ...form, number_of_connectors: Math.max(1, Number(v) || 1) })}
        />
      </div>
      {error && <div className="mt-3 text-sm text-destructive">{error}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={busy}>
          {busy ? "Creating..." : "Create"}
        </Button>
      </div>
    </Dialog>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <Input value={value} type={type} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
