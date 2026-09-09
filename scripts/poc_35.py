#!/usr/bin/env python3
"""POC/verifikasi Fase 35 — PAPAN MANDOR TAHAN SINYAL HILANG (antrean offline).

Yang dibuktikan di sini adalah KONTRAK SERVER yang dipakai antrean di perangkat
(IndexedDB) — lewat API NYATA, bukan unit test terisolasi:

  A. Papan bisa dijadikan cuplikan offline — payload `board/today` memuat SEMUA yang
     dibutuhkan untuk merender & mengisi kartu tanpa jaringan (id, unit, langkah, syarat
     foto, checklist mutu lengkap, instruksi, kebijakan bukti).
  B. Kamus label antrean ada di SSOT `/api/reference` (`offline_queue_status`,
     `offline_queue_kind`) — bukan peta hardcode di frontend.
  C. Unggah bukti yang ditunda: foto yang tersimpan di HP tetap diunggah dengan
     watermark + koordinat saat sinyal kembali.
  D. Aksi "mulai dikerjakan" yang diantrekan aman dikirim berulang; bila sudah tidak
     relevan, server menolak dengan alasan manusiawi (antrean menampilkannya).
  E. Penjaga Fase 31/32 tetap berlaku lewat jalur antrean: urutan tidak bisa dilangkahi,
     RBAC & pemisahan tugas tetap, jalur Work Hub generik tetap ditolak.
  F. INTI — kirim ulang TIDAK melahirkan bukti dobel: `client_ref` membuat pengajuan
     idempoten (jejak audit 1, foto tidak bertambah, tugas verifikasi tidak dobel),
     termasuk saat dua pengirim berbarengan (dua tab di HP yang sama).
  G. Antrean tidak berbohong: kalau server MENOLAK, alasannya asli & manusiawi, dan
     penanda antrean masih bisa dipakai lagi setelah diperbaiki (kunci dilepas) —
     supaya pekerjaan tidak "hilang senyap".
  H. Setelah antrean terkirim, alur verifikasi supervisor tetap tuntas.

Jalankan pada DB tersegar: bash scripts/seed_reset.sh (atau drop DB + restart backend),
lalu `python3 scripts/poc_35.py`.
"""
import io
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []
WORK_GROUPS = ("overdue", "today", "in_progress", "rework", "scheduled_later")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {str(detail)[:180]}" if detail else ""))
    return bool(cond)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=90)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=120)


