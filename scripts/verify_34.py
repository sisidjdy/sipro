#!/usr/bin/env python3
"""verify_34.py — GATE Fase 34: jadwal massal & geser tanggal serentak.

Melengkapi `poc_34.py` (aturan bisnis lewat API) dengan cek yang menahan pembusukan
diam-diam:

  A. Tidak ada endpoint Fase 34 yatim — semua operasi massal HARUS punya jalan masuk
     di frontend (kalau tidak, fitur ini cuma ada di API).
  B. Tidak ada `data-testid` Fase 34 yang mati.
  C. Penjaga tetap terpasang di KODE: bukti terikat waktu, alasan wajib, tidak menimpa
     jadwal berjalan, idempotensi klik ganda, larangan melangkahi bukti, dan RBAC.
  D. Kontrak API: bentuk data blok/kandidat/target-geser/pratinjau sesuai yang dirender
     UI, dan PRATINJAU tidak menulis apa pun.
  E. Invarian data hidup: setiap penggeseran punya alasan+catatan+pelaku, target selesai
     jadwal tidak lebih awal dari item terakhir, dan riwayat operasi konsisten dengan
     hasilnya.

Jalankan: python3 scripts/verify_34.py
"""
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label} {detail}")


def fe_sources() -> str:
    out = []
    for p in FE.rglob("*.js"):
        if "components/ui/" in p.as_posix():
            continue
        out.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(out)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def head(t):
    print(f"\n{t}")


# ---------------------------------------------------------------- A. endpoint dipakai UI
def audit_orphan_endpoints(fe: str):
    head("A. Endpoint Fase 34 punya jalan masuk di frontend")
    pairs = [
        ("/build/bulk/blocks", "ringkasan blok dipakai dialog jadwal massal & geser"),
        ("/build/bulk/candidates", "kandidat rumah belum terjadwal dirender"),
        ("/build/bulk/schedules/preview", "pratinjau jadwal massal dipakai sebelum eksekusi"),
        ("/build/bulk/schedules", "eksekusi jadwal massal terhubung tombol"),
        ("/build/bulk/shift/targets", "daftar jadwal yang bisa digeser dirender"),
        ("/build/bulk/shift/preview", "pratinjau dampak penggeseran dipakai"),
        ("/build/bulk/shift", "eksekusi penggeseran terhubung tombol"),
        ("/build/bulk/runs", "riwayat operasi massal dirender"),
    ]
    for needle, label in pairs:
        check(needle in fe, label, f"-> '{needle}' tidak dipanggil frontend")


# ---------------------------------------------------------------- B. testId hidup
def audit_dead_testids(fe: str):
    head("B. testId Fase 34 tidak ada yang mati")
    src = (FE / "constants" / "testIds" / "build.js").read_text(encoding="utf-8")
    marker = "Fase 34"
    if marker not in src:
        check(False, "blok testId Fase 34 ada di build.js")
        return
    tail = src.split(marker, 1)[1]
    names = [ln.split(":")[0].strip() for ln in tail.splitlines()
             if ":" in ln and ln.strip().endswith(",") and not ln.strip().startswith("//")]
    dead = [k for k in names if f"BUILD.{k}" not in fe]
    check(not dead, f"semua {len(names)} testId Fase 34 dipakai komponen", f"-> mati: {dead}")


