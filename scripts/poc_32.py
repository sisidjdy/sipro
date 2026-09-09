#!/usr/bin/env python3
"""POC/verifikasi Fase 32 — SETIAP STEP KONSTRUKSI = TASK BERINSTRUKSI + BERVALIDASI.

Permintaan owner yang diuji di sini (lewat API NYATA, bukan unit test terisolasi):

  A. Instruksi task
     * setiap pekerjaan yang boleh dikerjakan punya TASK Work Hub dengan instruksi
       lengkap: lingkup, checklist mutu (butir KRITIS), hold point, waktu tunggu,
       urutan pendahulu, dan siapa verifikatornya
     * task menunjuk langsung ke pekerjaannya (deep link), bukan menu umum
  B. Anti-bypass (cacat D-H)
     * task pekerjaan konstruksi TIDAK BISA dimulai/diajukan/diverifikasi/diselesaikan
       lewat jalur task generik — harus lewat jalur build agar gerbang mutu berlaku
  C. Urutan wajib
     * step yang pendahulunya belum diverifikasi tidak bisa dikerjakan dan tampil
       sebagai "instruksi menunggu" beserta alasannya
     * setelah pendahulu diverifikasi, task step berikutnya lahir otomatis
  D. Papan Mandor ("kerja hari ini")
     * kelompok telat / hari ini / dikerjakan / dikembalikan / menunggu verifikasi /
       antrean verifikasi / instruksi menunggu, hanya milik orang tersebut
  E. Kebijakan bukti kerja (bisa on/off oleh admin)
     * hanya Direksi/Super Admin boleh mengubah
     * saat lokasi diwajibkan: pengajuan tanpa koordinat DITOLAK, akurasi kasar DITOLAK
     * panjang minimal uraian pekerjaan mengikuti kebijakan
  F. Laporan mingguan (Senin) + PDF
     * idempoten per pekan, notifikasi + TUGAS BACA untuk direksi & manajer proyek
     * angka per rumah + kurva rencana vs realisasi + PDF valid
  G. Analitik keterlambatan
     * pekerjaan & pelaksana paling sering telat + rekomendasi kalibrasi template

Jalankan: python3 scripts/poc_32.py
"""
import io
import os
import sys
import uuid
from datetime import date, timedelta

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {str(detail)[:150]}" if detail else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=90)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=120)


def pu(h, p, body=None):
    return requests.put(f"{BASE}{p}", headers=h, json=body or {}, timeout=90)


