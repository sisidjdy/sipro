#!/usr/bin/env python3
"""POC/verifikasi Fase 37 — KALIBRASI SEKALI KLIK (lewat API NYATA).

Yang dibuktikan (semuanya lewat HTTP seperti dipakai UI, bukan unit test terisolasi):

  A. SSOT      Grup `calibration_kind` & `calibration_cause` ada di `/api/reference` dan
               nilainya sama dengan mesin (`build_calibration.KINDS`).
  B. USULAN    `GET /build/calibration/candidates` memuat rekomendasi dari data telat NYATA,
               setiap rekomendasi yang bisa dieksekusi membawa target template + snapshot
               langkah saat ini (tidak ada angka yang diketik ulang di UI).
  C. INV-37-1  PRATINJAU = HASIL: baris sebelum→sesudah pada pratinjau sama persis dengan
               isi template setelah kalibrasi diterapkan.
  D. INV-37-2  Kalibrasi TIDAK menyentuh jadwal/bukti yang sudah ada: seluruh
               `planned_start/planned_finish` item & tanggal jadwal unit tetap sama.
  E. INV-37-3  Jadwal BARU memakai angka baru (durasi langkah yang dikalibrasi ikut berubah).
  F. INV-37-10 Jadwal baru itu tetap menghormati kalender kerja Fase 36 (tidak ada tanggal
               rencana yang mendarat di hari libur / bukan hari kerja).
  G. INV-37-4  Tanpa alasan / catatan <10 karakter → 400. `client_ref` sama → tidak dobel.
  H. INV-37-5  Template tetap konsisten: durasi ≥1, day_from ≤ day_to, `week` benar,
               total bobot tidak berubah, urutan yang tadinya berurutan tetap tidak tumpang tindih.
  I. INV-37-6  Rollback mengembalikan TEPAT nilai sebelumnya; tidak bisa dua kali; kalibrasi
               lama tidak bisa dibatalkan bila template sudah berubah setelahnya.
  J. INV-37-7  RBAC: pelaksana boleh melihat tapi `can.calibrate=false` & apply 403; sales 403.
  K. INV-37-8  Setiap kalibrasi & pembatalan masuk `audit_logs`.
  L. INV-37-9  Rekomendasi yang sudah dikalibrasi ditandai "sudah diterapkan", dan tandanya
               HILANG lagi setelah dibatalkan.
  M. WAIT      `wait_time` tidak menggeser tanggal rencana (dan mengatakannya terus terang);
               `wait_into_plan` memasukkan waktu tunggu ke rencana tanpa mempersingkatnya.

Jalankan pada DB tersegar: `bash scripts/seed_reset.sh` lalu `python3 scripts/poc_37.py`.
Skrip ini MEMBERSIHKAN kembali perubahannya (semua kalibrasi uji dibatalkan, jadwal uji dihapus).
"""
import math
import os
import sys
import uuid
from datetime import date, timedelta
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


def de(h, p, **params):
    return requests.delete(f"{BASE}{p}", headers=h, params=params, timeout=60)


def steps_of(h, tid) -> dict:
    r = g(h, f"/build/templates/{tid}")
    return {s["code"]: s for s in r.json()["data"]["steps"]}


def item_dates() -> dict:
    """Tanggal rencana SELURUH item pekerjaan yang sudah ada (bukti yang tidak boleh bergeser)."""
    return {i["id"]: (i.get("planned_start"), i.get("planned_finish"), i.get("day_from"),
                      i.get("day_to"))
            for i in mdb.build_items.find({}, {"_id": 0, "id": 1, "planned_start": 1,
                                               "planned_finish": 1, "day_from": 1,
                                               "day_to": 1})}


def sched_dates() -> dict:
    return {s["id"]: (s.get("start_date"), s.get("target_finish_date"))
            for s in mdb.build_schedules.find({}, {"_id": 0, "id": 1, "start_date": 1,
                                                   "target_finish_date": 1})}