# ---------------------------------------------------------------- C. penjaga di kode
def audit_guards(fe: str):
    head("C. Penjaga Fase 34 masih terpasang di kode")
    bb = (BE / "build_bulk.py").read_text(encoding="utf-8")
    check('i.get("status") != "done"' in bb,
          "INV-34-1 hanya pekerjaan BELUM selesai yang digeser (bukti terikat waktu)")
    check("bukti terikat waktu" in bb,
          "alasan tanggal dipertahankan dijelaskan ke pengguna, bukan disembunyikan")
    check("len(clean) < 10" in bb and 'ref.values("build_delay_cause")' in bb,
          "INV-34-2 penggeseran wajib beralasan SSOT + catatan")
    check("Sudah punya jadwal" in bb,
          "INV-34-3 unit yang sudah terjadwal dilewati, tidak ditimpa")
    check(("ensure_optional_unique(" in bb and '("client_ref", 1)' in bb
           and "_prior_run" in bb),
          "INV-34-8 idempotensi klik ganda dijaga index unik (partial) + pemutaran ulang")
    check("MAX_BATCH" in bb and "Maksimal" in bb, "batas jumlah per operasi ditegakkan")
    check("SEBELUM" in bb and "sudah diverifikasi" in bb,
          "INV-34-9 geser ke belakang yang melangkahi bukti ditolak dengan alasan")
    check("refresh_gates" in bb and "recompute_schedule" in bb,
          "INV-34-7 gerbang & progres dihitung ulang setelah geser")
    check("shift_history" in bb, "riwayat penggeseran disimpan pada jadwal unit")
    check("create_notification" in bb,
          "pelaksana diberi tahu ketika tenggatnya berubah (bukan diam-diam)")
    rt = (BE / "routers" / "build_bulk_router.py").read_text(encoding="utf-8")
    check("SUPERVISOR_ROLES" in rt and "status_code=403" in rt,
          "INV-34-5 hanya Manajer Proyek/direksi boleh menjalankan operasi massal")
    check('require_permission("construction", "approve")' in rt,
          "penggeseran tenggat butuh izin setara persetujuan")
    check("plan_create" in rt and "plan_shift" in rt,
          "INV-34-6 pratinjau memakai fungsi hitung yang sama dengan eksekusi")
    mp = (FE / "components" / "construction" / "BuildMonitorPanel.js").read_text(encoding="utf-8")
    check("BulkScheduleDialog" in mp and "BulkShiftDialog" in mp,
          "dialog jadwal massal & geser terpasang di Monitoring Unit")
    check("BulkRunsPanel" in mp, "riwayat operasi massal terpasang di Monitoring Unit")
    # Fase 46: isi jadwal unit dipindah ke `UnitScheduleView` supaya layar Unit 360 dan
    # drawer monitoring memakai SATU kode (bukan dua salinan yang bisa berbeda diam-diam).
    # Aturannya tidak berubah: riwayat penggeseran WAJIB terlihat di layar jadwal unit.
    us = (FE / "components" / "build" / "UnitScheduleView.js").read_text(encoding="utf-8")
    sheet = (FE / "components" / "construction" / "UnitScheduleSheet.js").read_text(
        encoding="utf-8")
    check("ShiftHistoryPanel" in us,
          "riwayat penggeseran tampil pada layar jadwal unit (transparansi)")
    check("UnitScheduleView" in sheet,
          "drawer jadwal unit memakai komponen yang sama (tidak ada salinan kedua)")
    ref34 = (BE / "reference_p34.py").read_text(encoding="utf-8")
    check("build_bulk_wave" in ref34 and "build_shift_scope" in ref34,
          "grup SSOT Fase 34 terdaftar (dropdown tidak diketik bebas)")
    # Dicek pada REGISTRY HIDUP (bukan teks import) supaya cara penggabungannya bebas
    # berubah, tetapi jaminannya tetap: dropdown Fase 34 benar-benar ada di satu registry.
    sys.path.insert(0, str(BE))
    import reference as _ref  # noqa: PLC0415
    check("build_bulk_wave" in _ref.GROUPS and "build_shift_scope" in _ref.GROUPS,
          "grup SSOT Fase 34 digabung ke registry tunggal")


