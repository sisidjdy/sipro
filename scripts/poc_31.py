#!/usr/bin/env python3
"""POC/verifikasi Fase 31 — JADWAL PEMBANGUNAN BERBUKTI per UNIT.

Menguji lewat API NYATA (bukan unit test terisolasi) bahwa monitoring konstruksi
benar-benar berfungsi dan TIDAK BISA DICURANGI:

  A. Template per TIPE unit + kalender nyata
     * template default rumah tapak 60 hari kerja / 9 minggu, bobot total 100%
     * waktu tunggu kritis sesuai standar (pondasi→sloof, sloof→bata, bata→plester,
       plester→acian, acian→cat) dan hold point terpasang
     * tanggal rencana melewati hari libur mingguan (Minggu tidak dihitung)
     * tipe "Kavling" (tanah) ditolak dengan penjelasan, bukan error teknis
  B. Gerbang mutu (guard)
     * hanya item pertama yang boleh dikerjakan; sisanya terkunci dengan ALASAN jelas
     * pekerjaan berikutnya tetap terkunci sampai pendahulunya DIVERIFIKASI
     * waktu tunggu curing benar-benar menahan (tanggal, bukan sekadar teks)
  C. Bukti wajib (proof)
     * kurang dari jumlah foto minimal → ditolak
     * checklist belum lengkap → ditolak; item mutu KRITIS gagal → ditolak
     * foto daur ulang (hash identik) → ditolak
  D. Anti-kecurangan & pemisahan tugas
     * staf lapangan tidak boleh memverifikasi (403 RBAC)
     * pengaju tidak boleh memverifikasi pekerjaannya sendiri (403 SoD)
     * menerobos gerbang wajib alasan, dicatat, dan diberitahukan ke direksi
  E. Progres NYATA + reminder + eskalasi
     * progres unit = Σ bobot item terverifikasi (bukan angka yang diketik)
     * unit lain TIDAK ikut berubah (cacat lama: progres proyek ditimpa ke semua unit)
     * item lewat tenggat → eskalasi berjenjang + tugas TK-13 + notifikasi
  F. Ikatan unit ↔ deal ↔ lead ↔ pembeli tersimpan pada unit

Jalankan: python3 scripts/poc_31.py
"""
import io
import os
import sys
from datetime import date, datetime, timedelta

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}" + (f" — {str(detail)[:150]}" if detail else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=60)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=90)