# ============================================================ A + B
def audit_ssot_and_candidates(pm, site, sales):
    head("A. SSOT kalibrasi ada di kamus data (bukan hardcode UI)")
    ref = g(pm, "/reference").json()
    groups = ref.get("data") or ref.get("groups") or ref
    kinds = {o["value"] for o in (groups.get("calibration_kind") or {}).get("options", [])}
    causes = {o["value"] for o in (groups.get("calibration_cause") or {}).get("options", [])}
    check("grup calibration_kind tersedia di /api/reference",
          kinds == {"step_duration", "wait_time", "wait_into_plan"}, kinds)
    check("grup calibration_cause tersedia & memuat alasan pembatalan",
          "pembatalan_kalibrasi" in causes and len(causes) >= 6, sorted(causes))
    sys.path.insert(0, str(ROOT / "backend"))
    import build_calibration as bcx  # noqa: PLC0415
    check("nilai SSOT = nilai mesin", set(bcx.KINDS) == kinds, bcx.KINDS)

    head("B. Usulan kalibrasi lahir dari data telat NYATA")
    r = g(pm, "/build/calibration/candidates")
    if not check("GET /build/calibration/candidates 200", r.status_code == 200, r.text[:200]):
        sys.exit("usulan kalibrasi tidak bisa diambil — hentikan")
    body = r.json()
    d = body["data"]
    check("PM boleh mengalibrasi", body["can"]["calibrate"] is True, body["can"])
    for key in ("summary", "recommendations", "steps", "templates", "history"):
        check(f"payload memuat '{key}'", key in d)
    actionable = [x for x in d["recommendations"] if x.get("calibration")]
    check("ada rekomendasi yang benar-benar bisa dieksekusi", bool(actionable),
          [x["title"] for x in d["recommendations"]][:4])
    for rec in actionable:
        cal = rec["calibration"]
        check(f"rekomendasi '{rec['title'][:38]}' membawa jenis kalibrasi SSOT",
              cal["kind"] in bcx.KINDS, cal)
        check(f"rekomendasi '{rec['title'][:38]}' punya target template + snapshot langkah",
              bool(rec["targets"]) and all(t.get("current") for t in rec["targets"]),
              rec["targets"][:1])
    waits = [x for x in actionable if x["calibration"]["kind"] == "wait_into_plan"]
    if waits:
        check("kalimat rekomendasi waktu tunggu jujur (rencana yang dibuat jujur, "
              "bukan curing dipersingkat)",
              "tidak dipersingkat" in waits[0]["detail"], waits[0]["detail"][:160])
    check("setiap langkah pada tabel telat bisa dikalibrasi langsung",
          all(isinstance(s.get("targets"), list) for s in d["steps"]),
          [s["step_code"] for s in d["steps"]][:6])

    head("J. RBAC kalibrasi (INV-37-7)")
    rs = g(site, "/build/calibration/candidates")
    check("pelaksana boleh MELIHAT usulan", rs.status_code == 200, rs.text[:120])
    if rs.status_code == 200:
        check("pelaksana TIDAK boleh mengalibrasi (can.calibrate=false)",
              rs.json()["can"]["calibrate"] is False, rs.json()["can"])
    tpl_id = d["templates"][0]["id"]
    ap = po(site, "/build/calibration/apply",
            {"template_id": tpl_id, "step_code": d["steps"][0]["step_code"],
             "kind": "step_duration", "delta_days": 1, "cause": "data_telat",
             "note": "mencoba menerobos lewat API"})
    check("apply oleh pelaksana DITOLAK 403", ap.status_code == 403, ap.text[:160])
    sl = g(sales, "/build/calibration/candidates")
    check("sales DITOLAK melihat usulan kalibrasi (403)", sl.status_code == 403, sl.text[:160])
    return d


