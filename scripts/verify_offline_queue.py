#!/usr/bin/env python3
"""verify_offline_queue.py — GATE 40 (Fase 50B).

Menjaga janji "pekerjaan lapangan tidak hilang DAN tidak dobel" tetap benar di server:

  Q1  Absensi harian yang dikirim ULANG dengan `client_ref` yang sama hanya tercatat SEKALI
      (absensi ganda = upah ganda), dan kiriman kedua dijawab jujur `replay`.
  Q2  Buku harian proyek: kiriman ulang tidak melahirkan catatan kedua.
  Q3  Temuan punch list: kiriman ulang tidak melahirkan temuan (dan tugas) kembar.
  Q4  Perubahan status punch + foto bukti: kiriman ulang tidak melampirkan bukti dua kali.
  Q5  Kiriman yang DITOLAK server melepas kunci penanda, sehingga pemakai bisa memperbaiki
      lalu mengirim ulang dengan penanda yang sama (tidak ada kehilangan senyap).
  Q6  Kunci idempotensi tercatat di server per (organisasi, jenis, penanda) — dan dijaga
      indeks unik, bukan hanya pemeriksaan aplikasi.
  Q7  Jenis antrean baru terdaftar di kamus data `offline_queue_kind` (layar tidak menulis
      label sendiri).
  Q8  Klaim garansi & bukti perbaikan garansi juga aman diputar ulang (jalur Fase 50A yang
      dikerjakan di lokasi).

Seluruh bahan uji dibuat sendiri (bertanda `gate50`) lalu dibuang bersih.
"""
import pathlib
import sys

from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture50 as fx  # noqa: E402

FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = ""):
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return ok


def body(resp) -> dict:
    try:
        return resp.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def detail_of(resp) -> str:
    try:
        return str(resp.json().get("detail") or "")[:250]
    except Exception:  # noqa: BLE001
        return resp.text[:200]


def attendance_checks(site, project, worker):
    day = fx.today()
    ref = f"{fx.TAG}-q40-absensi"
    payload = {"project_id": project["id"], "work_date": day, "client_ref": ref,
               "entries": [{"worker_id": worker["id"], "status": "full",
                            "overtime_hours": 1}]}
    first = fx.api("POST", "/labor/attendance", site, json=payload)
    second = fx.api("POST", "/labor/attendance", site, json=payload)
    rows = fx.db.labor_attendance.count_documents(
        {"project_id": project["id"], "work_date": day, "worker_id": worker["id"]})
    check(first.status_code == 200 and second.status_code == 200 and rows == 1,
          "Q1a absensi dikirim dua kali hanya tercatat SEKALI", f"{rows} baris")
    check(second.json().get("replay") is True,
          "Q1b kiriman ulang dijawab jujur sebagai pemutaran ulang",
          str(second.json().get("message"))[:90])

    bad_ref = f"{fx.TAG}-q40-absensi-tolak"
    bad = fx.api("POST", "/labor/attendance", site, json={
        "project_id": project["id"], "work_date": day, "client_ref": bad_ref,
        "entries": [{"worker_id": "tidak-ada", "status": "full"}]})
    retry = fx.api("POST", "/labor/attendance", site, json={
        "project_id": project["id"], "work_date": fx.days_ago(1), "client_ref": bad_ref,
        "entries": [{"worker_id": worker["id"], "status": "half"}]})
    check(bad.status_code == 400 and retry.status_code == 200
          and retry.json().get("replay") is not True,
          "Q5 kiriman yang DITOLAK melepas kunci: bisa diperbaiki lalu dikirim ulang",
          f"tolak={detail_of(bad)[:60]} | ulang={retry.status_code}")


def diary_punch_checks(site, project, unit):
    dref = f"{fx.TAG}-q40-diary"
    dpay = {"project_id": project["id"], "log_date": fx.today(), "weather": "cerah",
            "workforce": 3, "work_description": "Uji antrean gate 40", "client_ref": dref}
    d1 = fx.api("POST", "/field/diary", site, json=dpay)
    d2 = fx.api("POST", "/field/diary", site, json=dpay)
    cnt = fx.db.site_diaries.count_documents({"project_id": project["id"]})
    check(d1.status_code == 200 and d2.json().get("replay") is True and cnt == 1,
          "Q2 buku harian: kiriman ulang tidak melahirkan catatan kedua", f"{cnt} catatan")

    pref = f"{fx.TAG}-q40-punch"
    ppay = {"project_id": project["id"], "unit_id": unit["id"], "severity": "medium",
            "title": "Nat keramik retak (uji gate 40)", "client_ref": pref}
    p1 = fx.api("POST", "/field/punchlist", site, json=ppay)
    p2 = fx.api("POST", "/field/punchlist", site, json=ppay)
    pid = body(p1).get("id")
    cnt = fx.db.punch_items.count_documents({"unit_id": unit["id"], "title": ppay["title"]})
    tasks = fx.db.tasks.count_documents({"related_entity_type": "punch_item",
                                         "related_entity_id": pid})
    check(p1.status_code == 200 and p2.json().get("replay") is True and cnt == 1 and tasks <= 1,
          "Q3 temuan punch: kiriman ulang tidak melahirkan temuan & tugas kembar",
          f"{cnt} temuan, {tasks} tugas")

    photo = fx.upload_photo(site)
    sref = f"{fx.TAG}-q40-punchstatus"
    spay = {"status": "closed", "note": "Nat diisi ulang.", "photos": [photo],
            "client_ref": sref}
    s1 = fx.api("POST", f"/field/punchlist/{pid}/status", site, json=spay)
    s2 = fx.api("POST", f"/field/punchlist/{pid}/status", site, json=spay)
    after = fx.db.punch_items.find_one({"id": pid}, {"_id": 0, "fix_photos": 1, "status": 1})
    check(s1.status_code == 200 and s2.json().get("replay") is True
          and len(after.get("fix_photos") or []) == 1,
          "Q4 bukti perbaikan tidak terlampir dua kali walau kiriman diulang",
          f"{len(after.get('fix_photos') or [])} foto")