def photo_bytes(label: str) -> bytes:
    """Foto berbeda tiap panggilan — penjaga 'anti foto daur ulang' memeriksa sha256."""
    img = Image.new("RGB", (900, 640), (196, 208, 220))
    dr = ImageDraw.Draw(img)
    dr.rectangle([40, 40, 860, 600], outline=(30, 40, 60), width=6)
    dr.text((70, 90), f"BUKTI LAPANGAN\n{label}\n{uuid.uuid4()}", fill=(10, 20, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def upload(h, label, owner_id=None, watermark=None, geo=None):
    """Meniru PERSIS apa yang dilakukan antrean saat sinyal kembali (multipart)."""
    files = {"file": (f"{label}.jpg", photo_bytes(label), "image/jpeg")}
    data = {"owner_type": "build"}
    if owner_id:
        data["owner_id"] = owner_id
    if watermark:
        data["watermark"] = watermark
    if geo:
        data.update({"lat": str(geo[0]), "lng": str(geo[1]), "accuracy": "12"})
    return requests.post(f"{BASE}/files/upload", headers=h, files=files, data=data, timeout=120)


def photo_ids(h, row, n):
    wm = f"Cluster Asri Blok A · Kavling {row.get('unit_code')}"
    out = []
    for i in range(max(0, n)):
        r = upload(h, f"antrean-{row.get('step_code')}-{i}", owner_id=row["id"], watermark=wm)
        out.append(((r.json() or {}).get("data") or {}).get("id"))
    return [x for x in out if x]


def item_detail(h, item_id):
    return g(h, f"/build/items/{item_id}").json()


def board(h):
    return (g(h, "/build/board/today").json() or {}).get("data") or {}


def rows_of(bd, *groups):
    return [r for k in groups for r in ((bd.get("groups") or {}).get(k) or [])]


def snapshot_answers(row):
    """Jawaban checklist disusun dari CUPLIKAN PAPAN — persis kemampuan perangkat offline."""
    return [{"code": c["code"], "result": "pass", "note": None}
            for c in (row.get("checklist") or [])]


def submit(h, item_id, note, photos, checklist, ref=None, geo=None):
    body = {"note": note, "photo_file_ids": photos, "checklist": checklist}
    if ref:
        body["client_ref"] = ref
    if geo:
        body["geo"] = {"lat": geo[0], "lng": geo[1], "accuracy": 12}
    return po(h, f"/build/items/{item_id}/submit", body)


def subs_count(h, item_id):
    return len(item_detail(h, item_id).get("submissions") or [])


def photos_of(h, item_id):
    ev = item_detail(h, item_id).get("data", {}).get("evidence") or []
    return [e for e in ev if str(e.get("content_type") or "").startswith("image")]


def verify_tasks(item_id):
    return mdb.tasks.count_documents({
        "meta.build_item_id": item_id, "jobdesk_code": "TK-11",
        "status": {"$in": ["open", "in_progress", "snoozed", "submitted"]}})


def main():  # noqa: C901 — satu alur POC dibaca berurutan, sengaja tidak dipecah
    site = login("site@sipro.co.id")
    pm = login("pm@sipro.co.id")
    sales = login("sales@sipro.co.id")

    # ============ A. papan bisa dijadikan cuplikan offline yang BERGUNA ============
    head("A. Papan Mandor bisa disimpan sebagai cuplikan offline yang bisa diisi")
    bd = board(site)
    groups = bd.get("groups") or {}
    check("papan memberi kelompok kerja + waktu acuan",
          bool(bd.get("as_of")) and isinstance(groups, dict), bd.get("counts"))
    workable = rows_of(bd, *WORK_GROUPS)
    if not check("ada minimal 3 pekerjaan siap kerja untuk skenario POC", len(workable) >= 3,
                 f"{len(workable)} kartu siap kerja"):
        print("\nDB belum tersegar. Jalankan: bash scripts/seed_reset.sh lalu ulangi.")
        sys.exit(1)
    need = {"id", "unit_code", "step_code", "name", "min_photos", "status"}
    check("setiap kartu memuat data yang cukup untuk dirender tanpa jaringan",
          all(need <= set(r) for r in workable), sorted(need - set(workable[0])))
    check("checklist mutu LENGKAP ikut di payload (bisa dijawab tanpa jaringan)",
          all(len(r.get("checklist") or []) == int(r.get("checklist_total") or 0)
              and all({"code", "text"} <= set(c) for c in (r.get("checklist") or []))
              for r in workable),
          [(r["step_code"], r.get("checklist_total"), len(r.get("checklist") or []))
           for r in workable])
    check("instruksi kerja ikut di payload (mandor tetap bisa baca saat offline)",
          all(isinstance(r.get("instruction"), list) and r["instruction"] for r in workable))
    check("kebijakan bukti kerja ikut dikirim (aturan sama saat offline)",
          "min_note_chars" in (bd.get("policy") or {}), bd.get("policy"))

    # Peran tiap kandidat DITETAPKAN DI AWAL supaya tidak ada langkah yang terlewat diam-diam.
    main_row, race_row, reject_row = workable[0], workable[1], workable[2]
    upcoming = rows_of(bd, "upcoming")
    check("ada 'instruksi menunggu' untuk uji urutan", bool(upcoming), len(upcoming))
    check("kandidat POC punya tugas Work Hub aktif (untuk uji anti-bypass)",
          bool(main_row.get("task_id")), main_row.get("task_id"))

    # ============ B. kamus label antrean dari SSOT ============
    head("B. Label antrean perangkat berasal dari SSOT /api/reference")
    reg = g(site, "/reference").json().get("data") or {}
    st = {o["value"] for o in (reg.get("offline_queue_status") or {}).get("options", [])}
    kd = {o["value"] for o in (reg.get("offline_queue_kind") or {}).get("options", [])}
    check("grup offline_queue_status terdaftar", {"pending", "sending", "rejected"} <= st, st)
    check("grup offline_queue_kind terdaftar", {"build_submit", "build_start"} <= kd, kd)
    check("label antrean berbahasa manusia (bukan kode mentah)",
          any("jaringan" in o["label"].lower()
              for o in reg["offline_queue_status"]["options"]),
          [o["label"] for o in reg["offline_queue_status"]["options"]])

    # ============ C. unggah bukti yang tertunda ============
    head("C. Foto yang tersimpan di HP tetap terunggah utuh saat sinyal kembali")
    wm = f"Cluster Asri Blok A · Kavling {main_row['unit_code']}"
    ru = upload(site, "antrean-1", owner_id=main_row["id"], watermark=wm,
                geo=(-6.2413, 106.8102))
    up = (ru.json() or {}).get("data") or {}
    check("unggah tertunda diterima server", ru.status_code == 200 and bool(up.get("id")),
          ru.text[:120])
    check("foto dioptimalkan & diberi watermark oleh server",
          up.get("saving_pct") is not None and int(up.get("size") or 0) > 0,
          f"{up.get('size')} byte, hemat {up.get('saving_pct')}%")
    check("koordinat pengambilan tersimpan terstruktur", bool(up.get("geo")), up.get("geo"))

    # ============ D. aksi 'mulai dikerjakan' yang diantrekan ============
    head("D. Aksi 'mulai dikerjakan' dari antrean aman dikirim berulang")
    a1 = po(site, f"/build/items/{main_row['id']}/start")
    a2 = po(site, f"/build/items/{main_row['id']}/start")
    check("kirim 'mulai' dua kali tetap diterima (antrean tidak macet)",
          a1.status_code == 200 and a2.status_code == 200, f"{a1.status_code}/{a2.status_code}")
    check("status akhir tetap 'sedang dikerjakan' (tidak ganda/mundur)",
          (a2.json().get("data") or {}).get("status") == "in_progress",
          (a2.json().get("data") or {}).get("status"))

    # ============ E. penjaga Fase 31/32 tetap berlaku ============
    head("E. Jalur antrean tidak melemahkan penjaga yang sudah ada")
    if upcoming:
        blocked = upcoming[0]
        rb = submit(site, blocked["id"], "Coba melangkahi urutan lewat jalur antrean offline.",
                    photo_ids(site, blocked, 1), snapshot_answers(blocked),
                    ref=f"poc35-{uuid.uuid4().hex[:8]}")
        check("urutan pekerjaan tetap tidak bisa dilangkahi (walau lewat antrean)",
              rb.status_code == 400 and "terkunci" in rb.text.lower(),
              f"{rb.status_code} {rb.text[:130]}")
    rs = submit(sales, main_row["id"], "Sales mencoba mengajukan hasil kerja konstruksi.",
                [], [], ref=f"poc35-{uuid.uuid4().hex[:8]}")
    check("sales tetap tidak boleh mengajukan hasil kerja", rs.status_code == 403, rs.status_code)
    if main_row.get("task_id"):
        rwh = po(site, f"/work/tasks/{main_row['task_id']}/submit",
                 {"note": "Bypass lewat Work Hub generik untuk pekerjaan konstruksi."})
        check("jalur Work Hub generik tetap ditolak & diarahkan ke Papan Mandor",
              rwh.status_code == 400 and "papan mandor" in rwh.text.lower(),
              f"{rwh.status_code} {rwh.text[:140]}")

    # ============ F. INTI: idempotensi client_ref ============
    head("F. Kirim ulang antrean TIDAK melahirkan bukti/pengajuan dobel")
    ans = snapshot_answers(main_row)
    minp = int(main_row.get("min_photos") or 1)
    ph = [up["id"]] + photo_ids(site, main_row, minp - 1)
    ref = f"poc35-{uuid.uuid4().hex[:12]}"
    note = "Pengecoran selesai, bekisting dibuka, hasil rata (uji antrean offline)."
    r1 = submit(site, main_row["id"], note, ph, ans, ref=ref)
    b1 = r1.json() if r1.status_code == 200 else {}
    check("pengajuan pertama dari antrean diterima (jawaban dari cuplikan papan)",
          r1.status_code == 200 and b1.get("data", {}).get("status") == "submitted",
          r1.text[:200])
    check("pengajuan pertama BUKAN pemutaran ulang", b1.get("replay") is False, b1.get("replay"))
    subs1 = subs_count(pm, main_row["id"])
    ph1 = len(photos_of(pm, main_row["id"]))
    tk1 = verify_tasks(main_row["id"])
    check("tepat 1 jejak audit pengajuan tercatat", subs1 == 1, subs1)
    check("tepat 1 tugas verifikasi dibuat untuk supervisor", tk1 == 1, tk1)

    r2 = submit(site, main_row["id"], note, ph, ans, ref=ref)
    b2 = r2.json() if r2.status_code == 200 else {}
    check("kirim ulang dengan penanda SAMA tidak error (diputar ulang)",
          r2.status_code == 200 and b2.get("replay") is True,
          f"{r2.status_code} {r2.text[:140]}")
    check("pesan kirim-ulang jujur ke pengguna (bukan 'berhasil' palsu)",
          "sudah diterima" in (b2.get("message") or "").lower(), b2.get("message"))
    check("jejak audit tetap 1 setelah kirim ulang", subs_count(pm, main_row["id"]) == subs1)
    check("bukti foto TIDAK bertambah setelah kirim ulang",
          len(photos_of(pm, main_row["id"])) == ph1, len(photos_of(pm, main_row["id"])))
    check("tugas verifikasi TIDAK dobel setelah kirim ulang",
          verify_tasks(main_row["id"]) == tk1, verify_tasks(main_row["id"]))
    r3 = submit(site, main_row["id"], note, ph, ans, ref=f"poc35-{uuid.uuid4().hex[:12]}")
    check("penanda BARU pada pekerjaan yang sudah diajukan ditolak dengan alasan",
          r3.status_code == 400 and "diajukan" in r3.text.lower(),
          f"{r3.status_code} {r3.text[:140]}")
    rstart = po(site, f"/build/items/{main_row['id']}/start")
    check("antrean 'mulai' yang sudah tidak relevan ditolak dengan alasan terbaca",
          rstart.status_code == 400 and "diajukan" in rstart.text.lower(),
          f"{rstart.status_code} {rstart.text[:130]}")

    # dua pengirim berbarengan (dua tab HP membaca antrean yang sama)
    cminp = int(race_row.get("min_photos") or 1)
    cph = photo_ids(site, race_row, cminp)
    cans = snapshot_answers(race_row)
    cref = f"poc35-race-{uuid.uuid4().hex[:10]}"
    cnote = "Uji kirim berbarengan dua tab — hasil harus tetap satu pengajuan."
    with ThreadPoolExecutor(max_workers=2) as ex:
        res = [f.result() for f in
               [ex.submit(submit, site, race_row["id"], cnote, cph, cans, cref)
                for _ in range(2)]]
    check("dua kiriman berbarengan tidak menghasilkan galat server (500)",
          all(x.status_code == 200 for x in res), sorted(x.status_code for x in res))
    check("kiriman berbarengan hanya menghasilkan 1 jejak audit",
          subs_count(pm, race_row["id"]) == 1, subs_count(pm, race_row["id"]))
    check("kiriman berbarengan hanya menghasilkan 1 tugas verifikasi",
          verify_tasks(race_row["id"]) == 1, verify_tasks(race_row["id"]))
    check("bukti foto kiriman berbarengan tidak dobel",
          len(photos_of(pm, race_row["id"])) == cminp, len(photos_of(pm, race_row["id"])))
    check("tepat satu kiriman berbarengan ditandai pemutaran ulang",
          sum(1 for x in res if (x.json() or {}).get("replay")) == 1,
          [(x.json() or {}).get("replay") for x in res])

    # ============ G. penolakan server tetap jujur & bisa diperbaiki ============
    head("G. Bila server menolak: alasan asli, bukti tidak dibuang, penanda bisa dipakai lagi")
    rminp = int(reject_row.get("min_photos") or 3)
    rans = snapshot_answers(reject_row)
    rref = f"poc35-retry-{uuid.uuid4().hex[:10]}"
    few = photo_ids(site, reject_row, 1)
    rr = submit(site, reject_row["id"], "Foto sengaja kurang untuk uji penolakan antrean.",
                few, rans, ref=rref)
    check("foto kurang dari syarat ditolak dengan angka jelas",
          rr.status_code == 400 and str(rminp) in rr.text,
          f"{rr.status_code} {(rr.json() or {}).get('detail', '')[:130]}")
    rshort = submit(site, reject_row["id"], "kurang", few, rans,
                    ref=f"poc35-{uuid.uuid4().hex[:8]}")
    check("catatan terlalu pendek ditolak server (bukan hanya di UI)",
          rshort.status_code in (400, 422), rshort.status_code)
    crit = [c for c in (reject_row.get("checklist") or []) if c.get("critical")]
    if crit:
        bad = [dict(a, result="fail") for a in rans]
        rbad = submit(site, reject_row["id"], "Uji item mutu kritis gagal pada antrean.",
                      photo_ids(site, reject_row, rminp), bad,
                      ref=f"poc35-{uuid.uuid4().hex[:8]}")
        check("item mutu KRITIS gagal tetap ditolak lewat jalur antrean",
              rbad.status_code == 400 and "kritis" in rbad.text.lower(),
              f"{rbad.status_code} {rbad.text[:130]}")
    # PENTING: penanda yang sama harus BISA dipakai lagi setelah diperbaiki — kalau tidak,
    # antrean akan menghapus pekerjaan yang sebenarnya belum pernah terkirim.
    full = few + photo_ids(site, reject_row, rminp - 1)
    rok = submit(site, reject_row["id"],
                 "Sudah dilengkapi seluruh foto bukti setelah ditolak server.",
                 full, rans, ref=rref)
    check("penanda antrean yang sama BISA dipakai lagi setelah penolakan diperbaiki",
          rok.status_code == 200 and rok.json().get("data", {}).get("status") == "submitted",
          f"{rok.status_code} {rok.text[:150]}")
    check("perbaikan itu menghasilkan tepat 1 jejak audit (bukan dua)",
          subs_count(pm, reject_row["id"]) == 1, subs_count(pm, reject_row["id"]))

    # ============ H. alur normal tetap tuntas ============
    head("H. Setelah antrean terkirim, alur verifikasi normal tetap berjalan")
    rself = po(site, f"/build/items/{main_row['id']}/verify", {"note": "verifikasi sendiri"})
    check("pemisahan tugas tetap: pengaju tidak bisa memverifikasi sendiri",
          rself.status_code == 403, f"{rself.status_code} {rself.text[:110]}")
    rv = po(pm, f"/build/items/{main_row['id']}/verify",
            {"note": "Bukti dari antrean offline sesuai spesifikasi."})
    check("supervisor bisa memverifikasi hasil yang datang dari antrean",
          rv.status_code == 200 and (rv.json().get("data") or {}).get("status") == "done",
          f"{rv.status_code} {rv.text[:150]}")
    check("bukti dari antrean tersimpan sebagai bukti resmi item",
          len(photos_of(pm, main_row["id"])) >= minp, len(photos_of(pm, main_row["id"])))

    print("\n" + "=" * 58)
    print(f"HASIL poc_35: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print(f"  - GAGAL: {f}")
        sys.exit(1)
    print("POC FASE 35 LULUS — antrean offline tidak kehilangan & tidak menggandakan bukti.")


if __name__ == "__main__":
    main()
