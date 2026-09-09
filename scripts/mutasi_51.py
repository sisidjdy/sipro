#!/usr/bin/env python3
"""mutasi_51.py — UJI-MUTASI Fase 51: membuktikan gate 41, 42, & 43 BERGIGI.

Cara kerja: satu per satu aturan dimatikan di kode (mutan), gate yang bersangkutan
dijalankan, lalu kode dipulihkan. Gate yang tetap HIJAU saat aturannya dimatikan berarti
gate itu tidak menguji apa pun — LOLOS adalah cacat perangkat uji, bukan kelulusan produk.

Yang diuji:
  * gate 41 `verify_retention_warranty.py` — jaminan mutu tidak cair saat mutunya
    dipersoalkan (penahanan klaim garansi, pengabaian beralasan, SoD, idempotensi).
  * gate 42 `verify_wa_reminders.py` — pengingat WhatsApp: kandidat dihitung dari data,
    ambang dari Pusat Konfigurasi, satu periode satu pengingat, status jujur.
  * gate 43 `verify_portal_warranty.py` — portal pembeli: dokumen miliknya sendiri,
    dokumen orang lain tidak bocor, pengakuan penyelesaian klaim.

## Perbaikan perangkat uji dibanding `mutasi_50.py` (penting, jangan dikembalikan)

`mutasi_50.py` menunggu backend memuat ulang kode dengan `time.sleep(6)` buta. Di container
ini `uvicorn --reload` menjalankan ulang seluruh startup (termasuk seed idempoten), yang
kadang lebih lama dari 6 detik. Akibatnya dua kebohongan bisa terjadi:

  * gate berjalan saat backend masih memuat ulang → gate MERAH karena koneksi, lalu mutasi
    dicatat "TERTANGKAP" padahal aturannya belum pernah diuji;
  * gate berjalan sebelum reload dimulai → kode LAMA yang diuji, mutasi dicatat "LOLOS"
    padahal aturannya masih utuh.

Di sini reload ditunggu secara DETERMINISTIK: PID anak `uvicorn server:app` dicatat sebelum
kode disentuh, lalu skrip menunggu sampai (1) PID-nya benar-benar berganti dan (2)
`/api/health` menjawab 200 lagi. Mutasi yang hanya menyentuh frontend tidak perlu menunggu
backend sama sekali (gate membaca berkas sumber), jadi lebih cepat.

Pakai:
    python3 scripts/mutasi_51.py --check          # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_51.py                  # penuh (~40-60 menit)
    python3 scripts/mutasi_51.py --only=M05,M31   # sebagian
    python3 scripts/mutasi_51.py --from=M20       # lanjutkan run yang terputus
    python3 scripts/mutasi_51.py --only=M01,M02,M03 --tanpa-baseline   # satu bagian
    python3 scripts/mutasi_51.py --ringkas        # laporan kumulatif semua bagian
    python3 scripts/mutasi_51.py --pulihkan       # kembalikan kode bila run terputus
"""
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

G_R = "verify_retention_warranty.py"   # gate 41 — retensi ↔ klaim garansi (51A)
G_W = "verify_wa_reminders.py"         # gate 42 — pengingat WhatsApp otomatis (51B)
G_C = "verify_portal_warranty.py"      # gate 43 — portal pembeli diperkuat (51C)

HEALTH = "http://localhost:8001/api/health"

# Mutasi DATABASE: (koleksi, nama index, keys) — dijatuhkan lalu dibangun ulang.
IDX_REMINDER = ("wa_reminders", "uq_wa_reminder_dedup",
                [("org_id", 1), ("dedup_key", 1)])