# ============================================================ C..F
def audit_preview_equals_apply(pm, cands):
    head("C. Pratinjau = hasil, dan bukti lama tidak bergeser (INV-37-1 & INV-37-2)")
    tpl_id = cands["templates"][0]["id"]
    before_steps = steps_of(pm, tpl_id)
    # Pilih langkah yang (1) punya langkah SETELAHNYA supaya pergeseran ikut teruji, dan
    # (2) BENAR-BENAR muncul di tabel telat — supaya tanda "sudah diterapkan" pada kartu
    # rekomendasi (INV-37-9) teruji di tempat rekomendasi itu tinggal, bukan di langkah
    # acak yang tidak pernah dianalisis.
    late_codes = [s["step_code"] for s in cands["steps"]
                  if any(t["template_id"] == tpl_id for t in s.get("targets") or [])]
    target = None
    for code, s in sorted(before_steps.items(), key=lambda kv: kv[1]["day_from"]):
        later = [x for x in before_steps.values() if x["day_from"] > s["day_to"]]
        if len(later) >= 3 and code in late_codes:
            target = code
            break
    if not check("ada langkah telat dengan penerus untuk diuji", bool(target),
                 {"telat": late_codes[:6]}):
        return None
    pv = po(pm, "/build/calibration/preview",
            {"template_id": tpl_id, "step_code": target, "kind": "step_duration",
             "delta_days": 2})
    if not check("pratinjau 200", pv.status_code == 200, pv.text[:200]):
        return None
    prev = pv.json()["data"]
    check("pratinjau menyebut langkah yang ikut bergeser", prev["shifted_count"] >= 1,
          prev["shifted_count"])
    check("pratinjau menyebut total durasi sebelum→sesudah",
          prev["total_days_after"] == prev["total_days_before"] + 2,
          (prev["total_days_before"], prev["total_days_after"]))
    check("pratinjau menyebut jadwal berjalan yang TIDAK diubah",
          "TIDAK diubah" in prev["impact"]["schedules_unchanged_note"]
          or prev["impact"]["schedules_running"] == 0,
          prev["impact"]["schedules_unchanged_note"][:120])
    check("pratinjau menyebut berapa rumah belum terjadwal yang akan memakai angka baru",
          isinstance(prev["impact"]["units_unscheduled"], int)
          and prev["impact"]["units_matching"] > 0,
          {k: prev["impact"][k] for k in ("units_matching", "units_unscheduled")})

    items_before, scheds_before = item_dates(), sched_dates()
    ref = f"poc37-{uuid.uuid4().hex[:10]}"
    ap = po(pm, "/build/calibration/apply",
            {"template_id": tpl_id, "step_code": target, "kind": "step_duration",
             "delta_days": 2, "cause": "data_telat", "client_ref": ref,
             "note": "Uji POC 37: durasi ditambah karena bukti telat berulang"})
    if not check("kalibrasi diterapkan 200", ap.status_code == 200, ap.text[:200]):
        return None
    cal = ap.json()["data"]
    after_steps = steps_of(pm, tpl_id)
    same = all(after_steps[r["code"]]["day_from"] == r["after"]["day_from"]
               and after_steps[r["code"]]["day_to"] == r["after"]["day_to"]
               and int(after_steps[r["code"]].get("wait_days") or 0) == r["after"]["wait_days"]
               for r in prev["rows"])
    check("INV-37-1 isi template setelah kalibrasi = baris 'sesudah' pada pratinjau", same,
          [(r["code"], r["after"]["day_from"], r["after"]["day_to"]) for r in prev["rows"]][:3])
    check("jumlah baris terdampak sama antara pratinjau & hasil",
          len(cal["rows"]) == len(prev["rows"]), (len(cal["rows"]), len(prev["rows"])))
    check("INV-37-2 tanggal rencana SEMUA item pekerjaan lama tidak bergeser",
          item_dates() == items_before)
    check("INV-37-2 tanggal jadwal unit lama tidak bergeser", sched_dates() == scheds_before)

    head("H. Template tetap konsisten setelah kalibrasi (INV-37-5)")
    wdpw = int((g(pm, f"/build/templates/{tpl_id}").json()["data"]
                .get("work_days_per_week")) or 6)
    check("durasi setiap langkah ≥ 1 hari",
          all(s["day_to"] >= s["day_from"] for s in after_steps.values()))
    check("nomor minggu setiap langkah dihitung ulang dengan benar",
          all(int(s["week"]) == max(1, math.ceil(s["day_from"] / wdpw))
              for s in after_steps.values()),
          [(s["code"], s["week"], s["day_from"]) for s in after_steps.values()
           if int(s["week"]) != max(1, math.ceil(s["day_from"] / wdpw))][:3])
    check("total bobot template tidak berubah",
          round(sum(float(s.get("weight") or 0) for s in before_steps.values()), 2)
          == round(sum(float(s.get("weight") or 0) for s in after_steps.values()), 2))
    broken = [(a["code"], b["code"]) for a in before_steps.values() for b in before_steps.values()
              if a["day_from"] > b["day_to"]
              and after_steps[a["code"]]["day_from"] <= after_steps[b["code"]]["day_to"]]
    check("urutan yang tadinya berurutan tetap tidak tumpang tindih", not broken, broken[:3])
    warn = g(pm, f"/build/templates/{tpl_id}").json().get("warnings")
    check("template tidak memunculkan peringatan baru", not warn, warn)
    return {"template_id": tpl_id, "step_code": target, "calibration": cal,
            "before_steps": before_steps, "client_ref": ref, "preview": prev}


