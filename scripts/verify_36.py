#!/usr/bin/env python3
"""verify_36.py — GATE Fase 36: Kalender Jadwal & master kalender kerja.

Melengkapi `poc_36.py` (aturan lewat API) dengan cek yang menahan PEMBUSUKAN DIAM-DIAM:

  A. Tidak ada `data-testid` Fase 36 yang mati & tidak ada komponen kalender yatim
     (halaman terdaftar di navigasi + route, semua panel benar-benar dipakai).
  B. Modul yang MEMAKAI sesuatu benar-benar meng-IMPORT-nya (cacat khas yang dulu
     membuat layar merah begitu dialog dibuka), dan halaman punya keadaan
     loading/error/kosong/akses-ditolak.
  C. Kalender READ-ONLY: tidak ada satu pun berkas kalender frontend yang menulis
     tanggal pekerjaan; pemindahan tanggal HANYA lewat dialog geser Fase 34.
  D. Mesin jadwal benar-benar memakai master kalender (bukan cuma UI diwarnai):
     `build_engine` menerima hari-libur mingguan, `generate_schedule` &
     `build_bulk.plan_shift`/`plan_for_template_at` memanggil resolver kalender.
  E. SSOT sinkron: daftar jenis acara di mesin = daftar di `reference_p36`, pola hari
     kerja memakai grup terpisah (tanpa nilai 'holiday' yang mustahil untuk pola mingguan),
     dan fase 36 terdaftar di `reference._PHASES`.
  F. Kontrak runtime (tanpa menulis apa pun): payload kalender konsisten dengan datanya
     sendiri, bentrok 'hari non-kerja' benar-benar jatuh di hari non-kerja, bentrok beban
     benar-benar melampaui ambang, indeks unik kalender aktif, dan daftar libur jujur
     (bernama, berjenis, tanpa duplikat, dengan catatan "wajib disesuaikan admin").

Jalankan: python3 scripts/verify_36.py
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
load_dotenv(BE / ".env")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
CAL_DIR = FE / "components" / "construction" / "calendar"

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label}" + (f" — {str(detail)[:180]}" if detail else ""))
    return bool(cond)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------ A. wiring
def audit_wiring():
    head("A. Halaman & komponen kalender terpasang (tidak ada testid/komponen mati)")
    ids_src = read(FE / "constants" / "testIds" / "buildCalendar.js")
    check(bool(ids_src), "constants/testIds/buildCalendar.js ada")
    check("export * from './buildCalendar'" in read(FE / "constants" / "testIds" / "index.js"),
          "testIds Fase 36 di-reexport dari index")
    values = set(re.findall(r'^\s*\w+:\s*"([a-z0-9-]+)"', ids_src, re.M))
    check(len(values) >= 35, f"jumlah testid kalender memadai ({len(values)})")
    all_src = "\n".join(read(p) for p in FE.rglob("*.js"))
    dead = sorted(v for v in values if all_src.count(v) < 1 and f'"{v}"' not in all_src)
    # testid dipakai lewat konstanta CAL.x, jadi periksa nama kuncinya juga terpakai
    keys = re.findall(r"^\s*(\w+):\s*\"[a-z0-9-]+\"", ids_src, re.M)
    unused = [k for k in keys if f"CAL.{k}" not in all_src]
    check(not dead, "tidak ada nilai testid yang tidak pernah muncul", dead[:5])
    check(not unused, "tidak ada kunci testid kalender yang tidak dipakai UI", unused[:6])

    nav = read(FE / "config" / "navigationConfig.js")
    app = read(FE / "App.js")
    hub = read(FE / "pages" / "BuildHubPage.js")
    check('"/build-calendar"' in nav, "halaman kalender terdaftar di PAGE_META")
    # Fase 40c melebur menu kalender ke hub `/build` (tab "Kalender Jadwal"). Yang WAJIB
    # dijaga adalah KETERJANGKAUAN fiturnya, bukan satu bentuk menu: boleh sebagai item nav
    # sendiri ATAU sebagai tab hub — tetapi rutenya harus tetap ada agar tautan lama
    # (notifikasi/tugas yang sudah terbit) tidak rusak.
    reachable = ('path: "/build-calendar"' in nav
                 or ("BuildCalendarPage" in hub and 'key: "kalender"' in hub))
    check(reachable, "halaman kalender bisa dijangkau dari menu (item nav atau tab hub)")
    check('path: "/build"' in nav or 'path: "/build-calendar"' in nav,
          "pintu masuk pembangunan ada di sidebar")
    check('<Route path="/build-calendar"' in app, "route /build-calendar terdaftar di App.js")

    page = read(FE / "pages" / "BuildCalendarPage.js")
    for comp in ("CalendarToolbar", "CalendarMonthGrid", "CalendarConflictPanel",
                 "CalendarDayPanel", "CalendarUnscheduledPanel", "WorkCalendarDialog",
                 "BulkShiftDialog"):
        check(comp in page, f"halaman memakai {comp}")
    # Tidak ada komponen yatim: dipakai LANGSUNG oleh halaman, atau oleh komponen kalender
    # lain yang sendirinya dipakai halaman (mis. daftar libur dipakai dialog pengaturan).
    siblings = "\n".join(read(p) for p in sorted(CAL_DIR.glob("*.js")))
    for f in sorted(CAL_DIR.glob("*.js")):
        used_by_page = f.stem in page
        used_by_sibling = len(re.findall(rf"\b{f.stem}\b", siblings)) > 1
        check(used_by_page or used_by_sibling,
              f"komponen {f.name} tidak yatim (dipakai halaman/komponen kalender lain)")
    for token, label in (("LoadingCards", "keadaan MEMUAT"), ("ErrorState", "keadaan GALAT"),
                         ("EmptyState", "keadaan KOSONG"),
                         ("AccessDenied", "keadaan AKSES DITOLAK")):
        check(token in page, f"halaman punya {label}")


# ------------------------------------------------------------------ B. import guards
def audit_imports():
    head("B. Modul memakai apa yang di-import (cegah layar merah)")
    for f in sorted(list(CAL_DIR.glob("*.js")) + [FE / "pages" / "BuildCalendarPage.js"]):
        src = read(f)
        if "useReference(" in src:
            check("useReference" in src.split("export default")[0],
                  f"{f.name}: useReference di-import")
        if re.search(r"\bapi\.(get|post|put|delete)\(", src):
            check("@/services/apiClient" in src, f"{f.name}: apiClient di-import")
        if "toast." in src:
            check("from \"sonner\"" in src, f"{f.name}: toast di-import dari sonner")
        if re.search(r"\bCAL\.", src):
            check("@/constants/testIds" in src, f"{f.name}: testIds di-import")
        if "useNavigate(" in src:
            check("react-router-dom" in src, f"{f.name}: useNavigate di-import")
        used_icons = set(re.findall(r"<([A-Z]\w+) className=\"h-", src))
        imported = set(re.findall(r"import \{([^}]*)\} from \"lucide-react\"", src))
        names = set()
        for blk in imported:
            names |= {x.strip() for x in blk.split(",") if x.strip()}
        missing = {i for i in used_icons if i not in names and i not in
                   ("RefLabel", "StatusPill", "Button", "Input", "ReferenceSelect")}
        check(not missing, f"{f.name}: semua ikon yang dipakai di-import", sorted(missing))


# ------------------------------------------------------------------ C. read-only
def audit_readonly():
    head("C. Kalender READ-ONLY terhadap tanggal pekerjaan (INV-36-6)")
    for f in sorted(CAL_DIR.glob("*.js")):
        src = read(f)
        bad = re.findall(r"api\.(?:post|put)\(\s*[`\"'](/build/items[^`\"']*)", src)
        check(not bad, f"{f.name}: tidak menulis langsung ke item pekerjaan", bad)
        bad2 = re.findall(r"api\.(?:post|put)\(\s*[`\"'](/build/schedules[^`\"']*)", src)
        check(not bad2, f"{f.name}: tidak membuat/menimpa jadwal unit", bad2)
    page = read(FE / "pages" / "BuildCalendarPage.js")
    check("BulkShiftDialog" in page,
          "pemindahan tanggal memakai dialog geser Fase 34 (bukan mesin baru)")
    router = read(BE / "routers" / "build_calendar_router.py")
    writes = re.findall(r"@router\.(post|put|delete)\(\"([^\"]*)\"", router)
    check(all("holiday" in p or p == "/settings" for _m, p in writes),
          "endpoint tulis router kalender hanya untuk master kalender", writes)
    check("audit_log(" in router, "perubahan kalender ditulis ke jejak audit")


# ------------------------------------------------------------------ D. mesin patuh kalender
def audit_engine():
    head("D. Mesin jadwal memakai MASTER kalender (bukan hanya warna di UI)")
    eng = read(BE / "build_engine.py")
    check("def is_workday(day: date, work_days_per_week: int, holidays: set, off_days=None)"
          in eng, "is_workday menerima pola hari libur mingguan (off_days)")
    check("off_days=None" in eng and "def date_for_day" in eng,
          "date_for_day/next_workday menerima off_days")
    check("bcal.params_for(" in eng, "generate_schedule memakai resolver kalender")
    bulk = read(BE / "build_bulk.py")
    check("import build_calendar as bcal" in bulk, "build_bulk meng-import kalender")
    check("plan_for_template_at" in bulk, "pratinjau jadwal massal sadar kalender")
    check(bulk.count("bcal.params_for(") >= 2,
          "plan_shift & plan_for_template_at memakai resolver kalender",
          bulk.count("bcal.params_for("))
    srv = read(BE / "server.py")
    check("build_calendar_router" in srv, "router kalender terpasang di server")
    check("seed_phase36" in srv, "seed kalender kerja dipanggil saat startup")
    insp = read(BE / "routers" / "inspection_router.py")
    check("/{iid}/schedule" in insp, "endpoint menjadwalkan inspeksi ada")
    check("bcal.day_info(" in insp, "penjadwalan inspeksi memeriksa hari kerja")


# ------------------------------------------------------------------ E. SSOT
def audit_ssot():
    head("E. SSOT sinkron antara mesin, referensi, dan UI")
    sys.path.insert(0, str(BE))
    import reference as ref  # noqa: PLC0415
    import reference_p36 as r36  # noqa: PLC0415
    import build_calendar as bcal  # noqa: PLC0415
    import build_calendar_view as bcv  # noqa: PLC0415
    check(36 in getattr(ref, "_PHASES", ()), "fase 36 terdaftar di reference._PHASES")
    check(tuple(bcv.KINDS) == tuple(r36.EVENT_KINDS),
          "jenis acara mesin = SSOT calendar_event_kind")
    patt = {o["value"] for o in ref.GROUPS["calendar_work_pattern"]["options"]}
    check(patt == set(bcal.DAY_MODES), "pola hari kerja SSOT = mode hari di mesin", patt)
    check("holiday" not in patt,
          "grup pola mingguan TIDAK menawarkan 'holiday' (itu tanggal, bukan pola)")
    day_kinds = {o["value"] for o in ref.GROUPS["calendar_day_kind"]["options"]}
    check(day_kinds == set(bcal.DAY_MODES) | {"holiday"},
          "jenis hari kalender lengkap (termasuk hari libur bernama)", day_kinds)
    check(set(r36.HOLIDAY_KINDS) == {o["value"] for o in
                                     ref.GROUPS["holiday_kind"]["options"]},
          "jenis hari libur konsisten")
    ui = read(FE / "utils" / "calendarUi.js")
    for k in r36.EVENT_KINDS:
        check(k in ui, f"nada warna UI tersedia untuk jenis acara '{k}'")
    check("KIND_ORDER" in ui and ui.count("work_deadline") >= 2,
          "urutan jenis acara UI stabil (legenda & filter memakai satu sumber)")


# ------------------------------------------------------------------ F. runtime
def audit_runtime():
    head("F. Kontrak runtime kalender (tanpa mengubah data)")
    try:
        pm = login("pm@sipro.co.id")
    except Exception as e:  # noqa: BLE001
        check(False, "login pm untuk cek runtime", e)
        return
    month = date.today().strftime("%Y-%m")
    r = requests.get(f"{BASE}/build/calendar", headers=pm, params={"month": month}, timeout=90)
    if not check(r.status_code == 200, "GET /build/calendar 200", r.text[:160]):
        return
    d = r.json()["data"]
    first, last = d["first"], d["last"]
    check(all(first <= e["date"] <= last for e in d["events"]),
          "tidak ada acara di luar rentang bulan")
    total = sum(v for k, v in d["summary"]["totals"].items() if k != "all")
    check(total == d["summary"]["totals"]["all"] == len(d["events"]),
          "ringkasan = jumlah acara nyata", (total, len(d["events"])))
    day_sum = sum(x["total"] for x in d["days"])
    check(day_sum == len(d["events"]), "jumlah acara per hari = total acara",
          (day_sum, len(d["events"])))
    by_date = {}
    for e in d["events"]:
        by_date[e["date"]] = by_date.get(e["date"], 0) + 1
    check(all(x["total"] == by_date.get(x["date"], 0) for x in d["days"]),
          "hitungan tiap sel hari benar")
    workdays = {x["date"]: x["is_workday"] for x in d["days"]}
    for c in d["conflicts"]:
        if c["kind"] == "non_workday":
            check(workdays.get(c["date"]) is False,
                  f"bentrok hari non-kerja {c['date']} memang bukan hari kerja")
            check(bool(c.get("suggested_date"))
                  and workdays.get(c["suggested_date"], True) is True,
                  f"saran tanggal {c.get('suggested_date')} adalah hari kerja")
        if c["kind"] in ("overload", "critical_stack"):
            check(c["count"] > c["threshold"],
                  f"bentrok {c['kind']} {c['date']} memang melampaui ambang", c)
            check(len(c.get("item_ids") or []) == c["count"],
                  f"bentrok {c['kind']} membawa daftar pekerjaan lengkap")
    check(len(d.get("outlook") or []) == 3, "pandangan 3 bulan ke depan disertakan")

    s = requests.get(f"{BASE}/build/calendar/settings", headers=pm, timeout=60)
    check(s.status_code == 200, "GET settings 200", s.text[:120])
    cal = s.json()["data"]
    check(set(cal["pattern"]) == set(("mon", "tue", "wed", "thu", "fri", "sat", "sun")),
          "pola 7 hari lengkap")
    hol = cal["holidays"]
    check(all(h.get("name") and h.get("kind") for h in hol),
          "setiap hari libur punya nama & jenis")
    check(len({h["date"] for h in hol}) == len(hol), "tidak ada hari libur duplikat")
    check("disesuaikan" in str(cal.get("note") or "").lower(),
          "catatan kejujuran daftar libur bawaan masih ada", cal.get("note"))
    check(cal["work_days_per_week"] == 7 - len([1 for v in cal["pattern"].values()
                                                if v == "off"]),
          "jumlah hari kerja per minggu konsisten dengan pola")

    idx = mdb.build_work_calendars.index_information()
    check(any(v.get("unique") for v in idx.values()),
          "indeks UNIK kalender per (org, proyek) aktif", list(idx))
    check(mdb.build_work_calendars.count_documents({"project_id": None}) == 1,
          "tepat satu kalender organisasi (tanpa duplikat)")
    sample = mdb.inspections.find_one({}, {"_id": 0, "scheduled_date": 1})
    check(sample is not None and "scheduled_date" in sample,
          "koleksi inspeksi punya field tanggal rencana")


# ------------------------------------------------------------------ G. pewarisan kalender
def audit_inheritance():
    """Regresi cacat nyata: override kalender proyek pernah MENGHAPUS libur organisasi.

    Cacatnya: `resolve()` memakai dokumen proyek sebagai PENGGANTI utuh dan `_ensure_doc`
    membuatnya dengan `holidays: []`, sehingga sekali menekan "Simpan pola & ambang" pada
    cakupan proyek, 18 libur nasional hilang senyap untuk proyek itu — tenggat 17 Agustus
    berhenti ditandai dan inspeksi QC bisa dijadwalkan pada Hari Kemerdekaan.
    Gate ini menguji SEMANTIK penggabungannya langsung (fungsi murni, tanpa mengubah data).
    """
    head("G. Pewarisan kalender organisasi → proyek (regresi libur hilang senyap)")
    sys.path.insert(0, str(BE))
    import build_calendar as bcal  # noqa: PLC0415
    import build_calendar_view as bcv  # noqa: PLC0415

    src = read(BE / "build_calendar.py")
    check("def _merge(" in src, "resolver kalender memakai penggabungan (bukan pengganti)")
    check("holiday_exclusions" in src,
          "pengecualian libur warisan punya wadah sendiri (bukan hapus data organisasi)")
    body = src.split("async def resolve(")[1].split("async def ")[0]
    check("_merge(" in body and "get_doc(org, None)" in body
          and "if not doc:" not in body,
          "resolve() membaca kalender organisasi DAN proyek lalu menggabungkannya "
          "(pola lama 'pakai proyek kalau ada, kalau tidak organisasi' hilang)")
    check("async def include_holiday" in src and "async def drop_override" in src,
          "pengecualian bisa dibatalkan & override bisa dilepas")

    org_doc = {"pattern": {"sat": "off"}, "holidays": [
        {"date": "2026-08-17", "name": "Kemerdekaan", "kind": "national"},
        {"date": "2026-12-25", "name": "Natal", "kind": "national"}],
        "thresholds": {"max_items_per_person_per_day": 3, "max_critical_per_day": 2}}
    plain = bcal._merge(org_doc, {"project_id": "P1", "holidays": [],
                                  "thresholds": {"max_items_per_person_per_day": 9}},
                        "org", "P1")
    check(len(plain["holidays"]) == 2,
          "override proyek TANPA libur tetap mewarisi seluruh libur organisasi",
          [h["date"] for h in plain["holidays"]])
    check(plain["thresholds"]["max_items_per_person_per_day"] == 9
          and plain["thresholds"]["max_critical_per_day"] == 2,
          "ambang: nilai yang di-override menang, sisanya diwarisi", plain["thresholds"])
    check(plain["pattern"]["sat"] == "off",
          "pola hari yang tidak diisi proyek tetap ikut organisasi", plain["pattern"])
    check(bcal.is_workday(plain, "2026-08-17") is False,
          "hari libur warisan tetap BUKAN hari kerja di kalender proyek")

    extra = bcal._merge(org_doc, {"project_id": "P1", "holiday_exclusions": ["2026-08-17"],
                                  "holidays": [{"date": "2026-09-01", "name": "Adat desa",
                                                "kind": "local"}]}, "org", "P1")
    check([h["date"] for h in extra["holidays"]] == ["2026-09-01", "2026-12-25"],
          "pengecualian hanya membuang tanggal yang DISENGAJA, libur khusus proyek ikut",
          [h["date"] for h in extra["holidays"]])
    check([h["date"] for h in extra["excluded_holidays"]] == ["2026-08-17"]
          and extra["excluded_holidays"][0].get("name") == "Kemerdekaan",
          "tanggal yang dikecualikan tetap DITAMPILKAN beserta namanya (tidak disembunyikan)")
    check({h["date"]: h["scope"] for h in extra["holidays"]}
          == {"2026-09-01": "project", "2026-12-25": "org"},
          "asal setiap libur ikut dikirim ke UI (warisan vs khusus proyek)")
    check(bcal._merge(org_doc, None, "org", None)["override_exists"] is False
          and bcal._merge(org_doc, {"project_id": "P1"}, "org", "P1")["override_exists"],
          "UI bisa membedakan proyek berkalender sendiri")

    check("inspection" in bcv.NONWORK_KINDS and "punch" in bcv.NONWORK_KINDS,
          "inspeksi & punch list yang jatuh di hari libur ikut ditandai bentrok",
          bcv.NONWORK_KINDS)
    view = read(BE / "build_calendar_view.py")
    outl = view.split("async def outlook")[1].split("async def month_view")[0]
    check("_inspections(" in outl and "_punch_items(" in outl,
          "chip bulan berikutnya menghitung lapisan yang sama (angka tidak mengecil)")

    router = read(BE / "routers" / "build_calendar_router.py")
    check('@router.post("/holidays/{day}/restore")' in router
          and '@router.delete("/settings")' in router,
          "endpoint batalkan-pengecualian & lepas-override tersedia")
    check("calendar_holiday_exclude" in router and "calendar_override_drop" in router,
          "kedua tindakan itu masuk jejak audit dengan nama stabil")

    dlg = read(CAL_DIR / "WorkCalendarDialog.js")
    check("calendar_settings_scope" in dlg,
          "dialog memaksa pengguna MEMILIH cakupan (organisasi / khusus proyek)")
    check("CAL.settingsScope" in dlg and "CAL.overrideDrop" in dlg,
          "pemilih cakupan & tombol lepas-override bisa diuji")
    hol = read(CAL_DIR / "WorkCalendarHolidays.js")
    check("holiday_source" in hol and "CAL.holidayRestore" in hol,
          "daftar libur menyebut asalnya & pengecualian bisa dibatalkan dari UI")
    check("Kecualikan" in hol,
          "tombol pada libur warisan berbunyi 'Kecualikan', bukan 'Hapus'")

    # runtime read-only: setiap override yang ADA di database harus tetap mewarisi
    org_row = mdb.build_work_calendars.find_one({"project_id": None}, {"_id": 0}) or {}
    base = {str(h.get("date"))[:10] for h in org_row.get("holidays") or []}
    for row in mdb.build_work_calendars.find({"project_id": {"$ne": None}}, {"_id": 0}):
        eff = bcal._merge(org_row, row, "org", row.get("project_id"))
        excl = {str(d)[:10] for d in row.get("holiday_exclusions") or []}
        check(base - excl <= {h["date"] for h in eff["holidays"]},
              f"kalender proyek {str(row.get('project_id'))[:8]} tidak kehilangan libur "
              "organisasi", sorted(base - excl - {h['date'] for h in eff['holidays']}))


def main():
    audit_wiring()
    audit_imports()
    audit_readonly()
    audit_engine()
    audit_ssot()
    audit_runtime()
    audit_inheritance()
    print("\n" + "-" * 58)
    print(f"HASIL verify_36: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        print("GATE FASE 36 GAGAL")
        sys.exit(1)
    print("GATE FASE 36 PASSED")


if __name__ == "__main__":
    main()
