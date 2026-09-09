#!/usr/bin/env python3
"""mutasi_39b.py — uji-mutasi untuk perubahan gate Fase 39b.

Sebuah gate yang TIDAK BISA GAGAL tidak menjaga apa pun. Skrip ini merusak kode secara
sengaja (satu cacat per kali), memastikan gate yang bersangkutan MEMERAH, lalu memulihkan
berkasnya. Dipakai untuk membuktikan tiga perubahan gate di Fase 39b tetap bergigi:

  M1  audit_forms_deep  — dropdown SSOT dikembalikan jadi input bebas   -> harus FAIL (E1)
  M2  audit_forms_deep  — peta label enum hardcode ditambahkan kembali  -> harus FAIL (E5)
  M3  audit_forms_deep  — tenggat memakai type=text                     -> harus FAIL (E3 lolos, E1/E5 tidak)
  M4  forensic_audit    — router berhenti meng-import settings_store    -> harus FAIL (HIGH kembali)
  M5  forensic_audit    — koleksi baru tanpa endpoint tulis sama sekali -> harus FAIL (CRITICAL)
  M6  endpoint_sweep    — parameter wajib tak bisa di-resolve           -> harus FAIL
  M7  verify_39b        — checklist dicabut dari layar Lead             -> harus FAIL
  M8  verify_39b        — input berkas kembali dipakai bersama          -> harus FAIL
  M9  verify_39b        — pemeriksaan bukti kembar (isi sama) dihapus   -> harus FAIL
  M10 verify_39b        — konteks tidak lagi diturunkan backend         -> harus FAIL
"""
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/app")
results = []


def run(script: str) -> tuple:
    # Tunggu backend siap lebih dulu. Beberapa mutasi menyentuh berkas backend sehingga
    # uvicorn memuat ulang; tanpa jeda ini, gate bisa dijalankan saat aplikasi belum siap
    # dan memerah/menghijau karena ALASAN YANG SALAH (pernah terjadi pada M7 — hasil
    # uji-mutasi jadi tidak bisa dipercaya).
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://localhost:8001/api/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                       capture_output=True, text=True, timeout=300)
    return p.returncode, (p.stdout + p.stderr)


def mutate(label: str, path: str, old: str, new: str, script: str, expect_in_output=None,
           blocking: bool = True):
    """`blocking=False`: temuan yang memang hanya PERINGATAN (E2/E3) — yang diuji adalah
    apakah cacatnya TERDETEKSI di keluaran, bukan apakah gate memerah."""
    f = ROOT / path
    src = f.read_text()
    if old not in src:
        results.append((label, "TIDAK BISA DIUJI", f"pola tidak ditemukan di {path}"))
        return
    f.write_text(src.replace(old, new, 1))
    try:
        code, out = run(script)
    finally:
        f.write_text(src)
    detected = expect_in_output is None or expect_in_output in out
    ok = detected and (code != 0 if blocking else True)
    detail = ("gate memerah seperti seharusnya" if blocking
              else "cacat terdeteksi sebagai peringatan") if ok else (
        f"cacat TIDAK TERTANGKAP (exit={code}, pola '{expect_in_output}' "
        f"{'ada' if detected else 'tidak ada'} di keluaran) :: "
        f"...{out.strip()[-320:]}")
    results.append((label, "PASS" if ok else "FAIL", detail))
    # Pastikan gate kembali hijau setelah pemulihan (bukti pemulihan berhasil).
    code2, _ = run(script)
    results.append((f"{label} (pulih)", "PASS" if code2 == 0 else "FAIL",
                    "hijau kembali" if code2 == 0 else "MASIH MERAH setelah dipulihkan"))