# (nama, gate, [(berkas, cari, ganti), ...])
MUTATIONS = [
    # ===================================================== 51A penahanan klaim garansi
    ("M01 gerbang retensi tidak lagi melihat klaim garansi sama sekali", G_R, [
        ("backend/subcon_finance.py",
         "    claims, wnote = await _active_warranty_claims(org, ret)\n"
         "    if claims:",
         "    claims, wnote = await _active_warranty_claims(org, ret)\n"
         "    if False:")]),
    ("M02 penahanan tidak menyebut NOMOR klaimnya (kembali ke 'ada kendala')", G_R, [
        ("backend/subcon_finance.py",
         "        sebut = \", \".join(f\"{c.get('number')} ({c.get('title') or '-'})\" "
         "for c in claims[:3])",
         '        sebut = "ada kendala mutu"')]),
    ("M03 daftar klaim penahan tidak dikirim ke layar (layar harus menebak)", G_R, [
        ("backend/subcon_finance.py",
         "                for c in claims],",
         "                for c in claims[:0]],")]),
    ("M04 status klaim dikirim sebagai enum mentah, bukan label Kamus Data", G_R, [
        ("backend/subcon_finance.py",
         '                 "state_label": ref.label_of("warranty_claim_state", c.get("state")),',
         '                 "state_label": c.get("state"),')]),
    ("M05 penahanan tidak lagi menandai sendiri apakah boleh diabaikan (SSOT hilang)", G_R, [
        ("backend/subcon_finance.py",
         '        b["waivable"] = b["code"] in WAIVABLE_BLOCKS',
         '        b["waivable"] = False')]),
    ("M06 pengajuan pencairan tidak lagi memeriksa gerbang (klaim aktif dilewati)", G_R, [
        ("backend/subcon_finance.py",
         '    gate = await retention_gate(org, ret)\n'
         '    if not gate["ok"]:\n'
         '        raise ValueError("Pencairan belum bisa diajukan. " + gate["detail"])',
         '    gate = await retention_gate(org, ret)\n'
         '    if False:\n'
         '        raise ValueError("Pencairan belum bisa diajukan. " + gate["detail"])')]),
    ("M07 siapa pun yang boleh mengajukan juga boleh MENGABAIKAN penahanan", G_R, [
        ("backend/routers/subcon_finance_router.py",
         '                                   require_permission("subcon_finance", "override"))):',
         '                                   require_permission("subcon_finance", "create"))):')]),
    ("M08 alasan pengabaian < 10 huruf diterima (dua lapis dimatikan)", G_R, [
        ("backend/models_p51.py",
         '        return _reason(v, MIN_REASON, "dasar keputusannya '
         '(mis. nomor adendum/kesepakatan)")',
         "        return v"),
        ("backend/subcon_finance.py",
         '    if len(reason) < 10:\n'
         '        raise ValueError("Alasan pengabaian wajib ditulis, minimal 10 huruf',
         '    if False:\n'
         '        raise ValueError("Alasan pengabaian wajib ditulis, minimal 10 huruf')]),
    ("M09 kode penahanan ASING bisa diabaikan (dua penyaring dimatikan)", G_R, [
        ("backend/subcon_finance.py",
         "    tidak_dikenal = [c for c in codes if c not in WAIVABLE_BLOCKS]",
         "    tidak_dikenal = []"),
        ("backend/subcon_finance.py",
         "    bukan_penahan = [c for c in codes if c not in aktif]",
         "    bukan_penahan = []")]),
    ("M10 penahanan yang TIDAK sedang menahan boleh diabaikan (pengabaian hantu)", G_R, [
        ("backend/subcon_finance.py",
         "    bukan_penahan = [c for c in codes if c not in aktif]",
         "    bukan_penahan = []")]),
    ("M11 jejak pengabaian tidak menyimpan siapa/kapan/kenapa", G_R, [
        ("backend/subcon_finance.py",
         '    baru = [{"code": c, "reason": reason, "by": actor, "at": ts} for c in codes]',
         '    baru = [{"code": c} for c in codes]')]),
    ("M12 penahanan yang diabaikan disembunyikan dari layar (auditor kehilangan jejak)",
     G_R, [
        ("backend/subcon_finance.py",
         '            "waived_blocks": [b for b in blocks if b.get("waived")],',
         '            "waived_blocks": [],')]),
    ("M13 izin pencairan dilonggarkan sampai PENGAJU bisa mencairkan sendiri", G_R, [
        ("backend/routers/subcon_finance_router.py",
         "async def release_retention(rid: str, payload: RetentionReleaseIn,\n"
         '                            user: dict = Depends('
         'require_permission("subcon_finance", "manage"))):',
         "async def release_retention(rid: str, payload: RetentionReleaseIn,\n"
         '                            user: dict = Depends('
         'require_permission("subcon_finance", "create"))):')]),
    ("M14 pemisahan tugas dimatikan: pengaju mencairkan sendiri dan BERHASIL", G_R, [
        ("backend/routers/subcon_finance_router.py",
         "async def release_retention(rid: str, payload: RetentionReleaseIn,\n"
         '                            user: dict = Depends('
         'require_permission("subcon_finance", "manage"))):',
         "async def release_retention(rid: str, payload: RetentionReleaseIn,\n"
         '                            user: dict = Depends('
         'require_permission("subcon_finance", "create"))):'),
        ("backend/subcon_finance.py",
         '    if ret.get("requested_by") == actor:\n'
         '        raise ValueError("Pengaju pencairan tidak boleh mencairkan retensi '
         'yang diajukannya "',
         '    if False:\n'
         '        raise ValueError("Pengaju pencairan tidak boleh mencairkan retensi '
         'yang diajukannya "')]),
    ("M15 kiriman ulang pencairan tidak dikenali (tagihan AP kedua lahir)", G_R, [
        ("backend/routers/subcon_finance_router.py",
         '    if lock["state"] == "replay":',
         "    if False:")]),
    ("M16 retensi bisa dicairkan DUA KALI (penjaga status dimatikan)", G_R, [
        ("backend/subcon_finance.py",
         '    if ret.get("state") == "released":\n'
         '        raise ValueError("Retensi ini sudah dicairkan — tidak bisa dicairkan '
         'dua kali.")',
         '    if False:\n'
         '        raise ValueError("Retensi ini sudah dicairkan — tidak bisa dicairkan '
         'dua kali.")')]),
    ("M17 klaim yang SUDAH DITUTUP tetap menahan retensi (uang subkon ditahan selamanya)",
     G_R, [
        ("backend/subcon_finance.py",
         'ACTIVE_WARRANTY_STATES = ("diajukan", "dikerjakan", "selesai", "diverifikasi")',
         'ACTIVE_WARRANTY_STATES = ("diajukan", "dikerjakan", "selesai", "diverifikasi",\n'
         '                          "ditutup")')]),
    ("M18 masa pemeliharaan yang belum dicatat ditulis '0 hari' (kebalikan artinya)",
     G_R, [
        ("backend/subcon_finance.py",
         '            "maintenance_detail": (\n'
         '                f"Masa pemeliharaan {ret.get(\'maintenance_days\')} hari sampai '
         '{until}."\n'
         '                if until and ret.get("maintenance_days") is not None else\n'
         '                "Masa pemeliharaan belum dicatat pada SPK ini — belum ada data, "\n'
         '                "bukan nol hari."),',
         '            "maintenance_detail": (\n'
         '                f"Masa pemeliharaan {int(ret.get(\'maintenance_days\') or 0)} hari '
         'sampai {until or \'-\'}."),')]),
    ("M19 kode penahanan garansi dihapus dari Kamus Data (layar mengetik labelnya sendiri)",
     G_R, [
        ("backend/reference_p51.py",
         '            _o("warranty_claim_active", "Masih ada klaim garansi berjalan"),\n',
         "")]),
    ("M20 pengabaian tidak tercatat sebagai 'override' di jejak audit", G_R, [
        ("backend/routers/subcon_finance_router.py",
         '    await audit_log(user, "override", "subcon_retention", rid,',
         '    await audit_log(user, "waive", "subcon_retention", rid,')]),
    ("M21 pengabaian tidak melahirkan tugas penelaahan (hilang dari radar)", G_R, [
        ("backend/routers/subcon_finance_router.py",
         "    await spawn_review(org, ret, payload, user)",
         "    pass  # tugas penelaahan dimatikan (mutan)")]),
    ("M22 layar menebak sendiri penahanan mana yang boleh diabaikan (bukan dari server)",
     G_R, [
        ("frontend/src/components/subcon/RetentionWaiveDialog.js",
         "  const waivable = (row?.gate?.blocks || []).filter((b) => b.waivable);\n"
         "  const notWaivable = (row?.gate?.blocks || []).filter((b) => !b.waivable);",
         '  const CODES = ["maintenance_active", "punch_open"];\n'
         "  const waivable = (row?.gate?.blocks || [])"
         ".filter((b) => CODES.includes(b.code));\n"
         "  const notWaivable = (row?.gate?.blocks || [])"
         ".filter((b) => !CODES.includes(b.code));")]),

    # ======================================================= 51B pengingat WhatsApp
    ("M23 mode kirim mengaku 'nyata' walau kredensial WhatsApp kosong", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "mode": "nyata" if whatsapp_configured() else "simulasi",',
         '        "mode": "nyata",')]),
    ("M24 ambang termin memakai ANGKA MATI, bukan Pusat Konfigurasi", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "installment_days_before": int(vals.get("reminder.installment_days_before")'
         ' or 3),',
         '        "installment_days_before": 3,')]),
    ("M25 setelan tidak menyebut key Pusat Konfigurasi (layar jadi jalan buntu)", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "setting_keys": list(SETTING_KEYS),',
         '        "setting_keys": [],')]),
    ("M26 pengingat garansi hampir habis tidak pernah lahir dari BAST", G_W, [
        ("backend/wa_reminder_engine.py",
         '        for w in (ho.get("warranties") or []):',
         "        for w in []:")]),
    ("M27 pengingat termin jatuh tempo tidak pernah lahir", G_W, [
        ("backend/wa_reminder_engine.py",
         "            if 0 <= selisih <= hn:",
         "            if False:")]),
    ("M28 pengingat tunggakan tidak pernah lahir", G_W, [
        ("backend/wa_reminder_engine.py",
         "            elif selisih < 0:",
         "            elif False:")]),
    ("M29 jenis penerima tidak ditulis (pelanggan vs calon pembeli jadi rancu)", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "recipient_type": jenis,',
         '        "recipient_type": None,')]),
    ("M30 penanda dedup dibuat unik tiap jalan (satu periode bisa berkali-kali)", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "dedup_key": cand["dedup_key"], "entity_type": cand.get("entity_type"),',
         '        "dedup_key": cand["dedup_key"] + ":" + new_id(),\n'
         '        "entity_type": cand.get("entity_type"),')]),
    ("M31 simulasi mengaku 'terkirim' (pesan tidak pergi tapi laporannya bilang pergi)",
     G_W, [
        ("backend/wa_reminder_engine.py",
         '        if res.get("status") == "sent":',
         "        if True:")]),
    ("M32 penerima tanpa nomor dianggap siap dikirim (sebabnya disembunyikan)", G_W, [
        ("backend/wa_reminder_engine.py",
         '        if not c.get("phone"):',
         "        if False:")]),
    ("M33 termin yang sudah LUNAS tetap diingatkan", G_W, [
        ("backend/wa_reminder_engine.py",
         '            if sisa_bayar <= 0 or not item.get("due_date"):',
         '            if not item.get("due_date"):')]),
    ("M34 garansi yang masanya SUDAH LEWAT tetap diingatkan", G_W, [
        ("backend/wa_reminder_engine.py",
         "            if sisa < 0 or sisa > ambang:",
         "            if sisa > ambang:")]),
    ("M35 siapa pun yang boleh MELIHAT pengingat juga boleh MENJALANKANNYA", G_W, [
        ("backend/routers/reminders_router.py",
         '                       user: dict = Depends(require_permission("reminders", '
         '"manage"))):',
         '                       user: dict = Depends(require_permission("reminders", '
         '"view"))):')]),
    ("M36 riwayat tidak menyimpan template & isi pesan (kalimatnya tak bisa diperiksa)",
     G_W, [
        ("backend/wa_reminder_engine.py",
         '        "body": body, "template_code": template_code,',
         '        "body": None, "template_code": None,')]),
    ("M37 riwayat tidak menyebut siapa yang menjalankan", G_W, [
        ("backend/wa_reminder_engine.py",
         '        "run_by": actor, "created_at": now_iso(),',
         '        "run_by": None, "created_at": now_iso(),')]),
    ("M38 ringkasan per status tidak dikirim (layar dipaksa menghitung sendiri)", G_W, [
        ("backend/wa_reminder_engine.py",
         '    return {"rows": rows, "total": total, "by_status": agg}',
         '    return {"rows": rows, "total": total, "by_status": {}}')]),
    ("M39 label jenis pengingat diketik di layar, bukan dari Kamus Data", G_W, [
        ("frontend/src/components/omni/RemindersPanel.js",
         '<StatusPill status={c.kind} group="reminder_kind" />',
         "<StatusPill status={c.kind} label={c.kind} />"),
        ("frontend/src/components/omni/RemindersPanel.js",
         '<StatusPill status={r.kind} group="reminder_kind" />',
         "<StatusPill status={r.kind} label={r.kind} />")]),

    # ======================================================= 51C portal pembeli
    ("M40 BAST pembeli LAIN bisa diunduh (pemeriksaan kepemilikan dimatikan)", G_C, [
        ("backend/routers/portal_router.py",
         "    mine = {h[\"id\"] for h in await _my_handovers(pu)}\n"
         "    if hid not in mine:",
         "    mine = {h[\"id\"] for h in await _my_handovers(pu)}\n"
         "    if False:")]),
    ("M41 kwitansi orang lain bisa diunduh (daftar diambil tanpa saringan pemilik)", G_C, [
        ("backend/routers/portal_router.py",
         '    rows = {r["id"]: r for r in await _my_receipts(pu)}',
         '    rows = {r["id"]: r for r in await db.receipts.find(\n'
         '        {"org_id": pu.get("org_id", ORG_ID)}, {"_id": 0}).to_list(500)}')]),
    ("M42 klaim garansi orang lain bisa dibuka & diakui pembeli ini", G_C, [
        ("backend/routers/portal_router.py",
         '    if not doc or (doc.get("customer_id") != pu.get("customer_id")\n'
         '                   and doc.get("unit_id") not in unit_ids):',
         "    if not doc:")]),
    ("M43 klaim yang belum diperiksa mutu bisa langsung ditutup atas pengakuan", G_C, [
        ("backend/warranty_engine.py",
         '    if doc["state"] != VERIFIED:\n'
         '        raise ValueError(f"Klaim {doc[\'number\']} berstatus',
         '    if False:\n'
         '        raise ValueError(f"Klaim {doc[\'number\']} berstatus')]),
    ("M44 'belum beres' tetap MENUTUP klaim (pengakuan negatif diabaikan)", G_C, [
        ("backend/routers/portal_router.py",
         "    if not payload.satisfied:",
         "    if False:")]),
    ("M45 catatan pembeli tidak disimpan (keluhannya hilang)", G_C, [
        ("backend/routers/portal_router.py",
         '            "ack_note": (payload.note or "").strip() or None,',
         '            "ack_note": None,')]),
    ("M46 pengakuan dicatat atas nama STAF, bukan pembeli", G_C, [
        ("backend/routers/portal_router.py",
         '    aktor = f"{pu.get(\'name\') or \'Pembeli\'} '
         '({pu.get(\'phone\') or pu.get(\'email\') or \'-\'})"',
         '    aktor = "staf portal"')]),
    ("M47 tim tidak diberi tahu saat pembeli menyatakan perbaikan belum beres", G_C, [
        ("backend/routers/portal_router.py",
         "        await create_notification(\n"
         '            user_email=doc.get("assigned_to"), '
         'title="Pembeli menyatakan perbaikan BELUM beres",\n'
         '            body=(f"Klaim {doc.get(\'number\')} — {doc.get(\'title\')}: "\n'
         '                  f"{(payload.note or \'tanpa catatan\')}"),\n'
         '            type="warranty", related_entity_type="warranty_claim", '
         'related_entity_id=cid,\n'
         "            org_id=org)",
         "        pass  # notifikasi ke tim dimatikan (mutan)")]),
    ("M48 daftar BAST kosong dikembalikan sebagai tabel hampa tanpa sebab", G_C, [
        ("backend/routers/portal_router.py",
         '            "detail": ("Belum ada berita acara serah terima atas nama Anda — '
         'rumah belum "\n'
         '                       "diserahterimakan, jadi memang belum ada dokumennya."',
         '            "detail": (""')]),
    ("M49 portal memakai tautan mentah <a href> untuk berkas (token bocor ke riwayat)",
     G_C, [
        ("frontend/src/components/portal/panels/DocumentsPanel.js",
         '                <div className="flex items-center gap-3">\n'
         "                  <StatusPill status={h.state}",
         '                <div className="flex items-center gap-3">\n'
         "                  <a href={`/api/portal/handovers/${h.id}/pdf`} "
         'className="hidden">unduh</a>\n'
         "                  <StatusPill status={h.state}")]),
    ("M50 layar tidak lagi menjelaskan akibat 'belum beres' (klaim tidak ditutup)", G_C, [
        ("frontend/src/components/portal/panels/ClaimAckDialog.js",
         "            Klaim TIDAK akan ditutup. Ia dikembalikan ke pengerjaan dan tim "
         "yang menangani",
         "            Masukan Anda kami catat dan tim yang menangani")]),
    ("M51 panel dokumen dilepas dari portal (BAST & kwitansi tak punya pintu)", G_C, [
        ("frontend/src/components/portal/PortalDashboard.js",
         'import DocumentsPanel from "@/components/portal/panels/DocumentsPanel";',
         'import DocsPanelLama from "@/components/portal/panels/DocumentsPanel";'),
        ("frontend/src/components/portal/PortalDashboard.js",
         'tid: PORTAL.tabDocuments, Comp: DocumentsPanel }',
         "tid: PORTAL.tabDocuments, Comp: DocsPanelLama }")]),
]

