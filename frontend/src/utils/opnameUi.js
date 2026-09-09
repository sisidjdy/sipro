// opnameUi — nada warna & teks bantu untuk lingkup SPK/opname (Fase 33).
// Label enum tetap dari SSOT `/api/reference` (StatusPill/RefLabel), di sini HANYA warna.

export const SCOPE_TONE = {
  billed: "paid",
  pending: "submitted",
  claimable: "approved",
  unverified: "pending",
  open: "draft",
};

export const scopeTone = (state) => SCOPE_TONE[state] || "draft";

/** Persen aman (tanpa pembagian nol) untuk bar alokasi/tagihan. */
export function pctOf(part, total) {
  const t = Number(total || 0);
  if (!t) return 0;
  return Math.max(0, Math.min(100, Math.round((Number(part || 0) / t) * 100)));
}

/** Ringkasan satu baris lingkup untuk teks pendek di kartu/tabel. */
export function scopeLabel(row) {
  const parts = [row.unit_code, row.step_code].filter(Boolean);
  return parts.join(" · ");
}
