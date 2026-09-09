#!/usr/bin/env python3
"""mutasi_50.py — UJI-MUTASI Fase 50: membuktikan gate 39 & 40 BERGIGI.

Cara kerja: satu per satu aturan dimatikan di kode (mutan), gate yang bersangkutan dijalankan,
lalu kode dipulihkan. Gate yang tetap HIJAU saat aturannya dimatikan berarti gate itu tidak
menguji apa pun (LOLOS = cacat perangkat uji, bukan kelulusan).

Pelajaran fase sebelumnya yang dipakai lagi:
  * **Matikan lapis yang BENAR.** Panjang alasan dijaga DUA kali (kontrak permintaan
    `models_p50` dan mesin `handover_engine`); mematikan satu lapis saja menghasilkan mutan
    ekuivalen yang membuat gate tampak longgar padahal tidak. Karena itu mutasi yang menguji
    "alasan pendek diterima" mematikan KEDUA lapis dalam satu mutan.
  * **Baseline dulu.** Bila gate sudah merah sebelum dirusak, hasil mutasi tidak berarti.
  * **Selalu pulihkan.** Kode dikembalikan walau gate gagal/putus di tengah jalan, lalu
    baseline diperiksa ulang di akhir.

Tambahan Fase 50: selain mutasi KODE, ada satu mutasi DATABASE (`--` index unik
`uq_offline_intake_ref` dijatuhkan sementara). Tanpa ini, janji "keunikan penanda antrean
dijaga database, bukan hanya aplikasi" tidak pernah teruji — dan justru itu satu-satunya
lapis yang masih berlaku saat dua tab mengirim absensi bersamaan.

Pakai:
    python3 scripts/mutasi_50.py --check   # cepat: pastikan semua pola mutasi masih ada
    python3 scripts/mutasi_50.py           # penuh (~25-35 menit, backend memuat ulang kode)
"""
import os
import pathlib
import subprocess
import sys
import time

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

G_HO = "verify_handover_warranty.py"      # gate 39
G_Q = "verify_offline_queue.py"           # gate 40

# Mutasi DATABASE: (koleksi, nama index, keys) — dijatuhkan lalu dibangun ulang.
IDX_OFFLINE = ("offline_intake", "uq_offline_intake_ref",
               [("org_id", 1), ("kind", 1), ("client_ref", 1)])

