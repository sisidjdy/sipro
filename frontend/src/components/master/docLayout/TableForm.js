import React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { P60 } from "@/constants/testIds";

const GRID = [
  { value: "full", label: "Kotak penuh (semua garis)" },
  { value: "horizontal", label: "Garis mendatar saja" },
  { value: "none", label: "Tanpa garis (transparan)" },
];

/**
 * TableForm — GAYA TABEL dokumen (Fase 66).
 *
 * Sebelum ini setiap tabel dokumen tercetak dengan kotak penuh, kepala tabel berwarna, dan
 * nama kolom yang selalu tampil — tidak bisa diubah tanpa menyentuh kode. Pemakai yang
 * mencetak di kertas berkop sendiri meminta tabel TRANSPARAN dan tanpa nama kolom; di sini
 * keduanya jadi setelan, dan pratinjau di kanan langsung memperlihatkan hasilnya.
 */
export default function TableForm({ table, setTable }) {
  const t = table || {};
  const row = (id, testId, label, keterangan, checked, onChange) => (
    <div className="flex items-start justify-between gap-3 rounded-lg border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
      <div>
        <Label htmlFor={id} className="text-[12px]">{label}</Label>
        <p className="text-[11px] text-muted-foreground">{keterangan}</p>
      </div>
      <Switch id={id} data-testid={testId} checked={checked} onCheckedChange={onChange} />
    </div>
  );

  return (
    <div className="space-y-2.5">
      <div className="space-y-1.5">
        <Label htmlFor="doc-table-grid">Garis tabel</Label>
        <Select value={t.grid || "full"} onValueChange={(v) => setTable("grid", v)}>
          <SelectTrigger id="doc-table-grid" data-testid={P60.tableGrid} className="bg-background">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GRID.map((g) => (
              <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {row("doc-table-show-header", P60.tableShowHeader, "Tampilkan nama kolom",
        "Matikan bila judul kolom tidak perlu tercetak (mis. kwitansi).",
        t.show_header !== false, (v) => setTable("show_header", v))}
      {row("doc-table-header-fill", P60.tableHeaderFill, "Kepala tabel berwarna aksen",
        "Matikan untuk kepala tabel polos tanpa blok warna.",
        t.header_fill !== false, (v) => setTable("header_fill", v))}
      {row("doc-table-zebra", P60.tableZebra, "Baris belang (zebra)",
        "Latar abu-abu bergantian agar baris panjang mudah diikuti.",
        t.zebra !== false, (v) => setTable("zebra", v))}
      {row("doc-table-total", P60.tableTotal, "Sorot baris total",
        "Baris total diberi latar hijau muda.",
        t.total_highlight !== false, (v) => setTable("total_highlight", v))}

      <div className="grid gap-2 sm:grid-cols-2">
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor="doc-table-width">Lebar tabel (%)</Label>
          <Input id="doc-table-width" data-testid="doc-table-width" type="number" min="40" max="100"
            value={t.width_pct ?? 100} onChange={e => setTable("width_pct", Number(e.target.value))} />
        </div>
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor="doc-table-alignment">Posisi tabel</Label>
          <Select value={t.alignment || "left"} onValueChange={v => setTable("alignment", v)}>
            <SelectTrigger id="doc-table-alignment" data-testid="doc-table-alignment"><SelectValue /></SelectTrigger>
            <SelectContent>{[{ value: "left", label: "Kiri" }, { value: "center", label: "Tengah" }, { value: "right", label: "Kanan" }].map(x => <SelectItem key={x.value} value={x.value} data-testid={`doc-table-alignment-${x.value}`}>{x.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="doc-table-font">Ukuran huruf tabel (pt)</Label>
          <Input id="doc-table-font" data-testid={P60.tableFontSize} type="number"
            step="0.5" min="6" max="12" className="bg-background"
            value={t.font_size ?? 8.5}
            onChange={(e) => setTable("font_size", Number(e.target.value))} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="doc-table-grid-color">Warna garis</Label>
          <Input id="doc-table-grid-color" type="text" className="bg-background font-mono"
            placeholder="#e2e8f0" value={t.grid_color || "#e2e8f0"}
            aria-label="Warna garis tabel (heksadesimal)"
            onChange={(e) => setTable("grid_color", e.target.value)} />
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Gaya ini dipakai SEMUA tabel pada dokumen jenis ini: rincian biaya, rincian item,
        dan laporan tabel.
      </p>
    </div>
  );
}
