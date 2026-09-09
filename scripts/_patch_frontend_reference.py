"""Patch frontend: ganti daftar dropdown hardcode & input teks bebas -> registry SSOT.

Idempoten. Jalankan: python scripts/_patch_frontend_reference.py
"""
import pathlib
import sys

S = pathlib.Path("/app/frontend/src")

RS_IMPORT = 'import ReferenceSelect from "@/components/patterns/ReferenceSelect";'
USE_REF_IMPORT = 'import { useReference } from "@/context/ReferenceContext";'

PATCHES = [
    # ---------------- BoQ: satuan (teks bebas) + kategori (hardcode) ----------------
    ("components/boq/AddBoQItemDialog.js",
     'const CATS = ["Persiapan", "Struktur", "Arsitektur", "MEP", "Finishing", "umum"];\n'
     'const EMPTY = { cost_code: "", category: "Struktur", description: "", uom: "unit", quantity: "1", unit_price: "0" };',
     '// Daftar kategori & satuan TIDAK lagi hardcode di sini — sumbernya /api/reference (SSOT).\n'
     'const EMPTY = { cost_code: "", category: "struktur", description: "", uom: "unit", quantity: "1", unit_price: "0" };'),
    ("components/boq/AddBoQItemDialog.js",
     '<Select value={form.category} onValueChange={(v) => set("category", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>{CATS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>\n'
     '            </Select></div>',
     '<ReferenceSelect group="work_category" value={form.category}\n'
     '              onChange={(v) => set("category", v)} testId="boq-form-category" /></div>'),
    ("components/boq/AddBoQItemDialog.js",
     '<div className="space-y-1.5"><Label>Satuan (UOM)</Label><Input value={form.uom} onChange={(e) => set("uom", e.target.value)} placeholder="m3 / kg / m2" /></div>',
     '<div className="space-y-1.5"><Label>Satuan (UOM)</Label>\n'
     '            <ReferenceSelect group="uom" value={form.uom} onChange={(v) => set("uom", v)}\n'
     '              testId="boq-form-uom" /></div>'),

    # ---------------- Punch list: kategori + severity ----------------
    ("components/field/AddPunchDialog.js",
     'const CATS = ["arsitektur", "struktur", "MEP", "finishing", "lainnya"];\n', ''),
    ("components/field/AddPunchDialog.js",
     '<Select value={form.category} onValueChange={(v) => set("category", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>{CATS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>\n'
     '            </Select></div>',
     '<ReferenceSelect group="work_category" value={form.category}\n'
     '              onChange={(v) => set("category", v)} testId="punch-form-category" /></div>'),
    ("components/field/AddPunchDialog.js",
     '<Select value={form.severity} onValueChange={(v) => set("severity", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>\n'
     '                <SelectItem value="low">Rendah</SelectItem>\n'
     '                <SelectItem value="medium">Sedang</SelectItem>\n'
     '                <SelectItem value="high">Tinggi</SelectItem>\n'
     '              </SelectContent>\n'
     '            </Select></div>',
     '<ReferenceSelect group="punch_severity" value={form.severity}\n'
     '              onChange={(v) => set("severity", v)} testId="punch-form-severity" /></div>'),

    # ---------------- Buku harian: cuaca (teks bebas) ----------------
    ("components/field/AddDiaryDialog.js",
     '<div className="space-y-1.5"><Label>Cuaca</Label><Input value={form.weather} onChange={(e) => set("weather", e.target.value)} placeholder="mis. Cerah berawan" /></div>',
     '<div className="space-y-1.5"><Label>Cuaca</Label>\n'
     '            <ReferenceSelect group="weather" value={form.weather}\n'
     '              onChange={(v) => set("weather", v)} testId="diary-form-weather" /></div>'),

    # ---------------- CoA: tipe akun ----------------
    ("components/gl/AddAccountDialog.js",
     'const TYPES = [\n'
     '  { v: "asset", l: "Aset" }, { v: "liability", l: "Liabilitas" }, { v: "equity", l: "Ekuitas" },\n'
     '  { v: "revenue", l: "Pendapatan" }, { v: "expense", l: "Beban" },\n'
     '];\n', ''),
    ("components/gl/AddAccountDialog.js",
     '<Select value={form.type} onValueChange={(v) => set("type", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>{TYPES.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>\n'
     '            </Select></div>',
     '<ReferenceSelect group="account_type" value={form.type}\n'
     '              onChange={(v) => set("type", v)} testId="gl-form-type" /></div>'),

    # ---------------- Lead: sumber + minat tipe unit ----------------
    ("components/sales/AddLeadDialog.js",
     'const SOURCES = [\n'
     '  { v: "manual", l: "Manual" }, { v: "walk_in", l: "Walk-in" },\n'
     '  { v: "referral", l: "Referral" }, { v: "website", l: "Website" },\n'
     '  { v: "whatsapp", l: "WhatsApp" }, { v: "meta_ads", l: "Meta Ads" },\n'
     '];\n', ''),
    ("components/sales/AddLeadDialog.js",
     '<Select value={form.source} onValueChange={(v) => set("source", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>\n'
     '                {SOURCES.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}\n'
     '              </SelectContent>\n'
     '            </Select>',
     '<ReferenceSelect group="lead_source" value={form.source}\n'
     '              onChange={(v) => set("source", v)} testId="lead-form-source" />'),
    ("components/sales/AddLeadDialog.js",
     '<Input id="i" value={form.interest_unit_type} onChange={(e) => set("interest_unit_type", e.target.value)} placeholder="mis. Tipe 45" />',
     '<ReferenceSelect group="unit_type" value={form.interest_unit_type}\n'
     '              onChange={(v) => set("interest_unit_type", v)} testId="lead-form-unit-type"\n'
     '              placeholder="Pilih tipe unit yang diminati" />'),

    # ---------------- Perizinan: jenis + instansi (teks bebas) ----------------
    ("components/permits/AddPermitDialog.js",
     'const TYPES = ["KRK", "IMB", "PBG", "SLF", "AMDAL", "ADDENDUM", "LAINNYA"];\n', ''),
    ("components/permits/AddPermitDialog.js",
     '<Select value={form.type} onValueChange={(v) => set("type", v)}>\n'
     '              <SelectTrigger><SelectValue /></SelectTrigger>\n'
     '              <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>\n'
     '            </Select></div>',
     '<ReferenceSelect group="permit_type" value={form.type}\n'
     '              onChange={(v) => set("type", v)} testId="permit-form-type" /></div>'),
    ("components/permits/AddPermitDialog.js",
     '<Input value={form.authority} onChange={(e) => set("authority", e.target.value)} placeholder="mis. DPMPTSP" /></div>',
     '<ReferenceSelect group="permit_authority" value={form.authority}\n'
     '              onChange={(v) => set("authority", v)} testId="permit-form-authority"\n'
     '              placeholder="Pilih instansi" /></div>'),

    # ---------------- Subkontraktor: bidang (teks bebas) ----------------
    ("components/subcon/AddSubcontractorDialog.js",
     '<div className="space-y-1.5"><Label>Bidang</Label><Input value={form.specialty} onChange={(e) => set("specialty", e.target.value)} placeholder="Struktur / MEP / Finishing" /></div>',
     '<div className="space-y-1.5"><Label>Bidang</Label>\n'
     '            <ReferenceSelect group="subcon_specialty" value={form.specialty}\n'
     '              onChange={(v) => set("specialty", v)} testId="subcon-form-specialty" /></div>'),

    # ---------------- Material: satuan (teks bebas) ----------------
    ("pages/MaterialsPage.js",
     '<div className="space-y-1.5"><Label>Satuan</Label><Input value={form.uom} onChange={(e) => set("uom", e.target.value)} placeholder="sak / m3 / batang" /></div>',
     '<div className="space-y-1.5"><Label>Satuan</Label>\n'
     '            <ReferenceSelect group="uom" value={form.uom} onChange={(v) => set("uom", v)}\n'
     '              testId="material-form-uom" /></div>'),

    # ---------------- PO: satuan baris (teks bebas) ----------------
    ("components/procurement/AddPODialog.js",
     '<div className="col-span-3 sm:col-span-2"><Input className="h-9" value={l.uom} onChange={(e) => setLine(i, "uom", e.target.value)} placeholder="UOM" /></div>',
     '<div className="col-span-3 sm:col-span-2">\n'
     '                <ReferenceSelect group="uom" value={l.uom} onChange={(v) => setLine(i, "uom", v)}\n'
     '                  testId={`po-line-uom-${i}`} className="h-9" /></div>'),

    # ---------------- Generate unit: tipe (teks bebas) ----------------
    ("pages/ProjectsPage.js",
     '<Input value={form.type} onChange={(e) => set("type", e.target.value)} /></div>',
     '<ReferenceSelect group="unit_type" value={form.type}\n'
     '              onChange={(v) => set("type", v)} testId="unit-gen-type" /></div>'),
    ("pages/ProjectsPage.js",
     'const [form, setForm] = useState({ prefix: "B", type: "Tipe 36/72", price: "650000000", count: "3", start_index: "1" });',
     'const [form, setForm] = useState({ prefix: "B", type: "Tipe 45/90", price: "650000000", count: "3", start_index: "1" });'),

    # ---------------- Lead stage filter (hardcode 3 versi berbeda) ----------------
    ("pages/LeadsPage.js",
     'const STAGES = [\n'
     '  { id: "", label: "Semua" },\n'
     '  { id: "acquisition", label: "Akuisisi" },\n'
     '  { id: "nurturing", label: "Nurturing" },\n'
     '  { id: "appointment", label: "Appointment" },\n'
     '  { id: "booking", label: "Booking" },\n'
     '  { id: "won", label: "Menang" },\n'
     '];',
     '// Tahap lead TIDAK lagi hardcode (dulu 3 file punya daftar berbeda) — sumber: /api/reference.'),

    # ---------------- Omnichannel: template category & channel type & stages ----------------
    ("components/omni/TemplatesPanel.js",
     'const CATEGORIES = ["utility", "marketing", "authentication"];\n', ''),
    ("components/omni/BroadcastPanel.js",
     'const STAGES = ["acquisition", "nurturing", "appointment", "booking", "won"];\n'
     'const SCORES = ["hot", "warm", "cold"];\n', ''),
    ("components/omni/RulesPanel.js",
     'const STAGES = ["nurturing", "appointment", "booking"];\n', ''),
]

