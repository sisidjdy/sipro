#!/usr/bin/env python3
"""mutasi_40_ia.py — uji-mutasi untuk gate Fase 40 (IA & Design System V2).

Gate yang tidak bisa gagal tidak menjaga apa pun. Skrip ini merusak kode dengan sengaja
(satu cacat per kali), memastikan gate yang bersangkutan MEMERAH, lalu memulihkan berkasnya
dan memastikan gate HIJAU kembali.

  M1  verify_ia_v2   — item "Segera Hadir" diberi `path`               -> harus FAIL
  M2  check_nav_map  — item "Segera Hadir" diberi path + route         -> harus FAIL
  M3  verify_ia_v2   — rute alias `/field` dihapus (tautan lama rusak) -> harus FAIL
  M4  verify_ia_v2   — menu lama `/deals` dipasang lagi di sidebar     -> harus FAIL
  M5  verify_ia_v2   — angka KPI dibuat BOHONG (+1 dari hasil filter)  -> harus FAIL
  M6  verify_ia_v2   — KPI kehilangan tautan drill                    -> harus FAIL
  M7  verify_ia_v2   — satu daftar kembali memakai <Table> mentah      -> harus FAIL
  M8  verify_ia_v2   — peta menu dicabut dari Sidebar                 -> harus FAIL
  M9  verify_ia_v2   — tujuan peta menu menunjuk rute yang tidak ada  -> harus FAIL
  M10 verify_ia_v2   — kotak cari tabel kehilangan data-testid        -> harus FAIL
  M11 verify_ia_v2   — halaman di hub menulis pathname hardcode       -> harus FAIL
  M12 verify_ia_v2   — filter satu tab bocor ke tab lain              -> harus FAIL
"""
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/app")
results = []


def wait_backend():
    """Beberapa mutasi menyentuh berkas backend sehingga uvicorn memuat ulang. Tanpa jeda ini
    gate bisa memerah/menghijau karena ALASAN YANG SALAH."""
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://localhost:8001/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)


def run(script: str) -> tuple:
    wait_backend()
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                       capture_output=True, text=True, timeout=420)
    return p.returncode, (p.stdout + p.stderr)


def mutate(label: str, edits: list, script: str, expect_in_output=None):
    """edits: [(path, old, new)] — satu mutasi boleh menyentuh beberapa berkas (mis. nav +
    route harus dirusak bersama agar cacatnya realistis)."""
    originals = {}
    for path, old, new in edits:
        f = ROOT / path
        src = f.read_text()
        if old not in src:
            for p, s in originals.items():
                (ROOT / p).write_text(s)
            results.append((label, "TIDAK BISA DIUJI", f"pola tidak ditemukan di {path}"))
            return
        originals[path] = src
        f.write_text(src.replace(old, new, 1))
    try:
        code, out = run(script)
    finally:
        for p, s in originals.items():
            (ROOT / p).write_text(s)
    detected = expect_in_output is None or expect_in_output in out
    ok = detected and code != 0
    detail = "gate memerah seperti seharusnya" if ok else (
        f"cacat TIDAK TERTANGKAP (exit={code}, pola '{expect_in_output}' "
        f"{'ada' if detected else 'tidak ada'}) :: ...{out.strip()[-320:]}")
    results.append((label, "PASS" if ok else "FAIL", detail))
    code2, _ = run(script)
    results.append((f"{label} (pulih)", "PASS" if code2 == 0 else "FAIL",
                    "hijau kembali" if code2 == 0 else "MASIH MERAH setelah dipulihkan"))


NAV = "frontend/src/config/navigationConfig.js"
APP = "frontend/src/App.js"


