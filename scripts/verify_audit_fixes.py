#!/usr/bin/env python3
"""verify_audit_fixes — gate anti-kambuh untuk temuan AUDIT_SINTESIS Tahap 1–2 + fitur tahapan.

Tiap pemeriksaan menunjuk ID temuan. Statis (tanpa server) supaya bisa jalan di CI/pre-commit.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
B, F = ROOT / "backend", ROOT / "frontend" / "src"
errors = []


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def check(cond: bool, ident: str, msg: str):
    print(f"  [{'OK' if cond else 'ERROR'}] {ident}: {msg}")
    if not cond:
        errors.append(f"{ident}: {msg}")


print("VERIFY AUDIT FIXES\n" + "-" * 60)

# ---- WA-02 / DOC-01: field item termin
wre = read(B / "wa_reminder_engine.py")
check('item.get("paid_amount")' in wre and 'item.get("paid")' not in wre, "WA-02",
      "wa_reminder_engine membaca paid_amount pada item termin")
ar = read(B / "routers" / "ar_router.py")
check('it.get("paid_amount")' in ar and 'it.get("paid")' not in ar, "DOC-01",
      "invoice PDF kolom Dibayar membaca paid_amount per termin")

# ---- WA-03: riwayat = yang dikirim
m = re.search(r"def _render\(.*?\n(?:.*\n)*?    return (.*)\n", wre)
check(bool(m) and "reason" not in m.group(1), "WA-03", "_render tidak menempelkan cand['reason'] ke body")

# ---- WA-13: example wajib pada komponen BODY
wtm = read(B / "wa_templates_meta.py")
check('body_comp["example"] = {"body_text"' in wtm, "WA-13", "meta_components menyertakan example.body_text")
check("example_required" in wtm and "def example_values" in wtm, "WA-13",
      "submit menolak variabel tanpa contoh nilai (example_required)")

# ---- WA-04: validasi body ↔ variables di pintu simpan
omni = read(B / "routers" / "omnichannel_router.py")
check("def validate_variables" in wtm, "WA-04", "validate_variables ada di wa_templates_meta")
check(omni.count("wtm.validate_variables(") >= 2, "WA-04",
      "create & update template memanggil validate_variables")
check("variables_mismatch" in wtm, "WA-04", "submit menolak template yang body≠variables")

# ---- WA-01: satu template per jenis pengingat, variabelnya = vars kandidat
import seed_phase29 as sp  # noqa: E402
import settings_store as st  # noqa: E402
import wa_reminder_engine as eng  # noqa: E402
defaults = {k: spec["value"] for k, spec in st.DEFAULTS.items()}
codes = [defaults.get(k) for k in eng.TEMPLATE_KEYS.values()]
check(len(set(codes)) == len(codes) and None not in codes, "WA-01",
      f"lima jenis pengingat memakai template berbeda: {codes}")
seeded = {c: set(v) for c, _n, _cat, _b, v in sp.REMINDER_TEMPLATES}
check(all(c in seeded for c in codes), "WA-01", "semua template bawaan pengingat di-seed (ensure_reminder_templates)")
CAND_VARS = {
    "installment_due": {"nama", "termin", "nominal", "tanggal", "unit"},
    "installment_overdue": {"nama", "termin", "nominal", "tanggal", "unit"},
    "arrears_warning": {"nama", "unit", "nominal", "bulan", "terlama"},
    "warranty_expiring": {"nama", "bagian", "unit", "tanggal", "sisa"},
    "booking_fee_due": {"nama", "termin", "nominal", "tanggal", "unit"},
}
for kind, key in eng.TEMPLATE_KEYS.items():
    code = defaults.get(key)
    check(seeded.get(code, set()) <= CAND_VARS[kind], "WA-01",
          f"variabel template '{code}' ⊆ vars kandidat {kind}")
    body = next((b for c, _n, _cat, b, _v in sp.REMINDER_TEMPLATES if c == code), "")
    import wa_templates_meta as w  # noqa: E402
    check(w.validate_variables(body, list(seeded.get(code, []))) == "", "WA-04",
          f"template seed '{code}' lolos validate_variables")
check("ensure_reminder_templates" in read(B / "server.py"), "WA-01",
      "server startup memanggil ensure_reminder_templates untuk semua org (bukan hanya demo)")

# ---- WA-12: status template di layar Lead WA jujur
tp = read(F / "components" / "omni" / "TemplatesPanel.js")
check('t.status === "approved" ? "approved" : "pending"' not in tp, "WA-12",
      "TemplatesPanel tidak lagi memetakan rejected → pending")
check("meta_reason" in tp, "WA-12", "TemplatesPanel menampilkan alasan penolakan Meta")
check("examples" in read(F / "components" / "config" / "WaTemplateEditorDialog.js"), "WA-13", "editor template (Pusat Konfigurasi) punya kolom contoh nilai per variabel")

# ---- Fitur: tahapan progres pembangunan
check((B / "phase_templates.py").exists() and "phases/apply" in read(B / "routers" / "phase_template_router.py"),
      "PRJ-CFG", "endpoint terapkan template fase proyek ada")
pp = read(F / "pages" / "ProjectsPage.js")
pd = read(F / "components" / "projects" / "PhaseDialogs.js")
check('api.post("/construction/phases"' in pd and "ApplyPhaseTemplateDialog" in pp, "PRJ-CFG",
      "layar proyek bisa MEMBUAT fase (POST /construction/phases) & menerapkan template")
cc = read(F / "pages" / "ConfigCenterPage.js")
check("PhaseTemplatePanel" in cc and "SurveyStagePanel" in cc, "CFG-UI",
      "Pusat Konfigurasi punya tab Tahapan Pembangunan & Tahapan Survey")

# ---- Fitur: tahapan survey
sr = read(B / "routers" / "survey_router.py")
check("checklist_for_new_survey" in sr and "unfinished_required" in sr, "SURVEY-CFG",
      "survey baru menyalin tahapan; finalisasi menolak poin wajib yang belum dinilai")
check("DEFAULT_CHECKLIST" not in sr, "SURVEY-CFG", "checklist datar hardcode dihapus dari survey_router (satu kebenaran)")
spn = read(F / "components" / "appointments" / "SurveyPanel.js")
check("SurveyStepper" in spn and "current_stage" in spn, "SURVEY-CFG", "form survey berjalan tahap demi tahap")

# ---- Gate ikut dijalankan
gates = read(ROOT / "scripts" / "run_all_gates.sh")
check("verify_field_names.py" in gates and "verify_audit_fixes.py" in gates, "GATE",
      "kedua gate terdaftar di run_all_gates.sh")

# ---- Tahap 3 (WA-05..09, WA-14) & Tahap 4 (RBAC-02/03) — 2026-09-06 sesi 2
gov_ok = (B / "wa_template_governance.py").exists()
check(gov_ok, "WA-14", "modul tata kelola template (usage_map, reminder_mapping, category_hints) ada")
check("/wa-templates/reminder-mapping" in omni and "gov.usage_map(" in omni, "WA-14",
      "endpoint pemetaan pengingat & pemakaian template ada di satu router")
check("Status 'approved' tidak bisa diberikan dari layar" in omni, "WA-05", "PUT status=approved ditolak")
check("frozen_fields_changed" in omni, "WA-06", "isi template APPROVED Meta dibekukan")
check("category_hints" in omni, "WA-07", "peringatan kategori↔isi saat simpan (tidak memblokir)")
check("masih dipakai oleh" in omni, "WA-08", "hapus template terpakai → 409 dengan lokasi pemakaian")
check("sudah dipakai template" in omni and "_{new_id()[:4]}" not in omni, "WA-09",
      "kode duplikat → 409, bukan sufiks acak diam-diam")
s22 = read(B / "seed_phase22.py")
check('("welcome", "Sapaan Awal", "marketing"' in s22 and '("price_info", "Info Harga", "marketing"' in s22,
      "WA-07", "seed welcome/price_info berkategori marketing")
check("api.post(" not in tp and "api.put(" not in tp and "api.delete(" not in tp, "WA-14",
      "layar Lead WA › Template hanya membaca (tidak lagi membuat/mengubah/menghapus)")
meta_panel = read(F / "components" / "config" / "WaTemplateMetaPanel.js")
check("WaTemplateEditorDialog" in meta_panel and "WaReminderMappingCard" in meta_panel, "WA-14",
      "Pusat Konfigurasi › Template = isi + status Meta + pemetaan pengingat dalam satu layar")
import rbac  # noqa: E402
import rbac_labels as rl  # noqa: E402
missing = [a for a in rbac.KNOWN_ACTIONS if a not in rl.ACTION_META]
check(not missing, "RBAC-02", f"setiap aksi KNOWN_ACTIONS punya ACTION_META (kurang: {missing})")
check('"action_meta"' in read(B / "routers" / "admin_router.py"), "RBAC-02", "GET /admin/permissions mengirim action_meta")
ap = read(F / "pages" / "AdminPermissions.js")
check("server?.action_meta" in ap and "permsActionLegend" in ap, "RBAC-02", "layar Hak Akses memakai label & legenda aksi dari server")
check('<b>{labelOf(c.resource)}</b>' in ap, "RBAC-03", "label manusia tampil lebih dulu dari kode mesin")

print("-" * 60)
if errors:
    print(f"AUDIT FIXES FAILED: {len(errors)} pemeriksaan gagal")
    sys.exit(1)
print("AUDIT FIXES PASSED")