# ---------------------------------------------------------------- D. kontrak API
def audit_runtime():
    head("D. Kontrak API operasi massal + pratinjau tidak menulis")
    pm = login("pm@sipro.co.id")
    sales = login("sales@sipro.co.id")
    blocks = requests.get(f"{BASE}/build/bulk/blocks", headers=pm, timeout=60).json()
    rows = blocks.get("data") or []
    check(bool(rows) and all({"block", "units", "scheduled", "unscheduled"} <= set(r)
                             for r in rows), "ringkasan blok memuat hitungan yang dirender UI")
    cands = requests.get(f"{BASE}/build/bulk/candidates", headers=pm, timeout=60).json()
    crows = cands.get("data") or []
    check("schedulable" in cands, "jumlah kandidat siap-jadwal disertakan")
    check(all(("template_code" in c) and ("reason" in c) and ("block" in c) for c in crows),
          "setiap kandidat membawa template / alasan / blok")
    targets = requests.get(f"{BASE}/build/bulk/shift/targets", headers=pm, timeout=60).json()
    trows = targets.get("data") or []
    check(bool(trows) and all({"schedule_id", "unit_code", "start_date",
                               "target_finish_date", "items_done"} <= set(t) for t in trows),
          "target penggeseran memuat kolom yang dirender UI")
    ready = [c for c in crows if c.get("schedulable")]
    if ready:
        before = len(crows)
        pv = requests.post(f"{BASE}/build/bulk/schedules/preview", headers=pm,
                           json={"unit_ids": [ready[0]["id"]],
                                 "start_date": trows[0]["start_date"]}, timeout=90)
        prow = (pv.json().get("data") or [{}])[0]
        check(pv.status_code == 200 and prow.get("target_finish_date"),
              "pratinjau jadwal massal mengembalikan tanggal & jumlah item")
        after = len(requests.get(f"{BASE}/build/bulk/candidates", headers=pm,
                                 timeout=60).json().get("data") or [])
        check(before == after, "pratinjau TIDAK menulis apa pun ke database")
    else:
        check(True, "semua unit sudah terjadwal — pratinjau jadwal tidak diuji (lewat)")
    if trows:
        sp = requests.post(f"{BASE}/build/bulk/shift/preview", headers=pm,
                           json={"schedule_ids": [trows[0]["schedule_id"]],
                                 "shift_days": 7}, timeout=90)
        srow = (sp.json().get("data") or [{}])[0]
        check(sp.status_code == 200 and {"items_shifted", "items_locked", "new_start"}
              <= set(srow), "pratinjau geser memisahkan digeser vs dipertahankan")
        check("moves" not in srow, "pratinjau tidak membocorkan payload internal per item")
        bad = requests.post(f"{BASE}/build/bulk/shift", headers=pm,
                            json={"schedule_ids": [trows[0]["schedule_id"]], "shift_days": 5,
                                  "cause": "weather", "note": "pendek"}, timeout=60)
        check(bad.status_code == 400, "catatan pendek ditolak lewat API, bukan hanya di UI")
    check(requests.get(f"{BASE}/build/bulk/candidates", headers=sales,
                       timeout=60).status_code == 403,
          "sales tidak bisa melihat operasi massal jadwal")


# ---------------------------------------------------------------- E. invarian data hidup
def audit_data():
    head("E. Invarian data hidup (jejak penggeseran & konsistensi jadwal)")
    pm = login("pm@sipro.co.id")
    targets = (requests.get(f"{BASE}/build/bulk/shift/targets", headers=pm, timeout=60)
               .json().get("data") or [])
    bad_hist, bad_finish = [], []
    for t in targets:
        bundle = requests.get(f"{BASE}/build/unit/{t['unit_id']}", headers=pm, timeout=90).json()
        sched = bundle.get("data") or {}
        items = bundle.get("items") or []
        for h in sched.get("shift_history") or []:
            if not (h.get("cause") and (h.get("note") or "").strip() and h.get("actor")):
                bad_hist.append((t["unit_code"], h))
        last = max((str(i.get("planned_finish") or "") for i in items), default="")
        if last and str(sched.get("target_finish_date") or "") < last:
            bad_finish.append((t["unit_code"], sched.get("target_finish_date"), last))
    check(not bad_hist, "setiap penggeseran punya penyebab + catatan + pelaku", bad_hist[:2])
    check(not bad_finish, "target selesai jadwal tidak lebih awal dari pekerjaan terakhir",
          bad_finish[:2])
    runs = (requests.get(f"{BASE}/build/bulk/runs", headers=pm, params={"limit": 50},
                         timeout=60).json().get("data") or [])
    bad_runs = []
    for r in runs:
        s, res = r.get("summary") or {}, r.get("results") or []
        if r.get("kind") == "schedule":
            n = len([x for x in res if x.get("status") == "created"])
            if int(s.get("created") or 0) != n:
                bad_runs.append((r["id"], "created", s.get("created"), n))
        else:
            n = len([x for x in res if x.get("status") == "shifted"])
            if int(s.get("shifted") or 0) != n:
                bad_runs.append((r["id"], "shifted", s.get("shifted"), n))
        if any("moves" in x for x in res):
            bad_runs.append((r["id"], "payload internal tersimpan", None, None))
    check(not bad_runs, f"riwayat {len(runs)} operasi massal konsisten dengan hasilnya",
          bad_runs[:2])


def main():
    fe = fe_sources()
    audit_orphan_endpoints(fe)
    audit_dead_testids(fe)
    audit_guards(fe)
    audit_runtime()
    audit_data()
    print("\n" + "-" * 58)
    print(f"HASIL verify_34: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        print("GATE FASE 34 GAGAL")
        sys.exit(1)
    print("GATE FASE 34 PASSED")


if __name__ == "__main__":
    main()