def audit_new_schedule_uses_it(pm, ctx):
    head("E+F. Jadwal BARU memakai angka baru & tetap patuh kalender (INV-37-3, INV-37-10)")
    tpl_id, code = ctx["template_id"], ctx["step_code"]
    after = steps_of(pm, tpl_id)[code]
    want = after["day_to"] - after["day_from"] + 1
    tpl = g(pm, f"/build/templates/{tpl_id}").json()["data"]
    types = tpl.get("unit_types") or []
    scheduled = set(mdb.build_schedules.distinct("unit_id"))
    unit = mdb.units.find_one({"type": {"$in": types}, "id": {"$nin": list(scheduled)}},
                              {"_id": 0, "id": 1, "code": 1, "project_id": 1})
    if not check("ada rumah belum terjadwal untuk diuji", bool(unit)):
        return
    start = (date.today() + timedelta(days=3)).isoformat()
    cr = po(pm, "/build/schedules", {"unit_id": unit["id"], "start_date": start,
                                     "template_id": tpl_id})
    if not check("jadwal baru dibuat 200", cr.status_code == 200, cr.text[:200]):
        return
    sid = (cr.json().get("data") or {}).get("id")
    rows = list(mdb.build_items.find({"schedule_id": sid},
                                     {"_id": 0, "step_code": 1, "day_from": 1, "day_to": 1,
                                      "planned_start": 1, "planned_finish": 1}))
    it = next((x for x in rows if x["step_code"] == code), None)
    check("INV-37-3 langkah yang dikalibrasi memakai durasi BARU pada jadwal baru",
          bool(it) and (it["day_to"] - it["day_from"] + 1) == want,
          it and {"day_from": it["day_from"], "day_to": it["day_to"], "harus": want})
    cal = g(pm, "/build/calendar/settings").json()["data"]
    holidays = {h["date"] for h in cal["holidays"]}
    offs = {i for i, k in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))
            if cal["pattern"][k] == "off"}
    bad = [(x["step_code"], x["planned_finish"]) for x in rows
           if x["planned_finish"] in holidays
           or date.fromisoformat(x["planned_finish"]).weekday() in offs]
    check("INV-37-10 tidak ada tanggal rencana jadwal baru yang mendarat di hari libur",
          not bad, bad[:4])
    dl = de(pm, f"/build/schedules/{sid}")
    check("jadwal uji dibersihkan kembali", dl.status_code == 200, dl.text[:140])


