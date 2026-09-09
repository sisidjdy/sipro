// testIds Fase 46 — hub Pembangunan unit-centric: Papan Unit, kesiapan mulai bangun,
// tab Pembangunan di Unit 360, dan izin bertingkat (coverage per objek).
//
// Tanpa testid, gate & agen uji tidak bisa membuktikan bahwa layar benar-benar menolak /
// memperingatkan / menampilkan "belum ada data" — dan janji "jujur" jadi tidak terverifikasi.

export const UNIT_BOARD = {
  panel: "unit-board-panel",
  table: "unit-board-table",
  row: "unit-board-row",
  summary: "unit-board-summary",
  modeBanner: "unit-board-mode-banner",
  readiness: "unit-board-readiness",
  planEmpty: "unit-board-plan-empty",
  openUnit: "unit-board-open-unit",
  extras: "unit-board-extras",
  extrasToggle: "unit-board-extras-toggle",
};

export const READINESS = {
  card: "unit-readiness-card",
  state: "unit-readiness-state",
  reason: "unit-readiness-reason",
  mode: "unit-readiness-mode",
  missing: "unit-readiness-missing",
  startBtn: "unit-start-build",
  dialog: "unit-start-dialog",
  ack: "unit-start-ack",
  reasonInput: "unit-start-reason",
  submit: "unit-start-submit",
  payment: "unit-readiness-payment",
  permits: "unit-readiness-permits",
};

export const UNIT_BUILD = {
  tab: "unit-build-tab",
  schedule: "unit-build-schedule",
  noSchedule: "unit-build-no-schedule",
  generateBtn: "unit-build-generate-btn",
  templateHint: "unit-build-template-hint",
  templateChip: "unit-build-template-chip",
  quality: "unit-quality-panel",
  inspectionRow: "unit-inspection-row",
  punchRow: "unit-punch-row",
  qualityEmpty: "unit-quality-empty",
  weekly: "unit-weekly-report",
  weeklyRow: "unit-weekly-row",
};

export const PERMIT_COVERAGE = {
  panel: "permit-coverage-panel",
  chain: "permit-coverage-chain",
  row: "permit-coverage-row",
  health: "permit-coverage-health",
  required: "permit-coverage-required",
  requiredRow: "permit-coverage-required-row",
  empty: "permit-coverage-empty",
  addBtn: "permit-coverage-add",
  renewBtn: "permit-renew-button",
  renewDialog: "permit-renew-dialog",
  renewDate: "permit-renew-date",
  renewRef: "permit-renew-ref",
  renewSubmit: "permit-renew-submit",
  detailDialog: "permit-detail-dialog",
  detailStatus: "permit-detail-status",
  detailStatusNote: "permit-detail-status-note",
  detailStatusSave: "permit-detail-status-save",
  detailOpenPage: "permit-detail-open-page",
  typesBtn: "permit-types-button",
  typesDialog: "permit-types-dialog",
  typesInput: "permit-types-input",
  typesAdd: "permit-types-add",
  typesSave: "permit-types-save",
  scanBtn: "permit-expiry-scan",
  scopeSelect: "permit-form-scope",
  scopeObject: "permit-form-scope-object",
  expiry: "permit-form-expiry",
  noExpiry: "permit-no-expiry",
};
