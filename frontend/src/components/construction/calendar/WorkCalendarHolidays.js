import React from "react";
import { Plus, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { longDate } from "@/utils/calendarUi";
import { CAL } from "@/constants/testIds";

/**
 * DAFTAR HARI LIBUR pada dialog kalender kerja.
 *
 * Dipisah dari `WorkCalendarDialog` bukan sekadar demi batas ukuran file: daftar ini punya
 * aturan sendiri yang lahir dari cacat nyata. Dulu override kalender proyek dianggap
 * PENGGANTI utuh kalender organisasi, sehingga menyimpan ambang pada cakupan proyek
 * menghapus 18 hari libur nasional secara senyap — tenggat 17 Agustus berhenti ditandai
 * dan inspeksi QC bisa dijadwalkan pada Hari Kemerdekaan.
 *
 * Sekarang:
 *  - setiap baris menyebut ASALNYA (diwarisi organisasi / khusus proyek),
 *  - pada cakupan proyek, libur warisan tidak bisa "dihapus" — hanya DIKECUALIKAN,
 *  - pengecualian ditampilkan terpisah dan bisa dibatalkan kembali.
 */
export default function WorkCalendarHolidays({
  cal, scope, busy, form, onForm, onAdd, onRemove, onRestore,
}) {
  const holidays = cal?.holidays || [];
  const excluded = cal?.excluded_holidays || [];
  const projectScope = scope === "project";

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold">Hari libur berlaku ({holidays.length})</p>
        {projectScope ? (
          <p data-testid={CAL.settingsInherit} className="text-[11px] text-muted-foreground">
            {cal?.org_holidays || 0} tanggal diwarisi dari kalender organisasi
            {cal?.project_holidays ? ` · ${cal.project_holidays} khusus proyek ini` : ""}
            {excluded.length ? ` · ${excluded.length} dikecualikan` : ""}
          </p>
        ) : null}
      </div>

      <div className="mt-2 max-h-56 space-y-1.5 overflow-y-auto pr-1">
        {!holidays.length ? (
          <p className="rounded-lg border border-dashed p-2 text-[11px] text-muted-foreground">
            Belum ada hari libur terdaftar — tenggat bisa mendarat di libur nasional.
          </p>
        ) : null}
        {holidays.map((h) => {
          const inherited = h.scope === "org" && projectScope;
          return (
            <div key={h.date} data-testid={CAL.holidayRow} data-date={h.date}
              data-scope={h.scope || "org"}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2 text-xs">
              <div className="min-w-0">
                <p className="font-medium">
                  <span className="font-mono">{h.date}</span> · {h.name}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  <RefLabel group="holiday_kind" value={h.kind} /> · {longDate(h.date)}
                  {projectScope ? (
                    <> · <RefLabel group="holiday_source" value={h.scope || "org"} /></>
                  ) : null}
                </p>
              </div>
              <Button size="sm" variant="ghost" disabled={busy}
                data-testid={CAL.holidayDelete} data-mode={inherited ? "exclude" : "delete"}
                aria-label={inherited
                  ? `Kecualikan hari libur ${h.date} untuk proyek ini`
                  : `Hapus hari libur ${h.date}`}
                title={inherited
                  ? "Libur ini milik kalender organisasi — akan dikecualikan untuk proyek ini saja"
                  : "Hapus hari libur ini"}
                onClick={() => onRemove(h.date, inherited)}>
                <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                {inherited ? <span className="ml-1 text-[11px]">Kecualikan</span> : null}
              </Button>
            </div>
          );
        })}
      </div>

      {excluded.length ? (
        <div className="mt-2 space-y-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2">
          <p className="text-[11px] font-semibold text-amber-900">
            Dikecualikan untuk proyek ini ({excluded.length}) — proyek ini tetap bekerja pada
            tanggal berikut meski kalender organisasi menandainya libur.
          </p>
          {excluded.map((h) => (
            <div key={h.date} data-testid={CAL.holidayExcludedRow} data-date={h.date}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-white p-2 text-xs">
              <span className="min-w-0">
                <span className="font-mono">{h.date}</span> · {h.name || "(tanpa nama)"}
              </span>
              <Button size="sm" variant="outline" disabled={busy}
                data-testid={CAL.holidayRestore}
                aria-label={`Ikutkan lagi hari libur ${h.date}`}
                onClick={() => onRestore(h.date)}>
                <RotateCcw className="mr-1 h-3.5 w-3.5" /> Ikutkan lagi
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-2 grid items-end gap-2 rounded-lg border bg-secondary/40 p-2 sm:grid-cols-4">
        <div>
          <Label htmlFor="cal-h-date" className="text-[11px]">Tanggal libur</Label>
          <Input id="cal-h-date" type="date" value={form.date}
            data-testid={CAL.holidayDate}
            onChange={(e) => onForm({ ...form, date: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="cal-h-name" className="text-[11px]">Nama hari libur</Label>
          <Input id="cal-h-name" value={form.name} data-testid={CAL.holidayName}
            placeholder="mis. Cuti bersama akhir tahun"
            onChange={(e) => onForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <Label className="text-[11px]">Jenis hari libur</Label>
          <ReferenceSelect group="holiday_kind" value={form.kind}
            onChange={(v) => onForm({ ...form, kind: v })} testId={CAL.holidayKind} />
        </div>
        <div className="sm:col-span-4 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy}
            data-testid={CAL.holidayAdd} onClick={onAdd}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Tambah hari libur
          </Button>
          <span className="text-[11px] text-muted-foreground">
            {projectScope
              ? "Ditambahkan hanya untuk proyek ini (mis. libur adat setempat)."
              : "Berlaku untuk seluruh proyek organisasi."}
          </span>
        </div>
      </div>
    </div>
  );
}
