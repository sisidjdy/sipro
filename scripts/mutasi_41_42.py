#!/usr/bin/env python3
"""mutasi_41_42.py — uji-mutasi untuk gate Fase 41 (jam tahap & SLA) dan Fase 42 (mitra & fee).

Gate yang tidak bisa gagal tidak menjaga apa pun. Skrip ini MERUSAK kode dengan sengaja
(satu cacat per kali), memastikan gate yang bersangkutan MEMERAH pada temuan yang tepat,
lalu memulihkan berkasnya dan memastikan gate HIJAU kembali.

Setiap mutasi di bawah adalah cacat yang REALISTIS — bukan sintaks yang dirusak — dan
mewakili satu janji yang gate klaim dijaganya:

  Fase 41 (verify_41.py)
    M1  jam tahap menyimpan tahap yang SALAH (semua baris jadi tidak sinkron)
    M2  pintu transisi tidak MERESET jam tahap (umur tahap membeku)
    M3  filter SLA tak dikenal diabaikan diam-diam (pemakai tertipu hasil "semua")
    M4  satu daftar menuliskan ambang SLA-nya sendiri lagi (72 jam hardcode)
    M5  AgingCell punya ambang bawaan lagi (klaim "lewat SLA" tanpa dasar kebijakan)
    M6  Pusat Konfigurasi jadi hiasan: ubah SLA tidak berlaku ke baris yang ada
    M7  tautan drill laporan menunjuk rute yang tidak ada (angka tak bisa ditelusuri)
    M8  RBAC bocor: sales boleh menjalankan pemeliharaan jam tahap

  Fase 42 (verify_partner.py)
    M9  menu "Mitra & Fee" ditutup lagi jadi "Segera Hadir"
    M10 rute alias lama `/marketing-fee` dihapus (bookmark & tautan lama mati)
    M10b alias hidup tapi tidak mendarat di tab Tagihan Fee (dua pintu untuk satu urusan)
    M11 grup SSOT `partner_tax_type` dicabut (aturan fee ber-pajak mati 500, bukan 400)
    M12 penjaga idempoten dicabut: satu pemicu bisa menerbitkan tagihan fee DUA KALI
    M13 RBAC bocor: sales boleh mendaftarkan mitra (atribusi & uang tak terkendali)
    M14 INV-09 tanpa penjelasan: fee ditolak tanpa menyebut aturan (tak bisa ditindak)
    M15 layar menyalin lagi matriks RBAC (tombol beda pendapat dengan server)
    M16 tombol "Ajukan Fee" lepas dari izin (CTA mati untuk finance)

  Gate global RBAC UI (verify_rbac_ui.py)
    M17 satu layar kembali menyalin daftar peran RBAC
    M18 layar memakai izin yang SALAH KETIK (tombol hilang selamanya tanpa error)
    M19 pengecualian nama peran kehilangan penjelasannya (pengecualian diam-diam)
    M20 RBAC backend bocor: sales boleh membuat proyek (bukti API memerah)
    M21 tab "Tagihan Fee" tampil untuk peran tanpa izin fee (tab mati, isinya 403)

Pakai: `python3 scripts/mutasi_41_42.py`. Exit !=0 bila ada mutasi yang TIDAK tertangkap.
"""
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path("/app")
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
results = []

STAGE_CLOCK = "backend/stage_clock.py"
LIFECYCLE = "backend/lead_lifecycle.py"
RBAC = "backend/rbac.py"
REF41 = "backend/reference_p41.py"
PENGINE = "backend/partner_engine.py"
PFEE = "backend/partner_fee.py"
NAV = "frontend/src/config/navigationConfig.js"
APP = "frontend/src/App.js"
LEADS = "frontend/src/pages/LeadsPage.js"
CELL = "frontend/src/components/patterns/AgingCell.js"
PREVIEW = "frontend/src/components/partners/FeePreviewDialog.js"
FEESPANEL = "frontend/src/components/marketingFee/FeesPanel.js"
JOURNAL = "frontend/src/components/gl/JournalPanel.js"
PERMITS = "frontend/src/pages/PermitsPage.js"
CONSTRUCTION = "frontend/src/pages/ConstructionPage.js"
PARTNERSPAGE = "frontend/src/pages/PartnersPage.js"

PERM_NOTE = (
    "  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di\n"
    "  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode\n"
    "  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang\n"
    "  // padahal peran itu berhak).\n"
)


