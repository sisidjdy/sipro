import React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { P60 } from "@/constants/testIds";

/**
 * RowsForm — baris data & komponen biaya dokumen.
 *
 * Aturan yang dijaga layar ini: konfigurasi boleh MENYEMBUNYIKAN, MENGURUTKAN, dan MENAMAI
 * baris — tidak boleh mengubah nilainya (nilai tetap milik mesin kontrak). Baris tambahan
 * yang diketik sendiri ditandai "manual" dan tercetak dengan tanda bintang di dokumen agar
 * auditor tahu itu bukan hasil hitungan sistem. "Sembunyikan bila 0" hanya menyembunyikan
 * nilai NOL — nilai yang belum diketahui tetap tercetak "belum ditetapkan".
 */
export default function RowsForm({ rows, sections, options, setRows, setSections, setOptions }) {
  const move = (i, dir) => {
    const next = [...rows];
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    setRows(next.map((r, idx) => ({ ...r, order: idx * 10 })));
  };
  const patch = (i, key, val) => setRows(rows.map((r, idx) =>
    (idx === i ? { ...r, [key]: val } : r)));
  const addManual = () => setRows([...rows, {
    code: `MANUAL_${rows.length + 1}`, label: "Baris tambahan", visible: true,
    order: rows.length * 10, hide_if_zero: false, manual: true, amount: 0,
  }]);

  return (
    <div className="space-y-3">
      <label data-testid={P60.hideZeroGlobal} className="flex items-center gap-2 text-[12px]">
        <input type="checkbox" checked={options.hide_zero_rows !== false}
          onChange={(e) => setOptions("hide_zero_rows", e.target.checked)} />
        Sembunyikan otomatis semua baris yang bernilai Rp 0
        <span className="text-muted-foreground">
          (nilai yang belum diketahui tetap tercetak “belum ditetapkan”)
        </span>
      </label>

      <div className="space-y-1.5">
        <p className="text-[12px] font-medium">Bagian dokumen (urutan = urutan cetak)</p>
        <div className="space-y-1">
          {[...sections].sort((a, b) => (a.order || 0) - (b.order || 0)).map((s, i, arr) => {
            const moveSec = (dir) => {
              const j = i + dir;
              if (j < 0 || j >= arr.length) return;
              const next = [...arr];
              [next[i], next[j]] = [next[j], next[i]];
              setSections(next.map((x, idx) => ({ ...x, order: idx * 10 })));
            };
            return (
              <div key={s.key} data-testid={P60.sectionItem} data-key={s.key}
                data-visible={s.visible !== false ? "true" : "false"}
                className="flex items-center gap-2 rounded-lg border bg-secondary/40 px-2.5 py-1 text-[12px]">
                <input type="checkbox" checked={s.visible !== false}
                  aria-label={`Tampilkan bagian ${s.label}`}
                  onChange={(e) => setSections(sections.map((x) =>
                    (x.key === s.key ? { ...x, visible: e.target.checked } : x)))} />
                <span className="flex-1">{s.label}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{s.key}</span>
                <Button size="icon" variant="ghost" data-testid={`${P60.sectionItem}-up`}
                  aria-label={`Naikkan bagian ${s.label}`} onClick={() => moveSec(-1)}>
                  <ArrowUp className="h-3.5 w-3.5" />
                </Button>
                <Button size="icon" variant="ghost" data-testid={`${P60.sectionItem}-down`}
                  aria-label={`Turunkan bagian ${s.label}`} onClick={() => moveSec(1)}>
                  <ArrowDown className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Bagian <strong>Tabel rincian biaya</strong> mencetak baris di bawah ini pada posisi urutannya.
          Untuk menaruh tabel di tengah naskah, tulis baris <code>{"{{tabel_biaya}}"}</code> di naskah.
        </p>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-medium">Komponen biaya (urutan = urutan cetak)</p>
          <Button size="sm" variant="outline" data-testid={P60.rowAddManual} onClick={addManual}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Baris manual
          </Button>
        </div>
        {rows.map((r, i) => (
          <div key={r.code} data-testid={P60.rowItem} data-code={r.code}
            data-visible={r.visible !== false ? "true" : "false"}
            className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-2 py-1.5 shadow-[var(--shadow-card)]">
            <input type="checkbox" data-testid={P60.rowVisible} checked={r.visible !== false}
              aria-label={`Tampilkan ${r.label}`}
              onChange={(e) => patch(i, "visible", e.target.checked)} />
            <Input data-testid={P60.rowLabel} className="h-8 w-[220px] bg-background"
              aria-label={`Teks baris ${r.code}`}
              value={r.label} onChange={(e) => patch(i, "label", e.target.value)} />
            <span className="w-[110px] font-mono text-[10px] text-muted-foreground">
              {r.code}
            </span>
            {r.manual ? (
              <RupiahInput data-testid={P60.rowAmount} className="h-8 w-[140px] bg-background"
                value={r.amount ?? 0} placeholder="Nominal"
                onChange={(e) => patch(i, "amount", Number(e.target.value))} />
            ) : (
              <label className="flex items-center gap-1 text-[11px]">
                <input type="checkbox" data-testid={P60.rowHideZero}
                  checked={r.hide_if_zero !== false}
                  onChange={(e) => patch(i, "hide_if_zero", e.target.checked)} />
                sembunyikan bila 0
              </label>
            )}
            <div className="ml-auto flex gap-1">
              <Button size="icon" variant="ghost" data-testid={P60.rowUp}
                aria-label={`Naikkan ${r.label}`} onClick={() => move(i, -1)}>
                <ArrowUp className="h-3.5 w-3.5" />
              </Button>
              <Button size="icon" variant="ghost" data-testid={P60.rowDown}
                aria-label={`Turunkan ${r.label}`} onClick={() => move(i, 1)}>
                <ArrowDown className="h-3.5 w-3.5" />
              </Button>
              {r.manual ? (
                <Button size="icon" variant="ghost" aria-label={`Hapus ${r.label}`}
                  onClick={() => setRows(rows.filter((_x, idx) => idx !== i))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              ) : null}
            </div>
          </div>
        ))}
        <Label className="text-[11px] text-muted-foreground">
          Nilai baris non-manual selalu diambil dari kontrak — layar ini hanya mengatur
          tampilannya.
        </Label>
      </div>
    </div>
  );
}
