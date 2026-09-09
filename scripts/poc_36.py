#!/usr/bin/env python3
"""POC/verifikasi Fase 36 — KALENDER JADWAL + MASTER KALENDER KERJA (lewat API NYATA).

Yang dibuktikan (bukan unit test terisolasi — semuanya lewat HTTP seperti dipakai UI):

  A. INV-36-1  Kalender = CERMIN DATA NYATA. Jumlah acara tiap jenis pada payload
               `GET /build/calendar` sama dengan hasil hitung langsung di MongoDB.
  B. SSOT      Grup `calendar_event_kind`, `calendar_day_kind`, `calendar_conflict_kind`,
               `holiday_kind`, `calendar_scope` ada di `/api/reference` (bukan hardcode UI).
  C. MASTER    Pola hari kerja & hari libur bisa dibaca + diubah admin; perubahan langsung
               terlihat di kalender (hari jadi 'holiday'/'off').
  D. INV-36-2  Hari libur MASTER DIPATUHI MESIN JADWAL: jadwal baru (jalur Fase 34) tidak
               menaruh satu pun tanggal pada hari libur/hari off, dan penggeseran massal
               juga tidak. Pratinjau tetap = hasil.
  E. INV-36-3/4/5  Tiga jenis bentrok terdeteksi dengan alasan yang bisa dibaca orang:
               beban pelaksana (ambang bisa diatur), tumpukan pekerjaan kritis, dan tenggat
               yang jatuh di hari non-kerja (+ saran hari kerja terdekat).
  F. INV-36-6  Kalender READ-ONLY: tidak ada endpoint kalender yang mengubah tanggal; satu-
               satunya jalan tetap `POST /build/bulk/shift` yang WAJIB penyebab + catatan.
  G. INV-36-7  RBAC: sales ditolak; pelaksana boleh melihat tapi `can.configure=false` dan
               PUT/POST pengaturan ditolak 403.
  H. INV-36-8  Setiap perubahan kalender tercatat di `audit_logs` (aksi + pelaku).
  I. INV-36-9  Portofolio lintas proyek hanya memuat proyek yang boleh diakses pengguna.
  J. INV-36-10 Bulan tanpa acara tetap mengembalikan grid hari lengkap + ringkasan nol.
  K. QC        Inspeksi bisa dijadwalkan (dan dibatalkan) — kalender tidak mengarang tanggal;
               menjadwalkan di hari libur ditolak dengan saran tanggal.
  L. FILTER    Filter jenis acara & pelaksana mengubah isi DAN ringkasan.

Jalankan pada DB tersegar: `bash scripts/seed_reset.sh` lalu `python3 scripts/poc_36.py`.
Skrip ini MEMBERSIHKAN kembali perubahan ujinya (ambang & hari libur uji dihapus).
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {str(detail)[:200]}" if detail else ""))
    return bool(cond)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=90)


def po(h, p, body=None, **params):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, params=params, timeout=120)


def pu(h, p, body=None, **params):
    return requests.put(f"{BASE}{p}", headers=h, json=body or {}, params=params, timeout=120)


def de(h, p, **params):
    return requests.delete(f"{BASE}{p}", headers=h, params=params, timeout=60)


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_range(month: str):
    y, m = int(month[:4]), int(month[5:7])
    first = date(y, m, 1)
    nxt = date(y + (m // 12), (m % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


# ============================================================ A + B
def audit_contract(pm, owner):
    head("A. Kontrak payload kalender + SSOT (INV-36-1)")
    today = date.today()
    month = month_of(today)
    r = g(pm, "/build/calendar", month=month)
    if not check("GET /build/calendar 200", r.status_code == 200, r.text[:200]):
        sys.exit("payload kalender tidak bisa diambil — hentikan")
    body = r.json()
    d = body["data"]
    for key in ("month", "days", "events", "conflicts", "summary", "calendar", "projects",
                "assignees", "unscheduled", "outlook", "prev_month", "next_month", "today"):
        check(f"payload memuat '{key}'", key in d)
    first, last = month_range(month)
    check("grid hari = jumlah hari bulan itu", len(d["days"]) == (last - first).days + 1,
          f"{len(d['days'])} vs {(last - first).days + 1}")
    check("setiap hari membawa jenis hari + status kerja",
          all({"date", "kind", "is_workday", "counts", "total"} <= set(x) for x in d["days"]))
    check("outlook 3 bulan ke depan disertakan", len(d.get("outlook") or []) == 3,
          d.get("outlook"))

    # ---- INV-36-1: cocokkan dengan hitungan LANGSUNG di database
    lo, hi = first.isoformat(), last.isoformat()
    pids = [p["id"] for p in d["projects"]]
    db_items = mdb.build_items.count_documents(
        {"project_id": {"$in": pids}, "planned_finish": {"$gte": lo, "$lte": hi}})
    api_items = d["summary"]["totals"]["work_deadline"]
    check("jumlah tenggat pekerjaan = hitungan database", db_items == api_items,
          f"db={db_items} api={api_items}")
    db_start = mdb.build_schedules.count_documents(
        {"project_id": {"$in": pids}, "start_date": {"$gte": lo, "$lte": hi}})
    check("jumlah 'mulai pembangunan' = hitungan database",
          db_start == d["summary"]["totals"]["schedule_start"],
          f"db={db_start} api={d['summary']['totals']['schedule_start']}")
    db_insp = mdb.inspections.count_documents(
        {"project_id": {"$in": pids}, "scheduled_date": {"$gte": lo, "$lte": hi}})
    check("jumlah inspeksi terjadwal = hitungan database",
          db_insp == d["summary"]["totals"]["inspection"],
          f"db={db_insp} api={d['summary']['totals']['inspection']}")
    check("total acara = jumlah seluruh jenis",
          d["summary"]["totals"]["all"] == sum(
              v for k, v in d["summary"]["totals"].items() if k != "all"))
    check("tidak ada tugas Work Hub turunan item pekerjaan (anti dobel)",
          all(not str(e.get("id", "")).startswith("build.item")
              for e in d["events"] if e["kind"] == "task"))
    build_task_ids = {t["id"] for t in mdb.tasks.find(
        {"meta.build_item_id": {"$exists": True}}, {"_id": 0, "id": 1})}
    check("tugas turunan pekerjaan TIDAK muncul sebagai acara tugas",
          not ({e["id"] for e in d["events"] if e["kind"] == "task"} & build_task_ids))

    head("B. SSOT daftar pilihan kalender ada di /api/reference")
    ref = g(pm, "/reference").json().get("data") or {}
    for grp, wajib in (("calendar_event_kind", {"work_deadline", "inspection", "task"}),
                       ("calendar_day_kind", {"full", "half", "off", "holiday"}),
                       ("calendar_conflict_kind", {"overload", "critical_stack",
                                                   "non_workday"}),
                       ("holiday_kind", {"national", "religious", "company", "local"}),
                       ("calendar_scope", {"project", "all"})):
        vals = {o["value"] for o in (ref.get(grp) or {}).get("options") or []}
        check(f"grup SSOT '{grp}' terdaftar & lengkap", wajib <= vals, sorted(vals))
    return d


# ============================================================ C + H
def audit_master(pm, site):
    head("C. Master kalender kerja bisa dibaca & diubah admin (INV-36-8 audit)")
    r = g(pm, "/build/calendar/settings")
    check("GET settings 200", r.status_code == 200, r.text[:160])
    body = r.json()
    cal = body["data"]
    check("pola 7 hari lengkap", set(cal["pattern"]) == set(WEEKDAY_KEYS), cal["pattern"])
    check("kalender bawaan hasil seed ada (source=org)", cal["source"] == "org", cal["source"])
    check("hari libur bawaan terisi", len(cal["holidays"]) >= 10, len(cal["holidays"]))
    check("hari libur membawa nama & jenis",
          all({"date", "name", "kind"} <= set(h) for h in cal["holidays"]))
    check("catatan jujur 'wajib disesuaikan admin' ada",
          "disesuaikan" in str(cal.get("note") or "").lower(), cal.get("note"))
    check("ambang bentrok ikut dikirim",
          {"max_items_per_person_per_day", "max_critical_per_day"} <= set(cal["thresholds"]))
    check("Sabtu setengah hari bisa dinyatakan", cal["pattern"]["sat"] == "half")
    check("pengguna admin/PM boleh mengubah", body["can"]["configure"] is True)
    check("daftar hari + nilai bawaan dikirim untuk form",
          len((body.get("defaults") or {}).get("weekdays") or []) == 7)

    # ---- ubah pola: Sabtu jadi libur, lalu kembalikan
    patt = dict(cal["pattern"])
    r = pu(pm, "/build/calendar/settings",
           {"pattern": {**patt, "sat": "off"}, "thresholds": cal["thresholds"]})
    check("PUT settings (Sabtu jadi libur) 200", r.status_code == 200, r.text[:200])
    after = r.json()["data"]
    check("pola tersimpan", after["pattern"]["sat"] == "off", after["pattern"])
    check("jumlah hari kerja per minggu ikut turun", after["work_days_per_week"] == 5,
          after["work_days_per_week"])
    sat = next((x for x in g(pm, "/build/calendar", month=month_of(date.today()))
                .json()["data"]["days"] if x["weekday_key"] == "sat"), None)
    check("kalender langsung menampilkan Sabtu sebagai libur",
          sat and sat["kind"] == "off" and sat["is_workday"] is False, sat)
    r = pu(pm, "/build/calendar/settings",
           {"pattern": patt, "thresholds": cal["thresholds"]})
    check("pola bisa dikembalikan", r.status_code == 200 and
          r.json()["data"]["pattern"]["sat"] == "half")

    # ---- pola tidak masuk akal ditolak
    r = pu(pm, "/build/calendar/settings",
           {"pattern": {k: "off" for k in WEEKDAY_KEYS}, "thresholds": cal["thresholds"]})
    check("semua hari libur DITOLAK dengan alasan", r.status_code == 400
          and "minimal satu hari kerja" in r.text.lower(), r.text[:160])
    r = pu(pm, "/build/calendar/settings",
           {"pattern": patt, "thresholds": {"max_items_per_person_per_day": 0,
                                            "max_critical_per_day": 2}})
    check("ambang 0 DITOLAK", r.status_code in (400, 422), r.text[:140])

    # ---- audit trail (INV-36-8)
    log = mdb.audit_logs.find_one({"action": "calendar_update"}, sort=[("created_at", -1)])
    check("perubahan kalender tercatat di audit_logs",
          bool(log) and log.get("actor") == "pm@sipro.co.id", (log or {}).get("actor"))

    head("G. RBAC kalender (INV-36-7)")
    sales = login("sales@sipro.co.id")
    check("sales DITOLAK melihat kalender", g(sales, "/build/calendar").status_code == 403)
    rs = g(site, "/build/calendar")
    check("pelaksana BOLEH melihat kalender", rs.status_code == 200, rs.text[:120])
    check("pelaksana tidak diberi tombol ubah (can.configure=false)",
          rs.json().get("can", {}).get("configure") is False)
    check("pelaksana DITOLAK mengubah pengaturan",
          pu(site, "/build/calendar/settings",
             {"pattern": patt, "thresholds": cal["thresholds"]}).status_code == 403)
    check("pelaksana DITOLAK menambah hari libur",
          po(site, "/build/calendar/holidays",
             {"date": "2026-12-31", "name": "Uji akses", "kind": "company"}).status_code == 403)
    return cal


# ============================================================ D
def audit_engine_obeys(pm):
    head("D. Hari libur MASTER dipatuhi MESIN jadwal (INV-36-2)")
    cands = g(pm, "/build/bulk/candidates").json()
    ready = [c for c in cands.get("data") or [] if c.get("schedulable")]
    if not check("ada unit yang belum terjadwal untuk diuji", bool(ready)):
        return
    unit = ready[0]
    unit_id = unit.get("unit_id") or unit.get("id")
    start = date.today() + timedelta(days=3)
    # hari libur BUATAN tepat pada hari kerja ke-2 setelah mulai -> harus dilewati mesin
    holiday = start + timedelta(days=1)
    while holiday.weekday() == 6:
        holiday += timedelta(days=1)
    tag = f"Uji POC 36 {uuid.uuid4().hex[:6]}"
    de(pm, f"/build/calendar/holidays/{holiday.isoformat()}")   # sisa run sebelumnya
    r = po(pm, "/build/calendar/holidays",
           {"date": holiday.isoformat(), "name": tag, "kind": "company"})
    check("hari libur uji bisa ditambahkan", r.status_code == 200, r.text[:180])
    check("hari libur uji langsung terbaca kalender",
          any(x["date"] == holiday.isoformat() and x["kind"] == "holiday"
              for x in g(pm, "/build/calendar", month=month_of(holiday))
              .json()["data"]["days"]))
    dup = po(pm, "/build/calendar/holidays",
             {"date": holiday.isoformat(), "name": tag, "kind": "company"})
    check("hari libur ganda DITOLAK dengan alasan jelas",
          dup.status_code == 400 and "sudah terdaftar" in dup.text.lower(), dup.text[:140])

    body = {"unit_ids": [unit_id], "start_date": start.isoformat(),
            "wave": "same", "stagger_days": 0}
    prev = po(pm, "/build/bulk/schedules/preview", body)
    check("pratinjau jadwal 200", prev.status_code == 200, prev.text[:160])
    prow = (prev.json().get("data") or [{}])[0]
    run = po(pm, "/build/bulk/schedules", {**body, "client_ref": f"poc36-{uuid.uuid4().hex[:8]}"})
    check("jadwal baru dibuat 200", run.status_code == 200, run.text[:200])
    res = (run.json()["data"]["results"] or [{}])[0]
    check("pratinjau = hasil (tanggal mulai & target selesai sama)",
          prow.get("start_date") == res.get("start_date")
          and prow.get("target_finish_date") == res.get("target_finish_date"),
          f"{prow.get('start_date')}/{prow.get('target_finish_date')} vs "
          f"{res.get('start_date')}/{res.get('target_finish_date')}")

    sched_id = res.get("schedule_id")
    items = list(mdb.build_items.find({"schedule_id": sched_id},
                                      {"_id": 0, "planned_start": 1, "planned_finish": 1,
                                       "step_code": 1}))
    check("jadwal baru punya item pekerjaan", bool(items), len(items))
    cal = g(pm, "/build/calendar/settings").json()["data"]
    off_keys = {k for k, v in cal["pattern"].items() if v == "off"}
    off_idx = {WEEKDAY_KEYS.index(k) for k in off_keys}
    hol = {h["date"] for h in cal["holidays"]}
    bad = [i for i in items
           if i["planned_start"] in hol or i["planned_finish"] in hol
           or datetime.strptime(i["planned_start"], "%Y-%m-%d").weekday() in off_idx
           or datetime.strptime(i["planned_finish"], "%Y-%m-%d").weekday() in off_idx]
    check("TIDAK ada tanggal jadwal baru yang mendarat di libur/hari off", not bad,
          [(b["step_code"], b["planned_start"], b["planned_finish"]) for b in bad[:4]])
    check("hari libur uji benar-benar dilewati (ada item sesudahnya)",
          any(i["planned_start"] > holiday.isoformat() for i in items))

    # ---- penggeseran massal juga patuh kalender
    sh = po(pm, "/build/bulk/shift/preview", {"schedule_ids": [sched_id], "shift_days": 9})
    check("pratinjau geser 200", sh.status_code == 200, sh.text[:160])
    srow = (sh.json().get("data") or [{}])[0]
    ru = po(pm, "/build/bulk/shift", {"schedule_ids": [sched_id], "shift_days": 9,
                                      "cause": "weather",
                                      "note": "uji POC 36 kalender kerja dipatuhi",
                                      "client_ref": f"poc36s-{uuid.uuid4().hex[:8]}"})
    check("geser massal 200", ru.status_code == 200, ru.text[:200])
    moved = list(mdb.build_items.find({"schedule_id": sched_id},
                                      {"_id": 0, "planned_start": 1, "planned_finish": 1}))
    bad2 = [i for i in moved
            if i["planned_start"] in hol or i["planned_finish"] in hol
            or datetime.strptime(i["planned_start"], "%Y-%m-%d").weekday() in off_idx
            or datetime.strptime(i["planned_finish"], "%Y-%m-%d").weekday() in off_idx]
    check("setelah digeser pun tidak ada tanggal di hari libur", not bad2, bad2[:3])
    check("pratinjau geser = hasil geser",
          srow.get("new_start") == (mdb.build_schedules.find_one(
              {"id": sched_id}, {"_id": 0, "start_date": 1}) or {}).get("start_date"),
          srow.get("new_start"))

    head("F. Kalender READ-ONLY: satu-satunya jalan ubah tanggal = Fase 34 (INV-36-6)")
    check("geser tanpa penyebab DITOLAK",
          po(pm, "/build/bulk/shift", {"schedule_ids": [sched_id], "shift_days": 3,
                                       "note": "tanpa penyebab sama sekali"}
             ).status_code == 400)
    check("geser tanpa catatan DITOLAK",
          po(pm, "/build/bulk/shift", {"schedule_ids": [sched_id], "shift_days": 3,
                                       "cause": "weather", "note": "pendek"}
             ).status_code == 400)
    spec = requests.get("http://localhost:8001/openapi.json", timeout=30).json()
    cal_paths = {p: set(v.keys()) for p, v in spec["paths"].items()
                 if p.startswith("/api/build/calendar")}
    writes = {p: m for p, m in cal_paths.items() if {"post", "put", "delete"} & m}
    check("endpoint tulis di /build/calendar hanya untuk master kalender",
          all("holiday" in p or p.endswith("/settings") for p in writes), sorted(writes))

    # ---- bersihkan hari libur uji
    rd = de(pm, f"/build/calendar/holidays/{holiday.isoformat()}")
    check("hari libur uji bisa dihapus", rd.status_code == 200, rd.text[:140])
    check("penghapusan hari libur tercatat audit",
          bool(mdb.audit_logs.find_one({"action": "calendar_holiday_remove",
                                        "entity_id": holiday.isoformat()})))
    check("hari libur yang tidak ada DITOLAK saat dihapus",
          de(pm, "/build/calendar/holidays/2019-01-02").status_code == 400)
    return sched_id


# ============================================================ E
def audit_conflicts(pm):
    head("E. Deteksi bentrok: beban, tumpukan kritis, hari non-kerja (INV-36-3/4/5)")
    base = g(pm, "/build/calendar/settings").json()["data"]
    # 1) beban pelaksana — ambang diturunkan ke 1 supaya perilaku terlihat pada data nyata
    pu(pm, "/build/calendar/settings",
       {"pattern": base["pattern"],
        "thresholds": {"max_items_per_person_per_day": 1,
                       "max_critical_per_day": base["thresholds"]["max_critical_per_day"]}})
    d = g(pm, "/build/calendar", month=month_of(date.today())).json()["data"]
    ov = [c for c in d["conflicts"] if c["kind"] == "overload"]
    check("bentrok beban pelaksana terdeteksi saat ambang diturunkan", bool(ov),
          d["summary"]["conflicts"])
    if ov:
        c = ov[0]
        check("bentrok beban menyebut ORANG, jumlah, dan ambang",
              c.get("person") and c["count"] > c["threshold"], c)
        check("bentrok beban membawa daftar pekerjaan & jadwal (untuk aksi geser)",
              len(c.get("item_ids") or []) == c["count"] and bool(c.get("schedule_ids")))
        check("alasan bentrok bisa dibaca orang (bukan kode)",
              "kebagian" in c["detail"] and str(c["threshold"]) in c["detail"], c["detail"])
        day = next((x for x in d["days"] if x["date"] == c["date"]), None)
        check("hari bentrok ditandai pada grid + beban per orang terlihat",
              day and "overload" in day["conflicts"] and day["load"], day)
    # 2) ambang dikembalikan -> bentrok beban ikut hilang/berkurang
    pu(pm, "/build/calendar/settings",
       {"pattern": base["pattern"], "thresholds": base["thresholds"]})
    d2 = g(pm, "/build/calendar", month=month_of(date.today())).json()["data"]
    check("ambang dikembalikan → jumlah bentrok beban ikut menyesuaikan",
          d2["summary"]["conflicts"]["overload"] <= d["summary"]["conflicts"]["overload"],
          (d["summary"]["conflicts"], d2["summary"]["conflicts"]))
    check("ambang yang dipakai ikut dikirim ke UI",
          d2["summary"]["thresholds"] == base["thresholds"], d2["summary"]["thresholds"])

    # 3) tenggat pada hari libur — cari bulan yang memuatnya (data seed: 17 Agustus)
    found = None
    for step in range(0, 6):
        y, m = date.today().year, date.today().month + step
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        dd = g(pm, "/build/calendar", month=f"{y:04d}-{m:02d}").json()["data"]
        nw = [c for c in dd["conflicts"] if c["kind"] == "non_workday"]
        cs = [c for c in dd["conflicts"] if c["kind"] == "critical_stack"]
        if nw and not found:
            found = (dd, nw[0], cs)
        if found:
            break
    if check("ada bentrok 'tenggat di hari non-kerja' pada data nyata", bool(found)):
        dd, c, cs = found
        check("bentrok hari libur menyebut alasan + saran hari kerja terdekat",
              c.get("suggested_date") and ("libur" in c["detail"] or "bukan hari kerja"
                                           in c["detail"]), c["detail"])
        info = next((x for x in dd["days"] if x["date"] == c["suggested_date"]), None)
        check("tanggal saran benar-benar hari kerja",
              info is None or info["is_workday"] is True, info)
        check("bentrok hari libur membawa unit & pekerjaan terkait",
              bool(c.get("unit_codes")) and bool(c.get("item_ids")), c.get("unit_codes"))
    # 4) tumpukan pekerjaan kritis (cari di 6 bulan ke depan)
    stack = None
    for step in range(0, 6):
        y, m = date.today().year, date.today().month + step
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        dd = g(pm, "/build/calendar", month=f"{y:04d}-{m:02d}").json()["data"]
        hit = [c for c in dd["conflicts"] if c["kind"] == "critical_stack"]
        if hit:
            stack = hit[0]
            break
    if check("ada bentrok 'pekerjaan kritis menumpuk' pada data nyata", bool(stack)):
        check("bentrok kritis menyebut jumlah + ambang + alasan",
              stack["count"] > stack["threshold"] and "kritis" in stack["detail"], stack)


# ============================================================ I + J + K + L
def audit_scope_filter_qc(pm, owner, site):
    head("I. Portofolio lintas proyek dibatasi hak akses (INV-36-9)")
    d_all = g(pm, "/build/calendar").json()["data"]
    check("tanpa project_id → cakupan 'all'", d_all["scope"] == "all", d_all["scope"])
    member_projects = {p["id"] for p in mdb.projects.find(
        {"members": "pm@sipro.co.id"}, {"_id": 0, "id": 1})}
    check("PM hanya melihat proyek yang dia ikuti",
          {p["id"] for p in d_all["projects"]} <= member_projects,
          [p["name"] for p in d_all["projects"]])
    d_owner = g(owner, "/build/calendar").json()["data"]
    total_projects = mdb.projects.count_documents({})
    check("direksi melihat SEMUA proyek", len(d_owner["projects"]) == total_projects,
          f"{len(d_owner['projects'])} vs {total_projects}")
    one = d_all["projects"][0]["id"] if d_all["projects"] else None
    if one:
        d_one = g(pm, "/build/calendar", project_id=one).json()["data"]
        check("dengan project_id → cakupan 'project' & hanya proyek itu",
              d_one["scope"] == "project" and all(
                  e.get("project_id") in (None, one) for e in d_one["events"]))
    check("proyek asing DITOLAK (404/403)",
          g(pm, "/build/calendar", project_id="tidak-ada").status_code in (403, 404))

    head("J. Bulan tanpa acara tetap jujur (INV-36-10)")
    far = g(pm, "/build/calendar", month="2029-02").json()["data"]
    check("bulan kosong: grid hari tetap lengkap", len(far["days"]) == 28, len(far["days"]))
    check("bulan kosong: total acara 0 & tanpa bentrok",
          far["summary"]["totals"]["all"] == 0 and far["summary"]["conflicts"]["total"] == 0)
    check("bulan salah format DITOLAK",
          g(pm, "/build/calendar", month="agustus").status_code == 400)

    head("K. Inspeksi/QC dijadwalkan (kalender tidak mengarang tanggal)")
    proj = one or (mdb.projects.find_one({}, {"_id": 0, "id": 1}) or {}).get("id")
    unit = mdb.units.find_one({"project_id": proj}, {"_id": 0, "id": 1, "code": 1}) or {}
    cr = po(pm, "/inspections", {"project_id": proj, "template_code": "QC-STR",
                                 "unit_id": unit.get("id"),
                                 "title": f"Uji kalender {uuid.uuid4().hex[:5]}"})
    check("inspeksi baru dibuat", cr.status_code == 200, cr.text[:180])
    iid = (cr.json().get("data") or {}).get("id")
    d = g(pm, "/build/calendar").json()["data"]
    check("inspeksi tanpa tanggal masuk daftar 'belum dijadwalkan'",
          any(x["id"] == iid for x in d["unscheduled"]),
          [x.get("inspection_number") for x in d["unscheduled"]][:5])
    cal = g(pm, "/build/calendar/settings").json()["data"]
    hol_future = sorted([h["date"] for h in cal["holidays"]
                         if h["date"] >= date.today().isoformat()])
    if hol_future:
        bad = pu(pm, f"/inspections/{iid}/schedule", {"scheduled_date": hol_future[0]})
        check("menjadwalkan inspeksi di hari libur DITOLAK + ada saran tanggal",
              bad.status_code == 400 and "terdekat" in bad.text, bad.text[:200])
    target = date.today() + timedelta(days=5)
    for _ in range(10):
        info = g(pm, "/build/calendar/workday", date=target.isoformat()).json()["data"]
        if info["is_workday"]:
            break
        target += timedelta(days=1)
    okr = pu(pm, f"/inspections/{iid}/schedule",
             {"scheduled_date": target.isoformat(), "note": "uji jadwal inspeksi"})
    check("inspeksi bisa dijadwalkan pada hari kerja", okr.status_code == 200, okr.text[:160])
    dd = g(pm, "/build/calendar", month=month_of(target)).json()["data"]
    check("inspeksi terjadwal muncul sebagai acara kalender",
          any(e["kind"] == "inspection" and e["id"] == iid for e in dd["events"]))
    check("inspeksi terjadwal keluar dari daftar 'belum dijadwalkan'",
          not any(x["id"] == iid for x in dd["unscheduled"]))
    back = pu(pm, f"/inspections/{iid}/schedule", {"scheduled_date": None})
    check("tanggal inspeksi bisa dibatalkan lagi", back.status_code == 200, back.text[:140])
    check("pemeriksa hari kerja menjelaskan hari libur",
          g(pm, "/build/calendar/workday", date="2026-08-17").json()["data"]["is_workday"]
          is False)

    head("L. Filter jenis acara & pelaksana (UI benar-benar didukung server)")
    only = g(pm, "/build/calendar", month=month_of(date.today()),
             kinds="work_deadline").json()["data"]
    check("filter jenis: hanya jenis yang diminta yang keluar",
          {e["kind"] for e in only["events"]} <= {"work_deadline"},
          {e["kind"] for e in only["events"]})
    check("filter jenis: ringkasan ikut menyesuaikan",
          only["summary"]["totals"]["task"] == 0
          and only["summary"]["totals"]["all"] == len(only["events"]))
    people = only.get("assignees") or []
    if check("daftar pelaksana untuk filter tersedia", bool(people), people):
        one_p = people[0]
        fp = g(pm, "/build/calendar", month=month_of(date.today()),
               assignee=one_p).json()["data"]
        check("filter pelaksana: semua acara milik orang itu",
              all(e.get("assigned_to") in (None, one_p) for e in fp["events"]), one_p)
    months = g(pm, "/build/calendar/months", months=6)
    check("daftar bulan untuk dropdown tersedia",
          months.status_code == 200 and len(months.json()["data"]) == 7,
          months.text[:120])


# ============================================================ M (regresi pewarisan)
def audit_inheritance(pm):
    """INV-36-11..14 — PEWARISAN KALENDER (regresi cacat nyata ronde-2 Fase 36).

    Cacat aslinya: `resolve()` memperlakukan kalender khusus proyek sebagai PENGGANTI utuh
    kalender organisasi, dan `_ensure_doc` membuatnya dengan `holidays: []`. Akibatnya satu
    kali menekan "Simpan pola & ambang" pada cakupan proyek (mis. hanya untuk mengubah ambang
    bentrok) MENGHAPUS 18 hari libur nasional untuk proyek itu secara senyap:
      * `summary.holidays` bulan Agustus jadi kosong,
      * bentrok `non_workday` (tenggat di 17 Agustus) hilang,
      * inspeksi QC BISA dijadwalkan pada Hari Kemerdekaan tanpa satu pun peringatan.
    Bagian ini membuktikan perilaku itu sudah mustahil terulang.
    """
    head("M. Pewarisan kalender proyek (libur nasional tidak boleh hilang senyap)")
    proj = (mdb.projects.find_one({}, {"_id": 0, "id": 1}) or {}).get("id")
    org_cal = g(pm, "/build/calendar/settings").json()["data"]
    n_org = len(org_cal["holidays"])
    check("kalender organisasi punya daftar libur", n_org > 0, n_org)
    hol = sorted(h["date"] for h in org_cal["holidays"]
                 if h["date"] >= date.today().isoformat())
    target_hol = hol[0] if hol else None

    # --- INV-36-11: menyimpan pengaturan pada cakupan proyek TIDAK menghapus libur warisan
    saved = pu(pm, "/build/calendar/settings",
               {"pattern": org_cal["pattern"], "project_id": proj,
                "thresholds": {"max_items_per_person_per_day": 4, "max_critical_per_day": 2}})
    check("PUT pengaturan cakupan proyek berhasil", saved.status_code == 200, saved.text[:160])
    pc = g(pm, "/build/calendar/settings", project_id=proj).json()["data"]
    check("override proyek terbentuk", pc["override_exists"] is True, pc["source"])
    check("INV-36-11 libur organisasi TETAP diwarisi (tidak hilang senyap)",
          len(pc["holidays"]) == n_org and pc["org_holidays"] == n_org,
          f"efektif={len(pc['holidays'])} org={pc['org_holidays']} (harus {n_org})")
    check("setiap libur warisan menyebut asalnya",
          all(h.get("scope") == "org" for h in pc["holidays"]),
          {h.get("scope") for h in pc["holidays"]})
    check("ambang khusus proyek benar-benar tersimpan",
          pc["thresholds"]["max_items_per_person_per_day"] == 4, pc["thresholds"])
    if target_hol:
        hm = target_hol[:7]
        cv = g(pm, "/build/calendar", month=hm, project_id=proj).json()["data"]
        check("bulan berlibur tetap menandai hari liburnya di kalender proyek",
              target_hol in [h["date"] for h in cv["summary"]["holidays"]],
              [h["date"] for h in cv["summary"]["holidays"]])
        wd = g(pm, "/build/calendar/workday", date=target_hol, project_id=proj).json()["data"]
        check("hari libur warisan tetap BUKAN hari kerja bagi proyek itu",
              wd["is_workday"] is False, wd)

    # --- INV-36-12: mengecualikan libur warisan disengaja, TIDAK mengubah kalender organisasi
    if target_hol:
        ex = de(pm, f"/build/calendar/holidays/{target_hol}", project_id=proj)
        check("hapus libur warisan pada cakupan proyek = DIKECUALIKAN (bukan dihapus)",
              ex.status_code == 200 and ex.json().get("action") == "excluded", ex.text[:200])
        after = ex.json()["data"]
        check("pengecualian tampil terpisah agar tidak tersembunyi",
              target_hol in [h["date"] for h in after.get("excluded_holidays") or []],
              after.get("excluded_holidays"))
        check("INV-36-12 kalender ORGANISASI tidak ikut kehilangan libur itu",
              len(g(pm, "/build/calendar/settings").json()["data"]["holidays"]) == n_org)
        wd2 = g(pm, "/build/calendar/workday", date=target_hol, project_id=proj).json()["data"]
        check("proyek yang mengecualikan boleh bekerja pada tanggal itu",
              wd2["is_workday"] is True, wd2)
        again = de(pm, f"/build/calendar/holidays/{target_hol}", project_id=proj)
        check("mengecualikan dua kali ditolak jujur", again.status_code == 400, again.text[:160])
        back = po(pm, f"/build/calendar/holidays/{target_hol}/restore", {}, project_id=proj)
        check("pengecualian bisa DIBATALKAN kembali",
              back.status_code == 200
              and not (back.json()["data"].get("excluded_holidays") or []), back.text[:160])
        wd3 = g(pm, "/build/calendar/workday", date=target_hol, project_id=proj).json()["data"]
        check("setelah dibatalkan, tanggal itu libur lagi", wd3["is_workday"] is False)
        dup = po(pm, "/build/calendar/holidays",
                 {"date": target_hol, "name": "Coba tambah ulang", "kind": "company"},
                 project_id=proj)
        check("menambah libur yang sudah diwarisi ditolak dengan penjelasan",
              dup.status_code == 400 and "diwarisi" in dup.text, dup.text[:200])

    # --- INV-36-13: override bisa dilepas -> kembali mengikuti kalender organisasi
    lst = g(pm, "/build/calendar/settings").json().get("overrides") or []
    check("daftar proyek berkalender sendiri terbuka (divergensi tidak disembunyikan)",
          any(o["project_id"] == proj for o in lst), lst)
    drop = de(pm, "/build/calendar/settings", project_id=proj)
    check("INV-36-13 kalender khusus proyek bisa dilepas",
          drop.status_code == 200 and drop.json()["data"]["override_exists"] is False,
          drop.text[:160])
    fin = g(pm, "/build/calendar/settings", project_id=proj).json()["data"]
    check("setelah dilepas, ambang kembali ikut organisasi",
          fin["thresholds"] == org_cal["thresholds"], fin["thresholds"])
    check("setelah dilepas, jumlah libur tetap utuh", len(fin["holidays"]) == n_org)
    check("melepas dua kali ditolak jujur",
          de(pm, "/build/calendar/settings", project_id=proj).status_code == 400)

    # --- INV-36-14: agenda lapangan (inspeksi/punch) yang jatuh di libur ikut ditandai
    unit = mdb.units.find_one({"project_id": proj}, {"_id": 0, "id": 1}) or {}
    cr = po(pm, "/inspections", {"project_id": proj, "template_code": "QC-STR",
                                 "unit_id": unit.get("id"),
                                 "title": f"Uji libur {uuid.uuid4().hex[:5]}"})
    iid = (cr.json().get("data") or {}).get("id")
    day = date.today() + timedelta(days=9)
    for _ in range(12):
        if g(pm, "/build/calendar/workday", date=day.isoformat()).json()["data"]["is_workday"]:
            break
        day += timedelta(days=1)
    iso = day.isoformat()
    check("inspeksi dijadwalkan pada hari kerja",
          pu(pm, f"/inspections/{iid}/schedule", {"scheduled_date": iso}).status_code == 200)
    add = po(pm, "/build/calendar/holidays",
             {"date": iso, "name": "Cuti bersama uji regresi", "kind": "company"})
    check("hari libur baru ditambahkan tepat pada tanggal inspeksi itu",
          add.status_code == 200, add.text[:160])
    cv = g(pm, "/build/calendar", month=month_of(day), project_id=proj).json()["data"]
    row = next((c for c in cv["conflicts"]
                if c["kind"] == "non_workday" and c["date"] == iso), None)
    check("INV-36-14 inspeksi yang mendadak jatuh di hari libur DITANDAI bentrok",
          bool(row) and "inspection" in (row.get("kinds") or []),
          row and {"kinds": row.get("kinds"), "detail": row.get("detail")[:120]})
    check("pesan bentrok menyebut jenis agendanya + saran hari kerja",
          bool(row) and "inspeksi" in (row or {}).get("detail", "").lower()
          and "terdekat" in (row or {}).get("detail", ""), row and row.get("detail")[:160])
    # bersihkan: hapus libur uji & inspeksi uji
    check("libur uji dihapus kembali",
          de(pm, f"/build/calendar/holidays/{iso}").status_code == 200)
    pu(pm, f"/inspections/{iid}/schedule", {"scheduled_date": None})
    mdb.inspections.delete_one({"id": iid})
    check("audit_logs mencatat pengecualian/pelepasan kalender",
          mdb.audit_logs.count_documents(
              {"action": {"$in": ["calendar_holiday_exclude", "calendar_holiday_restore",
                                  "calendar_override_drop"]}}) >= 2)


def main():
    print("=" * 66)
    print("POC FASE 36 — KALENDER JADWAL & MASTER KALENDER KERJA (API NYATA)")
    print("=" * 66)
    pm = login("pm@sipro.co.id")
    owner = login("owner@sipro.co.id")
    site = login("site@sipro.co.id")
    audit_contract(pm, owner)
    audit_master(pm, site)
    audit_engine_obeys(pm)
    audit_conflicts(pm)
    audit_scope_filter_qc(pm, owner, site)
    audit_inheritance(pm)
    print("\n" + "=" * 66)
    print(f"HASIL POC 36: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print("  FAIL:", f)
        sys.exit(1)
    print("SEMUA INVARIAN FASE 36 TERBUKTI LEWAT API NYATA")


if __name__ == "__main__":
    main()
