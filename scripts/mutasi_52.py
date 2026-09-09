#!/usr/bin/env python3
"""mutasi_52.py — UJI-MUTASI Fase 52: membuktikan GATE 44 BERGIGI.

Cara kerja: satu per satu aturan Fase 52 dimatikan di kode (mutan), lalu
`scripts/verify_panel_resilience.py` dijalankan. Gate yang tetap HIJAU saat aturannya
dimatikan berarti gate itu tidak menguji apa pun — **LOLOS adalah cacat perangkat uji**,
bukan kelulusan produk.

Yang dijaga Fase 52 (dan karena itu dimutasi di sini):
  * pemuat tahan-banting `utils/panelLoad.js` (allSettled, saringan pesan izin internal,
    lencana jujur `undefined`, daftar sumber yang tidak disertakan);
  * kartu keadaan panel `PanelDenied/PanelUnavailable/PanelStateView`;
  * halaman profil lead & pelanggan: hanya permintaan PRIMER yang boleh mematikan halaman;
  * tab yang ditolak bercerita jujur, tombol yang pasti 403 disembunyikan lewat `can()`;
  * peta menu: daftar "belum dibangun" DIDERIVASI dari `navigationConfig`;
  * RBAC: keuangan boleh MEMBACA appointments, tidak menjadwalkan; 403 lingkup baris
    ("bukan lead Anda") tetap berbeda dari 403 izin peran.

## Perangkat uji (mewarisi pelajaran mahal dari `mutasi_51.py`, jangan dikembalikan)

1. **Menunggu reload secara DETERMINISTIK.** `time.sleep(6)` buta pernah melahirkan dua
   kebohongan: gate berjalan saat backend belum siap (dicatat "TERTANGKAP" tanpa pernah
   menguji aturannya) atau berjalan sebelum reload dimulai (dicatat "LOLOS" padahal kodenya
   masih utuh). Di sini PID proses ANAK `uvicorn` ditunggu berganti lalu `/api/health` hidup.
2. **Hasil ditulis SEGERA** ke `memory/gatelogs/mutasi_52_hasil.tsv`; `--ringkas` menyusun
   laporannya walau run dipecah atau terputus di tengah.
3. **Snapshot kode bersih** di `memory/mutasi52_snapshot/` + `--pulihkan`, supaya kode mutan
   tidak pernah tertinggal di repo bila proses dibunuh lingkungan.
4. **Jejak DATA dibersihkan.** Gate 44 memang MENCOBA `POST /api/appointments` sebagai
   keuangan (harus 403). Di bawah mutan M35 percobaan itu BERHASIL, dan satu jadwal survei
   palsu ikut menaikkan TAHAP lead, melahirkan tugas Work Hub, dan menulis aktivitas. Karena
   itu setiap mutasi ditutup dengan pembersihan: baris baru dibuang dan tahap lead
   dikembalikan seperti sebelum run.
5. **Matriks izin dipulihkan.** Gate 44 sendiri mencabut lalu memulihkan izin lewat API
   resmi (D6..D8); mutasi database di bawah menulis langsung ke `permission_settings`.
   Dokumen matriks disalin sebelum run dan dipulihkan di akhir.

Pakai:
    python3 scripts/mutasi_52.py --check           # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_52.py                   # penuh (~30-45 menit)
    python3 scripts/mutasi_52.py --only=M05,M11    # sebagian
    python3 scripts/mutasi_52.py --from=M20        # lanjutkan run yang terputus
    python3 scripts/mutasi_52.py --only=M01,M02 --tanpa-baseline
    python3 scripts/mutasi_52.py --ringkas         # laporan kumulatif
    python3 scripts/mutasi_52.py --pulihkan        # kembalikan kode & data bila run terputus
"""
import copy
import os
import pathlib
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

G_P = "verify_panel_resilience.py"      # gate 44 — ketahanan panel & kejujuran layar
HEALTH = "http://localhost:8001/api/health"