def wait_backend():
    """Mutasi backend membuat uvicorn memuat ulang. Tanpa jeda ini gate bisa
    memerah/menghijau karena ALASAN YANG SALAH (server belum siap)."""
    for _ in range(120):
        try:
            with urllib.request.urlopen("http://localhost:8001/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)


def run(script: str) -> tuple:
    wait_backend()
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                       capture_output=True, text=True, timeout=900)
    return p.returncode, (p.stdout + p.stderr)


# ------------------------------------------------------- pembersih efek samping
def fee_ids() -> set:
    return {f["id"] for f in db.marketing_fees.find({}, {"_id": 0, "id": 1})}


def drop_new_fees(before: set):
    """M12 sengaja membuat tagihan fee KEDUA. Tagihan itu dibuang lagi supaya uji-mutasi
    tidak meninggalkan utang fee palsu yang membuat gate invarian keuangan memerah."""
    extra = list(fee_ids() - before)
    if extra:
        db.marketing_fees.delete_many({"id": {"$in": extra}})


def drop_sales_partner():
    """M13 membuat sales berhasil mendaftarkan mitra. Mitra itu dihapus lagi."""
    db.agents.delete_many({"name": "Mitra oleh Sales"})


def mutate(label: str, edits: list, script: str, expect: str = None,
           before=None, after=None):
    """edits: [(path, old, new)] — satu mutasi boleh menyentuh beberapa berkas.

    `before`/`after`: pembersih keadaan database, dipakai untuk mutasi yang efeknya
    MENULIS data (mis. tagihan fee kedua) supaya suite lain tidak ikut kotor.

    Bila argumen baris perintah diberikan (mis. `mutasi_41_42.py M7 M12`), hanya mutasi
    dengan label berawalan itu yang dijalankan — mempercepat penyelidikan satu temuan
    tanpa menunggu seluruh mutasi (tiap mutasi = 2 kali jalan gate).
    """
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    if only and not any(label.split()[0] == o for o in only):
        return
    state = before() if before else None
    originals = {}
    for path, old, new in edits:
        f = ROOT / path
        src = f.read_text()
        if old not in src:
            for p, s in originals.items():
                (ROOT / p).write_text(s)
            results.append((label, "TIDAK BISA DIUJI", f"pola tidak ditemukan di {path}"))
            return
        originals[path] = src
        f.write_text(src.replace(old, new, 1))
    try:
        code, out = run(script)
    finally:
        for p, s in originals.items():
            (ROOT / p).write_text(s)
        if after:
            after(state)
    detected = expect is None or expect in out
    ok = detected and code != 0
    detail = "gate memerah pada temuan yang tepat" if ok else (
        f"cacat TIDAK TERTANGKAP (exit={code}, pola '{expect}' "
        f"{'ada' if detected else 'TIDAK ada'}) :: ...{out.strip()[-320:]}")
    results.append((label, "PASS" if ok else "FAIL", detail))
    code2, out2 = run(script)
    results.append((f"{label} (pulih)", "PASS" if code2 == 0 else "FAIL",
                    "hijau kembali" if code2 == 0 else
                    f"MASIH MERAH setelah dipulihkan :: ...{out2.strip()[-240:]}"))


