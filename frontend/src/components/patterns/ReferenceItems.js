import React from "react";
import { SelectItem } from "@/components/ui/select";
import { useReference } from "@/context/ReferenceContext";

/**
 * Daftar <SelectItem> dari registry SSOT `/api/reference` (Audit Tahap 7 §3 / CFG-04).
 * Dipakai di dalam <SelectContent> yang sudah ada — menggantikan opsi enum yang diketik
 * ulang di layar, supaya menambah status di SSOT langsung muncul di semua dropdown.
 * `only`: batasi ke sebagian nilai (mis. dialog tutup lead hanya `lost`/`recycle`).
 */
export default function ReferenceItems({ group, only }) {
  const { options } = useReference();
  const opts = options(group).filter((o) => !only || only.includes(o.value));
  return (
    <>
      {opts.map((o) => (
        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
      ))}
    </>
  );
}