# (nama, gate, [(berkas, cari, ganti), ...])
MUTATIONS = [
    # ======================================================= 50A daftar periksa & tahanan
    ("M01 daftar periksa yang GAGAL tidak lagi menahan penerbitan BAST", G_HO, [
        ("backend/handover_engine.py",
         "    if blocking and not override:\n"
         '        raise HandoverHold([b["detail"] for b in blocking], blocking)',
         "    if False:\n"
         '        raise HandoverHold([b["detail"] for b in blocking], blocking)')]),
    ("M02 temuan punch list yang masih terbuka tidak lagi menahan", G_HO, [
        ("backend/handover_engine.py",
         '        add("punch_terbuka", BLOCKING,\n'
         '            f"{len(punch)} temuan punch list masih terbuka: {names}"',
         '        add("punch_terbuka", WARNING,\n'
         '            f"{len(punch)} temuan punch list masih terbuka: {names}"')]),
    ("M03 sebab tahanan tidak lagi menyebut temuan & nominalnya", G_HO, [
        ("backend/handover_engine.py",
         '            f"{len(punch)} temuan punch list masih terbuka: {names}"\n'
         '            + (" \u2026" if len(punch) > 3 else ""),',
         '            f"{len(punch)} temuan punch list masih terbuka.",'),
        ("backend/handover_engine.py",
         '                (f"Sisa kewajiban pembeli {_rp(inv.get(\'outstanding\'))} dari total "\n'
         '                 f"{_rp(inv.get(\'total\'))} belum beres."), "/finance?tab=ar")',
         '                "Kewajiban pembeli belum beres.", "/finance?tab=ar")')]),
    ("M04 kewajiban pembayaran pembeli yang belum beres tidak menahan", G_HO, [
        ("backend/handover_engine.py",
         '        elif int(inv.get("outstanding") or 0) > 0:',
         '        elif int(inv.get("outstanding") or 0) > 999_999_999_999:')]),
    ("M05 rumah tanpa inspeksi serah terima dianggap sudah beres", G_HO, [
        ("backend/handover_engine.py",
         '        add("inspeksi_serah_terima", BLOCKING,\n'
         '            "Belum ada inspeksi serah terima untuk rumah ini',
         '        add("inspeksi_serah_terima", OK,\n'
         '            "Belum ada inspeksi serah terima untuk rumah ini')]),
    ("M06 progres pembangunan yang belum selesai tidak menahan", G_HO, [
        ("backend/handover_engine.py",
         '        add("pembangunan_selesai", BLOCKING,\n'
         '            (f"Progres pembangunan baru {int(sched.get(\'progress\') or 0)}% "',
         '        add("pembangunan_selesai", OK,\n'
         '            (f"Progres pembangunan baru {int(sched.get(\'progress\') or 0)}% "')]),
    # ============================================================= 50A terobosan (waiver)
    ("M07 siapa pun boleh MENEROBOS daftar periksa (izin dimatikan)", G_HO, [
        ("backend/routers/handover_router.py",
         '        if not await can(user.get("role"), "handover", "override"):',
         "        if False:")]),
    ("M08 alasan terobosan < 10 huruf diterima (dua lapis dimatikan)", G_HO, [
        ("backend/models_p50.py",
         "    def _ov(cls, v):\n"
         '        return _reason(v, "Alasan terobosan serah terima")',
         "    def _ov(cls, v):\n        return v"),
        ("backend/handover_engine.py",
         '    if blocking and override and len((override_reason or "").strip()) < 10:',
         "    if False:")]),
    ("M09 terobosan tidak mencatat pemeriksaan yang dilewati", G_HO, [
        ("backend/handover_engine.py",
         '        "override_items": [b["code"] for b in blocking] if (blocking and override) else [],',
         '        "override_items": [],')]),
    ("M10 potret daftar periksa tidak disimpan di dokumen (tak bisa diaudit ulang)", G_HO, [
        ("backend/handover_engine.py",
         '        "checklist": [{"code": i["code"], "state": i["state"], "detail": i["detail"]}\n'
         '                      for i in check["items"]],',
         '        "checklist": [],')]),
    ("M11 terobosan tidak melahirkan TUGAS tinjauan (hanya catatan)", G_HO, [
        ("backend/handover_engine.py",
         "    if blocking and override:\n        await auto_create_task(",
         "    if False:\n        await auto_create_task(")]),
    ("M12 penerbitan BAST kedua TIDAK idempoten (dokumen kembar)", G_HO, [
        ("backend/handover_engine.py",
         "    prior = await active_handover(org, unit_id)\n    if prior:\n"
         '        logger.info("BAST idempoten: unit %s sudah punya %s", unit_id, prior.get("number"))',
         "    prior = await active_handover(org, unit_id)\n    if False:\n"
         '        logger.info("BAST idempoten: unit %s sudah punya %s", unit_id, prior.get("number"))')]),
    # ================================================================== 50A masa garansi
    ("M13 masa garansi memakai ANGKA MATI, bukan Pusat Konfigurasi", G_HO, [
        ("backend/handover_engine.py",
         '                     "months": int(vals.get(key) or 0), "setting_key": key})',
         '                     "months": 12, "setting_key": key})')]),
    ("M14 tanggal habis garansi digeser jauh (masa garansi tak pernah lewat)", G_HO, [
        ("backend/handover_engine.py",
         '                   "starts_at": day, "expires_at": add_months(day, p["months"])}',
         '                   "starts_at": day, "expires_at": add_months(day, 999)}')]),
    ("M15 masa garansi yang HABIS tetap dilaporkan aktif", G_HO, [
        ("backend/handover_engine.py",
         '        state = "habis" if days_left < 0 else ("hampir_habis" if days_left <= expiring_days\n'
         '                                              else "aktif")',
         '        state = "aktif"')]),
    # ================================================================= 50A klaim garansi
    ("M16 klaim lewat masa garansi diterima diam-diam (bukan ditolak berjejak)", G_HO, [
        ("backend/warranty_engine.py",
         '    elif row["state"] == "habis":\n'
         '        state, reject_reason = REJECTED, "lewat_masa_garansi"',
         "    elif False:\n"
         '        state, reject_reason = REJECTED, "lewat_masa_garansi"')]),
    ("M17 pengaju klaim boleh memutuskan klaimnya sendiri (izin dilonggarkan)", G_HO, [
        ("backend/routers/handover_router.py",
         "async def decide(cid: str, payload: WarrantyClaimDecision,\n"
         '                 user: dict = Depends(require_permission("warranty", "update"))):',
         "async def decide(cid: str, payload: WarrantyClaimDecision,\n"
         '                 user: dict = Depends(require_permission("warranty", "create"))):')]),
    ("M18 klaim diterima tidak melahirkan pekerjaan bertanda garansi", G_HO, [
        ("backend/warranty_engine.py",
         '        "fix_photos": [], "source": "warranty_claim", "warranty_claim_id": cid,',
         '        "fix_photos": [], "source": "manual", "warranty_claim_id": cid,')]),
    ("M19 'selesai' tanpa bukti foto diterima (tiga lapis dimatikan)", G_HO, [
        ("backend/models_p50.py",
         "    photo_file_ids: List[str] = Field(min_length=1)",
         "    photo_file_ids: List[str] = []"),
        ("backend/models_p50.py",
         "        rows = [str(x).strip() for x in (v or []) if str(x).strip()]\n"
         "        if not rows:",
         "        rows = [str(x).strip() for x in (v or []) if str(x).strip()]\n"
         "        if False:"),
        ("backend/warranty_engine.py",
         '    if not photos:\n        raise ValueError("Bukti foto perbaikan wajib',
         '    if False:\n        raise ValueError("Bukti foto perbaikan wajib')]),
    ("M20 pemeriksa boleh orang yang MENGERJAKAN perbaikannya", G_HO, [
        ("backend/warranty_engine.py",
         '    if doc.get("completed_by") and actor and doc["completed_by"] == actor:',
         "    if False:"),
        ("backend/routers/handover_router.py",
         "async def verify(cid: str, payload: WarrantyClaimVerify,\n"
         '                 user: dict = Depends(require_permission("warranty", "approve"))):',
         "async def verify(cid: str, payload: WarrantyClaimVerify,\n"
         '                 user: dict = Depends(require_permission("warranty", "update"))):')]),
    ("M21 penutupan klaim tidak menutup pekerjaan perbaikannya (menggantung)", G_HO, [
        ("backend/warranty_engine.py",
         '    if doc.get("punch_id"):\n'
         '        await db.punch_items.update_one({"id": doc["punch_id"], "org_id": org}, {"$set": {\n'
         '            "status": "closed", "closed_at": ts, "updated_at": ts}})',
         "    if False:\n"
         '        await db.punch_items.update_one({"id": doc["punch_id"], "org_id": org}, {"$set": {\n'
         '            "status": "closed", "closed_at": ts, "updated_at": ts}})')]),
    ("M22 penutupan klaim tidak menyimpan pengakuan pembeli", G_HO, [
        ("backend/warranty_engine.py",
         '        "ack_by": ack_by or doc.get("buyer_name") or actor,',
         '        "ack_by": None,')]),
    # =========================================================== 50A pembatalan BAST
    ("M23 BAST bisa dibatalkan walau klaim garansinya masih BERJALAN", G_HO, [
        ("backend/handover_engine.py",
         "    if open_claims:\n"
         '        raise ValueError(f"Masih ada {open_claims} klaim garansi berjalan',
         "    if False:\n"
         '        raise ValueError(f"Masih ada {open_claims} klaim garansi berjalan')]),
    ("M24 pembatalan BAST tidak mengembalikan status rumah", G_HO, [
        ("backend/handover_engine.py",
         '        "status": prev, "handover_id": None, "handover_number": None,\n'
         '        "handed_over_at": None, "updated_at": ts}})',
         '        "updated_at": ts}})')]),
    ("M25 pembatalan BAST tanpa alasan diterima (dua lapis dimatikan)", G_HO, [
        ("backend/models_p50.py",
         "    def _r(cls, v):\n"
         '        return _reason(v, "Alasan pembatalan serah terima")',
         "    def _r(cls, v):\n        return v"),
        ("backend/handover_engine.py",
         '    if len((reason or "").strip()) < 10:\n'
         '        raise ValueError("Alasan pembatalan minimal 10 huruf.")',
         "    if False:\n"
         '        raise ValueError("Alasan pembatalan minimal 10 huruf.")')]),
    ("M26 siapa pun boleh membatalkan BAST (izin dilonggarkan)", G_HO, [
        ("backend/routers/handover_router.py",
         '                 user: dict = Depends(require_permission("handover", "cancel"))):',
         '                 user: dict = Depends(require_permission("handover", "create"))):')]),
    # ================================================================ 50A laporan jujur
    ("M27 rekap klaim kehilangan status di luar daftar tulis tangan (tie-out bocor)", G_HO, [
        ("backend/warranty_engine.py",
         '    states = list(ref.values("warranty_claim_state"))',
         "    states = [SUBMITTED, IN_PROGRESS, DONE]")]),
    ("M28 masa tanpa klaim dilaporkan 'rata-rata 0 hari' (mengarang angka)", G_HO, [
        ("backend/warranty_engine.py",
         '        "avg_days_to_close": (round(sum(durations) / len(durations), 1) if durations else None),',
         '        "avg_days_to_close": (round(sum(durations) / len(durations), 1) if durations else 0),'),
        ("backend/warranty_engine.py",
         '        "avg_days_note": (None if durations else\n'
         '                          "Belum ada klaim yang ditutup pada saringan ini \u2014 rata-rata hari "\n'
         '                          "penyelesaian belum ada datanya (bukan 0 hari)."),',
         '        "avg_days_note": None,')]),
    # ====================================================== 50B antrean perangkat (gate 40)
    ("M29 server tidak lagi mengenali kiriman ulang (jawaban 'replay' hilang)", G_Q, [
        ("backend/offline_intake.py",
         '    if row and row.get("state") == "done":',
         "    if False:")]),
    ("M30 penanda antrean tidak pernah ditandai selesai (kunci tak berguna)", G_Q, [
        ("backend/offline_intake.py",
         '        {"$set": {"state": "done", "collection": collection, "doc_id": doc_id,',
         '        {"$set": {"state": "processing", "collection": collection, "doc_id": doc_id,')]),
    ("M31 kiriman yang DITOLAK tidak melepas kunci (pekerjaan hilang senyap)", G_Q, [
        ("backend/offline_intake.py",
         '    """Lepas kunci supaya kiriman yang DITOLAK bisa diperbaiki lalu dikirim ulang."""\n'
         "    if not ref:\n        return",
         '    """Lepas kunci supaya kiriman yang DITOLAK bisa diperbaiki lalu dikirim ulang."""\n'
         "    if True:\n        return")]),
    ("M32 absensi: jawaban kiriman ulang diabaikan router (upah ganda)", G_Q, [
        ("backend/routers/labor_router.py",
         '    if intake["state"] == "replay":\n'
         '        prior = intake.get("summary") or {}',
         '    if False:\n'
         '        prior = intake.get("summary") or {}')]),
    ("M33 buku harian & punch list: jawaban kiriman ulang diabaikan (data kembar)", G_Q, [
        ("backend/routers/field_router.py",
         '    intake = await oi.begin(org, kind, client_ref)\n'
         '    if intake["state"] == "replay":',
         '    intake = await oi.begin(org, kind, client_ref)\n'
         "    if False:")]),
    ("M34 klaim garansi dari antrean bisa jadi klaim kembar", G_Q, [
        ("backend/routers/handover_router.py",
         '    intake = await oi.begin(org, "warranty_claim", payload.client_ref)\n'
         '    if intake["state"] == "replay":',
         '    intake = await oi.begin(org, "warranty_claim", payload.client_ref)\n'
         "    if False:")]),
    ("M35 bukti perbaikan garansi dari antrean bisa terlampir dua kali", G_Q, [
        ("backend/routers/handover_router.py",
         '    intake = await oi.begin(org, "warranty_fix", payload.client_ref)\n'
         '    if intake["state"] == "replay":',
         '    intake = await oi.begin(org, "warranty_fix", payload.client_ref)\n'
         "    if False:")]),
    ("M36 jenis antrean baru dihapus dari Kamus Data (layar menulis label sendiri)", G_Q, [
        ("backend/reference_p35.py",
         '            _o("warranty_claim", "Klaim garansi"),\n',
         "")]),
]