def audit_guards(pm, ctx):
    head("G. Penjaga & idempotensi (INV-37-4)")
    tpl_id, code = ctx["template_id"], ctx["step_code"]
    cases = [
        ({"template_id": tpl_id, "step_code": code, "kind": "step_duration",
          "delta_days": 1}, "tanpa alasan & catatan"),
        ({"template_id": tpl_id, "step_code": code, "kind": "step_duration", "delta_days": 1,
          "cause": "data_telat", "note": "pendek"}, "catatan <10 karakter"),
        ({"template_id": tpl_id, "step_code": code, "kind": "step_duration", "delta_days": 1,
          "cause": "alasan_ngawur", "note": "alasan di luar kamus data"},
         "alasan di luar SSOT"),
        ({"template_id": tpl_id, "step_code": code, "kind": "kira_kira", "delta_days": 1,
          "cause": "data_telat", "note": "jenis kalibrasi tidak dikenal"},
         "jenis kalibrasi tidak dikenal"),
        ({"template_id": tpl_id, "step_code": "TIDAK-ADA", "kind": "step_duration",
          "delta_days": 1, "cause": "data_telat", "note": "langkah tidak ada di template"},
         "langkah tidak ada"),
        ({"template_id": tpl_id, "step_code": code, "kind": "step_duration", "delta_days": 0,
          "cause": "data_telat", "note": "tidak ada perubahan sama sekali"},
         "perubahan 0 hari"),
        ({"template_id": tpl_id, "step_code": code, "kind": "step_duration",
          "delta_days": -50, "cause": "data_telat",
          "note": "durasi dipaksa jadi negatif untuk uji"}, "durasi jadi < 1 hari"),
    ]
    for body, label in cases:
        r = po(pm, "/build/calibration/apply", body)
        check(f"apply DITOLAK 400 — {label}", r.status_code == 400, r.text[:150])
    rep = po(pm, "/build/calibration/apply",
             {"template_id": tpl_id, "step_code": code, "kind": "step_duration",
              "delta_days": 2, "cause": "data_telat", "client_ref": ctx["client_ref"],
              "note": "Uji POC 37: pengiriman ulang dengan penanda sama"})
    check("client_ref sama diputar ulang (bukan kalibrasi kedua)",
          rep.status_code == 200 and rep.json().get("replayed") is True, rep.text[:160])
    check("hanya ada SATU catatan kalibrasi untuk penanda itu",
          mdb.build_calibrations.count_documents({"client_ref": ctx["client_ref"]}) == 1)
    after = steps_of(pm, tpl_id)[code]
    check("template tidak berubah dua kali oleh pengiriman ulang",
          after["day_to"] == ctx["calibration"]["rows"][0]["after"]["day_to"],
          (after["day_to"], ctx["calibration"]["rows"][0]["after"]["day_to"]))


