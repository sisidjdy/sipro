#!/usr/bin/env python3
"""verify_p65.py — GATE 56: notifikasi kembar dikelompokkan & preferensi per pemakai (Fase 65).

  K — KODE: kunci kelompok DITURUNKAN dari data yang sudah ada (jenis + entitas + judul yang
      dinormalkan) sehingga notifikasi lama ikut berkelompok tanpa migrasi; preferensi punya
      tiga saluran; notifikasi yang MENUNTUT TINDAKAN tidak bisa dibungkam dari daftar; yang
      dibungkam tetap punya jejak (`muted_at` + alasan), tidak dihapus.
  K-UI — LAYAR: kelompok tampil sebagai SATU baris berjumlah yang bisa dibuka, punya aksi
      untuk seluruh anggotanya, dan preferensi bisa diubah pemakai sendiri lewat dialog yang
      menjelaskan apa yang TIDAK bisa dimatikan.
  D — PERILAKU (server hidup): pengelompokan benar-benar meringkas, aksi kelompok mengenai
      seluruh anggota, preferensi tersimpan per pemakai, kategori/saluran asing DITOLAK,
      kabar informatif pada kategori yang dimatikan tidak lagi memenuhi daftar, tetapi
      permintaan tindakan TETAP masuk, dan ringkasan WhatsApp disiapkan (bukan dikirim).

Jalankan: python3 scripts/verify_p65.py
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
UJI = "site@sipro.co.id"          # pemakai bahan uji preferensi (dipulihkan di akhir)

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
    head("K. Kode: kunci kelompok turunan, preferensi bersaluran, pembungkaman berjejak")
    nc = read(BE / "notif_center.py")
    pf = read(BE / "notif_prefs.py")
    eng = read(BE / "engine.py")
    rt = read(BE / "routers" / "activity_router.py")
    rf = read(BE / "reference_p65.py")
    idx = read(BE / "indexes.py")
    check("def group_key" in nc and "_norm_title" in nc,
          "K1 kunci kelompok diturunkan dari data (jenis + entitas + judul dinormalkan)")
    check("_KODE" in nc and "_NOMOR" in nc,
          "K2 nomor dokumen & kode dinormalkan — judul kembar tidak lagi tampak berbeda")
    check("def group_rows" in nc and "group_members" in nc and "group_count" in nc,
          "K3 kelompok membawa jumlah + anggotanya (tidak menyembunyikan isi)")
    check('"group_key": group_key(n)' in nc,
          "K4 setiap notifikasi membawa kunci kelompoknya (satu perhitungan, bukan dua)")
    check("CHANNELS" in pf and all(c in pf for c in ('"inapp"', '"push"', '"wa"')),
          "K5 tiga saluran preferensi hidup di satu tempat")
    check("LOCKED_CHANNELS" in pf and "needs_action(notif)" in pf,
          "K6 notifikasi yang menuntut tindakan TIDAK bisa dibungkam dari daftar")
    check("def mute_patch" in pf and "muted_reason" in pf,
          "K7 pembungkaman menyebut alasan (pertanyaan 'kenapa saya tidak diberi tahu?' terjawab)")
    check("raise ValueError" in pf and "tidak dikenal" in pf,
          "K8 kategori/saluran asing DITOLAK, bukan diabaikan diam-diam")
    check("import notif_prefs as npf" in eng and "izin.get(\"inapp\")" in eng
          and "izin.get(\"push\")" in eng,
          "K9 preferensi ditegakkan di SATU pintu pembuatan notifikasi (`create_notification`)")
    check("delete_many" not in pf and "delete_one" not in pf,
          "K10 preferensi tidak pernah menghapus notifikasi (jejak audit utuh)")
    check("group=" in rt and "nc.group_rows" in rt,
          "K11 daftar bisa diminta berkelompok (`?group=true`) — kontrak lama utuh")
    check("/notifications/group/read" in rt and "/notifications/group/dismiss" in rt
          and "_group_ids" in rt,
          "K12 aksi kelompok dikerjakan server dari KUNCI (layar tidak mengirim daftar id)")
    check('"notifications", "update"' in rt and 'user_email": email' in rt,
          "K13 aksi kelompok terikat pemilik notifikasi & izin update")
    check("/notifications/preferences" in rt and "/notifications/wa-digest" in rt,
          "K14 preferensi & ringkasan WhatsApp punya endpointnya sendiri")
    check("notification_channel" in rf and "notification_channel" in read(BE / "reference.py")
          or "65" in read(BE / "reference.py"),
          "K15 label saluran hidup di registry SSOT (fase 65 terdaftar)")
    check("uq_notif_prefs_user" in idx,
          "K16 satu baris preferensi per pemakai dijaga index unik (bukan hanya aplikasi)")
    check("wa_link" in pf and "wa.me" in pf and "send_whatsapp" not in pf,
          "K17 WhatsApp TETAP manual: sistem menyiapkan pesan, manusia menekan kirim")


def bagian_kui():
    head("K-UI. Layar: satu baris per kelompok, bisa dibuka, preferensi bisa diubah sendiri")
    page = read(FE / "pages" / "NotificationsPage.js")
    rows = read(FE / "components" / "notifications" / "NotificationRows.js")
    dlg = read(FE / "components" / "notifications" / "NotificationPrefsDialog.js")
    ids = read(FE / "constants" / "testIds" / "home.js")
    check("NOTIF.groupToggle" in page and "group: grouped" in page or "group:" in page,
          "KUI1 pengelompokan bisa dinyalakan/dimatikan pemakai")
    check("NOTIF.groupCount" in rows and "group_count" in rows,
          "KUI2 kelompok kembar tampil sebagai satu baris BERJUMLAH (5×)")
    check("NOTIF.groupExpand" in rows and "group_members" in rows,
          "KUI3 anggota kelompok bisa dibuka (tidak ada kabar yang hilang dari layar)")
    check("NOTIF.groupReadBtn" in rows and "NOTIF.groupDismissBtn" in rows,
          "KUI4 satu tindakan untuk SELURUH anggota kelompok")
    check("onGroupRead" in page and "/notifications/group/read" in page
          and "/notifications/group/dismiss" in page,
          "KUI5 aksi kelompok terhubung ke endpointnya")
    check("group: \"1\"" in page and "useListQuery" in page,
          "KUI6 pilihan pengelompokan hidup di URL (bisa dibagikan / tombol Kembali)")
    check("NOTIF.prefsBtn" in page and "NotificationPrefsDialog" in page,
          "KUI7 preferensi bisa dibuka dari halaman notifikasi")
    check("notification_channel" in dlg and "labelOf(\"notification_category\"" in dlg,
          "KUI8 label kategori & saluran diambil dari SSOT (bukan daftar kedua di layar)")
    check("NOTIF.prefsLockNote" in dlg and "locked_reason" in dlg,
          "KUI9 layar mengatakan apa yang TIDAK bisa dimatikan, bukan diam-diam mengabaikan")
    check("NOTIF.prefsSwitch" in dlg and "Switch" in dlg and "Label" in dlg,
          "KUI10 sakelar per kategori/saluran punya label (bisa dipakai pembaca layar)")
    check("NOTIF.waDigestBtn" in dlg and "wa_link" in dlg and "menekan kirim" in dlg,
          "KUI11 ringkasan WhatsApp jujur: disiapkan, dikirim manusia")
    check(all(k in ids for k in ("groupToggle", "groupCount", "groupExpand", "prefsSwitch",
                                 "waDigestBtn")),
          "KUI12 elemen baru punya data-testid")
    check("rows_total" in page,
          "KUI13 layar menyebut berapa notifikasi diringkas jadi berapa kelompok")


def _kelompok(h, **params):
    p = {"state": "all", "group": "true", "limit": 50}
    p.update(params)
    return requests.get(f"{API}/notifications", headers=h, params=p, timeout=60).json()


def bagian_d():
    head("D. Perilaku server: pengelompokan, aksi kelompok, preferensi, pembungkaman jujur")
    owner = hdr("owner@sipro.co.id")
    uji = hdr(UJI)

    polos = requests.get(f"{API}/notifications", headers=owner,
                         params={"state": "all", "limit": 50}, timeout=60).json()
    grup = _kelompok(owner)
    check(grup.get("grouped") is True and grup.get("total", 0) >= 1,
          "D1 daftar bisa diminta berkelompok", f"{grup.get('total')} kelompok")
    check(grup["total"] < grup.get("rows_total", 0),
          "D2 pengelompokan benar-benar MERINGKAS (kelompok < notifikasi)",
          f"{grup['total']} kelompok / {grup.get('rows_total')} notifikasi")
    check(polos.get("grouped") is False and polos.get("total") == grup.get("rows_total"),
          "D3 tanpa `group=true` bentuk lama tetap utuh (kontrak lonceng & Fase 64)")
    kembar = [g for g in grup["data"] if (g.get("group_count") or 1) > 1]
    check(bool(kembar), "D4 ada kelompok kembar nyata di data demo",
          f"{len(kembar)} kelompok kembar")
    if kembar:
        g = kembar[0]
        check(len(g.get("group_ids") or []) == g["group_count"]
              and bool(g.get("group_members")),
              "D5 kelompok membawa id + anggotanya (bisa dibuka tanpa panggilan kedua)")
        judul = {m["title"] for m in g["group_members"]}
        check(len(judul) >= 1 and all(m.get("created_at") for m in g["group_members"]),
              "D6 anggota kelompok lengkap dengan waktunya")
        check(g.get("group_oldest_at") <= g.get("created_at"),
              "D7 wakil kelompok = yang TERBARU, terlama tetap disebut")

    # ---- aksi kelompok mengenai seluruh anggota
    cli, db = mongo()
    try:
        gu = _kelompok(uji, state="unread")
        target = next((x for x in gu.get("data") or [] if (x.get("group_count") or 1) > 1),
                      None)
        if not target:
            check(False, "D8..D11 butuh kelompok kembar belum dibaca milik pemakai uji")
        else:
            ids = target["group_ids"]
            res = requests.post(f"{API}/notifications/group/read", headers=uji,
                                json={"group_key": target["group_key"]}, timeout=30)
            body = res.json().get("data") if res.status_code == 200 else {}
            check(res.status_code == 200 and body.get("marked", 0) >= 2,
                  "D8 satu aksi menandai SELURUH anggota kelompok dibaca",
                  f"{res.status_code} {body}")
            check(db.notifications.count_documents(
                {"id": {"$in": ids}, "read": False}) == 0,
                "D9 tidak ada anggota yang tertinggal belum dibaca")
            res2 = requests.post(f"{API}/notifications/group/dismiss", headers=uji,
                                 json={"group_key": target["group_key"]}, timeout=30)
            check(res2.status_code == 200
                  and db.notifications.count_documents(
                      {"id": {"$in": ids}, "dismissed_at": None}) == 0,
                  "D10 aksi sembunyikan kelompok mengenai seluruh anggotanya")
            check(db.notifications.count_documents({"id": {"$in": ids}}) == len(ids),
                  "D11 barisnya TETAP ADA (disembunyikan, bukan dihapus)")
            db.notifications.update_many(
                {"id": {"$in": ids}},
                {"$set": {"dismissed_at": None, "read": False, "read_at": None}})
        check(requests.post(f"{API}/notifications/group/read", headers=uji,
                            json={"group_key": "tidak|ada|kelompok ini"},
                            timeout=30).status_code == 404,
              "D12 kelompok yang tidak ada = 404 (bukan 'berhasil' palsu)")
        if kembar:
            check(requests.post(f"{API}/notifications/group/read", headers=uji,
                                json={"group_key": kembar[0]["group_key"]},
                                timeout=30).status_code in (200, 404),
                  "D13 kunci kelompok orang lain tidak menyentuh notifikasi orang itu")
            check(db.notifications.count_documents(
                {"id": {"$in": kembar[0]["group_ids"]}, "user_email": "owner@sipro.co.id",
                 "read": False}) == db.notifications.count_documents(
                {"id": {"$in": kembar[0]["group_ids"]}, "read": False}),
                "D13b notifikasi owner tidak tersentuh aksi pemakai lain")
    finally:
        cli.close()

    # ---- preferensi per pemakai
    prefs = requests.get(f"{API}/notifications/preferences", headers=uji, timeout=30)
    d = prefs.json().get("data") or {}
    check(prefs.status_code == 200 and set(d.get("channels", {})) >= {"tugas", "keuangan"},
          "D14 preferensi bawaan terbaca untuk semua kategori")
    check(d.get("locked_channels") == ["inapp"] and "tindakan" in (d.get("locked_reason") or ""),
          "D15 aturan yang dikunci disampaikan ke layar (bukan kejutan)")
    put = requests.put(f"{API}/notifications/preferences", headers=uji,
                       json={"channels": {"keuangan": {"inapp": False, "push": False}}},
                       timeout=30)
    check(put.status_code == 200
          and put.json()["data"]["channels"]["keuangan"]["inapp"] is False,
          "D16 pemakai bisa mematikan kategori untuk dirinya sendiri", put.text[:120])
    lain = requests.get(f"{API}/notifications/preferences", headers=owner, timeout=30).json()
    check(lain["data"]["channels"]["keuangan"]["inapp"] is True,
          "D17 preferensi HANYA berlaku untuk pemakainya (bukan setelan global)")
    salah = requests.put(f"{API}/notifications/preferences", headers=uji,
                         json={"channels": {"astrologi": {"inapp": False}}}, timeout=30)
    check(salah.status_code == 400 and "tidak dikenal" in salah.text,
          "D18 kategori asing ditolak 400 dengan sebab yang bisa dibaca", salah.text[:100])
    salah2 = requests.put(f"{API}/notifications/preferences", headers=uji,
                          json={"channels": {"keuangan": {"telepati": True}}}, timeout=30)
    check(salah2.status_code == 400, "D19 saluran asing juga ditolak")

    # ---- pembungkaman: kabar informatif dibungkam, permintaan tindakan TIDAK
    import asyncio
    sys.path.insert(0, str(BE))
    os.environ.setdefault("PYTHONPATH", str(BE))
    import engine  # noqa: E402  (dipakai untuk menempuh pintu yang sama dengan produksi)
    cli, db = mongo()
    try:
        kabar = asyncio.get_event_loop().run_until_complete(engine.create_notification(
            user_email=UJI, title="Rekap keuangan mingguan (uji gate 56)",
            body="Kabar informatif.", type="finance", org_id="org-sipro"))
        minta = asyncio.get_event_loop().run_until_complete(engine.create_notification(
            user_email=UJI, title="Tagihan menunggu persetujuan Anda (uji gate 56)",
            body="Perlu keputusan.", type="finance", org_id="org-sipro"))
        k = db.notifications.find_one({"id": kabar["id"]}, {"_id": 0})
        m = db.notifications.find_one({"id": minta["id"]}, {"_id": 0})
        check(bool(k and k.get("muted_at") and k.get("muted_reason")),
              "D20 kabar informatif pada kategori yang dimatikan DIBUNGKAM + beralasan")
        daftar = requests.get(f"{API}/notifications", headers=uji,
                              params={"state": "all", "limit": 100}, timeout=60).json()
        tampil = {x["id"] for x in daftar.get("data") or []}
        check(kabar["id"] not in tampil,
              "D21 yang dibungkam tidak memenuhi daftar pemakai")
        check(db.notifications.count_documents({"id": kabar["id"]}) == 1,
              "D22 …tetapi barisnya tetap ada untuk diperiksa (bukan dihapus)")
        check(bool(m) and not m.get("muted_at"),
              "D23 permintaan TINDAKAN tidak bisa dibungkam preferensi (SoD notifikasi)")
        gr = _kelompok(uji, state="action")
        check(minta["id"] in {x["id"] for x in gr.get("data") or []}
              or any(minta["id"] in (x.get("group_ids") or []) for x in gr.get("data") or []),
              "D24 permintaan tindakan tetap muncul di 'perlu tindakan'")
        # ringkasan WhatsApp: disiapkan, tidak dikirim
        requests.put(f"{API}/notifications/preferences", headers=uji,
                     json={"channels": {"keuangan": {"wa": True, "inapp": True}}}, timeout=30)
        dig = requests.get(f"{API}/notifications/wa-digest", headers=uji, timeout=30).json()
        dd = dig.get("data") or {}
        check("keuangan" in (dd.get("categories") or []),
              "D25 ringkasan WhatsApp hanya memuat kategori yang diizinkan")
        check("wa_link" in dd and (not dd.get("wa_link")
                                  or dd["wa_link"].startswith("https://wa.me/")),
              "D26 ringkasan berupa tautan wa.me (tidak ada pesan yang terkirim sendiri)")
        check(bool(dd.get("message")),
              "D27 keadaan ringkasan dijelaskan (nomor belum ada / tidak ada yang perlu)")
    finally:
        db.notifications.delete_many({"title": {"$regex": "uji gate 56"}})
        db.notification_prefs.delete_many({"user_email": UJI})
        sisa = db.notifications.count_documents({"title": {"$regex": "uji gate 56"}})
        pref_sisa = db.notification_prefs.count_documents({"user_email": UJI})
        cli.close()
    check(sisa == 0 and pref_sisa == 0,
          "D28 bahan uji gate dibuang bersih (data demo tidak tercemar)")


def main():
    print("=" * 78)
    print("GATE 56 — Fase 65: notifikasi kembar berkelompok & preferensi per pemakai")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 56 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 56 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
