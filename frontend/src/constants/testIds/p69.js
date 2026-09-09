// Portal pembeli — kartu booking fee.
export const PORTAL_BF = {
  card: "portal-booking-fee-card",
  status: "portal-booking-fee-status",
  proofBtn: "portal-booking-fee-proof-button",
  proofRow: "portal-booking-fee-proof-row",
};

// Booking fee sebagai komponen pembayaran terpisah (tagihan INV-BF + kwitansi).
export const BOOKING_FEE = {
  panel: "booking-fee-panel",
  none: "booking-fee-none",
  status: "booking-fee-status",
  outstanding: "booking-fee-outstanding",
  invoicePdf: "booking-fee-invoice-pdf",
  receiptPdf: "booking-fee-receipt-pdf",
  payBtn: "booking-fee-pay-button",
  payDialog: "booking-fee-pay-dialog",
  payAmount: "booking-fee-pay-amount",
  payMethod: "booking-fee-pay-method",
  refundBox: "booking-fee-refund-box",
  refundBtn: "booking-fee-refund-button",
  refundDialog: "booking-fee-refund-dialog",
  refundAmount: "booking-fee-refund-amount",
  refundFinalize: "booking-fee-refund-finalize",
  refundSubmit: "booking-fee-refund-submit",
  refundPdf: "booking-fee-refund-pdf",
  proofRow: "booking-fee-proof-row",
  proofVerifyBtn: "booking-fee-proof-verify-button",
  proofRejectBtn: "booking-fee-proof-reject-button",
  paySubmit: "booking-fee-pay-submit",
};

// Rincian harga tersimpan pada deal (daftar deal, Lead 360, Unit 360).
export const DEAL_PRICING = {
  openBtn: "deal-pricing-button",
  sheet: "deal-pricing-sheet",
  breakdown: "deal-pricing-breakdown",
  empty: "deal-pricing-empty",
  origin: "deal-pricing-origin",
  cashNote: "deal-pricing-cash-note",
};

// Fase 69 — mesin harga: skema diskon, promo, kupon; reservasi memakai breakdown penawaran.
export const PRICING = {
  tab: "config-tab-pricing",
  panel: "config-pricing-panel",
  subDiscount: "pricing-sub-discount",
  subPromo: "pricing-sub-promo",
  subCoupon: "pricing-sub-coupon",
  table: "pricing-rule-table",
  row: "pricing-rule-row",
  addBtn: "pricing-rule-add-button",
  editBtn: "pricing-rule-edit-button",
  redemptionsBtn: "pricing-coupon-redemptions-button",
  redemptionsDialog: "pricing-coupon-redemptions-dialog",
  redemptionRow: "pricing-coupon-redemption-row",
  dialog: "pricing-rule-dialog",
  formCode: "pricing-rule-form-code",
  formName: "pricing-rule-form-name",
  formKind: "pricing-rule-form-kind",
  formValue: "pricing-rule-form-value",
  formMax: "pricing-rule-form-max",
  formProject: "pricing-rule-form-project",
  formUnitType: "pricing-rule-form-unit-type",
  formFrom: "pricing-rule-form-from",
  formUntil: "pricing-rule-form-until",
  formQuota: "pricing-rule-form-quota",
  formQuotaCustomer: "pricing-rule-form-quota-customer",
  formApproval: "pricing-rule-form-approval",
  formStackable: "pricing-rule-form-stackable",
  formActive: "pricing-rule-form-active",
  formTarget: "pricing-rule-form-target",
  formTargetHelp: "pricing-rule-form-target-help",
  formTargetComponent: "pricing-rule-form-target-component",
  submit: "pricing-rule-submit",
};

// Field harga bersama (dipakai dialog penawaran & reservasi) — id dibedakan per dialog.
export const QUOTE_PRICING = {
  discountSelect: "quotation-discount-scheme-select",
  promoSelect: "quotation-promo-select",
  couponInput: "quotation-coupon-input",
  couponCheckBtn: "quotation-coupon-check-button",
  couponState: "quotation-coupon-state",
};

export const RESERVE = {
  dialog: "reserve-dialog",
  schemeSelect: "reserve-scheme-select",
  addonSelect: "reserve-addon-select",
  costsSummary: "reserve-costs-summary",
  addonAddBtn: "reserve-addon-add-button",
  discountSelect: "reserve-discount-scheme-select",
  promoSelect: "reserve-promo-select",
  couponInput: "reserve-coupon-input",
  couponCheckBtn: "reserve-coupon-check-button",
  couponState: "reserve-coupon-state",
  kprTenor: "reserve-kpr-tenor",
  kprRate: "reserve-kpr-rate",
  kprDp: "reserve-kpr-dp",
  bookingFee: "reserve-booking-fee",
  simulateBtn: "reserve-simulate-button",
  breakdown: "reserve-breakdown",
  error: "reserve-error",
};