def warranty_queue_checks(fin, pm, site, ready):
    unit = ready["unit"]
    ref = f"{fx.TAG}-q40-bast"
    p = {"unit_id": unit["id"], "client_ref": ref, "received_by": "Penerima gate 40"}
    a = fx.api("POST", "/handover/issue", fin, json=p)
    b = fx.api("POST", "/handover/issue", fin, json=p)
    check(a.status_code == 200 and body(b).get("number") == body(a).get("number"),
          "Q8a penerbitan BAST dari antrean aman diputar ulang", str(body(a).get("number")))

    cref = f"{fx.TAG}-q40-klaim"
    cp = {"unit_id": unit["id"], "category": "listrik", "source": "internal",
          "title": "Lampu teras mati (uji antrean)", "client_ref": cref}
    c1 = fx.api("POST", "/handover/claims", pm, json=cp)
    c2 = fx.api("POST", "/handover/claims", pm, json=cp)
    cnt = fx.db.warranty_claims.count_documents({"unit_id": unit["id"],
                                                 "title": cp["title"]})
    check(c1.status_code == 200 and c2.json().get("replay") is True and cnt == 1,
          "Q8b klaim garansi dari antrean tidak menjadi klaim kembar", f"{cnt} klaim")

    claim = body(c1)
    fx.api("POST", f"/handover/claims/{claim['id']}/decide", pm, json={
        "accept": True, "assigned_to": "site@sipro.co.id",
        "reason": "Diperiksa tukang listrik pekan ini."})
    photo = fx.upload_photo(site)
    fref = f"{fx.TAG}-q40-fix"
    fp = {"photo_file_ids": [photo], "note": "Ganti fitting.", "client_ref": fref}
    f1 = fx.api("POST", f"/handover/claims/{claim['id']}/complete", site, json=fp)
    f2 = fx.api("POST", f"/handover/claims/{claim['id']}/complete", site, json=fp)
    doc = fx.db.warranty_claims.find_one({"id": claim["id"]}, {"_id": 0, "fix_photos": 1})
    check(f1.status_code == 200 and f2.json().get("replay") is True
          and len(doc.get("fix_photos") or []) == 1,
          "Q8c bukti perbaikan garansi tidak dobel walau kiriman diulang",
          f"{len(doc.get('fix_photos') or [])} foto")


def store_checks(pm):
    rows = list(fx.db.offline_intake.find({"client_ref": {"$regex": f"^{fx.TAG}-q40"}},
                                          {"_id": 0}))
    check(len(rows) >= 6 and all(r.get("state") in ("done", "processing") for r in rows),
          "Q6a setiap penanda antrean tercatat di server", f"{len(rows)} penanda")
    idx = fx.db.offline_intake.index_information()
    want = [("org_id", 1), ("kind", 1), ("client_ref", 1)]
    guarded = [n for n, spec in idx.items()
               if spec.get("unique")
               and [(k, v) for k, v in spec.get("key", [])] == want]
    check(bool(guarded),
          "Q6b keunikan penanda dijaga INDEKS UNIK (organisasi+jenis+penanda)",
          str(guarded or sorted(idx)))
    # Buktikan indeksnya benar-benar BERGIGI: sisipan kembar langsung dari luar aplikasi
    # (jalur yang tidak pernah lewat pemeriksaan Python) harus DITOLAK database.
    twin = {"org_id": fx.ORG, "kind": "attendance_submit",
            "client_ref": f"{fx.TAG}-q40-kembar", "state": "processing"}
    fx.db.offline_intake.delete_many({"client_ref": twin["client_ref"]})
    bitten = False
    try:
        fx.db.offline_intake.insert_one(dict(twin))
        fx.db.offline_intake.insert_one(dict(twin))
    except DuplicateKeyError:
        bitten = True
    finally:
        fx.db.offline_intake.delete_many({"client_ref": twin["client_ref"]})
    check(bitten, "Q6c database MENOLAK penanda kembar (bukan hanya aplikasi)",
          "sisipan kedua lolos — index tidak berlaku")
    reg = fx.api("GET", "/reference", pm).json().get("data") or {}
    kinds = {o["value"] for o in (reg.get("offline_queue_kind") or {}).get("options", [])}
    need = {"attendance_submit", "field_diary", "punch_create", "punch_status",
            "warranty_claim", "warranty_fix"}
    check(need <= kinds, "Q7 jenis antrean baru terdaftar di kamus data",
          f"{len(kinds)} jenis" if need <= kinds else f"belum ada {sorted(need - kinds)}")


def main():
    print("=" * 78)
    print("GATE 40 — ANTREAN PERANGKAT TERPADU: TIDAK HILANG & TIDAK DOBEL (Fase 50B)")
    print("=" * 78)
    fin = fx.login("finance@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")
    site = fx.login("site@sipro.co.id")

    project = fx.make_project("Proyek Gate 40", "GATE40")
    worker = fx.make_worker(project, "Tukang Gate 40")
    ready = fx.ready_unit(project, "G40-SIAP", "Pembeli Gate 40")
    try:
        attendance_checks(site, project, worker)
        diary_punch_checks(site, project, ready["unit"])
        warranty_queue_checks(fin, pm, site, ready)
        store_checks(pm)
    finally:
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 40 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 40 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
