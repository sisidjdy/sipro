#!/usr/bin/env python3
"""verify_p64.py — GATE 55: pusat notifikasi berkategori & bisa habis (Fase 64).

  K — KODE: kategori & penanda "perlu tindakan" DITURUNKAN dari data yang sudah ada (bukan
      field baru yang harus diisi 30 pemanggil), tautan navigasi punya SATU peta, notifikasi
      yang tindakannya sudah dilakukan dicabut sendiri (tidak dihapus — `resolved_at` +
      alasan), dan yang sudah dilihat bisa dibersihkan.
  K-UI — LAYAR: satu notifikasi = satu BARIS padat (bukan kartu tiga baris), keadaan dipisah
      (perlu tindakan / belum dibaca / sudah dilihat / semua), kategori sebagai saringan
      berjumlah, dan barisnya membawa pemakai ke halaman pekerjaannya.
  D — PERILAKU (server hidup): saringan bekerja, pencabutan otomatis terbukti (tutup tugas →
      notifikasinya hilang dari "perlu tindakan"), dismiss & clear-read bekerja, dan
      notifikasi orang lain tidak bisa disentuh.

Jalankan: python3 scripts/verify_p64.py
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
API = "http://localhost:8001/api"
PASSWORD = "Sipro#2026"

ok, fails = 0, []


def check(cond, label, detail=None):
    global ok
    if cond:
        ok += 1
        print(f"  OK    {label}")
        return True
    fails.append(label)
    print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def hdr(email: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD},
                      timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def mongo():
    load_dotenv(BE / ".env")
    cli = MongoClient(os.environ["MONGO_URL"])
    return cli, cli[os.environ["DB_NAME"]]


def bagian_k():
    head("K. Kode: kategori turunan, satu peta tautan, notifikasi yang bisa habis")
    nc = read(BE / "notif_center.py")
    rt = read(BE / "routers" / "activity_router.py")
    rf = read(BE / "reference_p64.py")
    check("TYPE_CATEGORY" in nc and "ENTITY_CATEGORY" in nc,
          "K1 kategori diturunkan dari `type` + `related_entity_type` (data lama ikut)")
    check("def needs_action" in nc and "ACTION_TYPES" in nc,
          "K2 'perlu tindakan' dibedakan dari kabar informatif")
    check("ENTITY_LINK" in nc and "TYPE_LINK" in nc and "def link_of" in nc,
          "K3 tautan navigasi punya SATU peta (halaman & lonceng tidak menebak sendiri)")
    check("TYPE_LINK_WINS" in nc,
          "K4 notifikasi tugas membawa ke papan tugas (tempat tindakannya)")
    check("RESOLVERS" in nc and "resolved_reason" in nc,
          "K5 pencabutan otomatis menyebut ALASAN (jejaknya bisa diperiksa)")
    check("def resolve_done" in nc and "_resolve_task_notifs" in nc,
          "K6 dua jalur pencabutan: entitas berstatus & notifikasi tugas")
    check("dari_tugas = await _resolve_task_notifs" in nc
          and "if not rows:\n        return dari_tugas" in nc,
          "K7 pencabutan tugas tetap jalan walau tak ada notifikasi berentitas")
    check("update_many" in nc and "delete_many" not in nc,
          "K8 notifikasi TIDAK dihapus — hanya ditandai (audit tetap utuh)")
    check("dismissed_at" in rt and "clear-read" in rt,
          "K9 notifikasi bisa disembunyikan satu-satu & yang sudah dilihat dibersihkan")
    check('"user_email": user.get("email")' in rt,
          "K10 semua aksi terikat pemilik notifikasi (tidak bisa menyentuh milik orang lain)")
    check("state" in rt and "category" in rt and "summary" in rt,
          "K11 daftar menerima keadaan + kategori dan mengirim ringkasan berjumlah")
    check("unread_only" in rt,
          "K12 kontrak lama (`unread_only`) tetap didukung — lonceng TopBar tidak pecah")
    check("notification_category" in rf and "notification_state" in rf,
          "K13 label kategori & keadaan hidup di registry SSOT")


def bagian_kui():
    head("K-UI. Layar: baris padat, keadaan terpisah, kategori berjumlah, bisa dibuka")
    page = read(FE / "pages" / "NotificationsPage.js")
    rows = read(FE / "components" / "notifications" / "NotificationRows.js")
    ids = read(FE / "constants" / "testIds" / "home.js")
    check("NotificationRows" in page and "divide-y" in rows,
          "KUI1 satu notifikasi = satu baris pada daftar padat (bukan kartu tinggi)")
    check("truncate" in rows and "py-2" in rows,
          "KUI2 isi notifikasi dipangkas satu baris — daftar tidak lagi memanjang")
    check("NOTIF.stateTab" in page and "STATE_ORDER" in page
          and 'labelOf("notification_state"' in page,
          "KUI3 keadaan dipisah (perlu tindakan/belum dibaca/sudah dilihat/semua) dari SSOT")
    check("NOTIF.categoryChip" in page and "per_category" in page,
          "KUI4 kategori jadi saringan sekali klik BERJUMLAH")
    check("useNavigate" in rows and "n.link" in rows,
          "KUI5 baris membawa pemakai ke halaman pekerjaannya")
    check("NOTIF.actionBadge" in rows and "NOTIF.resolvedNote" in rows,
          "KUI6 penanda 'perlu tindakan' & 'sudah ditangani' terlihat di baris")
    check("NOTIF.dismissBtn" in rows and "NOTIF.clearReadBtn" in page,
          "KUI7 notifikasi bisa disembunyikan & yang sudah dilihat dibersihkan dari layar")
    check("NOTIF.search" in page,
          "KUI8 notifikasi bisa dicari (bukan digulir sampai bawah)")
    check("useListQuery" in page,
          "KUI9 keadaan & kategori hidup di URL (bisa dibagikan / tombol Kembali)")
    check("CATEGORY_ICON" in rows and "CATEGORY_ICON" in page,
          "KUI10 ikon kategori satu sumber (layar tidak punya dua peta ikon)")
    check("stateTab" in ids and "dismissBtn" in ids and "categoryChip" in ids,
          "KUI11 elemen baru punya data-testid")
    check("emptyFor" in page and "dicabut sendiri" in page,
          "KUI12 keadaan kosong menjelaskan MENGAPA kosong (bukan layar hampa)")


def bagian_d():
    head("D. Perilaku server: saringan, pencabutan otomatis, dismiss, milik orang lain")
    owner = hdr("owner@sipro.co.id")
    sales = hdr("sales@sipro.co.id")

    r = requests.get(f"{API}/notifications", headers=owner, params={"state": "action"},
                     timeout=60)
    d = r.json() if r.status_code == 200 else {}
    check(r.status_code == 200 and "summary" in d,
          "D1 daftar 'perlu tindakan' + ringkasan terbaca", f"status {r.status_code}")
    ring = d.get("summary") or {}
    check(all(k in ring for k in ("per_category", "unread", "read", "needs_action")),
          "D2 ringkasan memuat jumlah per kategori & per keadaan")
    check(all(x.get("needs_action") for x in d.get("data") or []),
          "D3 tampilan 'perlu tindakan' HANYA berisi yang menuntut tindakan")
    check(all(x.get("category") for x in d.get("data") or []),
          "D4 setiap notifikasi berkategori (tidak ada yang tanpa golongan)")
    bertautan = [x for x in d.get("data") or [] if x.get("link")]
    check(len(bertautan) >= max(1, len(d.get("data") or []) // 2),
          "D5 mayoritas notifikasi tindakan punya tautan ke pekerjaannya",
          f"{len(bertautan)}/{len(d.get('data') or [])}")

    sudah = requests.get(f"{API}/notifications", headers=owner, params={"state": "read"},
                         timeout=60).json()
    check(all(x.get("read") for x in sudah.get("data") or []),
          "D6 tampilan 'sudah dilihat' hanya berisi yang sudah dibaca")
    kat = requests.get(f"{API}/notifications", headers=owner,
                       params={"state": "all", "category": "keuangan"}, timeout=60).json()
    check(all(x.get("category") == "keuangan" for x in kat.get("data") or []),
          "D7 saringan kategori dipatuhi server")
    cari = requests.get(f"{API}/notifications", headers=owner,
                        params={"state": "all", "q": "komisi"}, timeout=60).json()
    check(all("komisi" in f"{x.get('title')} {x.get('body')}".lower()
              for x in cari.get("data") or []),
          "D8 pencarian judul/isi dipatuhi server")
    lonceng = requests.get(f"{API}/notifications", headers=owner,
                           params={"unread_only": True, "limit": 1}, timeout=60)
    check(lonceng.status_code == 200 and "unread" in lonceng.json(),
          "D9 kontrak lonceng TopBar (`unread_only`) tetap bekerja")

    # ---- pencabutan otomatis: tutup SELURUH tugas berjudul sama, notifikasinya harus lepas
    cli, db = mongo()
    try:
        n = db.notifications.find_one(
            {"user_email": "owner@sipro.co.id", "type": "task",
             "title": {"$regex": "^Tugas baru: "}}, {"_id": 0, "id": 1, "title": 1})
        if not n:
            check(False, "D10..D12 butuh notifikasi tugas di data demo")
        else:
            judul = n["title"][len("Tugas baru: "):]
            ids = [t["id"] for t in db.tasks.find(
                {"assigned_to": "owner@sipro.co.id", "title": judul}, {"id": 1})]
            db.tasks.update_many({"id": {"$in": ids}}, {"$set": {"status": "done"}})
            after = requests.get(f"{API}/notifications", headers=owner,
                                 params={"state": "action"}, timeout=60).json()
            check(after.get("auto_resolved", 0) >= 1,
                  "D10 tugas ditutup → notifikasinya DICABUT sendiri",
                  f"auto_resolved={after.get('auto_resolved')}")
            check(n["id"] not in [x["id"] for x in after.get("data") or []],
                  "D11 notifikasi yang tindakannya selesai hilang dari 'perlu tindakan'")
            fresh = db.notifications.find_one({"id": n["id"]},
                                              {"_id": 0, "resolved_at": 1,
                                               "resolved_reason": 1})
            check(bool(fresh and fresh.get("resolved_at") and fresh.get("resolved_reason")),
                  "D12 pencabutan menyimpan waktu + alasan (bukan menghapus baris)")
            # pulihkan bahan uji
            db.tasks.update_many({"id": {"$in": ids}}, {"$set": {"status": "open"}})
            db.notifications.update_many(
                {"user_email": "owner@sipro.co.id",
                 "resolved_reason": "tugasnya sudah tidak terbuka lagi"},
                {"$set": {"resolved_at": None, "resolved_reason": None, "read": False,
                          "read_at": None}})
            check(db.notifications.count_documents(
                {"user_email": "owner@sipro.co.id", "id": n["id"], "read": False}) == 1,
                "D13 bahan uji dipulihkan (data demo tidak tercemar)")
    finally:
        cli.close()

    # ---- dismiss & clear-read
    cli, db = mongo()
    try:
        target = db.notifications.find_one(
            {"user_email": "sales@sipro.co.id", "dismissed_at": None}, {"_id": 0, "id": 1})
        if not target:
            check(False, "D14..D16 butuh notifikasi milik sales di data demo")
        else:
            tid = target["id"]
            res = requests.post(f"{API}/notifications/{tid}/dismiss", headers=sales,
                                timeout=30)
            check(res.status_code == 200, "D14 notifikasi bisa disembunyikan satu-satu",
                  f"status {res.status_code}")
            daftar = requests.get(f"{API}/notifications", headers=sales,
                                  params={"state": "all", "limit": 50}, timeout=60).json()
            check(tid not in [x["id"] for x in daftar.get("data") or []],
                  "D15 notifikasi yang disembunyikan tidak muncul lagi di daftar")
            check(db.notifications.count_documents({"id": tid}) == 1,
                  "D16 barisnya TETAP ADA di basis data (bukan dihapus)")
            check(requests.post(f"{API}/notifications/{tid}/dismiss", headers=owner,
                                timeout=30).status_code == 404,
                  "D17 notifikasi milik orang lain tidak bisa disentuh (404)")
            # pulihkan
            db.notifications.update_one({"id": tid}, {"$set": {"dismissed_at": None,
                                                              "read": False,
                                                              "read_at": None}})
            check(True, "D18 bahan uji dismiss dipulihkan")
    finally:
        cli.close()

    kosong = requests.post(f"{API}/notifications/read-all", headers=owner,
                           params={"category": "layanan"}, timeout=30)
    check(kosong.status_code == 200,
          "D19 'tandai dibaca' bisa dibatasi SATU kategori", f"status {kosong.status_code}")
    check(requests.post(f"{API}/notifications/tidak-ada/read", headers=owner,
                        timeout=30).status_code == 404,
          "D20 notifikasi yang tidak ada = 404")


def main():
    print("=" * 78)
    print("GATE 55 — Fase 64: pusat notifikasi berkategori, bernavigasi, dan bisa habis")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 55 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 55 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