def photo(h, label, owner_id, tone=(60, 110, 90)):
    """Unggah foto lewat jalur NYATA (kompresi + watermark + hash) lalu kembalikan file_id.

    Setiap foto dibuat UNIK (ada nonce) karena mesin memang menolak berkas yang
    byte-nya identik dengan bukti pekerjaan lain — foto asli lapangan tidak pernah sama.
    """
    import uuid

    from PIL import Image, ImageDraw
    nonce = uuid.uuid4().hex
    img = Image.new("RGB", (900, 600), tone)
    d = ImageDraw.Draw(img)
    for y in range(0, 600, 3):
        d.line([(0, y), (900, y)], fill=(tone[0], min(255, tone[1] + y // 8), tone[2]))
    d.text((30, 520), label[:70], fill=(255, 255, 255))
    d.text((30, 560), nonce, fill=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    r = requests.post(f"{BASE}/files/upload", headers=h,
                      files={"file": (f"{label[:20].replace(' ', '_')}-{nonce[:6]}.jpg",
                                      buf.getvalue(), "image/jpeg")},
                      data={"owner_type": "build_item", "owner_id": owner_id}, timeout=90)
    r.raise_for_status()
    return r.json()["data"]["id"]


def answers(item, *, fail_critical=False, skip_one=False):
    out = []
    rows = item.get("checklist") or []
    for i, c in enumerate(rows):
        if skip_one and i == len(rows) - 1:
            continue
        res = "fail" if (fail_critical and c.get("critical")) else "pass"
        out.append({"code": c["code"], "result": res,
                    "note": "kondisi lapangan sesuai" if res == "pass" else "belum sesuai"})
    return out



def free_unit(pm, project_id):
    """Ambil unit yang belum terjadwal; bila habis, bebaskan satu jadwal yang BELUM ada
    pekerjaan terverifikasi (aman: endpoint menolak menghapus jadwal berbukti).

    POC dijalankan berulang kali; tanpa ini skrip gagal hanya karena data uji habis,
    bukan karena fiturnya rusak.
    """
    rows = g(pm, "/build/unscheduled", project_id=project_id).json().get("data") or []
    target = next((u for u in rows if u.get("buildable")), None)
    if target:
        return target, next((u for u in rows if not u.get("buildable")), None)
    scheds = g(pm, "/build/schedules", project_id=project_id,
               limit=100).json().get("data") or []
    for s in sorted(scheds, key=lambda x: x.get("items_done") or 0):
        if (s.get("items_done") or 0) == 0:
            requests.delete(f"{BASE}/build/schedules/{s['id']}", headers=pm, timeout=60)
            break
    rows = g(pm, "/build/unscheduled", project_id=project_id).json().get("data") or []
    return (next((u for u in rows if u.get("buildable")), None),
            next((u for u in rows if not u.get("buildable")), None))

def main():
    pm = login("pm@sipro.co.id")
    site = login("site@sipro.co.id")
    owner = login("owner@sipro.co.id")
    fin = login("finance@sipro.co.id")

    print("\n=== 31A. Template per tipe unit + kalender nyata ===")
    r = g(pm, "/build/templates")
    tpls = {t["code"]: t for t in (r.json().get("data") or [])}
    check("Template default tersedia (rumah tapak + ruko)",
          "RUMAH-9W" in tpls and "RUKO-14W" in tpls, list(tpls))
    rumah = tpls.get("RUMAH-9W") or {}
    check("Rumah tapak: 20 item, 9 minggu, 60 hari", rumah.get("steps_count") == 20
          and rumah.get("total_days") == 60, f"{rumah.get('steps_count')} item / "
          f"{rumah.get('total_days')} hari")
    check("Bobot template total 100%", abs((rumah.get("total_weight") or 0) - 100) < 0.5,
          rumah.get("total_weight"))
    full = g(pm, f"/build/templates/{rumah.get('id')}").json().get("data") or {}
    steps = {s["code"]: s for s in full.get("steps") or []}
    waits = {c: (s.get("wait_days"), s.get("predecessors")) for c, s in steps.items()
             if s.get("wait_days")}
    check("Waktu tunggu kritis terpasang (pondasi→sloof, sloof→bata, plester→acian, acian→cat)",
          steps["W2-01"]["wait_days"] >= 1 and steps["W3-01"]["wait_days"] >= 3
          and steps["W5-02"]["wait_days"] >= 2 and steps["W8-02"]["wait_days"] >= 7, waits)
    holds = [c for c, s in steps.items() if s.get("hold_point")]
    check("Hold point ada di titik rawan cacat (pondasi, bekisting, plester, atap, cat, final)",
          len(holds) >= 6, holds)
    check("Checklist mutu kritis ada pada tiap tahap kunci",
          all(any(x.get("critical") for x in steps[c].get("checklist") or [])
              for c in ("W1-02", "W4-02", "W7-01", "W9-02")))
    check("Semua item punya kategori pekerjaan SSOT",
          all(s.get("work_category") for s in steps.values()))

    # unit yang belum punya jadwal
    proj = g(pm, "/projects").json()["data"][0]
    target, kavling = free_unit(pm, proj["id"])
    if not check("Ada unit yang belum dijadwalkan untuk diuji", bool(target)):
        return
    start = (date.today() - timedelta(days=20)).isoformat()
    r = po(site, "/build/schedules", {"unit_id": target["id"], "start_date": start})
    check("Staf lapangan TIDAK boleh menetapkan jadwal (403)", r.status_code == 403,
          r.text[:120])
    r = po(pm, "/build/schedules", {"unit_id": target["id"], "start_date": start})
    if not check("Manajer Proyek membangkitkan jadwal unit", r.status_code == 200, r.text[:200]):
        return
    sched = r.json()["data"]
    check("Target selesai dihitung dari kalender (hari Minggu dilewati)",
          (datetime.strptime(sched["target_finish_date"], "%Y-%m-%d").date()
           - datetime.strptime(sched["start_date"], "%Y-%m-%d").date()).days >= 66,
          f"{sched['start_date']} → {sched['target_finish_date']}")
    r = po(pm, "/build/schedules", {"unit_id": target["id"], "start_date": start})
    check("Jadwal ganda untuk satu unit ditolak", r.status_code == 400, r.text[:120])
    if kavling:
        r = po(pm, "/build/schedules", {"unit_id": kavling["id"], "start_date": start})
        check("Kavling tanah ditolak dengan penjelasan (bukan error teknis)",
              r.status_code == 400 and "tanah" in r.text.lower(), r.text[:140])

    bundle = g(site, f"/build/unit/{target['id']}").json()
    items = {i["step_code"]: i for i in bundle["items"]}
    check("Jadwal berisi 20 item terkelompok 9 minggu", len(bundle["items"]) == 20
          and len(bundle["weeks"]) == 9)
    no_sunday = all(datetime.strptime(i["planned_start"], "%Y-%m-%d").date().weekday() != 6
                    for i in bundle["items"])
    check("Tidak ada item yang dijadwalkan pada hari libur mingguan", no_sunday)

    print("\n=== 31B. Gerbang mutu: tidak boleh loncat ===")
    check("Hanya item pertama yang siap dikerjakan",
          items["W1-01"]["status"] == "ready"
          and all(items[c]["status"] == "blocked" for c in ("W1-02", "W2-01", "W3-01")),
          items["W1-02"]["status"])
    check("Alasan terkunci disebutkan jelas (pekerjaan sebelumnya belum diverifikasi)",
          any(x["code"] == "predecessor" for x in items["W1-02"]["gate"]["reasons"]),
          items["W1-02"]["gate"]["reasons"][:1])
    first, second = items["W1-01"], items["W1-02"]
    r = po(site, f"/build/items/{second['id']}/submit",
           {"note": "coba loncat langsung ke pondasi", "photo_file_ids": []})
    check("Mengerjakan item terkunci DITOLAK", r.status_code == 400
          and "TERKUNCI" in r.text.upper(), r.text[:140])

    print("\n=== 31C. Bukti wajib (foto + checklist) ===")
    po(site, f"/build/items/{first['id']}/start")
    r = po(site, f"/build/items/{first['id']}/submit",
           {"note": "pembersihan lokasi & bowplank selesai", "photo_file_ids": []})
    check(f"Tanpa foto ditolak (minimal {first['min_photos']} foto)", r.status_code == 400
          and "foto" in r.text.lower(), r.text[:140])
    p1 = photo(site, "Persiapan bowplank 1", first["id"])
    p2 = photo(site, "Persiapan pengukuran 2", first["id"], tone=(70, 100, 120))
    r = po(site, f"/build/items/{first['id']}/submit",
           {"note": "pembersihan lokasi & bowplank selesai", "photo_file_ids": [p1, p2],
            "checklist": answers(first, skip_one=True)})
    check("Checklist belum lengkap ditolak", r.status_code == 400
          and "checklist" in r.text.lower(), r.text[:140])
    r = po(site, f"/build/items/{first['id']}/submit",
           {"note": "pembersihan lokasi & bowplank selesai", "photo_file_ids": [p1, p2],
            "checklist": answers(first, fail_critical=True)})
    check("Item mutu KRITIS gagal ditolak (tidak boleh dilewati)", r.status_code == 400
          and "kritis" in r.text.lower(), r.text[:140])
    r = po(site, f"/build/items/{first['id']}/submit",
           {"note": "pembersihan lokasi, pengukuran, dan bowplank selesai sesuai siteplan",
            "photo_file_ids": [p1, p2], "checklist": answers(first)})
    if not check("Pengajuan lengkap diterima", r.status_code == 200, r.text[:200]):
        return
    check("Status jadi 'menunggu verifikasi'", r.json()["data"]["status"] == "submitted")
    tasks = g(pm, "/work/tasks", scope="division", limit=200).json().get("data") or []
    check("Tugas verifikasi lahir untuk supervisor (TK-11)",
          any(t.get("jobdesk_code") == "TK-11" and (t.get("meta") or {}).get("build_item_id")
              == first["id"] for t in tasks))

    print("\n=== 31D. Pemisahan tugas & anti-kecurangan ===")
    r = po(site, f"/build/items/{first['id']}/verify", {"note": "oke"})
    check("Staf lapangan tidak punya izin verifikasi (403)", r.status_code == 403, r.text[:120])
    r = po(fin, f"/build/items/{first['id']}/verify", {"note": "oke"})
    check("Peran keuangan juga tidak boleh verifikasi (403)", r.status_code == 403)
    r = po(pm, f"/build/items/{second['id']}/override",
           {"reason_code": "schedule_recovery", "note": "pendek"})
    check("Override tanpa penjelasan cukup ditolak", r.status_code == 400, r.text[:120])
    r = po(pm, f"/build/items/{first['id']}/verify",
           {"note": "As bangunan & elevasi diperiksa langsung, sesuai siteplan."})
    if not check("Supervisor memverifikasi pekerjaan", r.status_code == 200, r.text[:200]):
        return
    prog_after_first = r.json()["schedule"]["progress"]
    check("Progres unit bertambah sesuai BOBOT item (bukan angka manual)",
          abs(prog_after_first - first["weight"]) < 0.6,
          f"{prog_after_first}% vs bobot {first['weight']}%")

    b2 = g(pm, f"/build/unit/{target['id']}").json()
    it2 = {i["step_code"]: i for i in b2["items"]}
    check("Item berikutnya TERBUKA setelah pendahulunya diverifikasi",
          it2["W1-02"]["status"] == "ready", it2["W1-02"]["status"])
    check("Item dua langkah ke depan tetap terkunci",
          it2["W2-01"]["status"] == "blocked")

    # foto daur ulang
    r = po(site, f"/build/items/{it2['W1-02']['id']}/submit",
           {"note": "galian pondasi, urugan pasir, dan pasangan batu belah selesai",
            "photo_file_ids": [p1, p2, p1], "checklist": answers(it2["W1-02"])})
    check("Foto DAUR ULANG ditolak (hash identik dengan bukti pekerjaan lain)",
          r.status_code == 400 and "IDENTIK" in r.text.upper(), r.text[:160])

    pf = [photo(site, f"Pondasi batu belah {n}", it2["W1-02"]["id"], tone=(80, 90 + n * 9, 70))
          for n in range(1, 4)]
    r = po(site, f"/build/items/{it2['W1-02']['id']}/submit",
           {"note": "galian sesuai kedalaman, urugan pasir dipadatkan, batu belah terkunci",
            "photo_file_ids": pf, "checklist": answers(it2["W1-02"])})
    check("Pondasi diajukan dengan 3 foto bukti", r.status_code == 200, r.text[:160])
    r = po(pm, f"/build/items/{it2['W1-02']['id']}/reject",
           {"reason": "Ada rongga di sudut belakang, spesi belum penuh — rapikan dulu."})
    check("Supervisor menolak dengan alasan → item jadi 'perbaiki'",
          r.status_code == 200 and r.json()["data"]["status"] == "rework", r.text[:140])
    tasks = g(pm, "/work/tasks", scope="division", limit=200).json().get("data") or []
    check("Tugas perbaikan (TK-12) dibuat untuk pelaksana",
          any(t.get("jobdesk_code") == "TK-12" for t in tasks))
    pf2 = photo(site, "Perbaikan sudut belakang", it2["W1-02"]["id"], tone=(96, 84, 66))
    r = po(site, f"/build/items/{it2['W1-02']['id']}/submit",
           {"note": "rongga sudut belakang sudah diisi spesi penuh, difoto ulang",
            "photo_file_ids": [], "checklist": answers(it2["W1-02"])})
    check("Pengajuan ulang TANPA foto perbaikan baru ditolak", r.status_code == 400
          and "PERBAIKAN" in r.text.upper(), r.text[:140])
    r = po(site, f"/build/items/{it2['W1-02']['id']}/submit",
           {"note": "rongga sudut belakang sudah diisi spesi penuh, difoto ulang",
            "photo_file_ids": [pf2], "checklist": answers(it2["W1-02"])})
    check("Pengajuan ulang setelah perbaikan diterima (foto lama tetap dihitung)",
          r.status_code == 200, r.text[:160])
    r = po(pm, f"/build/items/{it2['W1-02']['id']}/verify", {"note": "Sudah terkunci penuh."})
    check("Perbaikan diverifikasi", r.status_code == 200, r.text[:140])

    print("\n=== 31E. Waktu tunggu curing benar-benar menahan ===")
    b3 = g(pm, f"/build/unit/{target['id']}").json()
    it3 = {i["step_code"]: i for i in b3["items"]}
    sloof = it3["W2-01"]
    wait_reason = [x for x in sloof["gate"]["reasons"] if x["code"] == "wait_time"]
    check("Sloof tertahan waktu tunggu pondasi (1–2 hari) dengan tanggal jelas",
          sloof["status"] == "blocked" and bool(wait_reason),
          (wait_reason or [{}])[0].get("detail"))
    r = po(site, f"/build/items/{sloof['id']}/submit",
           {"note": "mau kerjakan sloof sekarang", "photo_file_ids": []})
    check("Mengerjakan sebelum waktu tunggu selesai DITOLAK", r.status_code == 400,
          r.text[:140])
    r = po(pm, f"/build/items/{sloof['id']}/override",
           {"reason_code": "verified_offline",
            "note": "Pondasi sudah dicek langsung bersama pengawas, kondisi terkunci penuh."})
    check("Override beralasan membuka gerbang", r.status_code == 200
          and r.json()["data"]["status"] == "ready", r.text[:160])
    check("Override tercatat pada item (audit)", bool(r.json()["data"].get("override")))
    notifs = g(owner, "/notifications", limit=30).json().get("data") or []
    check("Direksi diberi tahu ada gerbang yang diterobos",
          any("diterobos" in (n.get("title", "") + n.get("body", "")).lower() for n in notifs))
    board = g(pm, "/build/schedules", project_id=proj["id"]).json()
    mine = next((x for x in board["data"] if x["unit_id"] == target["id"]), {})
    check("Jumlah override tampil di papan pantau (transparan)",
          int(mine.get("overrides") or 0) >= 1, mine.get("overrides"))

    print("\n=== 31F. Progres nyata (cacat lama: progres unit ditimpa proyek) ===")
    units = g(pm, "/units", project_id=proj["id"], limit=200).json().get("data") or []
    umap = {u["code"]: u for u in units}
    tgt_unit = umap.get(target["code"], {})
    others = [u for u in units if u["id"] != target["id"]]
    distinct = {u.get("construction_progress") for u in units}
    check("Progres tiap unit berbeda sesuai jadwalnya sendiri", len(distinct) >= 3,
          sorted(distinct))
    check("Unit uji memakai progres jadwalnya sendiri",
          int(tgt_unit.get("construction_progress") or 0)
          == int(round(mine.get("progress") or 0)),
          f"{tgt_unit.get('construction_progress')}% vs {mine.get('progress')}%")
    unsched = [u for u in others if not u.get("construction_progress")]
    check("Unit tanpa jadwal tidak lagi menampilkan progres palsu", bool(unsched),
          f"{len(unsched)} unit 0%")

    print("\n=== 31G. Pengingat & eskalasi keterlambatan ===")
    r = po(pm, "/build/tick")
    tick = r.json().get("data") or {}
    check("Pemantauan berjalan (buka gerbang + pengingat + eskalasi)", r.status_code == 200
          and tick.get("schedules", 0) >= 1, tick)
    check("Ada eskalasi untuk item yang lewat tenggat", tick.get("escalations", 0) >= 1
          or tick.get("reminders", 0) >= 1, tick)
    tasks = g(pm, "/work/tasks", scope="division", limit=200).json().get("data") or []
    late_tasks = [t for t in tasks if t.get("jobdesk_code") == "TK-13"]
    check("Tugas 'kejar keterlambatan' (TK-13) dibuat", bool(late_tasks),
          [t["title"][:48] for t in late_tasks[:2]])
    on = g(owner, "/notifications", limit=50).json().get("data") or []
    check("Direksi menerima eskalasi keterlambatan (level ≥2)",
          any("telat" in (n.get("title", "") + n.get("body", "")).lower() for n in on))
    late_item = None
    for row in board["data"]:
        if row.get("late_detail"):
            late_item = row["late_detail"][0]
            break
    check("Papan pantau memuat rincian item telat + jumlah hari", bool(late_item), late_item)

    print("\n=== 31H. Penyebab telat (SSOT) & hentikan/lanjutkan jadwal ===")
    items_late = g(pm, "/build/items", project_id=proj["id"], status="ready",
                   limit=50).json().get("data") or []
    pick = items_late[0] if items_late else None
    if pick:
        r = po(site, f"/build/items/{pick['id']}/delay-cause",
               {"cause": "hujan_terus", "note": "x"})
        check("Penyebab telat di luar daftar SSOT ditolak", r.status_code == 400, r.text[:120])
        r = po(site, f"/build/items/{pick['id']}/delay-cause",
               {"cause": "material_late", "note": "Besi belum dikirim supplier sejak Senin."})
        check("Penyebab telat tersimpan dengan kode SSOT", r.status_code == 200, r.text[:120])
    rep = g(pm, "/build/delays", project_id=proj["id"]).json().get("data") or {}
    check("Laporan penyebab keterlambatan tersedia", "by_cause" in rep, rep.get("late_total"))
    r = po(pm, f"/build/schedules/{sched['id']}/hold",
           {"cause": "weather", "note": "Hujan deras 3 hari, lokasi tergenang."})
    check("Jadwal bisa dihentikan sementara dengan alasan SSOT", r.status_code == 200
          and r.json()["data"]["status"] == "on_hold", r.text[:140])
    b4 = g(pm, f"/build/unit/{target['id']}").json()
    it4 = {i["step_code"]: i for i in b4["items"]}
    check("Saat dihentikan, item ikut terkunci dengan alasan jadwal",
          any(x["code"] == "schedule_hold" for x in it4["W2-02"]["gate"]["reasons"]),
          it4["W2-02"]["gate"]["reasons"][:1])
    r = po(pm, f"/build/schedules/{sched['id']}/resume")
    check("Jadwal bisa dilanjutkan kembali", r.status_code == 200
          and r.json()["data"]["status"] != "on_hold", r.text[:140])

    print("\n=== 31I. Ikatan unit ↔ deal ↔ lead ↔ pembeli + integritas ===")
    board2 = g(pm, "/build/schedules", project_id=proj["id"]).json()
    bound = [x for x in board2["data"] if x.get("lead_id")]
    check("Jadwal unit terjual memuat lead & nama pembeli", bool(bound),
          [(b["unit_code"], b.get("lead_name")) for b in bound][:2])
    sold_unit = next((u for u in units if u.get("booked_by_deal")), None)
    check("Dokumen unit menyimpan ikatan lead/deal secara eksplisit",
          bool(sold_unit and sold_unit.get("lead_id") and sold_unit.get("deal_id")),
          {k: sold_unit.get(k) for k in ("code", "lead_id", "deal_id", "customer_id")}
          if sold_unit else None)
    r = requests.delete(f"{BASE}/build/schedules/{sched['id']}", headers=pm, timeout=60)
    check("Jadwal dengan pekerjaan terverifikasi tidak bisa dihapus (jejak audit utuh)",
          r.status_code == 400, r.text[:140])
    tl = g(pm, f"/build/unit/{target['id']}").json().get("timeline") or {}
    check("Kurva rencana vs realisasi per minggu dihitung dari data",
          len(tl.get("points") or []) >= 9 and tl["points"][-1]["planned"] >= 99,
          tl.get("points", [])[-1] if tl.get("points") else None)
    summ = g(pm, "/build/summary", project_id=proj["id"]).json().get("data") or {}
    check("Ringkasan monitoring lengkap (terjadwal/telat/tertahan/override)",
          all(k in summ for k in ("scheduled", "unscheduled", "late_items",
                                  "blocked_items", "overrides", "awaiting_verification")),
          summ)

    print(f"\n=== HASIL FASE 31: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
    if FAIL:
        for f in FAIL:
            print("  ✗", f)
        sys.exit(1)
    print("SEMUA VERIFIKASI FASE 31 LULUS")


if __name__ == "__main__":
    main()
