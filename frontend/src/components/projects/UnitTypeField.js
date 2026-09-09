import React, { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EMPTY_UNIT_TYPE, UnitTypeFormDialog } from "@/components/config/UnitTypeFormDialog";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";

/** Pemilih tipe unit yang membaca MASTER yang sama dengan Pusat Konfigurasi › Tipe Unit. */
export function UnitTypeField({ value, onChange, testId }) {
  const { reload } = useReference();
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(null);

  const load = useCallback(() => {
    api.get("/catalog/unit-types").then((r) => setTypes((r.data.data || []).filter((t) => t.active !== false)))
      .catch(() => setTypes([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const picked = types.find((t) => t.code === value);
  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <Select value={value || ""} onValueChange={onChange}>
          <SelectTrigger data-testid={testId} aria-label="Tipe unit" className="flex-1">
            <SelectValue placeholder="Pilih tipe unit dari master" />
          </SelectTrigger>
          <SelectContent>
            {types.map((t) => (
              <SelectItem key={t.code} value={t.code} data-testid={`${testId}-opt-${t.code}`}>
                {t.name} <span className="ml-1 font-mono text-[11px] text-muted-foreground">{t.code}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="button" size="sm" variant="secondary" data-testid={`${testId}-new`}
          onClick={() => setForm({ ...EMPTY_UNIT_TYPE })}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Tipe baru
        </Button>
      </div>
      <p data-testid={`${testId}-hint`} className="text-[11px] text-muted-foreground">
        {picked
          ? `${picked.building_area ?? "?"}/${picked.land_area_std ?? "?"} m² · harga dasar ${picked.base_price ? formatIDR(picked.base_price) : "belum diisi"} · ${picked.units_count || 0} unit memakai tipe ini`
          : "Daftar ini sama dengan Pusat Konfigurasi › Tipe Unit; tipe baru yang dibuat di sini juga muncul di sana."}
      </p>
      <UnitTypeFormDialog form={form} setForm={setForm}
        onSaved={(t) => { load(); reload(); if (t?.code) onChange(t.code); }} />
    </div>
  );
}
