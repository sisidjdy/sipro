// data-testid Fase 58 — toleransi keterlambatan & denda berjurnal.
//
// Tab "Rencana Bayar" dulu MENGAKU sendiri bahwa toleransi keterlambatan "belum dibangun",
// sementara toleransi yang disusun pemakai (Fase 57A) dan tercetak pada SPR tidak pernah
// dipakai penagihan. Panel di bawah ini yang membuat janji itu bisa dilihat & dijalankan
// manusia — tanpa testId, penguji tidak bisa membedakan "belum ada denda" dari "panel mati".
export const P58 = {
  panel: "late-fee-panel",
  policy: "late-fee-policy",
  summary: "late-fee-summary",
  termRow: "late-fee-term-row",
  graceNote: "late-fee-grace-note",
  graceBanner: "late-fee-grace-banner",
  blockNote: "late-fee-block-note",
  applyBtn: "late-fee-apply-btn",
  penaltyRow: "late-fee-penalty-row",
  waiveBtn: "late-fee-waive-btn",
  waiveDialog: "late-fee-waive-dialog",
  waiveReason: "late-fee-waive-reason",
  waiveSubmit: "late-fee-waive-submit",
  denied: "late-fee-denied",
  // Portal pembeli
  portalCard: "portal-late-fee-card",
  portalRow: "portal-late-fee-row",
  portalPenaltyRow: "portal-late-fee-penalty-row",
};