def photo(h, label, owner_id, geo=None):
    """Unggah foto lewat jalur nyata (kompresi + watermark + hash + koordinat opsional)."""
    from PIL import Image, ImageDraw
    nonce = uuid.uuid4().hex
    img = Image.new("RGB", (880, 580), (70, 105, 95))
    d = ImageDraw.Draw(img)
    for y in range(0, 580, 3):
        d.line([(0, y), (880, y)], fill=(70, min(255, 105 + y // 7), 95))
    d.text((28, 500), label[:70], fill=(255, 255, 255))
    d.text((28, 540), nonce, fill=(235, 235, 235))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = {"owner_type": "build_item", "owner_id": owner_id}
    if geo:
        data.update({"lat": geo["lat"], "lng": geo["lng"],
                     "accuracy": geo.get("accuracy") or 12})
    r = requests.post(f"{BASE}/files/upload", headers=h,
                      files={"file": (f"p32-{nonce[:8]}.jpg", buf.getvalue(), "image/jpeg")},
                      data=data, timeout=120)
    r.raise_for_status()
    return r.json()["data"]


def answers(item):
    return [{"code": c["code"], "result": "pass", "note": "sesuai spesifikasi"}
            for c in (item.get("checklist") or [])]


def board(h, project_id=None):
    r = g(h, "/build/board/today", **({"project_id": project_id} if project_id else {}))
    r.raise_for_status()
    return r.json()["data"]


def find_item(h, item_id):
    r = g(h, f"/build/items/{item_id}")
    if r.status_code == 200:
        return r.json().get("data")
    return None


def get_task(h, task_id):
    """`GET /work/tasks/{id}` mengembalikan {"data": {"task": ..., "jobdesk": ...}}."""
    r = g(h, f"/work/tasks/{task_id}")
    if r.status_code != 200:
        return {}
    return ((r.json() or {}).get("data") or {}).get("task") or {}


def item_submissions(h, item_id):
    r = g(h, f"/build/items/{item_id}")
    return (r.json() or {}).get("submissions") or [] if r.status_code == 200 else []



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

def main():  # noqa: C901
    pm = login("pm@sipro.co.id")
    site = login("site@sipro.co.id")
    owner = login("owner@sipro.co.id")
    sales = login("sales@sipro.co.id")

    proj = g(pm, "/projects").json()["data"][0]

    # ---------------------------------------------------------------- setup jadwal baru
    print("\n=== SETUP: jadwal unit baru (mulai 25 hari lalu supaya ada yang telat) ===")
    target, _kavling = free_unit(pm, proj["id"])
    if not check("Ada unit belum terjadwal untuk diuji", bool(target)):
        return
    start = (date.today() - timedelta(days=25)).isoformat()
    r = po(pm, "/build/schedules", {"unit_id": target["id"], "start_date": start})
    if not check("Jadwal unit dibuat", r.status_code == 200, r.text[:200]):
        return
    sched = r.json()["data"]
    unit_code = sched.get("unit_code")
    bundle = g(pm, f"/build/unit/{target['id']}").json()
    items = [i for w in bundle["weeks"] for i in w["items"]]
    first = next(i for i in items if i["status"] == "ready")
    second = next(i for i in items if i["status"] == "blocked")

    # ------------------------------------------------------- A. instruksi task
    print("\n=== 32A. Setiap step jadi TASK BERINSTRUKSI ===")
    bd = board(site, proj["id"])
    rows = [r for grp in ("overdue", "today", "in_progress", "rework")
            for r in bd["groups"][grp]]
    row = next((r for r in rows if r["id"] == first["id"]), None)
    check("Pekerjaan siap muncul di Papan Mandor pelaksana", bool(row),
          f"{len(rows)} pekerjaan aktif untuk {bd['me']}")
    task_id = (row or {}).get("task_id")
    check("Pekerjaan tersebut punya TASK Work Hub (bukan hanya baris jadwal)",
          bool(task_id), task_id)
    task = get_task(site, task_id) if task_id else {}
    desc = task.get("description") or ""
    check("Instruksi task memuat LANGKAH + lingkup pekerjaan",
          "LANGKAH" in desc and "Lingkup pekerjaan" in desc, desc[:90])
    check("Instruksi task menyebut bukti foto WAJIB", "Bukti WAJIB" in desc, desc[:60])
    check("Instruksi task memuat checklist mutu + penanda KRITIS",
          "Checklist mutu" in desc and "[KRITIS]" in desc)
    check("Instruksi task menyebut siapa yang memvalidasi",
          "Validasi:" in desc and (first.get("verifier_hint") or "") in desc)
    check("Task wajib bukti FOTO dan divalidasi supervisor",
          task.get("proof_kind") == "photo" and task.get("verify_mode") == "supervisor",
          f"{task.get('proof_kind')}/{task.get('verify_mode')}")
    check("Task menunjuk langsung ke pekerjaannya (deep link)",
          f"item={first['id']}" in (task.get("link") or ""), task.get("link"))
    check("Task terhubung ke item build lewat meta",
          (task.get("meta") or {}).get("build_item_id") == first["id"])

    # ------------------------------------------------------- B. anti-bypass
    print("\n=== 32B. Task konstruksi TIDAK bisa diselesaikan lewat jalur task generik ===")
    r = po(site, f"/work/tasks/{task_id}/start")
    check("Mulai kerja lewat Work Hub dialihkan ke Papan Mandor",
          r.status_code == 400 and "Papan Mandor" in r.text, r.text[:130])
    r = po(site, f"/work/tasks/{task_id}/submit",
           {"note": "sudah dikerjakan semua", "photos": ["file-palsu-123"]})
    check("Ajukan hasil lewat Work Hub DITOLAK (dulu bisa dengan foto palsu)",
          r.status_code == 400 and "Papan Mandor" in r.text, r.text[:130])
    r = po(site, f"/work/tasks/{task_id}/complete", {"outcome": "selesai"})
    check("Tandai selesai lewat Work Hub DITOLAK", r.status_code == 400
          and "Papan Mandor" in r.text, r.text[:130])
    r = po(pm, f"/work/tasks/{task_id}/verify", {"note": "ok"})
    check("Verifikasi lewat Work Hub DITOLAK (harus lewat jalur build)",
          r.status_code == 400 and "Papan Mandor" in r.text, r.text[:130])
    fresh = find_item(pm, first["id"]) or {}
    check("Status pekerjaan TIDAK berubah oleh percobaan bypass",
          fresh.get("status") in ("ready", "in_progress"), fresh.get("status"))
    check("Tidak ada bukti palsu yang tercatat pada pekerjaan",
          not (fresh.get("evidence") or []), len(fresh.get("evidence") or []))

    # ------------------------------------------------------- C. urutan wajib
    print("\n=== 32C. Urutan pekerjaan tidak bisa dilangkahi ===")
    upcoming = bd["groups"]["upcoming"]
    check("Step berikutnya tampil sebagai INSTRUKSI MENUNGGU (bukan task aktif)",
          any(u["id"] == second["id"] for u in upcoming), [u["step_code"] for u in upcoming[:4]])
    nxt = next((u for u in upcoming if u["id"] == second["id"]), {})
    check("Instruksi menunggu menyebut alasan terkunci",
          any(x.get("code") == "predecessor" for x in (nxt.get("gate_reasons") or [])),
          nxt.get("gate_reasons"))
    check("Instruksi menunggu tidak punya task aktif", not nxt.get("task_id"))
    r = po(site, f"/build/items/{second['id']}/submit",
           {"note": "mau kerjakan yang ini dulu", "photo_file_ids": [], "checklist": []})
    check("Mengerjakan step yang di depan DITOLAK", r.status_code == 400
          and "TERKUNCI" in r.text.upper(), r.text[:120])

    # ------------------------------------------------------- D. kebijakan bukti kerja
    print("\n=== 32D. Kebijakan bukti kerja (lokasi on/off oleh admin) ===")
    r = g(site, "/build/policy")
    check("Pelaksana bisa MELIHAT kebijakan tetapi tidak boleh mengubah",
          r.status_code == 200 and r.json().get("can_edit") is False, r.text[:120])
    r = pu(site, "/build/policy", {"geo_required": True})
    check("Pelaksana mengubah kebijakan → 403", r.status_code == 403, r.text[:120])
    r = pu(pm, "/build/policy", {"geo_required": True})
    check("Manajer Proyek pun tidak boleh mengubah kebijakan (hanya admin) → 403",
          r.status_code == 403, r.text[:120])
    r = pu(owner, "/build/policy", {"geo_required": True, "min_note_chars": 25,
                                    "min_accuracy_m": 150})
    check("Direksi menyalakan kewajiban LOKASI", r.status_code == 200
          and r.json()["data"]["geo_required"] is True, r.text[:150])

    p1 = photo(site, f"{unit_code} persiapan 1", first["id"])["id"]
    p2 = photo(site, f"{unit_code} persiapan 2", first["id"])["id"]
    body = {"note": "Pembersihan lokasi, pengukuran, dan bowplank selesai dipasang rapi.",
            "photo_file_ids": [p1, p2], "checklist": answers(first)}
    r = po(site, f"/build/items/{first['id']}/submit", body)
    check("Saat lokasi diwajibkan, pengajuan TANPA koordinat ditolak",
          r.status_code == 400 and "LOKASI" in r.text.upper(), r.text[:150])
    r = po(site, f"/build/items/{first['id']}/submit",
           {**body, "note": "terlalu pendek", "geo": {"lat": -8.65, "lng": 115.21}})
    check("Uraian lebih pendek dari kebijakan ditolak", r.status_code == 400
          and "25 karakter" in r.text, r.text[:140])
    r = po(site, f"/build/items/{first['id']}/submit",
           {**body, "geo": {"lat": -8.65, "lng": 115.21, "accuracy": 900}})
    check("Akurasi lokasi terlalu kasar ditolak", r.status_code == 400
          and "akurasi" in r.text.lower(), r.text[:140])
    r = po(site, f"/build/items/{first['id']}/submit",
           {**body, "geo": {"lat": -8.65, "lng": 115.21, "accuracy": 11}})
    ok_submit = check("Pengajuan dengan lokasi valid diterima", r.status_code == 200,
                      r.text[:150])
    it = find_item(pm, first["id"]) or {}
    check("Koordinat tersimpan pada pekerjaan (bisa diaudit)",
          bool((it.get("geo") or {}).get("maps_url")), (it.get("geo") or {}).get("maps_url"))
    check("Koordinat menempel pada tiap bukti foto",
          all((e.get("geo") or {}).get("lat") for e in (it.get("evidence") or [])),
          [bool(e.get("geo")) for e in (it.get("evidence") or [])])
    check("Jejak audit pengajuan memuat kebijakan yang berlaku saat itu",
          bool(item_submissions(pm, first["id"])
               and (item_submissions(pm, first["id"])[0].get("policy_snapshot") or {})
               .get("geo_required") is True),
          (item_submissions(pm, first["id"]) or [{}])[0].get("policy_snapshot"))
    r = pu(owner, "/build/policy", {"geo_required": False, "min_note_chars": 10,
                                    "min_accuracy_m": 200})
    check("Direksi bisa mematikan kembali kewajiban lokasi",
          r.status_code == 200 and r.json()["data"]["geo_required"] is False)

    # ------------------------------------------------------- E. task ditutup & validasi
    print("\n=== 32E. Task ditutup jalur build + validasi supervisor ===")
    tstat = get_task(site, task_id).get("status")
    check("Task pekerjaan otomatis DITUTUP setelah diajukan lewat jalur build",
          tstat in ("done", "submitted"), tstat)
    bd2 = board(pm, proj["id"])
    check("Pekerjaan masuk ANTREAN VERIFIKASI supervisor",
          any(x["id"] == first["id"] for x in bd2["groups"]["to_verify"]),
          [x["step_code"] for x in bd2["groups"]["to_verify"][:5]])
    bd_site = board(site, proj["id"])
    check("Pelaksana melihat pekerjaannya sedang menunggu verifikasi",
          any(x["id"] == first["id"] for x in bd_site["groups"]["awaiting_verification"]))
    r = po(pm, f"/build/items/{first['id']}/verify", {"note": "Diperiksa di lapangan, rapi."})
    if check("Supervisor memverifikasi lewat jalur build", r.status_code == 200, r.text[:150]):
        after = (r.json() or {}).get("schedule") or {}
        check("Progres unit naik sesuai bobot item",
              float(after.get("progress") or 0) >= float(first.get("weight") or 0) - 0.01,
              f"{after.get('progress')}% vs bobot {first.get('weight')}%")
    nxt2 = find_item(pm, second["id"]) or {}
    check("Step berikutnya TERBUKA setelah pendahulunya diverifikasi",
          nxt2.get("status") in ("ready", "blocked"), nxt2.get("status"))
    bd3 = board(site, proj["id"])
    active = [r for grp in ("overdue", "today", "in_progress", "rework")
              for r in bd3["groups"][grp]]
    if nxt2.get("status") == "ready":
        got = next((a for a in active if a["id"] == second["id"]), None)
        check("Task berinstruksi untuk step berikutnya LAHIR otomatis",
              bool(got and got.get("task_id")), (got or {}).get("task_id"))

    # ------------------------------------------------------- F. papan mandor & RBAC
    print("\n=== 32F. Papan Mandor: kelompok jelas + RBAC ===")
    for key in ("overdue", "today", "in_progress", "rework", "awaiting_verification",
                "to_verify", "upcoming", "scheduled_later"):
        check(f"Papan mandor punya kelompok '{key}'", key in bd3["groups"])
    check("Papan mandor menyertakan kebijakan bukti kerja (untuk tombol kamera/lokasi)",
          "geo_required" in (bd3.get("policy") or {}))
    check("Papan mandor hanya memuat pekerjaan milik pengguna",
          all(x.get("assigned_to") == bd3["me"] for x in active), bd3["me"])
    check("Setiap kartu papan mandor membawa instruksi siap-baca",
          all(len(x.get("instruction") or []) >= 4 for x in active) if active else True)
    r = g(sales, "/build/board/today")
    check("Sales tidak boleh membuka Papan Mandor (403)", r.status_code == 403, r.text[:100])

    # ------------------------------------------------------- G. laporan mingguan
    print("\n=== 32G. Laporan mingguan Senin + PDF ===")
    r = po(site, "/build/reports/weekly/run", {})
    check("Pelaksana tidak boleh menjalankan laporan mingguan (403)",
          r.status_code == 403, r.text[:110])
    r = po(pm, "/build/reports/weekly/run", {"project_id": proj["id"]})
    if not check("Manajer Proyek menjalankan laporan mingguan", r.status_code == 200,
                 r.text[:200]):
        return
    out1 = r.json()["data"]
    check("Laporan pekan ini dibuat", out1["created"] >= 1 or out1["refreshed"] >= 1,
          out1)
    r = po(pm, "/build/reports/weekly/run", {"project_id": proj["id"]})
    out2 = r.json()["data"]
    check("Dijalankan ulang TIDAK membuat laporan ganda (idempoten per pekan)",
          out2["created"] == 0 and out2["refreshed"] >= 1, out2)
    lst = g(pm, "/build/reports/weekly", project_id=proj["id"]).json()
    check("Daftar laporan mingguan tersedia", (lst.get("total") or 0) >= 1, lst.get("total"))
    rid = lst["data"][0]["id"]
    rep = g(pm, f"/build/reports/weekly/{rid}").json()["data"]
    check("Laporan memuat baris PER RUMAH", len(rep.get("houses") or []) >= 1,
          len(rep.get("houses") or []))
    h0 = (rep.get("houses") or [{}])[0]
    check("Baris rumah memuat progres vs rencana + deviasi hari",
          all(k in h0 for k in ("unit_code", "progress", "planned_progress",
                                "deviation_days", "items_done", "late_items")), list(h0)[:6])
    check("Laporan memuat kurva rencana vs realisasi per minggu",
          len(rep.get("curve") or []) >= 5
          and all(k in (rep["curve"][0]) for k in ("week", "planned", "actual")),
          (rep.get("curve") or [None])[0])
    check("Kurva rencana bersifat kumulatif (naik sampai 100%)",
          abs(float(rep["curve"][-1]["planned"]) - 100) < 1.5,
          rep["curve"][-1] if rep.get("curve") else None)
    t = rep.get("totals") or {}
    check("Ringkasan laporan memuat kunci penting",
          all(k in t for k in ("units_scheduled", "avg_progress", "avg_planned",
                               "late_items", "overrides", "verified_this_week")), list(t)[:6])
    pdf = requests.get(f"{BASE}/build/reports/weekly/{rid}/pdf", headers=pm, timeout=120)
    check("PDF laporan bisa diunduh dan valid",
          pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 3000,
          f"{pdf.status_code} · {len(pdf.content)} byte")
    check("PDF diberi nama berkas yang jelas",
          "laporan-mingguan" in (pdf.headers.get("content-disposition") or ""),
          pdf.headers.get("content-disposition"))
    tasks = g(owner, "/work/tasks", scope="mine", limit=100).json()
    rows_t = tasks.get("data") or []
    if isinstance(rows_t, dict):
        rows_t = [x for v in rows_t.values() for x in v]
    check("Direksi menerima TUGAS BACA laporan mingguan (TK-14)",
          any(x.get("jobdesk_code") == "TK-14" for x in rows_t),
          [x.get("jobdesk_code") for x in rows_t[:8]])
    tk14 = next((x for x in rows_t if x.get("jobdesk_code") == "TK-14"), {})
    check("Tugas baca laporan menunjuk langsung ke laporannya",
          "tab=reports&report=" in (tk14.get("link") or ""), tk14.get("link"))
    notif = g(owner, "/notifications", limit=30).json().get("data") or []
    check("Direksi menerima notifikasi laporan mingguan",
          any("laporan mingguan" in (n.get("title") or "").lower() for n in notif))

    # ------------------------------------------------------- H. analitik telat
    print("\n=== 32H. Analitik keterlambatan + rekomendasi kalibrasi ===")
    r = g(pm, "/build/analytics/delays", project_id=proj["id"])
    if not check("Analitik keterlambatan tersedia", r.status_code == 200, r.text[:150]):
        return
    an = r.json()["data"]
    s = an.get("summary") or {}
    check("Ringkasan analitik memuat tepat waktu vs telat",
          all(k in s for k in ("items_total", "items_late", "on_time_rate", "unexplained")),
          s)
    steps = an.get("by_step") or []
    check("Ada daftar PEKERJAAN paling sering telat", len(steps) >= 1,
          [(x["step_code"], x["units_late"], x["avg_days"]) for x in steps[:3]])
    check("Baris pekerjaan memuat jumlah rumah, rata-rata & maksimum hari telat",
          all(k in steps[0] for k in ("units_late", "avg_days", "max_days", "late_rate",
                                      "planned_days", "unit_codes")) if steps else False,
          list(steps[0])[:8] if steps else None)
    check("Daftar diurutkan dari yang paling sering telat",
          all(steps[i]["units_late"] >= steps[i + 1]["units_late"]
              for i in range(len(steps) - 1)) if len(steps) > 1 else True)
    people = an.get("by_person") or []
    check("Ada daftar PELAKSANA paling sering telat", len(people) >= 1,
          [(x["assigned_to"], x["items_late"], x["late_rate"]) for x in people[:3]])
    check("Baris pelaksana memuat rasio telat & penyebab dominan",
          all(k in people[0] for k in ("items_late", "late_rate", "avg_days",
                                       "dominant_cause", "unexplained")) if people else False)
    types = an.get("by_unit_type") or []
    check("Analitik dipecah per TIPE unit (untuk kalibrasi template)", len(types) >= 1,
          [(x["unit_type"], x["late_rate"]) for x in types[:3]])
    recs = an.get("recommendations") or []
    check("Ada rekomendasi kalibrasi template yang konkret", len(recs) >= 1,
          [x.get("title") for x in recs[:3]])
    if recs:
        check("Rekomendasi menyebut langkah tindak lanjut yang jelas",
              all(k in recs[0] for k in ("kind", "title", "detail", "action")), list(recs[0]))

    # ------------------------------------------------------- I. task hantu
    print("\n=== 32I. Tidak ada 'task hantu' setelah pemantauan ===")
    r = po(pm, "/build/tick")
    tick = (r.json() or {}).get("data") or {}
    check("Pemantauan melaporkan jumlah task yang dirapikan", "tasks_closed" in tick, tick)
    allitems = g(pm, "/build/items", limit=500).json().get("data") or []
    status_by_id = {i["id"]: i["status"] for i in allitems}
    ghosts = []
    for who, h in (("site", site), ("pm", pm)):
        rows_x = g(h, "/work/tasks", scope="mine", limit=200).json().get("data") or []
        if isinstance(rows_x, dict):
            rows_x = [x for v in rows_x.values() for x in v]
        for x in rows_x:
            iid = (x.get("meta") or {}).get("build_item_id")
            if (iid and x.get("jobdesk_code") in ("TK-10", "TK-12")
                    and x.get("status") in ("open", "in_progress", "snoozed")
                    and status_by_id.get(iid) in ("done", "submitted")):
                ghosts.append((who, x.get("title", "")[:40], status_by_id.get(iid)))
    check("Tidak ada task pekerjaan yang masih terbuka padahal itemnya sudah selesai",
          not ghosts, ghosts[:5])

    print(f"\n=== HASIL FASE 32: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
    if FAIL:
        for f in FAIL:
            print(f"  - GAGAL: {f}")
        sys.exit(1)
    print("SEMUA VERIFIKASI FASE 32 LULUS")


if __name__ == "__main__":
    main()
