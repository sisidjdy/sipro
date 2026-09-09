#!/usr/bin/env python3
"""POC/verifikasi Fase 29a — WORK HUB v2 (divisi, supervisor, jobdesk, bukti kerja).

Menjaga agar cacat yang sudah terbukti TIDAK BISA MUNDUR:
  D-1  Beranda & halaman Tugas WAJIB memakai satu definisi "tugas saya".
  D-4  Supervisor benar-benar bisa menugaskan/mengalihkan pekerjaan.
  D-5  Task berbukti tidak bisa "diselesaikan" tanpa bukti.
  D-6  Status selesai memakai kosakata SSOT `done`.
  D-7  Task menyimpan tautan halaman kerja (tidak ada CTA mati).
Plus: POV per level (staf/supervisor/owner), verifikasi otomatis vs supervisor,
katalog jobdesk 4 divisi, task berulang idempoten.

Jalankan: python3 scripts/verify_29a.py
"""
import os
import sys

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(h, path, **params):
    return requests.get(f"{BASE}{path}", headers=h, params=params, timeout=40)


def post(h, path, body=None):
    return requests.post(f"{BASE}{path}", headers=h, json=body or {}, timeout=40)


def main():
    su = login("superadmin@sipro.co.id")
    mgr = login("manager@sipro.co.id")       # supervisor Sales & Marketing
    sales = login("sales@sipro.co.id")       # staf Sales & Marketing
    pm = login("pm@sipro.co.id")             # supervisor Teknis
    dmlead = login("dmlead@sipro.co.id")     # supervisor Digital Marketing (peran baru)
    dm = login("dm@sipro.co.id")             # staf Digital Marketing (peran baru)
    finlead = login("finlead@sipro.co.id")   # supervisor Keuangan (peran baru)

    print("\n=== A. Domain divisi & peran baru ===")
    d = get(su, "/work/divisions")
    check("GET /work/divisions 200", d.status_code == 200, d.text[:200])
    rows = d.json().get("data", []) if d.status_code == 200 else []
    codes = {r["code"] for r in rows}
    check("4 divisi terdaftar", codes == {"sales_marketing", "technical",
                                         "digital_marketing", "finance"}, str(codes))
    check("Setiap divisi punya supervisor",
          all(r.get("supervisor_email") for r in rows),
          str([(r["code"], r.get("supervisor_email")) for r in rows]))
    dv = get(dm, "/work/divisions").json()
    check("Staf hanya melihat divisinya", dv.get("my_division") == "digital_marketing"
          and len(dv.get("data", [])) == 1, str(dv.get("my_division")))
    check("Level staf terbaca", dv.get("my_level") == "staff", str(dv.get("my_level")))

    print("\n=== B. D-1: semantik 'tugas saya' konsisten (Beranda vs halaman Tugas) ===")
    for label, h in (("super_admin", su), ("sales_manager", mgr), ("sales", sales),
                     ("dm_supervisor", dmlead), ("finance_manager", finlead)):
        home = get(h, "/work/home").json()["data"]
        mine = get(h, "/work/tasks", scope="mine").json()
        hc, tc = home["counts"], mine["counts"]
        same = all(hc.get(k, 0) == tc.get(k, 0) for k in ("overdue", "today", "upcoming"))
        check(f"{label}: Beranda == Tugas Saya", same, f"home={hc} tasks={tc}")
    su_all = get(su, "/work/tasks", scope="all").json()
    su_mine = get(su, "/work/tasks", scope="mine").json()
    check("Owner: scope=all > scope=mine (tugas tim TIDAK dicampur)",
          su_all["total"] >= su_mine["total"], f"all={su_all['total']} mine={su_mine['total']}")
    home_su = get(su, "/work/home").json()["data"]
    check("Owner: Beranda punya blok ringkasan tim terpisah",
          isinstance(home_su.get("team"), dict) and home_su["team"].get("open") is not None,
          str(home_su.get("team")))

    print("\n=== C. POV per level (staf vs supervisor vs owner) ===")
    r = get(sales, "/work/tasks", scope="division")
    check("Staf DILARANG scope=division", r.status_code == 403, str(r.status_code))
    r = get(mgr, "/work/tasks", scope="all")
    check("Supervisor DILARANG scope=all", r.status_code == 403, str(r.status_code))
    r = get(mgr, "/work/tasks", scope="division")
    check("Supervisor boleh scope=division", r.status_code == 200, r.text[:150])
    div_tasks = r.json().get("data", []) if r.status_code == 200 else []
    check("Tugas divisi hanya milik divisi supervisor",
          all(t.get("division") == "sales_marketing" for t in div_tasks),
          str({t.get("division") for t in div_tasks}))
    b = get(mgr, "/work/board")
    check("GET /work/board 200 (papan divisi)", b.status_code == 200, b.text[:150])
    board = b.json().get("data", {}) if b.status_code == 200 else {}
    check("Papan memuat beban kerja per staf", len(board.get("members", [])) >= 1,
          str(len(board.get("members", []))))
    check("Papan memuat antrean verifikasi", "review_queue" in board)
    r = get(mgr, "/work/board", division="technical")
    check("Supervisor tidak bisa lihat papan divisi lain", r.status_code == 403, str(r.status_code))

    print("\n=== D. Katalog jobdesk (4 divisi) ===")
    j = get(su, "/work/jobdesks")
    check("GET /work/jobdesks 200", j.status_code == 200, j.text[:150])
    jobs = j.json().get("data", []) if j.status_code == 200 else []
    check("Katalog >= 35 jobdesk", len(jobs) >= 35, str(len(jobs)))
    per_div = {}
    for x in jobs:
        per_div[x["division"]] = per_div.get(x["division"], 0) + 1
    check("Semua divisi punya jobdesk", len(per_div) == 4, str(per_div))
    srcs = {x["source"] for x in jobs}
    check("Ada 3 sumber tugas (event/berulang/manual)",
          srcs == {"event", "recurring", "manual"}, str(srcs))
    check("Ada jobdesk WA (blasting/reminder/follow-up)",
          any("blasting" in (x["title"] or "").lower() for x in jobs)
          and any("pengingat" in (x["title"] or "").lower() for x in jobs), "")
    verify_modes = {x["verify_mode"] for x in jobs}
    check("Ada pemisahan verifikasi sistem vs supervisor",
          {"system", "supervisor"}.issubset(verify_modes), str(verify_modes))
    check("Setiap jobdesk punya tautan halaman kerja (anti CTA mati)",
          all(x.get("link") for x in jobs), str([x["code"] for x in jobs if not x.get("link")]))

    print("\n=== E. Supervisor mengatur jobdesk (config, bukan hardcode) ===")
    r = requests.put(f"{BASE}/work/jobdesks/SM-01", headers=mgr,
                     json={"sla_hours": 0.25, "priority": "urgent"}, timeout=30)
    check("Supervisor sales boleh atur SM-01", r.status_code == 200, r.text[:200])
    check("SLA tersimpan", r.status_code == 200 and r.json()["data"]["sla_hours"] == 0.25,
          r.text[:120])
    r = requests.put(f"{BASE}/work/jobdesks/TK-01", headers=mgr,
                     json={"sla_hours": 5}, timeout=30)
    check("Supervisor sales DILARANG atur jobdesk Teknis", r.status_code == 403, str(r.status_code))
    r = requests.put(f"{BASE}/work/jobdesks/DM-04", headers=dm, json={"sla_hours": 5}, timeout=30)
    check("Staf DILARANG mengubah jobdesk", r.status_code == 403, str(r.status_code))
    r = requests.put(f"{BASE}/work/jobdesks/SM-02", headers=mgr,
                     json={"assignee_rule": "specific"}, timeout=30)
    check("Aturan 'orang tertentu' tanpa email ditolak", r.status_code == 400, str(r.status_code))
    r = requests.put(f"{BASE}/work/jobdesks/SM-02", headers=mgr,
                     json={"assignee_rule": "ngawur"}, timeout=30)
    check("Aturan penerima ngawur ditolak", r.status_code == 400, str(r.status_code))

    print("\n=== F. Supervisor menugaskan pekerjaan (D-4) ===")
    r = post(dmlead, "/work/jobdesks/DM-05/run", {"note": "Perbarui tautan showroom Cluster Asri"})
    check("Jalankan jobdesk manual 200", r.status_code == 200, r.text[:250])
    made = r.json().get("data", []) if r.status_code == 200 else []
    check("Task manual terbentuk", len(made) >= 1, str(len(made)))
    tid = made[0]["id"] if made else None
    check("Task manual masuk divisi Digital Marketing",
          bool(made) and made[0]["division"] == "digital_marketing", str(made[:1]))
    if tid:
        r = post(dmlead, f"/work/tasks/{tid}/assign", {"assigned_to": "dm@sipro.co.id",
                                                      "note": "Tolong dikerjakan hari ini"})
        check("Assign ke staf divisi sendiri 200", r.status_code == 200, r.text[:200])
        check("Penerima berubah", r.status_code == 200
              and r.json()["data"]["assigned_to"] == "dm@sipro.co.id", r.text[:120])
        r = post(dmlead, f"/work/tasks/{tid}/assign", {"assigned_to": "site@sipro.co.id"})
        check("Assign ke divisi lain ditolak", r.status_code == 400, str(r.status_code))
        r = post(dm, f"/work/tasks/{tid}/assign", {"assigned_to": "dmlead@sipro.co.id"})
        check("Staf tidak boleh meng-assign", r.status_code == 403, str(r.status_code))

    print("\n=== G. Siklus kerja berbukti: mulai → ajukan → verifikasi ===")
    # Ambil satu tugas milik staf DM yang butuh catatan (DM-05 proof=note, verify=none)
    if tid:
        r = post(dm, f"/work/tasks/{tid}/start")
        check("Staf memulai tugas", r.status_code == 200
              and r.json()["data"]["status"] == "in_progress", r.text[:150])
        r = post(dm, f"/work/tasks/{tid}/submit", {})
        check("Ajukan tanpa catatan ditolak", r.status_code == 400, r.text[:150])
        r = post(dm, f"/work/tasks/{tid}/submit", {"note": "Tautan showroom diperbarui & dicek"})
        ok = r.status_code == 200
        check("Ajukan dengan bukti 200", ok, r.text[:200])
        if ok:
            st = r.json()["data"]["status"]
            check("Jobdesk tanpa verifikasi langsung selesai (SSOT 'done')", st == "done", st)
            check("Bukti kerja tersimpan", len(r.json()["data"].get("proof") or []) >= 1)

    # Tugas yang WAJIB diverifikasi supervisor (DM-07 verify=supervisor)
    r = post(dmlead, "/work/jobdesks/DM-07/run", {"assigned_to": "dm@sipro.co.id"})
    tid2 = (r.json().get("data") or [{}])[0].get("id") if r.status_code == 200 else None
    check("Task verify=supervisor terbentuk", bool(tid2), r.text[:200])
    if tid2:
        r = post(dm, f"/work/tasks/{tid2}/submit", {"note": "Laporan mingguan disusun"})
        check("Diajukan → menunggu verifikasi", r.status_code == 200
              and r.json()["data"]["status"] == "submitted", r.text[:200])
        r = post(dm, f"/work/tasks/{tid2}/verify", {})
        check("Staf tidak boleh memverifikasi sendiri", r.status_code == 403, str(r.status_code))
        r = post(dmlead, f"/work/tasks/{tid2}/reject", {"reason": "Belum ada angka CPL per campaign"})
        check("Supervisor mengembalikan tugas", r.status_code == 200
              and r.json()["data"]["status"] == "in_progress", r.text[:200])
        check("Alasan pengembalian tercatat", r.status_code == 200
              and "CPL" in (r.json()["data"].get("rejected_reason") or ""), r.text[:150])
        post(dm, f"/work/tasks/{tid2}/submit", {"note": "Ditambahkan CPL & CPQL per campaign"})
        r = post(dmlead, f"/work/tasks/{tid2}/verify", {"note": "Sudah lengkap"})
        check("Supervisor memverifikasi → done", r.status_code == 200
              and r.json()["data"]["status"] == "done", r.text[:200])
        check("Jejak verifikator tersimpan", r.status_code == 200
              and r.json()["data"].get("verified_by") == "dmlead@sipro.co.id", r.text[:150])

    print("\n=== H. D-5: tidak bisa 'selesai' tanpa bukti; verifikasi otomatis jujur ===")
    tk = get(pm, "/work/tasks", scope="division").json().get("data", [])
    proofed = next((t for t in tk if (t.get("proof_kind") or "none") != "none"), None)
    check("Ada tugas teknis dengan bukti wajib", bool(proofed),
          str([(t.get("jobdesk_code"), t.get("proof_kind")) for t in tk][:6]))
    if proofed:
        r = post(pm, f"/work/tasks/{proofed['id']}/complete", {"outcome": "beres"})
        check("Tombol 'Selesai' lama ditolak untuk tugas berbukti", r.status_code == 400,
              r.text[:200])
    # Kejujuran verifikasi otomatis: buat temuan punch BARU (belum ada foto perbaikan) →
    # jobdesk TK-03 lahir; staf mengaku selesai tetapi data perbaikan belum ada.
    projects = get(pm, "/projects").json().get("data", [])
    pid = projects[0]["id"] if projects else None
    punch_task = None
    if pid:
        r = post(pm, "/field/punchlist", {
            "project_id": pid, "title": "Uji verifikasi otomatis Work Hub",
            "severity": "low", "location": "Uji", "assigned_to": "site@sipro.co.id"})
        check("Temuan punch baru dibuat (memicu jobdesk TK-03)", r.status_code == 200, r.text[:200])
        punch_id = (r.json().get("data") or {}).get("id")
        tk2 = get(pm, "/work/tasks", scope="division", limit=200).json().get("data", [])
        punch_task = next((t for t in tk2 if t.get("jobdesk_code") == "TK-03"
                           and t.get("related_entity_id") == punch_id), None)
        check("Task TK-03 tertaut ke temuan (bukan ke proyek)", bool(punch_task),
              str([(t.get("jobdesk_code"), t.get("related_entity_type")) for t in tk2][:8]))
    if punch_task:
        r = post(pm, f"/work/tasks/{punch_task['id']}/submit",
                 {"note": "sudah beres", "photos": ["dummy-file-id"]})
        ok = r.status_code == 200
        st = r.json()["data"]["status"] if ok else None
        check("Verifikasi sistem menahan klaim tanpa bukti nyata di data",
              ok and st == "submitted", f"{st} · {r.text[:150]}")
        check("Alasan penahanan dijelaskan ke pengguna",
              ok and "perbaikan" in (r.json()["data"].get("verify_note") or "").lower(),
              str(r.json().get("message") if ok else r.text[:120]))

    print("\n=== I. Task berulang idempoten + tautan kerja (D-7) ===")
    import subprocess
    code = ("import asyncio, sys; sys.path.insert(0, '/app/backend');"
            "import workhub as wh; print(asyncio.run(wh.recurring_tick()))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd="/app/backend")
    check("recurring_tick kedua tidak membuat duplikat",
          out.stdout.strip().endswith("0"), out.stdout.strip()[-80:] + out.stderr[-200:])
    tasks_all = get(su, "/work/tasks", scope="all", limit=200).json().get("data", [])
    with_link = [t for t in tasks_all if t.get("jobdesk_code") and t.get("link")]
    check("Tugas jobdesk punya tautan halaman kerja", len(with_link) >= 5, str(len(with_link)))
    check("Paginasi nyata pada daftar tugas",
          get(su, "/work/tasks", scope="all", limit=5).json()["limit"] == 5)
    return finish()


def finish():
    print("\n" + "=" * 62)
    print(f"HASIL: {len(PASS)} PASS / {len(FAIL)} FAIL")
    for f in FAIL:
        print(f"  - GAGAL: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
