// Marketing Fee agen/broker/referral (Fase 27) testIds.
//
// FASE 42 — halaman `/marketing-fee` DIHAPUS: rutenya kini mengalihkan ke tab "Tagihan Fee"
// di hub Mitra & Fee (`/partners?hub=tagihan`) supaya tidak ada dua pintu untuk satu urusan.
// Karena itu testId untuk halaman & tab lama (`page`, `tabFees`, `tabAgents`) dan untuk
// MASTER AGEN lama (`agent*`) ikut dibuang — masternya sekarang "Master Mitra"
// (`constants/testIds/partners.js`), yang punya kontrak, status beralasan, dan aturan fee.
// Panel pengajuan/persetujuan/pembayaran fee (`FeesPanel`) TIDAK berubah: dipakai ulang
// sebagai isi tab, bukan disalin.
export const MFEE = {
  summary: "mfee-summary",
  feesPanel: "mfee-fees-panel",
  feeRow: "mfee-fee-row",
  feesEmpty: "mfee-fees-empty",
  statusFilter: "mfee-status-filter",
  submitBtn: "mfee-submit-button",
  submitDialog: "mfee-submit-dialog",
  submitAgent: "mfee-submit-agent",
  submitDeal: "mfee-submit-deal",
  submitBasis: "mfee-submit-basis",
  submitValue: "mfee-submit-value",
  submitTrigger: "mfee-submit-trigger",
  submitPph: "mfee-submit-pph",
  submitPreview: "mfee-submit-preview",
  submitConfirm: "mfee-submit-confirm",
  approveBtn: "mfee-approve-button",
  rejectBtn: "mfee-reject-button",
  payBtn: "mfee-pay-button",
  payDialog: "mfee-pay-dialog",
  payAmount: "mfee-pay-amount",
  paySource: "mfee-pay-source",
  payConfirm: "mfee-pay-confirm",
  leaderboard: "mfee-leaderboard",
  leaderboardRow: "mfee-leaderboard-row",
};
