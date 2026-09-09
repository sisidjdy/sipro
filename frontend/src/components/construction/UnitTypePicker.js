import React from "react";

import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { BUILD } from "@/constants/testIds";

/**
 * Pilih beberapa TIPE unit dari SSOT `/api/reference` (chip bisa dihapus satu-satu).
 *
 * Dipakai template jadwal: satu template boleh berlaku untuk beberapa tipe rumah,
 * dan kosong berarti berlaku untuk semua tipe.
 */
export default function UnitTypePicker({ value = [], onChange, testId = BUILD.templateTypes }) {
  const add = (v) => { if (v && !value.includes(v)) onChange([...value, v]); };
  return (
    <div className="space-y-1.5">
      <ReferenceSelect group="unit_type" value="" onChange={add} testId={testId}
        placeholder="Tambah tipe unit…" />
      <div className="flex flex-wrap gap-1">
        {value.map((t) => (
          <button key={t} type="button" data-type={t}
            aria-label={`Hapus tipe unit ${t}`}
            onClick={() => onChange(value.filter((x) => x !== t))}
            className="rounded-full border bg-background px-2 py-0.5 text-[11px] hover:bg-secondary">
            {t} ×
          </button>
        ))}
        {!value.length ? (
          <span className="text-[11px] text-muted-foreground">
            Kosong = berlaku untuk semua tipe unit.
          </span>
        ) : null}
      </div>
    </div>
  );
}