def main():
    mutate("M1 dropdown SSOT -> input bebas",
           "frontend/src/components/config/PriceComponentPanel.js",
           '<ReferenceSelect group="gl_account" value={form.gl_account || ""}\n'
           '                    testId={CONFIG.priceFormAccount} placeholder="Pilih akun dari bagan akun…"\n'
           '                    onChange={(v) => setForm({ ...form, gl_account: v })} />',
           '<Input id="pc-acc" value={form.gl_account || ""} placeholder="4-1100"\n'
           '                    onChange={(e) => setForm({ ...form, gl_account: e.target.value })} />',
           "audit_forms_deep.py", "E1 — Harus dropdown (BLOCKING): 1")

    mutate("M2 peta label enum hardcode",
           "frontend/src/components/config/SettingsPanel.js",
           "function valueText(row) {",
           'const ORIGIN_LABEL = { default: "Bawaan sistem", org: "Diubah organisasi", '
           'project: "Khusus proyek" };\n\nfunction valueText(row) {',
           "audit_forms_deep.py", "E5 — Vocabulary enum hardcode (BLOCKING): 1")

    mutate("M3 tenggat pakai type=text (peringatan)",
           "frontend/src/components/work/CreateTaskDialog.js",
           '<Input id="nt-due" type="datetime-local" value={form.due}',
           '<Input id="nt-due" type="text" value={form.due}',
           "audit_forms_deep.py", "E3 — Sebaiknya type=date: 1", blocking=False)

    mutate("M4 router lepas dari settings_store",
           "backend/routers/settings_router.py",
           "import settings_store as cfg",
           "import reference as cfg  # mutasi: router tak lagi menyentuh settings_store",
           "forensic_audit.py", "[HIGH] settings")

    mutate("M5 koleksi tanpa endpoint tulis",
           "backend/core_utils.py", "def now_iso(",
           "async def _mutasi_orphan():\n"
           "    return await db.zz_koleksi_yatim.find({}).to_list(1)\n\n\ndef now_iso(",
           "forensic_audit.py", "TIDAK BISA DIINPUT")

    mutate("M6 parameter wajib tak bisa di-resolve",
           "scripts/audit_endpoint_sweep.py",
           'lead_id = _first_id(headers, "/leads?limit=1")',
           'lead_id = _first_id(headers, "/koleksi-tidak-ada?limit=1")',
           "audit_endpoint_sweep.py", "tidak bisa di-resolve")

    # ---- mutasi untuk GATE BARU verify_39b.py (checklist dokumen) ----
    # M7 mengikuti PEMINDAHAN Fase 40b: checklist kini hidup di HALAMAN kanonik
    # `/leads/:id` (dulu di drawer `components/sales/LeadDetail.js` yang sudah dihapus).
    mutate("M7 checklist dicabut dari layar Lead",
           "frontend/src/pages/LeadProfilePage.js",
           '<DocChecklist entityType="lead" entityId={id} onChanged={refresh} />',
           "<p>mutasi: checklist dicabut</p>",
           "verify_39b.py", "FAIL  checklist terpasang di layar Lead")

    mutate("M8 input berkas kembali dipakai bersama (gagal senyap)",
           "frontend/src/components/patterns/DocChecklist.js",
           "                        data-testid={DOCCHK.uploadInput} data-requirement={req.code}",
           "                        data-testid={DOCCHK.uploadInput}",
           "verify_39b.py", "FAIL  input berkas PER BARIS")
    mutate("M9 pemeriksaan bukti kembar (isi sama) dihapus",
           "backend/doc_registry.py",
           "    dup = await _same_evidence_status(payload, meta, org)",
           "    dup = None  # mutasi: pemeriksaan bukti kembar dilewati",
           "verify_39b.py", "FAIL  ISI berkas yang sama ditolak 400")

    mutate("M10 konteks tidak lagi diturunkan backend",
           "backend/routers/docreq_router.py",
           "    if not ctx:\n        ctx = await docreg.contexts_for(entity_type, entity_id, _org(user))",
           "    # mutasi: konteks tidak diturunkan",
           "verify_39b.py", "FAIL  backend menurunkan konteks sendiri")

    print("\n" + "=" * 72)
    print("UJI-MUTASI GATE FASE 39b")
    print("=" * 72)
    bad = 0
    for label, status, detail in results:
        mark = "  OK  " if status == "PASS" else "  !!  "
        if status != "PASS":
            bad += 1
        print(f"{mark}{status:16s} {label} — {detail}")
    print("-" * 72)
    if bad:
        print(f"UJI-MUTASI GAGAL: {bad} mutasi tidak tertangkap gate")
        return 1
    print(f"UJI-MUTASI LULUS: {len(results)} pemeriksaan (semua mutasi tertangkap & pulih)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
