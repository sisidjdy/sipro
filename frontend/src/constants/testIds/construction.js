export const PROJECTS = {
  page: "projects-page",
  card: "project-card",
  addBtn: "project-add-button",
  createSubmit: "project-create-submit",
  detail: "project-detail",
  addUnitBtn: "project-add-unit-button",
  unitGenSubmit: "unit-generate-submit",
};

export const CONSTRUCTION = {
  page: "construction-page",
  projectSelect: "construction-project-select",
  denied: "construction-access-denied",
  phaseRow: "phase-row",
  progressInput: "phase-progress-input",
  progressSubmit: "phase-progress-submit",
  qcBtn: "qc-button",
  qcSubmit: "qc-submit",
  curve: "kurva-s-chart",
  logItem: "construction-log-item",
};

export const MATERIALS = {
  page: "materials-page",
  projectSelect: "materials-project-select",
  row: "material-row",
  addBtn: "material-add-button",
  addSubmit: "material-add-submit",
  txnBtn: "material-txn-button",
  txnSubmit: "material-txn-submit",
  opnameBtn: "material-opname-button",
  opnameSubmit: "material-opname-submit",
  tabStock: "materials-tab-stock",
  tabReq: "materials-tab-requisitions",
  tabBudget: "materials-tab-budget",
  // Fase 48 (penutupan): keadaan AKSES DITOLAK yang sopan. Sebelum ini halaman material
  // tetap dirender untuk peran yang backend-nya menjawab 403 (mis. sales), sehingga layar
  // menulis "Belum ada transaksi" — berbohong "tidak ada data" padahal yang benar
  // "tidak boleh melihat data".
  denied: "materials-access-denied",
};

// Phase 18 — EPIC 2.6 Material Requisition (Permintaan Material)
export const REQUISITION = {
  panel: "requisitions-panel",
  newBtn: "requisition-new-button",
  purpose: "requisition-purpose-input",
  phaseSelect: "requisition-phase-select",
  itemMaterial: "requisition-item-material",
  itemQty: "requisition-item-qty",
  addItem: "requisition-add-item",
  createSave: "requisition-create-save",
  row: "requisition-row",
  detail: "requisition-detail",
  approveBtn: "requisition-approve-button",
  rejectBtn: "requisition-reject-button",
  issueBtn: "requisition-issue-button",
};

// Phase 18 — Anggaran material (RAB) vs pemakaian
export const MATBUDGET = {
  panel: "material-budget-panel",
  row: "material-budget-row",
};
