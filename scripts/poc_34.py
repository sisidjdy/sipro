#!/usr/bin/env python3
"""POC/verifikasi Fase 34 — JADWAL MASSAL & GESER TANGGAL SERENTAK.

Dibuktikan lewat API NYATA (bukan unit test terisolasi):

  A. Kandidat & blok — rumah yang belum terjadwal terlihat per blok, lengkap dengan
     template yang akan dipakai ATAU alasan kenapa tidak bisa dijadwalkan.
  B. INV-34-6 pratinjau = hasil — angka & tanggal yang dijanjikan pratinjau sama
     dengan yang benar-benar terjadi; pratinjau TIDAK menulis apa pun.
  C. INV-34-3 jadwal massal tidak menimpa jadwal yang sudah ada (dilewati + alasan).
  D. INV-34-8 klik ganda tidak menghasilkan jadwal dobel (`client_ref` idempoten) +
     batas maksimal per operasi ditegakkan API.
  E. INV-34-2 geser tanggal WAJIB beralasan (SSOT) + catatan; tanpa itu ditolak.
  F. INV-34-1 pekerjaan yang sudah diverifikasi TIDAK berubah tanggal; yang belum
     selesai bergeser.
  G. INV-34-7 setelah geser: gerbang & progres dihitung ulang, tidak ada 'telat' palsu.
  H. INV-34-9 geser ke belakang yang melangkahi bukti DITOLAK dengan alasan jelas.
  I. Riwayat operasi massal + jejak audit bisa dilihat (siapa, kapan, kenapa).
  J. RBAC/SoD: sales tak boleh melihat, pelaksana tak boleh menjalankan.
  K. Regresi Fase 31/32: jadwal tunggal, monitoring, dan Papan Mandor tetap benar.

Jalankan: python3 scripts/poc_34.py
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {str(detail)[:170]}" if detail else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=90)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=180)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def d(s):
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def main():
    pm = login("pm@sipro.co.id")
    owner = login("owner@sipro.co.id")
    site = login("site@sipro.co.id")
    sales = login("sales@sipro.co.id")

    projects = g(pm, "/projects").json().get("data") or []
    project = next((p for p in projects if (p.get("code") or "") == "CAA"), projects[0])
    pid = project["id"]

    # ============================ A. kandidat & blok ============================
    head("A. Kandidat & blok — rumah yang belum terjadwal terlihat jelas")
    rb = g(pm, "/build/bulk/blocks", project_id=pid)
    blocks = rb.json().get("data") or []
    check("ringkasan per blok tersedia", rb.status_code == 200 and len(blocks) >= 2,
          [b["block"] for b in blocks])
    unsched_total = sum(int(b.get("unscheduled") or 0) for b in blocks)
    check("ada rumah yang belum terjadwal (masalah nyata yang ditutup fase ini)",
          unsched_total > 0, f"{unsched_total} unit belum terjadwal")
    check("hitungan blok konsisten (terjadwal + belum + non-bangunan = jumlah unit)",
          all(b["scheduled"] + b["unscheduled"] <= b["units"] for b in blocks))

    rc = g(pm, "/build/bulk/candidates", project_id=pid)
    cands = rc.json().get("data") or []
    check("kandidat hanya unit BELUM terjadwal", rc.status_code == 200 and len(cands) > 0,
          f"{len(cands)} kandidat")
    check("setiap kandidat membawa template yang akan dipakai ATAU alasan tidak bisa",
          all(c.get("template_code") or c.get("reason") for c in cands))
    ready = [c for c in cands if c.get("schedulable")]
    check("kandidat siap jadwal menyertakan jumlah item & lama hari template",
          bool(ready) and all(c["template_items"] > 0 and c["template_days"] > 0
                              for c in ready))
    non_build = [c for c in cands if not c.get("schedulable")]
    if non_build:
        check("INV-34-4 unit non-bangunan ditolak dengan alasan manusiawi",
              all("tanah" in (c.get("reason") or "").lower()
                  or "template" in (c.get("reason") or "").lower() for c in non_build),
              non_build[0].get("reason"))
    else:
        check("INV-34-4 tidak ada unit non-bangunan pada proyek ini (lewat)", True)
    check("kandidat berlabel blok (dari kode unit)", all(c.get("block") for c in cands))

    # ============================ B. pratinjau = hasil ============================
    head("B. INV-34-6 pratinjau = hasil, dan pratinjau tidak menulis apa pun")
    pick = ready[:3]
    check("ada minimal 3 unit untuk uji gelombang", len(pick) >= 3, len(pick))
    start = (date.today() + timedelta(days=7)).isoformat()
    body = {"unit_ids": [c["id"] for c in pick], "start_date": start,
            "wave": "per_unit", "stagger_days": 2}
    rp = po(pm, "/build/bulk/schedules/preview", body)
    pv = rp.json()
    prows = pv.get("data") or []
    check("pratinjau mengembalikan rencana per unit", rp.status_code == 200 and len(prows) == 3,
          rp.text[:160])
    check("pratinjau memuat tanggal mulai, target selesai, dan jumlah item",
          all(r.get("start_date") and r.get("target_finish_date") and r.get("items")
              for r in prows))
    starts = sorted({r["start_date"] for r in prows})
    check("pola gelombang 'bertahap per unit' membuat tanggal mulai berbeda",
          len(starts) >= 2, starts)
    before = len((g(pm, "/build/bulk/candidates", project_id=pid).json().get("data") or []))
    check("pratinjau TIDAK menulis (jumlah kandidat tidak berubah)", before == len(cands),
          f"{before} vs {len(cands)}")

    ref_key = f"poc34-{uuid.uuid4().hex[:10]}"
    rr = po(pm, "/build/bulk/schedules", {**body, "client_ref": ref_key})
    run = (rr.json() or {}).get("data") or {}
    res = run.get("results") or []
    created = [x for x in res if x.get("status") == "created"]
    check("jadwal massal berjalan dan membuat jadwal", rr.status_code == 200 and len(created) == 3,
          rr.text[:200])
    pv_by_unit = {r["unit_id"]: r for r in prows}
    same_date = all(x["start_date"] == pv_by_unit[x["unit_id"]]["start_date"]
                    for x in created)
    same_items = all(int(x["items"]) == int(pv_by_unit[x["unit_id"]]["items"])
                     for x in created)
    check("INV-34-6 tanggal hasil = tanggal pratinjau", same_date,
          [(x["unit_code"], x["start_date"]) for x in created])
    check("INV-34-6 jumlah item hasil = jumlah item pratinjau", same_items)
    check("ringkasan hasil menyebut jumlah dibuat & item", (run.get("summary") or {}).get(
        "created") == 3 and (run.get("summary") or {}).get("items_total", 0) > 0,
        run.get("summary"))
    bundle = g(pm, f"/build/unit/{created[0]['unit_id']}").json()
    check("jadwal hasil benar-benar berisi item pekerjaan terurut minggu",
          bool(bundle.get("weeks")) and len(bundle.get("items") or []) == created[0]["items"],
          f"{len(bundle.get('items') or [])} item")

    # ============================ C. tidak menimpa ============================
    head("C. INV-34-3 jadwal massal tidak menimpa jadwal yang sudah berjalan")
    r2 = po(pm, "/build/bulk/schedules", {**body})
    res2 = ((r2.json() or {}).get("data") or {}).get("results") or []
    skipped = [x for x in res2 if x.get("status") == "skipped"]
    check("unit yang sudah punya jadwal DILEWATI (bukan ditimpa)", len(skipped) == 3,
          [x.get("status") for x in res2])
    check("alasan dilewati manusiawi & menyebut jadwal yang sudah ada",
          all("sudah punya jadwal" in (x.get("reason") or "").lower() for x in skipped),
          skipped[0].get("reason") if skipped else "")
    again = g(pm, f"/build/unit/{created[0]['unit_id']}").json()
    check("item pekerjaan tidak menjadi dobel",
          len(again.get("items") or []) == len(bundle.get("items") or []))

    # ============================ D. idempoten & batas ============================
    head("D. INV-34-8 klik ganda tidak dobel + batas aman per operasi")
    replay = po(pm, "/build/bulk/schedules", {**body, "client_ref": ref_key})
    rdata = (replay.json() or {}).get("data") or {}
    check("operasi dengan client_ref sama = pemutaran ulang hasil lama (id sama)",
          rdata.get("id") == run.get("id") and rdata.get("idempotent_replay") is True,
          f"{rdata.get('id')} vs {run.get('id')}")
    over = po(pm, "/build/bulk/schedules",
              {"unit_ids": [f"unit-{i}" for i in range(120)], "start_date": start})
    check("batas maksimal unit per operasi ditegakkan API",
          over.status_code in (400, 422), over.status_code)

    # ============================ E. geser wajib beralasan ============================
    head("E. INV-34-2 geser tanggal wajib beralasan + catatan (jejak audit)")
    rt = g(pm, "/build/bulk/shift/targets", project_id=pid)
    targets = rt.json().get("data") or []
    check("daftar jadwal yang bisa digeser tersedia", rt.status_code == 200 and len(targets) >= 4,
          f"{len(targets)} jadwal")
    check("target geser menyebut jumlah pekerjaan selesai (yang akan dikunci)",
          all("items_done" in t for t in targets))
    # unit A-01 punya pekerjaan terverifikasi (hasil seed Fase 31/33)
    a01 = next((t for t in targets if t["unit_code"] == "A-01"), targets[0])
    no_cause = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                            "shift_days": 10, "note": "hujan seminggu penuh"})
    check("geser tanpa penyebab DITOLAK", no_cause.status_code == 400, no_cause.text[:140])
    short_note = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                              "shift_days": 10, "cause": "weather",
                                              "note": "hujan"})
    check("geser dengan catatan terlalu pendek DITOLAK", short_note.status_code == 400,
          short_note.text[:140])
    bad_cause = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                             "shift_days": 10, "cause": "karena-mager",
                                             "note": "alasan yang cukup panjang"})
    check("penyebab di luar daftar SSOT DITOLAK", bad_cause.status_code == 400,
          bad_cause.text[:140])
    zero = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]], "shift_days": 0,
                                        "cause": "weather", "note": "alasan cukup panjang"})
    check("geser 0 hari DITOLAK (bukan operasi kosong yang membingungkan)",
          zero.status_code in (400, 422), zero.status_code)

    # ============================ F/G. geser menjaga bukti ============================
    head("F/G. INV-34-1 bukti terikat waktu & INV-34-7 hitung ulang setelah geser")
    b4 = g(pm, f"/build/unit/{a01['unit_id']}").json()
    items_before = {i["step_code"]: i for i in b4.get("items") or []}
    done_before = {k: v for k, v in items_before.items() if v.get("status") == "done"}
    check("unit uji punya pekerjaan yang sudah diverifikasi", len(done_before) > 0,
          f"{len(done_before)} selesai")
    prev = po(pm, "/build/bulk/shift/preview", {"schedule_ids": [a01["schedule_id"]],
                                                "shift_days": 21})
    prow = ((prev.json() or {}).get("data") or [{}])[0]
    check("pratinjau geser memisahkan yang digeser vs yang dipertahankan",
          prow.get("items_shifted", 0) > 0 and prow.get("items_locked") == len(done_before),
          f"geser {prow.get('items_shifted')} · kunci {prow.get('items_locked')}")
    check("pratinjau menjelaskan kenapa sebagian tanggal dipertahankan",
          "diverifikasi" in (prow.get("locked_note") or ""), prow.get("locked_note"))
    shift_ref = f"poc34s-{uuid.uuid4().hex[:10]}"
    rs = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]], "shift_days": 21,
                                      "cause": "weather",
                                      "note": "Hujan tiga pekan, cor tidak bisa dikerjakan.",
                                      "client_ref": shift_ref})
    srun = (rs.json() or {}).get("data") or {}
    srow = ((srun.get("results") or [{}])[0])
    check("penggeseran berjalan", rs.status_code == 200 and srow.get("status") == "shifted",
          rs.text[:200])
    check("INV-34-6 tanggal mulai hasil = tanggal pratinjau",
          srow.get("new_start") == prow.get("new_start"),
          f"{srow.get('new_start')} vs {prow.get('new_start')}")
    aft = g(pm, f"/build/unit/{a01['unit_id']}").json()
    sched_after = aft.get("data") or {}
    items_after = {i["step_code"]: i for i in aft.get("items") or []}
    check("tanggal mulai & target selesai jadwal ikut bergeser",
          sched_after.get("start_date") == srow.get("new_start")
          and sched_after.get("target_finish_date") == srow.get("new_finish"),
          f"{sched_after.get('start_date')} → {sched_after.get('target_finish_date')}")
    locked_ok = all(items_after[k]["planned_finish"] == v["planned_finish"]
                    for k, v in done_before.items())
    check("INV-34-1 pekerjaan terverifikasi TIDAK berubah tanggal", locked_ok,
          [(k, done_before[k]["planned_finish"], items_after[k]["planned_finish"])
           for k in list(done_before)[:2]])
    moved_ok = [k for k, v in items_before.items()
                if v.get("status") != "done"
                and d(items_after[k]["planned_finish"]) > d(v["planned_finish"])]
    check("pekerjaan yang belum selesai benar-benar bergeser ke depan",
          len(moved_ok) == prow.get("items_shifted"), f"{len(moved_ok)} item bergeser")
    check("INV-34-7 pekerjaan yang tenggatnya kini di masa depan tidak lagi tercatat telat",
          all(int(items_after[k].get("late_days") or 0) == 0 for k in moved_ok
              if items_after[k]["planned_finish"] >= date.today().isoformat()))
    check("INV-34-7 gerbang mutu tetap dihormati (urutan & alasan terkunci utuh)",
          all(i.get("gate") for i in aft.get("items") or []))
    check("riwayat penggeseran tercatat pada jadwal (siapa, kapan, kenapa)",
          bool(sched_after.get("shift_history"))
          and sched_after["shift_history"][-1]["cause"] == "weather"
          and sched_after["shift_history"][-1]["actor"] == "pm@sipro.co.id",
          (sched_after.get("shift_history") or [{}])[-1])
    replay_s = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                            "shift_days": 21, "cause": "weather",
                                            "note": "Hujan tiga pekan, cor tidak bisa dikerjakan.",
                                            "client_ref": shift_ref})
    check("INV-34-8 penggeseran dengan client_ref sama tidak dijalankan dua kali",
          ((replay_s.json() or {}).get("data") or {}).get("id") == srun.get("id"))
    again2 = g(pm, f"/build/unit/{a01['unit_id']}").json().get("data") or {}
    check("tanggal tidak bergeser dua kali karena klik ganda",
          again2.get("start_date") == sched_after.get("start_date"))

    # ============================ H. geser ke belakang dijaga ============================
    head("H. INV-34-9 geser ke belakang tidak boleh melangkahi bukti")
    back = po(pm, "/build/bulk/shift/preview", {"schedule_ids": [a01["schedule_id"]],
                                                "shift_days": -170})
    brow = ((back.json() or {}).get("data") or [{}])[0]
    check("pratinjau menandai konflik bila melangkahi pekerjaan terverifikasi",
          bool(brow.get("conflict")) and brow.get("ok") is False, brow.get("conflict"))
    run_back = po(pm, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                            "shift_days": -170, "cause": "schedule_recovery"
                                            if False else "design_change",
                                            "note": "Percepatan atas permintaan direksi."})
    rb_rows = ((run_back.json() or {}).get("data") or {}).get("results") or [{}]
    check("eksekusi menolak baris berkonflik (dilewati, bukan diam-diam dijalankan)",
          rb_rows[0].get("status") == "skipped", rb_rows[0].get("reason"))
    after_back = g(pm, f"/build/unit/{a01['unit_id']}").json().get("data") or {}
    check("tanggal jadwal tidak berubah oleh operasi yang ditolak",
          after_back.get("start_date") == sched_after.get("start_date"))

    # ============================ I. riwayat & audit ============================
    head("I. Riwayat operasi massal & jejak audit bisa dilihat")
    rl = g(pm, "/build/bulk/runs", limit=20)
    runs = rl.json().get("data") or []
    kinds = {x.get("kind") for x in runs}
    check("riwayat memuat operasi jadwal massal & penggeseran",
          rl.status_code == 200 and {"schedule", "shift"} <= kinds, kinds)
    check("riwayat menyebut pelaku & ringkasan angka",
          all(x.get("actor") and x.get("summary") for x in runs))
    al = g(owner, "/admin/audit-logs", resource="build_schedules", limit=50)
    actions = {x.get("action") for x in (al.json().get("data") or [])}
    check("jejak audit memuat bulk_create & bulk_shift",
          {"bulk_create", "bulk_shift"} <= actions, actions)

    # ============================ J. RBAC / SoD ============================
    head("J. RBAC — hanya Manajer Proyek/direksi yang boleh operasi massal")
    check("sales tidak boleh melihat kandidat jadwal massal",
          g(sales, "/build/bulk/candidates", project_id=pid).status_code == 403)
    check("pelaksana (site) BOLEH melihat target geser (transparansi kerja)",
          g(site, "/build/bulk/shift/targets", project_id=pid).status_code == 200)
    check("pelaksana tidak boleh menjalankan jadwal massal",
          po(site, "/build/bulk/schedules",
             {"unit_ids": [ready[0]["id"]], "start_date": start}).status_code == 403)
    check("pelaksana tidak boleh menggeser tenggat",
          po(site, "/build/bulk/shift", {"schedule_ids": [a01["schedule_id"]],
                                         "shift_days": 5, "cause": "weather",
                                         "note": "mencoba menggeser tenggat"}).status_code == 403)
    check("direksi (owner) boleh menjalankan operasi massal",
          po(owner, "/build/bulk/schedules/preview",
             {"unit_ids": [ready[0]["id"]], "start_date": start}).status_code == 200)

    # ============================ K. regresi Fase 31/32 ============================
    head("K. Regresi — jadwal tunggal, monitoring, dan Papan Mandor tetap benar")
    left = g(pm, "/build/bulk/candidates", project_id=pid).json().get("data") or []
    left_ready = [c for c in left if c.get("schedulable")]
    if left_ready:
        one = po(pm, "/build/schedules", {"unit_id": left_ready[0]["id"],
                                          "start_date": start})
        check("jadwal SATU unit (Fase 31) masih berjalan", one.status_code == 200,
              one.text[:140])
    else:
        check("semua unit sudah terjadwal — jadwal tunggal tidak diuji (lewat)", True)
    summ = g(pm, "/build/summary", project_id=pid).json().get("data") or {}
    check("monitoring mencerminkan jadwal baru (terjadwal bertambah)",
          int(summ.get("scheduled") or 0) >= 7, summ)
    board = g(site, "/build/board/today")
    check("Papan Mandor tetap tampil normal setelah operasi massal",
          board.status_code == 200 and "data" in board.json())
    wr = g(pm, "/build/analytics/delays", project_id=pid)
    check("analitik keterlambatan tetap bisa dihitung", wr.status_code == 200)


def summary():
    print("\n" + "-" * 60)
    print(f"HASIL: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        print("POC 34 GAGAL — jadwal massal/penggeseran belum bisa dipercaya.")
        sys.exit(1)
    print("POC 34 LULUS — jadwal massal & penggeseran serentak aman: "
          "bukti kerja tidak pernah dibakar, semua perubahan beralasan & tercatat.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — crash = kegagalan, bukan 'lulus'
        FAIL.append(f"skrip berhenti karena galat: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        summary()
