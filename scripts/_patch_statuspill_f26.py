#!/usr/bin/env python3
"""_patch_statuspill_f26.py — Fase 26: setiap <StatusPill> memakai grup SSOT.

Tanpa prop `group`, StatusPill jatuh ke peta label lokal (fallback yang sengaja dipertahankan
HANYA untuk portal pembeli yang tidak punya akses `/api/reference`). Akibatnya nilai enum yang
tidak ada di peta itu tampil MENTAH di UI staf (mis. 'meta_ads' di Inbox).
Skrip ini menambahkan `group="..."` pada semua pemakaian di halaman staf.
"""
import sys

FE = "/app/frontend/src/"

EDITS = {
    "pages/AppointmentsPage.js": [("<StatusPill status={a.status} />",
                                   '<StatusPill status={a.status} group="appointment_status" />')],
    "pages/ProjectsPage.js": [("<StatusPill status={u.status} />",
                               '<StatusPill status={u.status} group="unit_status" />')],
    "pages/LeadsPage.js": [("<StatusPill status={l.stage} />",
                            '<StatusPill status={l.stage} group="lead_stage" />')],
    "pages/DealsPage.js": [
        ("<StatusPill status={s} /> <span", '<StatusPill status={s} group="unit_status" /> <span'),
        ("<StatusPill status={u.status} />", '<StatusPill status={u.status} group="unit_status" />'),
        ("<StatusPill status={d.status} />", '<StatusPill status={d.status} group="deal_status" />'),
    ],
    "pages/DocumentsPage.js": [("<StatusPill status={d.status} />",
                                '<StatusPill status={d.status} group="document_status" />')],
    "pages/ComplaintsPage.js": [("<StatusPill status={c.priority} />",
                                 '<StatusPill status={c.priority} group="priority" />')],
    "components/finance/ApPanel.js": [("<StatusPill status={b.status} />",
                                       '<StatusPill status={b.status} group="ap_status" />')],
    "components/finance/ArDetailSheet.js": [("<StatusPill status={it.status} />",
                                             '<StatusPill status={it.status} group="ar_status" />')],
    "components/finance/CommissionsPanel.js": [("<StatusPill status={r.status} />",
                                                '<StatusPill status={r.status} group="commission_status" />')],
    "components/sales/CommissionBreakdown.js": [("<StatusPill status={c.status} />",
                                                 '<StatusPill status={c.status} group="commission_status" />')],
    "components/sales/DealLegalDialog.js": [("<StatusPill status={legal.financing.status} />",
                                             '<StatusPill status={legal.financing.status} group="financing_status" />')],
    "components/sales/LeadDetail.js": [
        ("<StatusPill status={lead.stage} />", '<StatusPill status={lead.stage} group="lead_stage" />'),
        ('<StatusPill status={ap.status} tone={ap.status === "scheduled" ? "active" : ap.status} />',
         '<StatusPill status={ap.status} group="appointment_status" tone={ap.status === "scheduled" ? "active" : ap.status} />'),
    ],
    "components/procurement/PODetailSheet.js": [("<StatusPill status={b.status} />",
                                                 '<StatusPill status={b.status} group="ap_status" />')],
    "components/procurement/ThreeWayPanel.js": [("<StatusPill status={b.status} />",
                                                 '<StatusPill status={b.status} group="threeway_status" />')],
    "components/omni/TemplatesPanel.js": [
        ('<StatusPill status={t.status === "approved" ? "approved" : "pending"} />',
         '<StatusPill status={t.status === "approved" ? "approved" : "pending"} group="wa_template_status" />')],
    "components/customers/CustomerDetailSheet.js": [("<StatusPill status={f.status} />",
                                                     '<StatusPill status={f.status} group="financing_status" />')],
    "components/subcon/ChangeOrdersSection.js": [("<StatusPill status={co.status} />",
                                                  '<StatusPill status={co.status} group="change_order_status" />')],
    "components/subcon/ClaimsPanel.js": [("<StatusPill status={c.status} />",
                                          '<StatusPill status={c.status} group="claim_status" />')],
    "components/complaints/ComplaintDetailSheet.js": [("<StatusPill status={c.priority} />",
                                                       '<StatusPill status={c.priority} group="priority" />')],
    "components/appointments/SurveyPanel.js": [
        ("{survey ? <StatusPill status={survey.status} /> : null}",
         '{survey ? <StatusPill status={survey.status} group="survey_status" /> : null}'),
        ("<StatusPill status={survey.result} />",
         '<StatusPill status={survey.result} group="survey_result" />'),
    ],
    "components/construction/InspectionsPanel.js": [
        ("<StatusPill status={i.status} />", '<StatusPill status={i.status} group="inspection_status" />'),
        ("<StatusPill status={inspection.status} /></DialogTitle>",
         '<StatusPill status={inspection.status} group="inspection_status" /></DialogTitle>'),
    ],
    "components/tax/TaxRecordsPanel.js": [("<StatusPill status={r.status} />",
                                           '<StatusPill status={r.status} group="tax_status" />')],
    "components/tax/FakturPanel.js": [("<StatusPill status={f.status} />",
                                       '<StatusPill status={f.status} group="faktur_status" />')],
    "components/patterns/TaskCard.js": [("<StatusPill status={task.priority} />",
                                         '<StatusPill status={task.priority} group="priority" />')],
}


def main():
    bad = []
    for rel, pairs in EDITS.items():
        path = FE + rel
        src = open(path, encoding="utf-8").read()
        for old, new in pairs:
            n = src.count(old)
            if n != 1:
                bad.append(f"{rel}: pola {n}x (harus 1x): {old[:60]!r}")
                continue
            src = src.replace(old, new)
        open(path, "w", encoding="utf-8").write(src)
        print(f"OK  {rel} ({len(pairs)})")
    if bad:
        print("\nGAGAL:")
        for b in bad:
            print("  - " + b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
