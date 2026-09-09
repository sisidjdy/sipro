// testId permukaan Fase 53 — konversi lead → pembeli, kontrak & legal, KPR, dokumen owner.
//
// Dipisah per fase (aturan repo) supaya berkas testId tidak pernah menjadi tempat sampah:
// setiap id di sini menempel pada layar yang BARU lahir di Fase 53.
export const P53 = {
  // --- konversi lead → pembeli
  convertBtn: "convert-to-customer-button",
  convertDialog: "convert-to-customer-dialog",
  convertScheme: "convert-scheme-select",
  convertNik: "convert-nik-input",
  convertSubmit: "convert-submit",
  convertBlocked: "convert-blocked",
  convertNote: "convert-note",
  bookBtn: "deal-book-button",

  // --- kontrak
  contractPanel: "contract-panel",
  contractEmpty: "contract-empty",
  contractScoped: "contract-out-of-scope",
  contractNumber: "contract-number",
  breakdownRow: "contract-breakdown-row",
  breakdownEmptyState: "contract-breakdown-empty-note",
  totalProvisional: "contract-total-provisional",
  costsBtn: "contract-costs-button",
  costsDialog: "contract-costs-dialog",
  costsSubmit: "contract-costs-submit",
  activateBtn: "contract-activate-button",
  planRow: "contract-plan-row",
  planEmpty: "contract-plan-empty",

  // --- tahap legal
  legalStep: "contract-legal-step",
  legalBtn: "contract-legal-button",
  legalBlocked: "contract-legal-blocked",
  legalDialog: "contract-legal-dialog",
  legalSubmit: "contract-legal-submit",

  // --- KPR
  kprPanel: "contract-kpr-panel",
  kprStage: "contract-kpr-stage",
  kprBtn: "contract-kpr-button",
  kprDialog: "contract-kpr-dialog",
  kprSubmit: "contract-kpr-submit",
  kprRejectBtn: "contract-kpr-reject-button",

  // --- dokumen owner (SPR/SPKT) + cetak
  docPanel: "contract-documents-panel",
  docGenerateBtn: "contract-doc-generate",
  docRow: "contract-doc-row",
  docPrint: "contract-doc-print",
  docBlocked: "contract-doc-blocked",
  docWarning: "contract-doc-warning",
};
