// Kontrak & Harga, Rencana Bayar (profil pelanggan), dan Fee Mitra (profil lead).
//
// Ketiga tab ini SEMPAT MATI dengan label "dijadwalkan Fase 43/45" — nomor fase yang sudah
// lewat karena urutan pengerjaan nyata berbeda dari roadmap awal (lihat tabel pemetaan di
// docs/v2/34_ROADMAP_EKSEKUSI.md). Sekarang ketiganya menampilkan DATA NYATA yang memang
// sudah dimiliki sistem (penawaran, jadwal tagihan AR, fee mitra), dan hal yang benar-benar
// belum dibangun (kontrak formal + rincian biaya per komponen) dinyatakan apa adanya.
export const CRMC = {
  // ---------- Kontrak & Harga ----------
  contractTab: "cust-contract-tab",
  contractGap: "cust-contract-gap-note",
  contractDealRow: "cust-contract-deal-row",
  contractQuotationRow: "cust-contract-quotation-row",
  contractAddonRow: "cust-contract-addon-row",
  contractEmpty: "cust-contract-empty",
  contractOpenQuotation: "cust-contract-open-quotation",

  // ---------- Rencana Bayar ----------
  planTab: "cust-payment-plan-tab",
  planDeal: "cust-payment-plan-deal",
  planSummary: "cust-payment-plan-summary",
  planRow: "cust-payment-plan-row",
  planReceiptRow: "cust-payment-plan-receipt-row",
  planOverdue: "cust-payment-plan-overdue",
  planEmpty: "cust-payment-plan-empty",
  planGap: "cust-payment-plan-gap-note",
  planOpenFinance: "cust-payment-plan-open-finance",

  // ---------- Fee Mitra (profil lead) ----------
  feeTab: "lead-partner-fee-tab",
  feeAttribution: "lead-partner-fee-attribution",
  feeRow: "lead-partner-fee-row",
  feeSummary: "lead-partner-fee-summary",
  feeRuleRow: "lead-partner-fee-rule-row",
  feeEmpty: "lead-partner-fee-empty",
  feeOpenPartner: "lead-partner-fee-open-partner",
  // Kartu "akses dibatasi" (peran tanpa izin `marketing_fee:view`, mis. manajer proyek &
  // pelaksana lapangan) dan catatan lingkup baris untuk peran ber-`view_own` (sales).
  // Keduanya HARUS bisa dikenali penguji: tanpa testId, layar "dibatasi" dan layar
  // "memang belum ada data" tampak sama dari luar.
  feeDenied: "lead-partner-fee-denied",
  feeScopeNote: "lead-partner-fee-scope-note",
};