def main():
    # ------------------------------------------------------------------ Fase 41
    mutate("M1 jam tahap menyimpan tahap yang salah",
           [(STAGE_CLOCK, "        CLOCK_STAGE: stage, CLOCK_SRC: source,",
             "        CLOCK_STAGE: None, CLOCK_SRC: source,")],
           # Ditangkap di PINTU TRANSISI, bukan di pemeriksaan sinkron seluruh koleksi:
           # `reconcile` hanya menyentuh baris yang jam tahapnya sudah menyimpang, jadi saat
           # gate mulai (semua baris masih sinkron) tidak ada baris yang ditulis ulang.
           # Cacatnya baru terlihat pada transisi NYATA berikutnya — dan di situlah gate
           # menagihnya.
           "verify_41.py", "FAIL  jam tahap menyebut tahap barunya")

    mutate("M2 transisi tidak mereset jam tahap (umur tahap membeku)",
           [(LIFECYCLE,
             '    updates.update(await clock.patch_for("lead", to_stage, org_id=org, at=ts))',
             '    updates.update(await clock.patch_for(\n'
             '        "lead", to_stage, org_id=org, at=lead.get("stage_entered_at") or ts))')],
           "verify_41.py", "FAIL  stage_entered_at berubah saat pindah tahap")

    mutate("M3 filter SLA tak dikenal diabaikan diam-diam",
           [(STAGE_CLOCK,
             "    if v not in SLA_FILTERS:\n"
             '        query["id"] = {"$in": []}\n'
             "        return query",
             "    if v not in SLA_FILTERS:\n        return query")],
           "verify_41.py", "FAIL  filter SLA tak dikenal → hasil kosong")

    mutate("M4 daftar menuliskan ambang SLA sendiri lagi (72 jam hardcode)",
           [(LEADS, "slaHours={l.stage_sla_hours} state={l.sla_state} />,",
             "slaHours={72} state={l.sla_state} />,")],
           "verify_41.py", "FAIL  LeadsPage.js tidak menulis ambang SLA sendiri")

    mutate("M5 AgingCell punya ambang SLA bawaan lagi",
           [(CELL,
             "export default function AgingCell({ ageHours, stageAgeHours, slaHours, "
             "state, className }) {",
             "export default function AgingCell({ ageHours, stageAgeHours, slaHours = 72, "
             "state, className }) {")],
           "verify_41.py", "FAIL  AgingCell tidak punya ambang bawaan")

    mutate("M6 Pusat Konfigurasi jadi hiasan (ubah SLA tidak berlaku ke baris)",
           [(STAGE_CLOCK,
             '    for ent, sp in ENTITIES.items():\n'
             '        if sp["sla_key"] == key:\n'
             "            return await resync(ent, org_id=org_id)\n"
             "    return {}",
             "    return {}")],
           "verify_41.py", "FAIL  baris memakai ambang SLA terbaru")

    mutate("M7 tautan drill laporan menunjuk rute yang tidak ada",
           [(STAGE_CLOCK, '    path = sp["list_path"]',
             '    path = "/laporan-umur-tahap-lama"')],
           "verify_41.py", "FAIL  drill '/laporan-umur-tahap-lama")

    mutate("M8 RBAC bocor: sales boleh memelihara jam tahap",
           [(RBAC, '    "sales_manager": {"documents": ["verify"]},',
             '    "sales_manager": {"documents": ["verify"]},\n'
             '    "sales": {"aging": ["manage"]},')],
           "verify_41.py", "FAIL  sales TIDAK boleh menjalankan pemeliharaan")

    # ------------------------------------------------------------------ Fase 42
    mutate("M9 menu Mitra & Fee ditutup lagi jadi 'Segera Hadir'",
           [(NAV,
             '{ id: "partners", label: "Mitra & Fee", icon: Handshake, path: "/partners",',
             '{ id: "partners", label: "Mitra & Fee", icon: Handshake, comingSoon: true,')],
           "verify_partner.py", "FAIL  menu mitra TIDAK lagi 'Segera Hadir'")

    mutate("M10 rute alias lama /marketing-fee dihapus",
           [(APP, '            <Route path="/marketing-fee"\n'
                  '              element={<Navigate to="/partners?hub=tagihan" replace />} />\n',
             "")],
           "verify_partner.py", "FAIL  rute alias /marketing-fee TETAP hidup")

    mutate("M10b alias hidup tapi tidak mendarat di tab Tagihan Fee (dua pintu lagi)",
           [(APP, 'element={<Navigate to="/partners?hub=tagihan" replace />} />',
             'element={<Navigate to="/partners" replace />} />')],
           "verify_partner.py",
           "FAIL  alias /marketing-fee MENGALIHKAN ke tab Tagihan Fee (satu pintu)")

    mutate("M11 grup SSOT partner_tax_type dicabut (aturan fee ber-pajak mati 500)",
           [(REF41, '    "partner_tax_type": {', '    "partner_tax_type_DICABUT": {')],
           "verify_partner.py", "FAIL  tarif PPh di luar batas ditolak")

    mutate("M12 penjaga idempoten dicabut: satu pemicu bisa menagih dua kali",
           [(PENGINE,
             '         "trigger": trigger, "status": {"$in": mfee_open_statuses()}}, {"_id": 0})',
             '         "trigger": "__tidak_pernah_ada__", '
             '"status": {"$in": mfee_open_statuses()}}, {"_id": 0})')],
           "verify_partner.py", "FAIL  pemicu yang sama TIDAK bisa menerbitkan tagihan kedua",
           before=fee_ids, after=drop_new_fees)

    mutate("M13 RBAC bocor: sales boleh mendaftarkan mitra",
           [(RBAC, '    "sales_manager": {"documents": ["verify"]},',
             '    "sales_manager": {"documents": ["verify"]},\n'
             '    "sales": {"partners": ["create"]},')],
           "verify_partner.py", "FAIL  sales TIDAK boleh mendaftarkan mitra",
           after=lambda _s: drop_sales_partner())

    mutate("M14 INV-09 ditolak tanpa menjelaskan aturannya",
           [(PFEE,
             '        return None, ("Tidak ada aturan fee yang berlaku untuk mitra/proyek/'
             'tipe unit ini pada "\n'
             '                      f"pemicu \'{(ctx or {}).get(\'trigger\')}\'. '
             'Buat aturan fee dulu "\n'
             '                      "(INV-09: tidak ada fee tanpa aturan).")',
             '        return None, "Fee tidak dapat dihitung untuk kombinasi ini."')],
           "verify_partner.py",
           "FAIL  tanpa aturan berlaku → fee DITOLAK dengan alasan (INV-09)",
           before=fee_ids, after=drop_new_fees)

    mutate("M15 layar menyalin lagi matriks RBAC (tombol beda pendapat dengan server)",
           [(PREVIEW, '  const canIssue = can("marketing_fee", "create");',
             '  const canIssue = ["owner", "super_admin", "sales_manager", "marketing_admin",\n'
             '    "dm_supervisor", "finance", "finance_manager"].includes(user?.role);')],
           "verify_partner.py",
           "FAIL  FeePreviewDialog.js tidak menyalin matriks RBAC ke layar")

    mutate("M16 tombol Ajukan Fee lepas dari izin (CTA mati untuk finance)",
           [(FEESPANEL, '  const canSubmit = can("marketing_fee", "create");',
             "  const canSubmit = true;")],
           "verify_partner.py",
           'FAIL  FeesPanel.js memakai izin efektif can("marketing_fee", "create")')

    # ------------------------------------------- gate global RBAC UI (verify_rbac_ui.py)
    mutate("M17 satu layar kembali menyalin daftar peran RBAC",
           [(JOURNAL,
             "  const { can } = useAuth();\n" + PERM_NOTE
             + '  const canManage = can("gl", "create");',
             "  const { user } = useAuth();\n"
             '  const canManage = ["owner", "super_admin", "finance"].includes(user?.role);')],
           "verify_rbac_ui.py", "FAIL  tidak ada layar yang menyalin daftar peran RBAC")

    mutate("M18 layar memakai izin yang SALAH KETIK (tombol hilang tanpa error)",
           [(PERMITS, '  const canCreate = can("permits", "create");',
             '  const canCreate = can("permit", "create");')],
           "verify_rbac_ui.py", 'FAIL  izin can("permit", "create") dipaksakan backend')

    mutate("M19 pengecualian nama peran kehilangan penjelasannya",
           [(CONSTRUCTION, '// PENGECUALIAN SAH dari aturan "jangan salin matriks RBAC": ini BUKAN',
             "// catatan: ini BUKAN")],
           "verify_rbac_ui.py",
           "FAIL  pengecualian 'pages/ConstructionPage.js' menjelaskan alasannya di berkasnya")

    mutate("M20 RBAC backend bocor: sales boleh membuat proyek",
           [(RBAC, '    "sales_manager": {"documents": ["verify"]},',
             '    "sales_manager": {"documents": ["verify"]},\n'
             '    "sales": {"projects": ["create"]},')],
           "verify_rbac_ui.py", "FAIL  sales -> POST /projects = 403")

    mutate("M21 tab Tagihan Fee tampil untuk peran tanpa izin fee (tab mati)",
           [(PARTNERSPAGE,
             '    seeFees && { key: "tagihan", label: "Tagihan Fee", icon: Banknote,'
             " content: <FeesPanel /> },",
             '    { key: "tagihan", label: "Tagihan Fee", icon: Banknote,'
             " content: <FeesPanel /> },")],
           "verify_partner.py",
           "FAIL  tab Tagihan Fee hanya tampil bila peran boleh membaca tagihan fee")

    print("\n" + "=" * 78)
    print("UJI-MUTASI GATE FASE 41 (jam tahap & SLA) + FASE 42 (mitra & fee)")
    print("=" * 78)
    bad = 0
    for label, status, detail in results:
        print(f"  {status:16} {label} — {detail}")
        if status != "PASS":
            bad += 1
    print("=" * 78)
    if bad:
        print(f"UJI-MUTASI GAGAL: {bad} pemeriksaan tidak lulus "
              "(cacat lolos atau gate tidak pulih)")
        sys.exit(1)
    print(f"UJI-MUTASI LULUS: {len(results)} pemeriksaan — semua gate bergigi & pulih")


if __name__ == "__main__":
    main()