IMPORTS = [
    ("components/boq/AddBoQItemDialog.js", RS_IMPORT),
    ("components/field/AddPunchDialog.js", RS_IMPORT),
    ("components/field/AddDiaryDialog.js", RS_IMPORT),
    ("components/gl/AddAccountDialog.js", RS_IMPORT),
    ("components/sales/AddLeadDialog.js", RS_IMPORT),
    ("components/permits/AddPermitDialog.js", RS_IMPORT),
    ("components/subcon/AddSubcontractorDialog.js", RS_IMPORT),
    ("pages/MaterialsPage.js", RS_IMPORT),
    ("components/procurement/AddPODialog.js", RS_IMPORT),
    ("pages/ProjectsPage.js", RS_IMPORT),
    ("pages/LeadsPage.js", USE_REF_IMPORT),
    ("components/omni/TemplatesPanel.js", USE_REF_IMPORT),
    ("components/omni/BroadcastPanel.js", USE_REF_IMPORT),
    ("components/omni/RulesPanel.js", USE_REF_IMPORT),
]


def main():
    ok, skip, fail = 0, 0, []
    for rel, old, new in PATCHES:
        p = S / rel
        if not p.exists():
            fail.append(f"{rel}: file tidak ada")
            continue
        s = p.read_text()
        if old not in s:
            if new and new.strip() and new in s:
                skip += 1
            else:
                fail.append(f"{rel}: pola tidak ditemukan -> {old[:60]!r}")
            continue
        p.write_text(s.replace(old, new, 1))
        ok += 1
        print(f"  [OK] {rel}: {old[:52]!r}")
    for rel, imp in IMPORTS:
        p = S / rel
        s = p.read_text()
        if imp in s:
            continue
        marker = 'import api from "@/services/apiClient";'
        if marker in s:
            s = s.replace(marker, imp + "\n" + marker, 1)
        else:
            lines = s.split("\n")
            last = max(i for i, ln in enumerate(lines) if ln.startswith("import "))
            lines.insert(last + 1, imp)
            s = "\n".join(lines)
        p.write_text(s)
        print(f"  [OK] {rel}: + import")
    print(f"\napplied={ok} skipped={skip} failed={len(fail)}")
    for f in fail:
        print("  [FAIL]", f)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