# Mutasi DATABASE (bukan kode): index unik penanda antrean dijatuhkan.
DB_MUTATIONS = [
    ("M37 keunikan penanda antrean hanya dijaga aplikasi (index unik dijatuhkan)", G_Q,
     IDX_OFFLINE),
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str):
    (ROOT / rel).write_text(src, encoding="utf-8")


def run_gate(gate: str) -> bool:
    # Log ditaruh di /app (BUKAN /tmp): /tmp bisa dibersihkan sistem di tengah jalan dan
    # jejak mutasi ikut hilang justru saat paling dibutuhkan.
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut50_{gate}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / gate)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    return p.returncode == 0


def selected(mutations):
    """Saring mutasi lewat `--only M05,M07` atau `--from M28` (lanjutkan run yang terputus)."""
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


def restore(backup: dict):
    for path, src in backup.items():
        write(path, src)


def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def drop_index(coll: str, name: str):
    _mongo()[coll].drop_index(name)


def build_index(coll: str, name: str, keys):
    _mongo()[coll].create_index(keys, name=name, unique=True)


def check_patterns() -> int:
    """Mode cepat: pastikan seluruh pola mutasi masih ada di kode (tanpa menjalankan gate)."""
    print("=" * 78)
    print("PERIKSA POLA MUTASI FASE 50 (cepat, tanpa menjalankan gate)")
    print("=" * 78)
    bad = []
    for name, _gate, patches in MUTATIONS:
        missing = [f"{p} :: {find[:60]}" for p, find, _r in patches if find not in read(p)]
        print(f"  {'OK   ' if not missing else 'HILANG'} {name}")
        for m in missing:
            print(f"        - {m}")
        bad += missing
    idx = _mongo()[IDX_OFFLINE[0]].index_information()
    has = IDX_OFFLINE[1] in idx
    print(f"  {'OK   ' if has else 'HILANG'} M37 index unik {IDX_OFFLINE[1]} ada di database")
    if not has:
        bad.append("index uq_offline_intake_ref tidak ada")
    print("-" * 78)
    print(f"{len(MUTATIONS) + 1} mutasi · {len(bad)} pola hilang")
    return 1 if bad else 0


