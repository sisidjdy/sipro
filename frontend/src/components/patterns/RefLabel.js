import React from "react";
import { useReference } from "@/context/ReferenceContext";

/**
 * RefLabel — menampilkan LABEL manusia sebuah nilai enum langsung dari SSOT
 * (`GET /api/reference`), tanpa peta label lokal.
 *
 * Sebelum Fase 26 ada ~22 peta label hardcode di 20 file (mis. status SPK ditulis
 * ulang di 3 file, status PO di 2 file). Kalau backend menambah/mengubah pilihan,
 * label di UI ikut basi tanpa ada yang tahu. Komponen ini menghapus duplikasi itu.
 *
 * Pemakaian: <RefLabel group="po_status" value={po.status} />
 */
export default function RefLabel({ group, value, fallback = "-", className }) {
  const { labelOf } = useReference();
  if (value === undefined || value === null || value === "") {
    return <span className={className}>{fallback}</span>;
  }
  return <span className={className}>{labelOf(group, value)}</span>;
}