def main():
    mutate("M1 item Segera Hadir diberi path",
           [(NAV, '{ id: "bi", label: "Analitik & BI", icon: BarChart3, roles: ALL, comingSoon: true,',
             '{ id: "bi", label: "Analitik & BI", icon: BarChart3, roles: ALL, comingSoon: true,\n'
             '        path: "/analytics",')],
           "verify_ia_v2.py", "FAIL  comingSoon 'Analitik & BI' tanpa path")

    mutate("M2 Segera Hadir punya path + route (halaman kosong)",
           [(NAV, '{ id: "bi", label: "Analitik & BI", icon: BarChart3, roles: ALL, comingSoon: true,',
             '{ id: "bi", label: "Analitik & BI", icon: BarChart3, roles: ALL, comingSoon: true,\n'
             '        path: "/analytics",'),
            (APP, '<Route path="/tasks" element={<TasksPage />} />',
             '<Route path="/tasks" element={<TasksPage />} />\n'
             '            <Route path="/analytics" element={<TasksPage />} />')],
           "check_nav_map.py", "comingSoon '/analytics' punya route")

    mutate("M3 rute alias /field dihapus (bookmark & notifikasi lama rusak)",
           [(APP, '<Route path="/field" element={<FieldPage />} />', "")],
           "verify_ia_v2.py", "FAIL  rute alias '/field' TETAP hidup")

    mutate("M4 menu lama /deals dipasang lagi di sidebar (duplikasi pintu)",
           [(NAV, '{ id: "leads", label: "Pipeline Lead", icon: UserPlus, path: "/leads", roles: SALES_SIDE },',
             '{ id: "leads", label: "Pipeline Lead", icon: UserPlus, path: "/leads", roles: SALES_SIDE },\n'
             '      { id: "deals", label: "Deal & Unit", icon: Handshake, path: "/deals", roles: SALES_SIDE },')],
           "verify_ia_v2.py", "FAIL  menu lama '/deals' tidak lagi di sidebar")

    mutate("M5 angka KPI dibuat bohong (tidak cocok dengan daftarnya)",
           [("backend/routers/work_router.py",
             '    base = [{"label": "Terlambat", "value": c.get("overdue", 0), "tone": "rose",',
             '    base = [{"label": "Terlambat", "value": c.get("overdue", 0) + 1, "tone": "rose",')],
           "verify_ia_v2.py", "sama dengan hasil filter")

    mutate("M6 KPI kehilangan tautan drill",
           [("backend/routers/work_router.py",
             '{"label": "Tugas Hari Ini", "value": c.get("today", 0), "tone": "amber",\n'
             '             "drill": "/tasks?tab=tasks&scope=mine&bucket=today"}]',
             '{"label": "Tugas Hari Ini", "value": c.get("today", 0), "tone": "amber"}]')],
           "verify_ia_v2.py", "punya drill")

    mutate("M7 daftar kembali memakai <Table> mentah (tanpa filter/sort/ekspor)",
           [("frontend/src/components/complaints/ComplaintsListTab.js",
             'import DataTable from "@/components/patterns/DataTable";',
             'import DataTable from "@/components/patterns/DataTable";\n'
             'import { Table } from "@/components/ui/table";')],
           "verify_ia_v2.py", "FAIL  ComplaintsListTab.js tidak lagi memakai <Table> mentah")

    mutate("M8 peta menu dicabut dari Sidebar",
           [("frontend/src/components/layout/Sidebar.js", "        <NavMigrationDialog />", "")],
           "verify_ia_v2.py", "FAIL  dialog peta menu terpasang di Sidebar")

    mutate("M9 tujuan peta menu menunjuk rute yang tidak ada",
           [("frontend/src/config/navMigrationMap.js", 'to: "/customers?hub=deal"',
             'to: "/deal-unit-lama?hub=deal"')],
           "verify_ia_v2.py", "punya route")

    mutate("M10 kotak cari tabel kehilangan data-testid",
           [("frontend/src/components/patterns/DataTableToolbar.js",
             "data-testid={testIds.search || DT.search}", "")],
           "verify_ia_v2.py", "FAIL  toolbar tabel punya kotak cari ber-testid")

    # ---- mutasi untuk dua CACAT NYATA yang ditemukan lewat uji browser (bukan dari gate) ----
    mutate("M11 halaman di hub menulis pathname hardcode (pemakai tertendang keluar hub)",
           [("frontend/src/pages/BuildCalendarPage.js",
             'nav({ pathname: selfPath(loc.pathname, "/build-calendar"), search: `?${q.toString()}` },',
             'nav({ pathname: "/build-calendar", search: `?${q.toString()}` },')],
           "verify_ia_v2.py", "FAIL  BuildCalendarPage.js tidak menulis pathname hardcode")

    mutate("M12 filter satu tab bocor ke tab lain (query dibawa apa adanya)",
           [("frontend/src/components/patterns/TabPage.js",
             "    const next = new URLSearchParams();",
             "    const next = new URLSearchParams(params);")],
           "verify_ia_v2.py", "FAIL  TabPage memulai query BERSIH saat pindah tab")

    print("\n" + "=" * 72)
    print("UJI-MUTASI GATE FASE 40 (IA & Design System V2)")
    print("=" * 72)
    bad = 0
    for label, status, detail in results:
        print(f"  {status:16} {label} — {detail}")
        if status != "PASS":
            bad += 1
    print("=" * 72)
    if bad:
        print(f"UJI-MUTASI GAGAL: {bad} mutasi tidak tertangkap / tidak pulih")
        sys.exit(1)
    print(f"UJI-MUTASI LULUS: {len(results)} pemeriksaan — semua gate bergigi & pulih")


if __name__ == "__main__":
    main()
