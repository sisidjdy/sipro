// testIds Fase 33 — lingkup SPK, opname berbukti, dan kendali biaya RAB.
export const SCOPE = {
  section: "spk-scope-section",
  metrics: "spk-scope-metrics",
  contract: "spk-scope-contract",
  blockers: "spk-scope-blockers",
  row: "spk-scope-row",
  addBtn: "spk-scope-add",
  removeBtn: "spk-scope-remove",
  dialog: "spk-scope-dialog",
  unitFilter: "spk-scope-unit-filter",
  candidate: "spk-scope-candidate",
  candidateCheck: "spk-scope-candidate-check",
  valueInput: "spk-scope-value",
  dialogTotal: "spk-scope-dialog-total",
  save: "spk-scope-save",
  lumpsumHint: "spk-scope-lumpsum-hint",
  progressNote: "spk-scope-progress-note",
};

export const OPNAME = {
  preview: "claim-opname-preview",
  previewRow: "claim-opname-preview-row",
  previewTotal: "claim-opname-preview-total",
  blocked: "claim-opname-blocked",
  sheet: "claim-opname-sheet",
  line: "claim-opname-line",
  toggle: "claim-opname-toggle",
  reason: "claim-opname-reason",
  note: "claim-opname-note",
  total: "claim-opname-total",
  save: "claim-opname-save",
  sodHint: "claim-opname-sod-hint",
  basis: "claim-basis",
  lines: "claim-lines",
};

export const COST = {
  // Catatan Fase 45: `itemsTab`/`controlTab` DIHAPUS. Hub `/boq` kini memakai `TabPage`
  // (tab sinkron ke URL `?hub=`), yang menghasilkan test id `tabpage-tab-<key>` — lihat
  // `BUDGET.targetTab`/`BUDGET.realizationTab`. Menyimpan dua penanda untuk satu tab hanya
  // membuat agen uji memilih penanda yang sudah mati.
  panel: "boq-cost-control",
  metrics: "boq-cost-metrics",
  warning: "boq-cost-warning",
  categoryRow: "boq-cost-category-row",
  codeRow: "boq-cost-code-row",
  mapBtn: "boq-map-steps",
  mapDialog: "boq-map-dialog",
  mapStep: "boq-map-step",
  mapSave: "boq-map-save",
  mapCount: "boq-map-count",
};
