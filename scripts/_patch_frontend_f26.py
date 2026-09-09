#!/usr/bin/env python3
"""_patch_frontend_f26.py — Fase 26: hapus SEMUA vocabulary enum hardcode di frontend
(E5), ubah field enum yang masih input bebas jadi dropdown SSOT (E1), dan beri
label aksesibilitas pada input tanpa label (E4).

Sumber label kini tunggal: `GET /api/reference` (lewat `useReference()` / `<RefLabel/>` /
`<StatusPill group="...">`). Setiap pola HARUS ketemu tepat 1x; kalau tidak, skrip gagal.
"""
import re
import sys

FE = "/app/frontend/src/"
IMPORT_REF_LABEL = 'import RefLabel from "@/components/patterns/RefLabel";\n'
IMPORT_USE_REF = 'import { useReference } from "@/context/ReferenceContext";\n'
IMPORT_REF_SELECT = 'import ReferenceSelect from "@/components/patterns/ReferenceSelect";\n'

# file -> list of (old, new); string "IMPORT:<baris>" = tambahkan import bila belum ada
EDITS = {
    # ---------------- E5: peta label hardcode -> SSOT ----------------
    "components/appointments/AppointmentDetailSheet.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const TYPE_LABEL = { survey: "Survey", meeting: "Pertemuan", call: "Telepon" };\n', ''),
        ("                {TYPE_LABEL[appointment.type] || appointment.type}",
         '                <RefLabel group="appointment_type" value={appointment.type} />'),
    ],
    "components/complaints/ComplaintDetailSheet.js": [
        ('const STATUS_LABEL = { open: "Terbuka", in_progress: "Dikerjakan", resolved: "Selesai" };\n', ''),
        ('toast.success(`Status → ${STATUS_LABEL[status]}.`);',
         'toast.success(`Status → ${labelOf("complaint_status", status)}.`);'),
        ('<StatusPill status={c.status} label={STATUS_LABEL[c.status]} />',
         '<StatusPill status={c.status} group="complaint_status" />'),
    ],
    "components/construction/InspectionsPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const CAT_LABEL = { structural: "Struktur", mep: "MEP", finishing: "Finishing", handover: "Serah Terima", lainnya: "Lainnya" };\n', ''),
        ('· {CAT_LABEL[i.category] || i.category}</span></p>',
         '· <RefLabel group="inspection_category" value={i.category} /></span></p>'),
        ('{inspection.title} · {CAT_LABEL[inspection.category] || inspection.category}',
         '{inspection.title} · <RefLabel group="inspection_category" value={inspection.category} />'),
    ],
    "components/field/PunchDetailSheet.js": [
        ('const STATUS_LABEL = { open: "Terbuka", in_progress: "Dikerjakan", verified: "Diverifikasi", closed: "Selesai" };\n'
         'const SEV_LABEL = { low: "Rendah", medium: "Sedang", high: "Tinggi" };\n'
         'const OPTIONS = Object.keys(STATUS_LABEL);\n', ''),
        ('  const { labelOf } = useReference();', '  const { labelOf, options } = useReference();'),
        ('toast.success(`Status → ${STATUS_LABEL[status]}.`);',
         'toast.success(`Status → ${labelOf("punch_status", status)}.`);'),
        ('<StatusPill status={punch.status} label={STATUS_LABEL[punch.status]} />',
         '<StatusPill status={punch.status} group="punch_status" />'),
        ('<StatusPill status={punch.severity} label={SEV_LABEL[punch.severity]} />',
         '<StatusPill status={punch.severity} group="punch_severity" />'),
        ('<SelectContent>{OPTIONS.map((o) => <SelectItem key={o} value={o}>{STATUS_LABEL[o]}</SelectItem>)}</SelectContent>',
         '<SelectContent>{options("punch_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>'),
    ],
    "components/field/PunchListPanel.js": [
        ('const STATUS_LABEL = { open: "Terbuka", in_progress: "Dikerjakan", verified: "Diverifikasi", closed: "Selesai" };\n'
         'const SEV_LABEL = { low: "Rendah", medium: "Sedang", high: "Tinggi" };\n', ''),
        ('<StatusPill status={p.severity} label={SEV_LABEL[p.severity]} />',
         '<StatusPill status={p.severity} group="punch_severity" />'),
        ('<StatusPill status={p.status} label={STATUS_LABEL[p.status]} />',
         '<StatusPill status={p.status} group="punch_status" />'),
    ],
    "components/finance/CollectionsPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const BUCKET_LABEL = { overdue: "Menunggak", due_soon: "Jatuh Tempo Dekat", current: "Lancar" };\n', ''),
        ('                      {BUCKET_LABEL[r.bucket] || "-"}',
         '                      <RefLabel group="collection_bucket" value={r.bucket} />'),
    ],
    "components/finance/CommissionsPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const TRIGGER_LABEL = { booked: "Saat Booking", paid_off: "Saat Lunas" };\n', ''),
        ('{TRIGGER_LABEL[r.trigger] || r.trigger}',
         '<RefLabel group="commission_trigger" value={r.trigger} />'),
    ],
    "components/gl/CoAPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('export const TYPE_LABEL = {\n'
         '  asset: "Aset", liability: "Liabilitas", equity: "Ekuitas", revenue: "Pendapatan", expense: "Beban",\n'
         '};\n', ''),
        ('{TYPE_LABEL[a.type] || a.type}', '<RefLabel group="account_type" value={a.type} />'),
    ],
    "components/gl/TrialBalancePanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('import { TYPE_LABEL } from "@/components/gl/CoAPanel";\n', ''),
        ('{TYPE_LABEL[r.type] || r.type}', '<RefLabel group="account_type" value={r.type} />'),
    ],
    "components/omni/AttributionPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const SOURCE_LABEL = {\n'
         '  meta_ads: "Meta Ads", whatsapp: "WhatsApp", google_lead: "Google", tiktok_lead: "TikTok",\n'
         '  website: "Website", walk_in: "Walk-in", referral: "Referral", manual: "Manual", unknown: "Lainnya",\n'
         '};\n', ''),
        ('{SOURCE_LABEL[r.source] || r.source}', '<RefLabel group="lead_source" value={r.source} />'),
    ],
    "components/patterns/TaskCard.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const TYPE_LABEL = {\n'
         '  contact: "Kontak", follow_up: "Follow-up", todo: "To-do", review: "Review",\n'
         '  survey: "Survey", document: "Dokumen",\n'
         '};\n', ''),
        ('              {TYPE_LABEL[task.type] || task.type}',
         '              <RefLabel group="task_type" value={task.type} />'),
    ],
    "components/permits/PermitDetailSheet.js": [
        ('const STATUS_LABEL = {\n'
         '  not_started: "Belum Mulai", in_progress: "Proses", submitted: "Diajukan",\n'
         '  approved: "Disetujui", rejected: "Ditolak", expired: "Kadaluarsa",\n'
         '};\n'
         'const OPTIONS = Object.keys(STATUS_LABEL);\n', ''),
        ('  const { labelOf } = useReference();', '  const { labelOf, options } = useReference();'),
        ('toast.success(`Status → ${STATUS_LABEL[status]}.`);',
         'toast.success(`Status → ${labelOf("permit_status", status)}.`);'),
        ('<StatusPill status={permit.status} label={STATUS_LABEL[permit.status]} />',
         '<StatusPill status={permit.status} group="permit_status" />'),
        ('<SelectContent>{OPTIONS.map((o) => <SelectItem key={o} value={o}>{STATUS_LABEL[o]}</SelectItem>)}</SelectContent>',
         '<SelectContent>{options("permit_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>'),
    ],
    "components/procurement/PODetailSheet.js": [
        ('const PO_LABEL = {\n'
         '  draft: "Draft", approved: "Disetujui", partially_received: "Diterima Sebagian",\n'
         '  received: "Diterima", closed: "Selesai", cancelled: "Batal",\n'
         '};\n', ''),
        ('<StatusPill status={po.status} label={PO_LABEL[po.status]} />',
         '<StatusPill status={po.status} group="po_status" />'),
        # E4: kolom qty GRN tanpa label -> beri aria-label per item
        ('<Input className="h-9 w-28" type="number" value={grnQty[i] || ""} disabled={remaining <= 0}\n'
         '                          onChange={(e) => setGrnQty((g) => ({ ...g, [i]: e.target.value }))} placeholder="0" />',
         '<Input className="h-9 w-28" type="number" value={grnQty[i] || ""} disabled={remaining <= 0}\n'
         '                          aria-label={`Qty diterima untuk ${it.description}`}\n'
         '                          onChange={(e) => setGrnQty((g) => ({ ...g, [i]: e.target.value }))} placeholder="0" />'),
    ],
    "components/procurement/POPanel.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ('const PO_LABEL = {\n'
         '  draft: "Draft", approved: "Disetujui", partially_received: "Diterima Sebagian",\n'
         '  received: "Diterima", closed: "Selesai", cancelled: "Batal",\n'
         '};\n'
         'const TYPE_LABEL = { material: "Material", subcon: "Subkon", general: "Umum" };\n', ''),
        ('{TYPE_LABEL[p.po_type] || p.po_type}', '<RefLabel group="po_type" value={p.po_type} />'),
        ('<StatusPill status={p.status} label={PO_LABEL[p.status]} />',
         '<StatusPill status={p.status} group="po_status" />'),
    ],
    "components/sales/LeadDetail.js": [
        ('const STAGE_LABEL = {', 'const _UNUSED_STAGE_LABEL = {'),
        ('{STAGE_LABEL[s]}', '{labelOf("lead_stage", s)}'),
    ],
    "components/subcon/SPKDetailSheet.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const SPK_LABEL = { draft: "Draft", active: "Aktif", completed: "Selesai", cancelled: "Batal" };\n'
         'const OPTIONS = Object.keys(SPK_LABEL);\n', ''),
        ('export default function SPKDetailSheet({ spk, open, canManage, onOpenChange, onChanged }) {\n'
         '  const [status, setStatus] = useState("");',
         'export default function SPKDetailSheet({ spk, open, canManage, onOpenChange, onChanged }) {\n'
         '  const { labelOf, options } = useReference();\n'
         '  const [status, setStatus] = useState("");'),
        ('toast.success(`Status SPK → ${SPK_LABEL[status]}.`);',
         'toast.success(`Status SPK → ${labelOf("spk_status", status)}.`);'),
        ('<StatusPill status={spk.status} label={SPK_LABEL[spk.status]} />',
         '<StatusPill status={spk.status} group="spk_status" />'),
        ('<SelectContent>{OPTIONS.map((o) => <SelectItem key={o} value={o}>{SPK_LABEL[o]}</SelectItem>)}</SelectContent>',
         '<SelectContent>{options("spk_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>'),
    ],
    "components/subcon/SPKPanel.js": [
        ('const SPK_LABEL = { draft: "Draft", active: "Aktif", completed: "Selesai", cancelled: "Batal" };\n', ''),
        ('<StatusPill status={s2.status} label={SPK_LABEL[s2.status]} />',
         '<StatusPill status={s2.status} group="spk_status" />'),
    ],
    "components/subcon/SubcontractorDetailSheet.js": [
        ('const SPK_LABEL = { draft: "Draft", active: "Aktif", completed: "Selesai", cancelled: "Batal" };\n', ''),
        ('<StatusPill status={s.status} label={SPK_LABEL[s.status]} />',
         '<StatusPill status={s.status} group="spk_status" />'),
    ],
    "components/tax/TaxRecordsPanel.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const TYPE_LABEL = { ppn: "PPN", pph: "PPh Final 4(2)", bphtb: "BPHTB" };\n'
         'const TYPE_FILTERS = [\n'
         '  { v: "all", l: "Semua jenis" },\n'
         '  { v: "ppn", l: "PPN Keluaran" },\n'
         '  { v: "pph", l: "PPh Final 4(2)" },\n'
         '  { v: "bphtb", l: "BPHTB" },\n'
         '];\n'
         'const STATUSES = ["pending", "reported", "paid"];\n', ''),
        ('export default function TaxRecordsPanel() {\n  const [rows, setRows] = useState([]);',
         'export default function TaxRecordsPanel() {\n'
         '  const { labelOf, options } = useReference();\n'
         '  const TYPE_FILTERS = [{ v: "all", l: "Semua jenis" },\n'
         '    ...options("tax_type").map((o) => ({ v: o.value, l: o.label }))];\n'
         '  const STATUSES = options("tax_status").map((o) => o.value);\n'
         '  const [rows, setRows] = useState([]);'),
        ('{TYPE_LABEL[r.type] || r.type}', '{labelOf("tax_type", r.type)}'),
        ('${TYPE_LABEL[edit.type] || edit.type}', '${labelOf("tax_type", edit.type)}'),
    ],
    "pages/AppointmentsPage.js": [
        ("IMPORT:" + IMPORT_REF_LABEL, None),
        ("IMPORT:" + IMPORT_REF_SELECT, None),
        ('const STATUS_FILTERS = [\n'
         '  { v: "all", l: "Semua status" },\n'
         '  { v: "scheduled", l: "Terjadwal" },\n'
         '  { v: "done", l: "Selesai" },\n'
         '  { v: "no_show", l: "Tidak Hadir" },\n'
         '  { v: "cancelled", l: "Batal" },\n'
         '];\n'
         'const TYPE_LABEL = { survey: "Survey", meeting: "Pertemuan", call: "Telepon" };\n', ''),
        ('        <Select value={statusFilter} onValueChange={setStatusFilter}>\n'
         '          <SelectTrigger data-testid={APPTS.statusFilter} className="h-9 w-44"><SelectValue /></SelectTrigger>\n'
         '          <SelectContent>\n'
         '            {STATUS_FILTERS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}\n'
         '          </SelectContent>\n'
         '        </Select>',
         '        <ReferenceSelect group="appointment_status" allowEmpty emptyLabel="Semua status"\n'
         '          className="h-9 w-44" testId={APPTS.statusFilter}\n'
         '          value={statusFilter === "all" ? "" : statusFilter}\n'
         '          onChange={(v) => setStatusFilter(v || "all")} />'),
        ('{TYPE_LABEL[a.type] || a.type}', '<RefLabel group="appointment_type" value={a.type} />'),
    ],
    "pages/ComplaintsPage.js": [
        ('const STATUS_LABEL = { open: "Terbuka", in_progress: "Dikerjakan", resolved: "Selesai" };\n', ''),
        ('<StatusPill status={c.status} label={STATUS_LABEL[c.status]} />',
         '<StatusPill status={c.status} group="complaint_status" />'),
    ],
    "pages/LeadsPage.js": [
        ('const SOURCE_LABEL = {\n'
         '  walk_in: "Walk-in", meta_ads: "Meta Ads", whatsapp: "WhatsApp", referral: "Referral",\n'
         '  website: "Website", manual: "Manual", import: "Import",\n'
         '};\n', ''),
        ('  const { options } = useReference();', '  const { options, labelOf } = useReference();'),
        ('{SOURCE_LABEL[l.source] || l.source}', '{labelOf("lead_source", l.source)}'),
    ],
    "pages/PermitsPage.js": [
        ('const STATUS_LABEL = {\n'
         '  not_started: "Belum Mulai", in_progress: "Proses", submitted: "Diajukan",\n'
         '  approved: "Disetujui", rejected: "Ditolak", expired: "Kadaluarsa",\n'
         '};\n', ''),
        ('<StatusPill status={p.status} label={STATUS_LABEL[p.status]} />',
         '<StatusPill status={p.status} group="permit_status" />'),
    ],
    # ---------------- E1: field enum masih input bebas ----------------
    "components/customers/FinancingDialogs.js": [
        ("IMPORT:" + IMPORT_REF_SELECT, None),
        ('          <div className="space-y-1.5"><Label htmlFor="bk">Bank</Label>\n'
         '            <Input id="bk" value={form.bank_name} onChange={(e) => set("bank_name", e.target.value)} placeholder="mis. Bank Negara Griya" /></div>',
         '          <div className="space-y-1.5"><Label htmlFor="bk">Bank</Label>\n'
         '            <ReferenceSelect group="financing_bank" value={form.bank_name}\n'
         '              onChange={(v) => set("bank_name", v)} testId="financing-bank-select"\n'
         '              placeholder="Pilih bank…" /></div>'),
    ],
    "components/finance/ApPanel.js": [
        ("IMPORT:" + IMPORT_REF_SELECT, None),
        ('            <Label htmlFor="vendor">Vendor</Label>\n'
         '            <Input id="vendor" value={vendor} data-testid="ap-bill-vendor"\n'
         '              onChange={(e) => setVendor(e.target.value)} placeholder="mis. CV Bangun Jaya" />',
         '            <Label htmlFor="vendor">Vendor</Label>\n'
         '            <ReferenceSelect group="vendor" value={vendor} testId="ap-bill-vendor"\n'
         '              onChange={setVendor} placeholder="Pilih vendor / subkontraktor…" />'),
    ],
    "components/procurement/AddPODialog.js": [
        ('<div className="space-y-1.5"><Label>Vendor</Label><Input value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="Nama vendor/toko" /></div>',
         '<div className="space-y-1.5"><Label>Vendor</Label>\n'
         '            <ReferenceSelect group="vendor" value={vendor} onChange={setVendor}\n'
         '              testId="po-form-vendor" placeholder="Pilih vendor / toko…" /></div>'),
    ],
    "components/subcon/AddSubcontractorDialog.js": [
        # PIC di master subkontraktor memang nama orang (kontak vendor) -> label dibuat jujur
        ('<div className="space-y-1.5"><Label>PIC</Label><Input value={form.pic_name} onChange={(e) => set("pic_name", e.target.value)} /></div>',
         '<div className="space-y-1.5"><Label>Nama PIC (kontak vendor)</Label><Input value={form.pic_name} onChange={(e) => set("pic_name", e.target.value)} placeholder="mis. Bpk. Andi" /></div>'),
    ],
    # ---------------- E4: input tanpa label ----------------
    "components/customers/AddCustomerDialog.js": [
        ('      <Input id={k} value={form[k]} onChange={(e) => set(k, e.target.value)} {...props} />',
         '      <Input id={k} aria-label={label} value={form[k]} onChange={(e) => set(k, e.target.value)} {...props} />'),
    ],
    "components/patterns/ReferenceSelect.js": [
        ('        <Input autoFocus value={custom} data-testid={testId}\n'
         '          placeholder={`${meta.label} baru`}',
         '        <Input autoFocus value={custom} data-testid={testId}\n'
         '          aria-label={`${meta.label} baru`}\n'
         '          placeholder={`${meta.label} baru`}'),
    ],
    "pages/ConstructionPage.js": [
        ('                        <Input data-testid={CONSTRUCTION.progressInput} type="number" min={0} max={100}\n'
         '                          className="h-8 w-24" value={edits[ph.id] ?? ph.progress}',
         '                        <Input data-testid={CONSTRUCTION.progressInput} type="number" min={0} max={100}\n'
         '                          aria-label={`Progres fase ${ph.name} (%)`}\n'
         '                          className="h-8 w-24" value={edits[ph.id] ?? ph.progress}'),
    ],
}


def add_import(src: str, imp: str) -> str:
    if imp.strip() in src:
        return src
    last = None
    for m in re.finditer(r'^import .*?;\n', src, re.M | re.S):
        last = m
    if not last:
        return imp + src
    return src[:last.end()] + imp + src[last.end():]


def main():
    bad = []
    for rel, pairs in EDITS.items():
        path = FE + rel
        src = open(path, encoding="utf-8").read()
        for old, new in pairs:
            if old.startswith("IMPORT:"):
                src = add_import(src, old[len("IMPORT:"):])
                continue
            n = src.count(old)
            if n != 1:
                bad.append(f"{rel}: pola {n}x (harus 1x): {old[:70]!r}")
                continue
            src = src.replace(old, new)
        open(path, "w", encoding="utf-8").write(src)
        print(f"OK  {rel} ({len(pairs)} suntingan)")
    if bad:
        print("\nGAGAL:")
        for b in bad:
            print("  - " + b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
