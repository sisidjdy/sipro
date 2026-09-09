// data-testid Fase 59 — laporan keringanan denda, kandidat pembatalan karena tunggakan,
// dan laporan utang refund (2-1460).
//
// Ketiganya adalah "tugas berikutnya" yang dicatat Fase 58. Tanpa testId, penguji tidak bisa
// membedakan laporan yang KOSONG karena tidak ada keringanan dari laporan yang MATI karena
// panelnya tidak pernah dirender — dua keadaan yang artinya sangat berbeda bagi auditor.
export const P59 = {
  // Laporan keringanan denda
  waiverPanel: "late-fee-waiver-report",
  waiverTabState: "late-fee-tab-state",
  waiverTabReport: "late-fee-tab-waivers",
  waiverScope: "waiver-scope-toggle",
  waiverFrom: "waiver-date-from",
  waiverTo: "waiver-date-to",
  waiverRow: "waiver-row",
  waiverActorRow: "waiver-actor-row",
  waiverSummary: "waiver-summary",
  waiverEmpty: "waiver-empty",
  waiverCsvBtn: "waiver-export-csv",
  waiverPdfBtn: "waiver-export-pdf",
  waiverDenied: "waiver-denied",

  // Kandidat pembatalan karena tunggakan
  arrearsPanel: "arrears-candidates-panel",
  arrearsRow: "arrears-candidate-row",
  arrearsSummary: "arrears-summary",
  arrearsRule: "arrears-rule-note",
  arrearsBlock: "arrears-block-note",
  arrearsSweepBtn: "arrears-sweep-btn",
  arrearsOpenBtn: "arrears-open-contract",
  arrearsEmpty: "arrears-empty",

  // Laporan utang refund
  refundPanel: "refund-debt-panel",
  refundTab: "finance-tab-refund-debt",
  refundRow: "refund-debt-row",
  refundSummary: "refund-debt-summary",
  refundBuckets: "refund-debt-buckets",
  refundProjection: "refund-debt-projection",
  refundUnscheduled: "refund-debt-unscheduled",
  refundLedger: "refund-debt-ledger",
  refundCsvBtn: "refund-debt-export-csv",
  refundPdfBtn: "refund-debt-export-pdf",
  refundEmpty: "refund-debt-empty",
};