def audit_applied_flag_and_rollback(pm, ctx):
    head("L. Rekomendasi ditandai 'sudah diterapkan' (INV-37-9)")
    tpl_id, code = ctx["template_id"], ctx["step_code"]
    d = g(pm, "/build/calibration/candidates").json()["data"]
    row = next((t for s in d["steps"] if s["step_code"] == code
                for t in s["targets"] if t["template_id"] == tpl_id), None)
    check("langkah yang baru dikalibrasi ditandai sudah diterapkan pada tabel telat",
          bool(row) and bool(row.get("applied")), row and row.get("applied"))
    tstep = next((s for t in d["templates"] if t["id"] == tpl_id
                  for s in t["steps"] if s["code"] == code), None)
    check("daftar langkah template membawa angka yang berlaku sekarang + tanda kalibrasi",
          bool(tstep) and bool(tstep.get("applied"))
          and tstep["day_to"] == ctx["calibration"]["rows"][0]["after"]["day_to"],
          tstep and {"day_to": tstep["day_to"], "applied": tstep.get("applied")})
    check("setiap template bisa dikalibrasi dari satu layar (langkah lengkap ikut dibawa)",
          all(t.get("steps") and t.get("total_days") for t in d["templates"]),
          [(t["code"], t.get("steps_count"), t.get("total_days")) for t in d["templates"]])
    hist = g(pm, "/build/calibration/history", template_id=tpl_id).json()["data"]
    check("riwayat kalibrasi memuat sebelum→sesudah, pelaku, dan alasan",
          bool(hist) and all(k in hist[0] for k in ("rows", "actor", "cause", "note",
                                                    "explain")), hist[0].keys())

    head("I. Rollback tepat & tidak bisa dipakai dua kali (INV-37-6)")
    cid = ctx["calibration"]["id"]
    short = po(pm, f"/build/calibration/{cid}/rollback", {"note": "batal"})
    check("rollback tanpa catatan layak DITOLAK 400", short.status_code == 400, short.text[:140])
    # kalibrasi KEDUA di atasnya → rollback yang lama harus ditolak dengan jujur
    later = po(pm, "/build/calibration/apply",
               {"template_id": tpl_id, "step_code": code, "kind": "step_duration",
                "delta_days": 1, "cause": "cuaca_musiman",
                "note": "Uji POC 37: kalibrasi kedua di atas kalibrasi pertama"})
    check("kalibrasi kedua diterapkan", later.status_code == 200, later.text[:160])
    stale = po(pm, f"/build/calibration/{cid}/rollback",
               {"note": "Uji POC 37: mencoba mengembalikan kalibrasi yang sudah tertimpa"})
    check("rollback kalibrasi lama DITOLAK karena template sudah berubah",
          stale.status_code == 400 and "berubah" in stale.text, stale.text[:200])
    cid2 = later.json()["data"]["id"]
    rb2 = po(pm, f"/build/calibration/{cid2}/rollback",
             {"note": "Uji POC 37: kembalikan kalibrasi kedua lebih dulu"})
    check("kalibrasi terbaru bisa dikembalikan", rb2.status_code == 200, rb2.text[:160])
    rb1 = po(pm, f"/build/calibration/{cid}/rollback",
             {"note": "Uji POC 37: kembalikan kalibrasi pertama setelah yang kedua"})
    check("kalibrasi pertama bisa dikembalikan setelahnya", rb1.status_code == 200,
          rb1.text[:160])
    again = po(pm, f"/build/calibration/{cid}/rollback",
               {"note": "Uji POC 37: mengembalikan dua kali harus ditolak"})
    check("rollback dua kali DITOLAK 400", again.status_code == 400, again.text[:150])
    rev_id = rb1.json()["data"]["id"]
    revrev = po(pm, f"/build/calibration/{rev_id}/rollback",
                {"note": "Uji POC 37: membatalkan baris pembatalan harus ditolak"})
    check("baris pembatalan tidak bisa dibatalkan lagi", revrev.status_code == 400,
          revrev.text[:150])

    now_steps = steps_of(pm, tpl_id)
    diff = [c for c in ctx["before_steps"]
            if (now_steps[c]["day_from"], now_steps[c]["day_to"],
                int(now_steps[c].get("wait_days") or 0), int(now_steps[c]["week"]))
            != (ctx["before_steps"][c]["day_from"], ctx["before_steps"][c]["day_to"],
                int(ctx["before_steps"][c].get("wait_days") or 0),
                int(ctx["before_steps"][c]["week"]))]
    check("INV-37-6 template kembali TEPAT seperti sebelum kalibrasi", not diff, diff[:5])
    d2 = g(pm, "/build/calibration/candidates").json()["data"]
    row2 = next((t for s in d2["steps"] if s["step_code"] == code
                 for t in s["targets"] if t["template_id"] == tpl_id), None)
    check("tanda 'sudah diterapkan' HILANG setelah dibatalkan",
          bool(row2) and not row2.get("applied"), row2 and row2.get("applied"))
    tstep2 = next((s for t in d2["templates"] if t["id"] == tpl_id
                   for s in t["steps"] if s["code"] == code), None)
    check("tanda kalibrasi pada daftar langkah template juga HILANG setelah dibatalkan",
          bool(tstep2) and not tstep2.get("applied"), tstep2 and tstep2.get("applied"))

    head("K. Jejak audit (INV-37-8)")
    check("audit_logs memuat calibration_apply beserta pelakunya",
          bool(mdb.audit_logs.find_one({"action": "calibration_apply",
                                        "actor": "pm@sipro.co.id"})))
    check("audit_logs memuat calibration_rollback",
          bool(mdb.audit_logs.find_one({"action": "calibration_rollback"})))