# Mutasi DATABASE (bukan kode): index unik penanda dedup pengingat dijatuhkan.
DB_MUTATIONS = [
    ("M52 keunikan penanda pengingat hanya dijaga aplikasi (index unik dijatuhkan)", G_W,
     IDX_REMINDER),
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
SNAP = ROOT / "memory" / "mutasi51_snapshot"


def files_touched() -> list:
    out = []
    for _n, _g, patches in MUTATIONS:
        for path, _f, _r in patches:
            if path not in out:
                out.append(path)
    return out


def snapshot() -> None:
    """Simpan salinan bersih semua berkas yang akan dirusak.

    Kalau run terputus di tengah (pod restart / proses dihentikan), `finally` tidak pernah
    jalan dan kode mutan bisa tertinggal di repo — cacat yang jauh lebih mahal daripada
    beberapa kilobyte salinan. `--pulihkan` mengembalikannya.
    """
    SNAP.mkdir(parents=True, exist_ok=True)
    for rel in files_touched():
        dest = SNAP / rel.replace("/", "__")
        dest.write_text(read(rel), encoding="utf-8")


def pulihkan() -> int:
    if not SNAP.exists():
        print("Tidak ada snapshot — tidak ada yang perlu dipulihkan.")
    n = 0
    for rel in files_touched():
        src = SNAP / rel.replace("/", "__")
        if src.exists() and src.read_text(encoding="utf-8") != read(rel):
            write(rel, src.read_text(encoding="utf-8"))
            print(f"  dipulihkan  {rel}")
            n += 1
    print(f"{n} berkas dipulihkan dari snapshot.")
    # Jejak mutan yang paling berbahaya bukan kode, tetapi DATA: baris pengingat berstatus
    # "terkirim" padahal kredensial WhatsApp kosong — kombinasi yang MUSTAHIL pada kode yang
    # benar, jadi pasti lahir dari mutan M31. Baris seperti itu memakan slot dedup pembeli
    # demo ("Sudah diingatkan untuk periode ini") DAN memajang "Terkirim" untuk pesan yang
    # tidak pernah pergi. Dua-duanya kebohongan di layar manusia.
    if not (os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_ID")):
        hapus = _mongo().wa_reminders.delete_many({"status": "terkirim"}).deleted_count
        print(f"{hapus} baris pengingat 'terkirim' palsu dibuang "
              f"(kredensial WhatsApp kosong → status itu tidak mungkin sah).")
    return 0


# ------------------------------------------------------- menunggu backend memuat ulang
def server_pids() -> tuple:
    """PID proses PEKERJA (anak) dari `uvicorn server:app --reload`.

    Penting — ini pernah salah dan membuat skrip menunggu 180 detik per mutasi: proses
    anaknya TIDAK memuat "uvicorn server:app" pada baris perintah (ia lahir lewat
    `multiprocessing.spawn`), sehingga `pgrep -f "uvicorn server:app"` hanya menemukan si
    INDUK — dan PID induk TIDAK pernah berganti saat reload. Yang berganti adalah anaknya,
    jadi penanda "kode sudah dimuat ulang" harus dibaca dari daftar anak.
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


def wait_reload(before: tuple, batas_ganti: int = 40, batas_sehat: int = 180) -> str:
    """Tunggu sampai kode benar-benar dimuat ulang: PID pekerja berganti LALU /health hidup.

    Mengembalikan keterangan singkat untuk log. Kalau PID tidak pernah berganti, itu
    dilaporkan apa adanya — lebih baik satu baris "TANPA reload terdeteksi" daripada hasil
    mutasi yang tidak berarti (gate menguji kode LAMA lalu dicatat "LOLOS").
    """
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


# --------------------------------------------------------------------------- gate
def run_gate(gate: str, tag: str) -> bool:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut51_{tag}_{gate}.log"
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


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_51_hasil.tsv"


def catat_hasil(nama: str, hasil: str, catatan: str = "") -> None:
    """Tulis hasil satu mutasi ke berkas kumulatif.

    Run penuh berjalan puluhan menit dan pernah MATI di tengah jalan (proses latar dibunuh
    lingkungan), sehingga seluruh temuan hilang dan harus diulang dari nol. Karena itu setiap
    mutasi menuliskan hasilnya SEGERA; `--ringkas` menyusun laporannya dari berkas ini,
    apa pun yang terjadi pada prosesnya.
    """
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
    """Laporan kumulatif dari `mutasi_51_hasil.tsv` (aman walau run dipecah/terputus)."""
    semua = [m[0] for m in MUTATIONS] + [m[0] for m in DB_MUTATIONS]
    hasil = baca_hasil()
    print("=" * 78)
    print("RINGKASAN UJI-MUTASI FASE 51 (kumulatif)")
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
        {"TERTANGKAP": tertangkap, "LOLOS": lolos, "LEWAT": lewat}.get(status, belum).append(nama)
    print("-" * 78)
    print(f"TERTANGKAP: {len(tertangkap)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)} · "
          f"BELUM DIJALANKAN: {len(belum)} · TOTAL: {len(semua)}")
    if lolos:
        print("\nMutasi yang LOLOS (gate harus diperkuat, bukan diabaikan):")
        for e in lolos:
            print(f"   - {e}")
    print("=" * 78)
    return 0 if (not lolos and not lewat and not belum) else 1


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def drop_index(coll: str, name: str) -> None:
    _mongo()[coll].drop_index(name)


def build_index(coll: str, name: str, keys) -> None:
    _mongo()[coll].create_index(keys, name=name, unique=True)


# ------------------------------------------- membersihkan jejak mutan di data pengingat
def reminder_ids() -> set:
    """Id `wa_reminders` yang ADA sebelum run — batas antara fakta dan jejak mutan."""
    return {r["id"] for r in _mongo().wa_reminders.find({}, {"_id": 0, "id": 1})}


def purge_reminder_artefak(sebelum: set) -> int:
    """Buang baris pengingat yang lahir SELAMA run mutasi.

    Kenapa ini wajib (ditemukan setelah run pertama): mutan M31 ("simulasi mengaku
    terkirim") membuat gate 42 mencatat pengingat milik pembeli DEMO berstatus
    **`terkirim`** padahal tidak ada pesan yang pergi — kredensial WhatsApp memang kosong.
    `_fixture51.purge()` sengaja TIDAK menghapus baris `terkirim` karena dalam keadaan
    normal itu fakta yang tidak boleh dihapus; tetapi di bawah mutan baris itu adalah
    KEBOHONGAN. Akibatnya dua kerusakan tertinggal di layar manusia: (1) slot dedup pembeli
    demo terpakai sehingga semua kandidat berlabel "Sudah diingatkan untuk periode ini",
    dan (2) riwayat menampilkan "Terkirim" untuk pesan yang tidak pernah terkirim.

    Selama run mutasi TIDAK ADA pengingat sah yang lahir — semuanya sintetis — jadi setiap
    baris baru dibuang tanpa kecuali.
    """
    db = _mongo()
    ids = [r["id"] for r in db.wa_reminders.find({}, {"_id": 0, "id": 1})
           if r["id"] not in sebelum]
    if not ids:
        return 0
    return db.wa_reminders.delete_many({"id": {"$in": ids}}).deleted_count


def check_patterns() -> int:
    """Mode cepat: pastikan seluruh pola mutasi masih ada (tanpa menjalankan gate)."""
    print("=" * 78)
    print("PERIKSA POLA MUTASI FASE 51 (cepat, tanpa menjalankan gate)")
    print("=" * 78)
    bad = []
    for name, _gate, patches in MUTATIONS:
        missing = [f"{p} :: {find[:60]}" for p, find, _r in patches if find not in read(p)]
        print(f"  {'OK    ' if not missing else 'HILANG'} {name}")
        for m in missing:
            print(f"        - {m}")
        bad += missing
    coll, iname, _keys = IDX_REMINDER
    info = _mongo()[coll].index_information()
    has = iname in info
    print(f"  {'OK    ' if has else 'HILANG'} M52 index unik {iname} ada di database")
    if not has:
        bad.append(f"index {iname} tidak ada")
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
    print("UJI-MUTASI FASE 51 — membuktikan gate 41/42/43 BERGIGI")
    print("=" * 78)
    snapshot()
    print(f"\nSnapshot berkas bersih disimpan di {SNAP.relative_to(ROOT)} "
          f"({len(files_touched())} berkas) — pakai `--pulihkan` bila run terputus.")
    if lewati_baseline:
        print("Baseline DILEWATI (--tanpa-baseline): dipakai saat run dipecah "
              "menjadi beberapa bagian; jalankan `--ringkas` di akhir.")
    else:
        print("\nBaseline (tiga gate harus HIJAU sebelum merusak apa pun):")
        for g in (G_R, G_W, G_C):
            ok = run_gate(g, "baseline")
            print(f"  {'HIJAU' if ok else 'MERAH'}  {g}")
            if not ok:
                print(f"  BASELINE MERAH — perbaiki dulu "
                      f"(log: memory/gatelogs/mut51_baseline_{g}.log)")
                return 1

    caught, escaped, skipped = [], [], []
    todo = selected(MUTATIONS)
    pengingat_awal = reminder_ids()
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
            dibuang = purge_reminder_artefak(pengingat_awal)
            if dibuang:
                catatan = (catatan + f" · {dibuang} jejak pengingat dibuang").strip(" ·")
        if ok:
            escaped.append(name)
            catat_hasil(name, "LOLOS", catatan)
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya  [{catatan}]")
        else:
            caught.append(name)
            catat_hasil(name, "TERTANGKAP", catatan)
            print(f"  TERTANGKAP {name}  [{catatan}]")

    for name, gate, (coll, iname, keys) in selected(DB_MUTATIONS):
        try:
            drop_index(coll, iname)
        except Exception as e:  # noqa: BLE001 — index tidak ada = mutasi tak bisa diuji
            skipped.append(name)
            print(f"  LEWAT      {name} — {e}")
            continue
        try:
            ok = run_gate(gate, name.split()[0])
        finally:
            build_index(coll, iname, keys)
            purge_reminder_artefak(pengingat_awal)
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
    sehat = True
    if lewati_baseline:
        print("Baseline akhir DILEWATI (--tanpa-baseline) — jalankan gate-nya sendiri "
              "setelah bagian terakhir.")
    else:
        print("\nBaseline setelah semua mutasi dipulihkan:")
        for g in (G_R, G_W, G_C):
            ok = run_gate(g, "akhir")
            print(f"  {'HIJAU' if ok else 'MERAH'}  {g}")
            sehat = sehat and ok
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
