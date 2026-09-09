import React from "react";
import { Label } from "@/components/ui/label";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EXCLUDED = "__excluded__";
const TREATMENTS = {
  developer_borne: "Developer (all-in)", customer_pass_through: "Pembeli (titipan)", [EXCLUDED]: "Tidak termasuk skema",
};

/** Baris = SEMUA komponen aktif dari tabel "Komponen biaya transaksi" (sinkron otomatis). */
export const AllinSchemeItems = ({ items, components, onChange }) => {
  const rows = components.filter((c) => !c.is_legacy && c.is_active !== false);
  const itemOf = (code) => items.find((it) => it.component_code === code);
  const setItem = (comp, change) => {
    const cur = itemOf(comp.code);
    if (change.treatment === EXCLUDED) { onChange(items.filter((it) => it.component_code !== comp.code)); return; }
    if (cur) { onChange(items.map((it) => (it.component_code === comp.code ? { ...it, ...change } : it))); return; }
    onChange([...items, { component_code: comp.code, treatment: comp.default_treatment || "customer_pass_through", override_amount: "", ...change }]);
  };
  const orphan = items.filter((it) => it.component_code && !rows.some((c) => c.code === it.component_code));
  return (
    <div className="min-w-0 space-y-2" data-testid="allin-items-editor">
      <div className="hidden grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 px-1 text-[11px] uppercase tracking-wide text-muted-foreground sm:grid">
        <span>Komponen biaya</span><span>Ditanggung oleh</span><span>Nominal pengganti (opsional)</span>
      </div>
      {rows.map((c, i) => {
        const it = itemOf(c.code);
        return (
          <div key={c.code} data-testid={`allin-item-${i}`} data-code={c.code}
            className="grid min-w-0 grid-cols-1 items-center gap-3 rounded-md border bg-card p-2 sm:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium" data-testid={`allin-component-${i}`}>{c.name}{c.kpr_only ? <span className="ml-1 text-[10px] text-muted-foreground">(KPR)</span> : null}</p>
              <p className="font-mono text-[11px] text-muted-foreground">{c.code}</p>
            </div>
            <div className="min-w-0">
              <Label htmlFor={`allin-treatment-${i}`} className="sr-only">Ditanggung oleh</Label>
              <Select value={it ? it.treatment : EXCLUDED} onValueChange={(v) => setItem(c, { treatment: v })}>
                <SelectTrigger id={`allin-treatment-${i}`} data-testid={`allin-treatment-${i}`}><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(TREATMENTS).map(([k, v]) => <SelectItem key={k} value={k} data-testid={`allin-treatment-option-${i}-${k}`}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="min-w-0">
              <Label htmlFor={`allin-amount-${i}`} className="sr-only">Nominal pengganti</Label>
              <RupiahInput id={`allin-amount-${i}`} data-testid={`allin-amount-${i}`} placeholder="Sesuai rumus" disabled={!it}
                value={it?.override_amount ?? ""} onChange={(e) => setItem(c, { override_amount: e.target.value })} />
            </div>
          </div>
        );
      })}
      {orphan.length ? (
        <p className="text-[11px] text-amber-700" data-testid="allin-orphan-note">
          Komponen nonaktif masih tercantum di skema ini: {orphan.map((o) => o.component_code).join(", ")} (tidak dipakai kontrak baru).
        </p>
      ) : null}
      <p className="text-[11px] text-muted-foreground">
        Daftar komponen mengikuti tabel <b>Komponen biaya transaksi</b> di atas — tambah/nonaktifkan komponen di sana, lalu tentukan siapa yang menanggungnya di sini.
      </p>
    </div>
  );
};