# (nama, gate, [(berkas, cari, ganti), ...])
MUTATIONS = [
    # ============================================== pemuat tahan-banting (panelLoad.js)
    ("M01 pemuat panel kembali ke Promise.all (satu penolakan membatalkan semuanya)", G_P, [
        ("frontend/src/utils/panelLoad.js",
         "  const settled = await Promise.allSettled(keys.map((key) => {",
         "  const settled = await Promise.all(keys.map((key) => {")]),
    ("M02 pesan penegak izin backend diteruskan apa adanya ke layar", G_P, [
        ("frontend/src/utils/panelLoad.js",
         '    detail: isInternalPermissionMessage(rawDetail) ? "" : rawDetail,',
         "    detail: rawDetail,")]),
    ("M03 pola pesan izin internal tidak lagi dikenali (saringan jadi hiasan)", G_P, [
        ("frontend/src/utils/panelLoad.js",
         "const INTERNAL_PERMISSION_RE = /(tidak memiliki izin|akses ditolak)/i;",
         "const INTERNAL_PERMISSION_RE = /(^tidak akan pernah cocok$)/i;")]),
    ("M04 lencana tab menulis 0 pada panel yang ditolak ('tidak ada datanya')", G_P, [
        ("frontend/src/utils/panelLoad.js",
         "  if (!panel || !panel.ok) return undefined;",
         "  if (!panel || !panel.ok) return 0;")]),
    ("M05 omittedSources dilepas (layar tak bisa menyebut panel yang hilang)", G_P, [
        ("frontend/src/utils/panelLoad.js",
         "export function omittedSources(panels, labels) {",
         "export function omittedSourcesLama(panels, labels) {")]),

    # ====================================================== kartu keadaan panel (StateViews)
    ("M06 penanda data-panel-state='denied' dihapus (uji kehilangan pegangan)", G_P, [
        ("frontend/src/components/patterns/StateViews.js",
         '    <div data-testid={testId} data-panel-state="denied"',
         '    <div data-testid={testId} data-state="ditolak"')]),
    ("M07 kartu ditolak tidak lagi menegaskan 'ini BUKAN belum ada data'", G_P, [
        ("frontend/src/components/patterns/StateViews.js",
         "        Ini BUKAN \u201cbelum ada data\u201d: datanya mungkin ada, hanya tidak untuk "
         "dibaca peran Anda.",
         "        Hubungi admin sistem bila Anda memang membutuhkan bagian ini.")]),
    ("M08 PanelStateView dihapus (setiap tab harus memilih kartunya sendiri)", G_P, [
        ("frontend/src/components/patterns/StateViews.js",
         "export function PanelStateView({ panel, subject, whoMay = null, onRetry = null, "
         "testId }) {",
         "export function PanelState({ panel, subject, whoMay = null, onRetry = null, "
         "testId }) {")]),
    ("M09 testId keadaan panel dicabut dari daftar resmi", G_P, [
        ("frontend/src/constants/testIds/ia.js",
         '  denied: "panel-denied",',
         '  denied: "panel-ditolak",')]),

    # ============================================== halaman profil lead (cacat inti Fase 52)
    ("M10 profil lead memakai Promise.all lagi (pola all-or-nothing kembali)", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         "  const load = useCallback(async () => {\n"
         '    setState({ loading: true, error: "" });',
         "  const load = useCallback(async () => {\n"
         '    setState({ loading: true, error: "" });\n'
         "    await Promise.all([]);   // pola lama (mutan)")]),
    ("M11 permintaan primer dicampur panel (403 panel mematikan halaman lagi)", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         "    const primer = res.lead;",
         "    const primer = res.appointments.ok ? res.lead : res.appointments;")]),
    ("M12 kalimat galat halaman disusun dari STATUS PANEL, bukan permintaan primer", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         '        error: primer.status === 404 ? "Lead tidak ditemukan."',
         '        error: res.appointments.status === 404 ? "Lead tidak ditemukan."'),
        ("frontend/src/pages/LeadProfilePage.js",
         "          : primer.status === 403 ? (bukanMilikSaya",
         "          : res.appointments.status === 403 ? (bukanMilikSaya")]),
    ("M13 lencana tab Survey dihitung dari daftar mentah (0 saat ditolak)", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         "          badge: honestBadge(panels.appointments),",
         "          badge: appts.length || undefined,")]),
    ("M14 sebab 403 tidak dibaca dari permintaan lead (layar menuduh izin yang salah)",
     G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         '      const bukanMilikSaya = /bukan lead anda/i.test(primer.rawDetail || "");',
         "      const bukanMilikSaya = false;")]),
    ("M15 spanduk 'sebagian panel tidak ditampilkan' dilepas dari profil lead", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         "        <div data-testid={LEADPROFILE.partial}",
         '        <div data-testid="lead-profile-catatan"')]),
    ("M16 daftar panel yang tidak ditampilkan tidak lagi disusun", G_P, [
        ("frontend/src/pages/LeadProfilePage.js",
         "  const omitted = omittedSources(panels, PANEL_LABELS);",
         "  const omitted = [];")]),

    # ============================================================ halaman profil pelanggan
    ("M17 penolakan panel diubah menjadi daftar kosong (403 = 'belum ada data')", G_P, [
        ("frontend/src/pages/CustomerProfilePage.js",
         '      complaints: () => api.get("/complaints", '
         "{ params: { customer_id: id, limit: 50 } }),",
         '      complaints: () => api.get("/complaints", '
         "{ params: { customer_id: id, limit: 50 } })\n"
         "        .catch(() => ({ data: { data: [] } })),")]),
    ("M18 spanduk sebagian panel dilepas dari profil pelanggan", G_P, [
        ("frontend/src/pages/CustomerProfilePage.js",
         "        <div data-testid={CUSTPROFILE.partial}",
         '        <div data-testid="customer-profile-catatan"')]),
    ("M19 lencana tab Unit pelanggan dihitung dari daftar mentah", G_P, [
        ("frontend/src/pages/CustomerProfilePage.js",
         "          badge: honestBadge(panels.units),",
         "          badge: units.length || undefined,")]),
    ("M20 primer profil pelanggan dicampur panel unit", G_P, [
        ("frontend/src/pages/CustomerProfilePage.js",
         "    const primer = res.customer;",
         "    const primer = res.units.ok ? res.customer : res.units;")]),

    # ================================================================ tab & panel di layar
    ("M21 tab Survey tetap menggambar daftar walau panelnya ditolak", G_P, [
        ("frontend/src/components/leads/LeadSurveyTab.js",
         '  if (panel && !panel.ok) return <div className="space-y-3">{blocked}</div>;',
         '  if (false) return <div className="space-y-3">{blocked}</div>;')]),
    ("M22 tombol 'Jadwalkan Survey' muncul untuk peran yang pasti 403 (tombol mati)", G_P, [
        ("frontend/src/components/leads/LeadSurveyTab.js",
         '  const mayCreate = can("appointments", "create");',
         "  const mayCreate = true;")]),
    ("M23 tombol 'Buat Reservasi' muncul untuk peran yang pasti 403", G_P, [
        ("frontend/src/components/leads/LeadUnitsTab.js",
         '  const mayReserve = can("deals", "create");',
         "  const mayReserve = true;")]),
    ("M24 timeline tidak lagi menandai jejak yang SEBAGIAN", G_P, [
        ("frontend/src/components/leads/LeadTimelineTab.js",
         "        <div data-testid={PANELSTATE.omitted}",
         '        <div data-testid="lead-timeline-catatan"')]),
    ("M25 kalimat 'Jejak ini SEBAGIAN' diperhalus sampai tak bermakna", G_P, [
        ("frontend/src/components/leads/LeadTimelineTab.js",
         '            <ShieldOff className="h-4 w-4" /> Jejak ini SEBAGIAN',
         '            <ShieldOff className="h-4 w-4" /> Catatan tampilan')]),
    ("M26 checklist dokumen memuntahkan detail galat backend ke layar", G_P, [
        ("frontend/src/components/patterns/DocChecklist.js",
         "      setPanel(classifyRequestError(e));",
         '      setError(e?.response?.data?.detail || "Gagal memuat checklist.");')]),
    ("M27 panel penawaran tidak lagi membedakan 403 dari 'gagal dimuat'", G_P, [
        ("frontend/src/components/quotations/QuotationsTab.js",
         "      setPanel(classifyRequestError(e));",
         '      setPanel({ ok: false, state: "failed", detail: "Gagal memuat penawaran." });')]),
    ("M28 panel percakapan WA menampilkan detail galat backend apa adanya", G_P, [
        ("frontend/src/components/sales/LeadWaPanel.js",
         "      setPanel(classifyRequestError(e));",
         '      setError(e?.response?.data?.detail || "");')]),

    # ================================================================== peta menu (Fase 52)
    ("M29 daftar 'belum dibangun' ditulis TANGAN lagi (bisa membusuk diam-diam)", G_P, [
        ("frontend/src/config/navMigrationMap.js",
         "export const NAV_SOON = comingSoonItems();",
         "export const NAV_SOON = [\n"
         '  { label: "Kampanye & Biaya Iklan", where: "Marketing", note: "Fase 44" },\n'
         '  { label: "Analitik & BI", where: "Analitik & BI", note: "Fase 45" },\n'
         "];")]),
    ("M30 baris peta 'Analitik & BI' menunjuk rute yang tidak ada", G_P, [
        ("frontend/src/config/navMigrationMap.js",
         '  { old: "Analitik & BI (dulu terkunci)", now: "Analitik & BI \u203a Dashboard '
         'Analitik",\n    to: "/bi",',
         '  { old: "Analitik & BI (dulu terkunci)", now: "Analitik & BI \u203a Dashboard '
         'Analitik",\n    to: "/bi-lama",')]),
    ("M31 kotak 'belum dibangun' selalu dipasang walau tidak ada yang terkunci", G_P, [
        ("frontend/src/components/layout/NavMigrationDialog.js",
         "        {soon.length ? (",
         "        {true ? (")]),
    ("M32 cabang jujur 'semua menu bisa dibuka' dihapus", G_P, [
        ("frontend/src/components/layout/NavMigrationDialog.js",
         "          <div data-testid={HUB.navMapAllOpen}",
         "          <div data-testid={HUB.navMapRow}")]),

    # ========================================================================= server/RBAC
    ("M33 izin BACA appointments untuk keuangan dicabut dari KODE (default)", G_P, [
        ("backend/rbac_matrix.py",
         '        "finance": ["view_all"],\n'
         '        "finance_manager": ["view_all"],\n'
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey",
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey")]),
    ("M34 pemisahan tugas dimatikan: keuangan boleh MENJADWALKAN survei (kode)", G_P, [
        ("backend/rbac_matrix.py",
         '        "finance": ["view_all"],\n'
         '        "finance_manager": ["view_all"],\n'
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey",
         '        "finance": ["view_all", "create"],\n'
         '        "finance_manager": ["view_all", "create"],\n'
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey")]),
    ("M35 endpoint penjadwalan hanya butuh izin BACA (siapa pun pembaca bisa menjadwalkan)",
     G_P, [
        ("backend/routers/leads_router.py",
         "async def create_appointment(payload: AppointmentCreate,\n"
         "                             user: dict = Depends("
         'require_permission("appointments", "create"))):',
         "async def create_appointment(payload: AppointmentCreate,\n"
         "                             user: dict = Depends("
         'require_permission("appointments", "view"))):')]),
    ("M36 403 lingkup baris memakai kalimat izin peran (dua sebab jadi satu kalimat)",
     G_P, [
        ("backend/routers/leads_router.py",
         'raise HTTPException(status_code=403, detail="Akses ditolak: bukan lead Anda")',
         'raise HTTPException(status_code=403, '
         'detail="Akses ditolak: tidak memiliki izin \'view\' pada \'leads\'")')]),
    ("M37 izin melebar: peran proyek diberi baca appointments tanpa alasan bisnis", G_P, [
        ("backend/rbac_matrix.py",
         '        "finance": ["view_all"],\n'
         '        "finance_manager": ["view_all"],\n'
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey",
         '        "finance": ["view_all"],\n'
         '        "finance_manager": ["view_all"],\n'
         '        "project_manager": ["view_all"],\n'
         '        "site_engineer": ["view_all"],\n'
         "    },\n"
         "    # Phase 14 \u2014 EPIC 1.2 Survey")]),
]

# Mutasi DATABASE (bukan kode): matriks izin TERSIMPAN mencabut hak baca appointments
# keuangan tanpa lewat API. Kenapa penting: `get_matrix()` menggabungkan DEFAULT_PERMISSIONS
# dengan dokumen `permission_settings`, dan dokumen itu MENANG per-peran. Jadi kebenaran yang
# dipakai saat runtime bisa berbeda dari kode — gate harus memeriksa keduanya.
DB_MUTATIONS = [
    ("M38 matriks TERSIMPAN mencabut hak baca appointments keuangan (langsung ke database)",
     G_P, ("appointments", "finance")),
]


# --------------------------------------------------------------------------- berkas
def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str) -> None:
    (ROOT / rel).write_text(src, encoding="utf-8")


def apply_patches(patches) -> dict:
    backup = {}
    for path, find, repl in patches:
        src = read(path)
        if path not in backup:
            backup[path] = src
        if find not in src:
            raise RuntimeError(f"pola tidak ditemukan di {path}: {find[:70]}")
        write(path, src.replace(find, repl, 1))
    return backup


def restore(backup: dict) -> None:
    for path, src in backup.items():
        write(path, src)


# ---------------------------------------------- jaring pengaman bila run terputus
SNAP = ROOT / "memory" / "mutasi52_snapshot"


def files_touched() -> list:
    out = []
    for _n, _g, patches in MUTATIONS:
        for path, _f, _r in patches:
            if path not in out:
                out.append(path)
    return out


def snapshot() -> None:
    SNAP.mkdir(parents=True, exist_ok=True)
    for rel in files_touched():
        (SNAP / rel.replace("/", "__")).write_text(read(rel), encoding="utf-8")


def pulihkan() -> int:
    if not SNAP.exists():
        print("Tidak ada snapshot kode — tidak ada berkas yang perlu dipulihkan.")
    n = 0
    for rel in files_touched():
        src = SNAP / rel.replace("/", "__")
        if src.exists() and src.read_text(encoding="utf-8") != read(rel):
            write(rel, src.read_text(encoding="utf-8"))
            print(f"  dipulihkan  {rel}")
            n += 1
    print(f"{n} berkas kode dipulihkan dari snapshot.")
    # Jejak DATA: jadwal survei bernama "gate44" hanya bisa lahir dari mutan M35 (dalam kode
    # yang benar percobaan itu dijawab 403). Baris seperti itu menaikkan tahap lead demo dan
    # melahirkan tugas — dua kebohongan di layar manusia bila dibiarkan.
    print(bersihkan_jejak_gate44())
    # Matriks izin: mutasi database M38 menulis langsung ke `permission_settings`.
    kembalikan_izin_appointments()
    return 0


# ------------------------------------------------------- menunggu backend memuat ulang
def server_pids() -> tuple:
    """PID proses PEKERJA (anak) `uvicorn server:app --reload`.

    Induknya TIDAK pernah berganti PID saat reload; yang berganti adalah anaknya (lahir
    lewat `multiprocessing.spawn`, jadi tidak muncul pada `pgrep -f "uvicorn server:app"`).
    """
    induk = subprocess.run(["pgrep", "-f", "uvicorn server:app"],
                           capture_output=True, text=True)
    pids = []
    for p in induk.stdout.split():
        if not p.strip().isdigit():
            continue
        anak = subprocess.run(["pgrep", "-P", p.strip()], capture_output=True, text=True)
        pids += [int(x) for x in anak.stdout.split() if x.strip().isdigit()]
    return tuple(sorted(pids))


def health_ok(timeout: float = 3.0) -> bool:
    try:
        return requests.get(HEALTH, timeout=timeout).status_code == 200
    except requests.RequestException:
        return False


def wait_reload(before: tuple, batas_ganti: int = 40, batas_sehat: int = 240) -> str:
    mulai = time.time()
    ganti = False
    while time.time() - mulai < batas_ganti:
        now = server_pids()
        if now and now != before:
            ganti = True
            break
        time.sleep(0.4)
    while time.time() - mulai < batas_sehat:
        if health_ok():
            time.sleep(1.0)     # beri jeda agar router selesai terpasang
            return (f"reload {time.time() - mulai:.0f}s" if ganti else
                    f"TANPA reload terdeteksi ({time.time() - mulai:.0f}s)")
        time.sleep(0.5)
    return "backend TIDAK sehat setelah menunggu"


# --------------------------------------------------------------------------- database
def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def snapshot_data() -> dict:
    """Foto keadaan data yang bisa disentuh gate 44 (untuk dibandingkan sesudah tiap mutasi).

    Gate 44 sengaja MENCOBA `POST /api/appointments` sebagai keuangan; pada kode yang benar
    jawabannya 403 dan tidak ada apa pun yang lahir. Di bawah mutan M35 percobaan itu
    berhasil, dan satu jadwal survei palsu ikut MENAIKKAN TAHAP lead + melahirkan tugas +
    menulis aktivitas. Semua itu harus dibersihkan, kalau tidak gate berikutnya menguji dunia
    yang sudah dirusak perangkat uji.
    """
    db = _mongo()
    return {
        "appointments": {r["id"] for r in db.appointments.find({}, {"_id": 0, "id": 1})},
        "tasks": {r["id"] for r in db.tasks.find({}, {"_id": 0, "id": 1})},
        "activities": {r["id"] for r in db.activities.find({}, {"_id": 0, "id": 1})},
        "leads": {r["id"]: {"stage": r.get("stage"),
                            "stage_history": r.get("stage_history") or []}
                  for r in db.leads.find({}, {"_id": 0, "id": 1, "stage": 1,
                                              "stage_history": 1})},
        "matrix": copy.deepcopy(
            (_matrix_doc() or {}).get("matrix") or {}),
        "matrix_ada": _matrix_doc() is not None,
    }


def purge_data_artefak(base: dict) -> str:
    """Buang baris yang lahir SELAMA satu mutasi + pulihkan tahap lead. Kembalikan catatan."""
    db = _mongo()
    catatan = []
    for coll in ("appointments", "tasks", "activities"):
        baru = [r["id"] for r in db[coll].find({}, {"_id": 0, "id": 1})
                if r["id"] not in base[coll]]
        if baru:
            db[coll].delete_many({"id": {"$in": baru}})
            catatan.append(f"{len(baru)} {coll} dibuang")
    balik = 0
    for lid, snap in base["leads"].items():
        row = db.leads.find_one({"id": lid}, {"_id": 0, "stage": 1, "stage_history": 1})
        if not row:
            continue
        if row.get("stage") != snap["stage"] or \
                len(row.get("stage_history") or []) != len(snap["stage_history"]):
            db.leads.update_one({"id": lid}, {"$set": {
                "stage": snap["stage"], "stage_history": snap["stage_history"]}})
            balik += 1
    if balik:
        catatan.append(f"{balik} tahap lead dipulihkan")
    return " · ".join(catatan)


def _matrix_doc():
    return _mongo().permission_settings.find_one({"key": "rbac_matrix"}, {"_id": 0})


def cabut_izin_tersimpan(resource: str, role: str) -> None:
    """Mutasi DATABASE: kosongkan izin satu peran pada satu resource di matriks tersimpan."""
    doc = _matrix_doc()
    if not doc:
        raise RuntimeError("dokumen matriks izin tidak ada di database")
    matrix = copy.deepcopy(doc.get("matrix") or {})
    if role not in (matrix.get(resource) or {}):
        raise RuntimeError(f"matriks tersimpan tidak memuat {resource}.{role}")
    matrix[resource][role] = []
    _mongo().permission_settings.update_one({"key": "rbac_matrix"},
                                            {"$set": {"matrix": matrix}})


def kembalikan_izin_appointments() -> None:
    """Pastikan keuangan kembali boleh MEMBACA appointments di matriks tersimpan.

    Gate 44 sendiri mencabut lalu memulihkan izin ini lewat API resmi (D6..D8), jadi baris
    ini adalah jaring pengaman untuk kasus run terputus di tengah mutasi database.
    """
    doc = _matrix_doc()
    if not doc:
        return
    matrix = copy.deepcopy(doc.get("matrix") or {})
    ubah = False
    for role in ("finance", "finance_manager"):
        cur = (matrix.get("appointments") or {}).get(role)
        if cur is not None and "view_all" not in cur:
            matrix.setdefault("appointments", {})[role] = ["view_all"]
            ubah = True
    if ubah:
        _mongo().permission_settings.update_one({"key": "rbac_matrix"},
                                                {"$set": {"matrix": matrix}})
        print("  izin baca appointments keuangan dipulihkan di matriks tersimpan.")


def bersihkan_jejak_gate44() -> str:
    """Buang jadwal survei bernama 'gate44' + tugas/aktivitas turunannya (jaring pengaman)."""
    db = _mongo()
    rows = list(db.appointments.find({"title": "gate44"}, {"_id": 0, "id": 1, "lead_id": 1}))
    if not rows:
        return "Tidak ada jejak 'gate44' di data."
    ids = [r["id"] for r in rows]
    db.appointments.delete_many({"id": {"$in": ids}})
    tugas = db.tasks.delete_many(
        {"source_event": {"$in": [f"appointment:{i}" for i in ids]}}).deleted_count
    akt = db.activities.delete_many({"body": "Appointment dijadwalkan: gate44"}).deleted_count
    return (f"{len(ids)} jadwal 'gate44' + {tugas} tugas + {akt} aktivitas dibuang "
            "(jejak mutan M35).")


# --------------------------------------------------------------------------- gate
def run_gate(gate: str, tag: str) -> bool:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut52_{tag}_{gate}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / gate)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    return p.returncode == 0


def selected(mutations):
    only = None
    start = None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = {x.strip().upper() for x in arg.split("=", 1)[1].split(",") if x.strip()}
        elif arg.startswith("--from="):
            start = arg.split("=", 1)[1].strip().upper()
    rows = list(mutations)
    if only:
        rows = [m for m in rows if m[0].split()[0].upper() in only]
    if start:
        idx = next((i for i, m in enumerate(rows) if m[0].split()[0].upper() == start), 0)
        rows = rows[idx:]
    return rows


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_52_hasil.tsv"


def catat_hasil(nama: str, hasil: str, catatan: str = "") -> None:
    HASIL.parent.mkdir(parents=True, exist_ok=True)
    with HASIL.open("a", encoding="utf-8") as fh:
        fh.write(f"{nama.split()[0]}\t{hasil}\t{nama}\t{catatan}\n")


def baca_hasil() -> dict:
    if not HASIL.exists():
        return {}
    out = {}
    for line in HASIL.read_text(encoding="utf-8").splitlines():
        bagian = line.split("\t")
        if len(bagian) >= 3:
            out[bagian[0]] = (bagian[1], bagian[2], bagian[3] if len(bagian) > 3 else "")
    return out


def ringkas() -> int:
    semua = [m[0] for m in MUTATIONS] + [m[0] for m in DB_MUTATIONS]
    hasil = baca_hasil()
    print("=" * 78)
    print("RINGKASAN UJI-MUTASI FASE 52 (kumulatif) — gate 44 verify_panel_resilience.py")
    print("=" * 78)
    tertangkap, lolos, lewat, belum = [], [], [], []
    for nama in semua:
        kode = nama.split()[0]
        row = hasil.get(kode)
        if not row:
            belum.append(nama)
            print(f"  BELUM      {nama}")
            continue
        status, _n, catatan = row
        print(f"  {status:<10} {nama}" + (f"  [{catatan}]" if catatan else ""))
        {"TERTANGKAP": tertangkap, "LOLOS": lolos,
         "LEWAT": lewat}.get(status, belum).append(nama)
    print("-" * 78)
    print(f"TERTANGKAP: {len(tertangkap)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)} · "
          f"BELUM DIJALANKAN: {len(belum)} · TOTAL: {len(semua)}")
    if lolos:
        print("\nMutasi yang LOLOS (gate harus diperkuat, bukan diabaikan):")
        for e in lolos:
            print(f"   - {e}")
    print("=" * 78)
    return 0 if (not lolos and not lewat and not belum) else 1


def check_patterns() -> int:
    print("=" * 78)
    print("PERIKSA POLA MUTASI FASE 52 (cepat, tanpa menjalankan gate)")
    print("=" * 78)
    bad = []
    for name, _gate, patches in MUTATIONS:
        missing = [f"{p} :: {find[:60]}" for p, find, _r in patches if find not in read(p)]
        print(f"  {'OK    ' if not missing else 'HILANG'} {name}")
        for m in missing:
            print(f"        - {m}")
        bad += missing
    doc = _matrix_doc()
    for name, _gate, (res, role) in DB_MUTATIONS:
        ada = bool(((doc or {}).get("matrix") or {}).get(res, {}).get(role) is not None)
        print(f"  {'OK    ' if ada else 'HILANG'} {name}")
        if not ada:
            bad.append(f"matriks tersimpan tidak memuat {res}.{role}")
    print("-" * 78)
    print(f"{len(MUTATIONS) + len(DB_MUTATIONS)} mutasi · {len(bad)} pola hilang")
    return 1 if bad else 0


def main() -> int:
    if "--check" in sys.argv:
        return check_patterns()
    if "--pulihkan" in sys.argv:
        return pulihkan()
    if "--ringkas" in sys.argv:
        return ringkas()
    lewati_baseline = "--tanpa-baseline" in sys.argv
    print("=" * 78)
    print("UJI-MUTASI FASE 52 — membuktikan GATE 44 BERGIGI")
    print("=" * 78)
    snapshot()
    print(f"\nSnapshot berkas bersih disimpan di {SNAP.relative_to(ROOT)} "
          f"({len(files_touched())} berkas) — pakai `--pulihkan` bila run terputus.")
    if lewati_baseline:
        print("Baseline DILEWATI (--tanpa-baseline): dipakai saat run dipecah; "
              "jalankan `--ringkas` di akhir.")
    else:
        print("\nBaseline (gate 44 harus HIJAU sebelum merusak apa pun):")
        ok = run_gate(G_P, "baseline")
        print(f"  {'HIJAU' if ok else 'MERAH'}  {G_P}")
        if not ok:
            print(f"  BASELINE MERAH — perbaiki dulu "
                  f"(log: memory/gatelogs/mut52_baseline_{G_P}.log)")
            return 1

    base = snapshot_data()
    caught, escaped, skipped = [], [], []
    todo = selected(MUTATIONS)
    print(f"\n{len(todo)} mutasi kode akan dijalankan"
          f"{' (saringan --only/--from aktif)' if len(todo) != len(MUTATIONS) else ''}.")
    for name, gate, patches in todo:
        tag = name.split()[0]
        backend_touched = any(p.startswith("backend/") for p, _f, _r in patches)
        before = server_pids()
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            skipped.append(name)
            catat_hasil(name, "LEWAT", str(e)[:80])
            print(f"  LEWAT      {name} — {e}")
            continue
        catatan = ""
        try:
            if backend_touched:
                catatan = wait_reload(before)
            ok = run_gate(gate, tag)
        finally:
            before2 = server_pids()
            restore(backup)
            if backend_touched:
                wait_reload(before2)
            bersih = purge_data_artefak(base)
            if bersih:
                catatan = (catatan + " · " + bersih).strip(" ·")
        if ok:
            escaped.append(name)
            catat_hasil(name, "LOLOS", catatan)
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya  [{catatan}]")
        else:
            caught.append(name)
            catat_hasil(name, "TERTANGKAP", catatan)
            print(f"  TERTANGKAP {name}  [{catatan}]")

    for name, gate, (res, role) in selected(DB_MUTATIONS):
        try:
            cabut_izin_tersimpan(res, role)
        except Exception as e:  # noqa: BLE001 — tanpa dokumen matriks mutasi tak bisa diuji
            skipped.append(name)
            catat_hasil(name, "LEWAT", str(e)[:80])
            print(f"  LEWAT      {name} — {e}")
            continue
        try:
            ok = run_gate(gate, name.split()[0])
        finally:
            kembalikan_izin_appointments()
            purge_data_artefak(base)
        if ok:
            escaped.append(name)
            catat_hasil(name, "LOLOS", "mutasi database")
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya")
        else:
            caught.append(name)
            catat_hasil(name, "TERTANGKAP", "mutasi database")
            print(f"  TERTANGKAP {name}")

    print("\n" + "=" * 78)
    print(f"TERTANGKAP: {len(caught)} · LOLOS: {len(escaped)} · LEWAT: {len(skipped)}")
    print(bersihkan_jejak_gate44())
    sehat = True
    if lewati_baseline:
        print("Baseline akhir DILEWATI (--tanpa-baseline) — jalankan gate-nya sendiri "
              "setelah bagian terakhir.")
    else:
        ok = run_gate(G_P, "akhir")
        print(f"\nBaseline setelah semua mutasi dipulihkan: "
              f"{'HIJAU' if ok else 'MERAH'}  {G_P}")
        sehat = ok
    if escaped:
        print("\nMutasi yang LOLOS (gate harus diperkuat, bukan diabaikan):")
        for e in escaped:
            print(f"   - {e}")
    if skipped:
        print("\nMutasi yang DILEWAT (pola kode berubah — perbarui skripnya):")
        for s in skipped:
            print(f"   - {s}")
    print("=" * 78)
    return 0 if (not escaped and not skipped and sehat) else 1


if __name__ == "__main__":
    sys.exit(main())
