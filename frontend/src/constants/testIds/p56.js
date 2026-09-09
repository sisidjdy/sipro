// testId permukaan Fase 56 — pembatalan kontrak & refund berjurnal.
//
// Dipisah per fase (aturan repo) supaya berkas testId tidak menjadi tempat sampah: setiap
// id di sini menempel pada layar yang BARU lahir di Fase 56.
export const P56 = {
  // --- panel pembatalan pada kontrak pembeli
  panel: "cancellation-panel",
  requestBtn: "cancellation-request-button",
  requestDialog: "cancellation-request-dialog",
  requestReason: "cancellation-request-reason",
  requestSubmit: "cancellation-request-submit",
  blocked: "cancellation-blocked",
  preview: "cancellation-preview",
  row: "cancellation-row",
  stateBadge: "cancellation-state",
  moneyNote: "cancellation-money-note",

  // --- keputusan (Manajer Keuangan)
  decideBtn: "cancellation-decide-button",
  decideDialog: "cancellation-decide-dialog",
  decideNote: "cancellation-decide-note",
  decideApprove: "cancellation-decide-approve",
  decideReject: "cancellation-decide-reject",
  decisionSoD: "cancellation-decision-sod",

  // --- refund (Keuangan) + penahanan
  refundBtn: "cancellation-refund-button",
  refundDialog: "cancellation-refund-dialog",
  refundAmount: "cancellation-refund-amount",
  refundMethod: "cancellation-refund-method",
  refundSubmit: "cancellation-refund-submit",
  refundHold: "cancellation-refund-hold",
  refundOverride: "cancellation-refund-override",
  refundOverrideReason: "cancellation-refund-override-reason",
  refundPaymentRow: "cancellation-refund-payment-row",

  // --- dokumen & jurnal
  docPrint: "cancellation-doc-print",
  journalRow: "cancellation-journal-row",

  // --- daftar di Keuangan
  financeTab: "finance-tab-cancellations",
  financePanel: "cancellations-finance-panel",
  financeRow: "cancellations-finance-row",
  financeSearch: "cancellations-finance-search",
  financeStateFilter: "cancellations-finance-state",

  // --- portal pembeli
  portalTab: "portal-tab-cancellation",
  portalPanel: "portal-cancellation-panel",
  portalRow: "portal-cancellation-row",
  portalWaiting: "portal-cancellation-waiting",
  portalEmpty: "portal-cancellation-empty",
  portalDocPrint: "portal-cancellation-doc",
};