def main() -> int:
    if "--check" in sys.argv:
        return check_patterns()
    print("=" * 78)
    print("UJI-MUTASI FASE 50 — membuktikan gate serah terima/garansi & antrean BERGIGI")
    print("=" * 78)
    print("\nBaseline (dua gate harus HIJAU sebelum merusak apa pun):")
    for g in (G_HO, G_Q):
        ok = run_gate(g)
        print(f"  {'HIJAU' if ok else 'MERAH'}  {g}")
        if not ok:
            print(f"  BASELINE MERAH — perbaiki dulu (log: /tmp/mut50_{g}.log)")
            return 1

    caught, escaped, skipped = [], [], []
    todo = selected(MUTATIONS)
    print(f"\n{len(todo)} mutasi kode akan dijalankan"
          f"{' (saringan --only/--from aktif)' if len(todo) != len(MUTATIONS) else ''}.")
    for name, gate, patches in todo:
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            skipped.append(name)
            print(f"  LEWAT      {name} — {e}")
            continue
        try:
            time.sleep(6)          # tunggu backend memuat ulang kode yang dirusak
            ok = run_gate(gate)
        finally:
            restore(backup)
            time.sleep(6)          # tunggu backend kembali ke kode yang benar
        if ok:
            escaped.append(name)
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya")
        else:
            caught.append(name)
            print(f"  TERTANGKAP {name}")

    for name, gate, (coll, iname, keys) in selected(DB_MUTATIONS):
        try:
            drop_index(coll, iname)
        except Exception as e:  # noqa: BLE001 — index tidak ada = mutasi tidak bisa diuji
            skipped.append(name)
            print(f"  LEWAT      {name} — {e}")
            continue
        try:
            ok = run_gate(gate)
        finally:
            build_index(coll, iname, keys)
        if ok:
            escaped.append(name)
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya")
        else:
            caught.append(name)
            print(f"  TERTANGKAP {name}")

    print("\n" + "=" * 78)
    print(f"TERTANGKAP: {len(caught)} · LOLOS: {len(escaped)} · LEWAT: {len(skipped)}")
    print("\nBaseline setelah semua mutasi dipulihkan:")
    final_ok = True
    for g in (G_HO, G_Q):
        ok = run_gate(g)
        final_ok = final_ok and ok
        print(f"  {'hijau kembali' if ok else 'MASIH MERAH'}  {g}")
    if escaped or skipped or not final_ok:
        for n in escaped:
            print(f"  - LOLOS: {n}")
        for n in skipped:
            print(f"  - LEWAT: {n}")
        return 1
    print("\nSEMUA MUTASI TERTANGKAP — gate Fase 50 terbukti bergigi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
