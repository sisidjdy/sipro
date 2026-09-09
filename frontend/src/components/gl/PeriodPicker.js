import React from "react";
import { CalendarRange } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { GL } from "@/constants/testIds";

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** Preset periode akuntansi (dihitung di zona waktu perangkat pengguna). */
export function presetRange(key) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  if (key === "this_month") return { date_from: iso(new Date(y, m, 1)), date_to: iso(now) };
  if (key === "last_month") {
    return { date_from: iso(new Date(y, m - 1, 1)), date_to: iso(new Date(y, m, 0)) };
  }
  if (key === "quarter") {
    const qStart = Math.floor(m / 3) * 3;
    return { date_from: iso(new Date(y, qStart, 1)), date_to: iso(now) };
  }
  if (key === "ytd") return { date_from: `${y}-01-01`, date_to: iso(now) };
  if (key === "last_year") return { date_from: `${y - 1}-01-01`, date_to: `${y - 1}-12-31` };
  return { date_from: iso(new Date(y, m, 1)), date_to: iso(now) };
}

const PRESETS = [
  ["this_month", "Bulan ini"],
  ["last_month", "Bulan lalu"],
  ["quarter", "Kuartal ini"],
  ["ytd", "Tahun berjalan"],
  ["last_year", "Tahun lalu"],
];

export default function PeriodPicker({ value, onChange, hint }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <CalendarRange className="h-4 w-4 text-primary" /> Periode
      </div>
      <div className="space-y-1">
        <Label className="text-xs" htmlFor="gl-from">Dari</Label>
        <Input id="gl-from" type="date" data-testid={GL.periodFrom} className="w-[150px]"
          value={value.date_from} onChange={(e) => set("date_from", e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label className="text-xs" htmlFor="gl-to">Sampai</Label>
        <Input id="gl-to" type="date" data-testid={GL.periodTo} className="w-[150px]"
          value={value.date_to} onChange={(e) => set("date_to", e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map(([key, label]) => (
          <Button key={key} type="button" size="sm" variant="outline"
            data-testid={GL.periodPreset} data-preset={key} aria-label={`Periode ${label}`}
            className="h-8 text-xs" onClick={() => onChange(presetRange(key))}>
            {label}
          </Button>
        ))}
      </div>
      {hint ? <p className="ml-auto text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