def audit_wait_kinds(pm, cands):
    head("M. Waktu tunggu: jujur soal apa yang berubah dan apa yang tidak")
    tpl_id = cands["templates"][0]["id"]
    steps = steps_of(pm, tpl_id)
    code = next((c for c, s in sorted(steps.items(), key=lambda kv: kv[1]["day_from"])
                 if int(s.get("wait_days") or 0) > 0), None)
    if not check("ada langkah dengan waktu tunggu wajib untuk diuji", bool(code)):
        return
    before = steps[code]
    pv = po(pm, "/build/calibration/preview",
            {"template_id": tpl_id, "step_code": code, "kind": "wait_time", "delta_days": 1})
    check("pratinjau wait_time 200", pv.status_code == 200, pv.text[:160])
    p = pv.json()["data"]
    check("wait_time TIDAK menggeser tanggal rencana (dan mengatakannya)",
          p["moves_planned_dates"] is False
          and "TANGGAL RENCANA tidak berubah" in p["explain"], p["explain"][:150])
    ap = po(pm, "/build/calibration/apply",
            {"template_id": tpl_id, "step_code": code, "kind": "wait_time", "delta_days": 1,
             "cause": "metode_berubah",
             "note": "Uji POC 37: waktu tunggu dinaikkan satu hari"})
    check("wait_time diterapkan 200", ap.status_code == 200, ap.text[:160])
    now = steps_of(pm, tpl_id)[code]
    check("hanya waktu tunggu yang berubah, tanggal langkah tetap",
          int(now.get("wait_days") or 0) == int(before.get("wait_days") or 0) + 1
          and now["day_from"] == before["day_from"] and now["day_to"] == before["day_to"],
          {"wait": now.get("wait_days"), "day": (now["day_from"], now["day_to"])})
    rb = po(pm, f"/build/calibration/{ap.json()['data']['id']}/rollback",
            {"note": "Uji POC 37: kembalikan waktu tunggu ke nilai semula"})
    check("wait_time bisa dikembalikan", rb.status_code == 200, rb.text[:140])

    # ---- wait_into_plan: memasukkan waktu tunggu ke rencana
    pv2 = po(pm, "/build/calibration/preview",
             {"template_id": tpl_id, "step_code": code, "kind": "wait_into_plan"})
    if pv2.status_code == 400:
        check("wait_into_plan menolak dengan jujur bila rencana sudah cukup memberi jeda",
              "sudah" in pv2.text, pv2.text[:200])
        return
    p2 = pv2.json()["data"]
    check("wait_into_plan menggeser langkah sebanyak kekurangan jeda saja",
          p2["shift_days"] > 0 and p2["moves_planned_dates"] is True, p2["shift_days"])
    check("wait_into_plan menegaskan waktu tunggu TIDAK dipersingkat",
          "tidak dipersingkat" in p2["explain"], p2["explain"][:170])
    ap2 = po(pm, "/build/calibration/apply",
             {"template_id": tpl_id, "step_code": code, "kind": "wait_into_plan",
              "cause": "waktu_tunggu_fisik",
              "note": "Uji POC 37: waktu tunggu curing dimasukkan ke tanggal rencana"})
    check("wait_into_plan diterapkan 200", ap2.status_code == 200, ap2.text[:160])
    after = steps_of(pm, tpl_id)[code]
    check("langkah benar-benar bergeser sesuai pratinjau",
          after["day_from"] == before["day_from"] + p2["shift_days"], after["day_from"])
    twice = po(pm, "/build/calibration/preview",
               {"template_id": tpl_id, "step_code": code, "kind": "wait_into_plan"})
    check("kalibrasi yang sama kedua kali ditolak jujur (jeda sudah cukup)",
          twice.status_code == 400 and "sudah" in twice.text, twice.text[:200])
    rb2 = po(pm, f"/build/calibration/{ap2.json()['data']['id']}/rollback",
             {"note": "Uji POC 37: kembalikan pergeseran waktu tunggu ke rencana"})
    check("wait_into_plan bisa dikembalikan", rb2.status_code == 200, rb2.text[:140])
    fin = steps_of(pm, tpl_id)[code]
    check("template bersih kembali setelah semua uji waktu tunggu",
          (fin["day_from"], fin["day_to"], int(fin.get("wait_days") or 0))
          == (before["day_from"], before["day_to"], int(before.get("wait_days") or 0)),
          (fin["day_from"], fin["day_to"], fin.get("wait_days")))


def main():
    print("=" * 66)
    print("POC FASE 37 — KALIBRASI SEKALI KLIK (API NYATA)")
    print("=" * 66)
    pm = login("pm@sipro.co.id")
    site = login("site@sipro.co.id")
    sales = login("sales@sipro.co.id")
    cands = audit_ssot_and_candidates(pm, site, sales)
    ctx = audit_preview_equals_apply(pm, cands)
    if ctx:
        audit_new_schedule_uses_it(pm, ctx)
        audit_guards(pm, ctx)
        audit_applied_flag_and_rollback(pm, ctx)
    audit_wait_kinds(pm, cands)
    print("\n" + "=" * 66)
    print(f"HASIL POC 37: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print("  FAIL:", f)
        sys.exit(1)
    print("SEMUA INVARIAN FASE 37 TERBUKTI LEWAT API NYATA")


if __name__ == "__main__":
    main()
