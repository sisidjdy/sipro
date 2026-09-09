#!/usr/bin/env python3
"""verify_37.py — GATE Fase 37: Kalibrasi Sekali Klik (durasi & waktu tunggu template).

Melengkapi `poc_37.py` (aturan dibuktikan lewat API nyata) dengan cek yang menahan
PEMBUSUKAN DIAM-DIAM — hal-hal yang tidak akan ketahuan dari satu kali uji manual:

  A. Wiring UI: halaman `/build-calibration` terdaftar di navigasi + route + PAGE_META,
     seluruh panel kalibrasi benar-benar dipakai (tidak ada komponen yatim), dan tidak ada
     `data-testid` Fase 37 yang mati (dideklarasikan tapi tidak pernah dipakai).
  B. Import & keadaan layar: modul yang MEMAKAI sesuatu benar-benar meng-IMPORT-nya (cacat
     khas yang membuat layar merah begitu dialog dibuka), dan halaman punya keadaan
     loading/error/kosong/akses-ditolak.
  C. Kalibrasi TIDAK menyentuh jadwal berjalan: tidak satu pun berkas kalibrasi (backend
     maupun frontend) menulis `build_items`/`build_schedules`; memindahkan tanggal jadwal
     berjalan tetap lewat Fase 34.
  D. Pratinjau = hasil: router memakai SATU fungsi hitung (`build_calibration.plan`) untuk
     pratinjau dan eksekusi, dan frontend tidak pernah menghitung sendiri hari/pergeseran.
  E. SSOT sinkron: jenis & alasan kalibrasi di mesin = di `reference_p37`, fase 37 terdaftar
     di `reference._PHASES`, dan frontend tidak menyimpan peta label kalibrasi sendiri.
  F. Penjaga model: `apply` mewajibkan alasan + catatan pada MODEL (bukan hanya di UI),
     sehingga curl pun tidak bisa mengubah template tanpa jejak.
  G. Kontrak runtime (read-only): payload `/build/calibration/candidates` konsisten dengan
     template yang sebenarnya tersimpan, indeks idempotensi `client_ref` aktif, setiap
     kalibrasi tersimpan punya baris sebelum→sesudah + alasan + pelaku, dan setiap kalibrasi
     yang masih berlaku benar-benar tercermin pada template (tidak ada tanda "sudah
     dikalibrasi" yang bohong).

Jalankan: python3 scripts/verify_37.py
"""
import os
import re
import sys
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
CAL_DIR = FE / "components" / "construction" / "calibration"
PANELS = ("CalibrationDialog.js", "CalibrationRecommendations.js", "CalibrationStepTable.js",
          "CalibrationTemplatePanel.js", "CalibrationHistoryPanel.js",
          "CalibrationRollbackDialog.js")

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label}" + (f" — {str(detail)[:200]}" if detail else ""))
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
    head("A. Halaman & panel kalibrasi benar-benar terpasang")
    nav = read(FE / "config" / "navigationConfig.js")
    app = read(FE / "App.js")
    hub = read(FE / "pages" / "BuildHubPage.js")
    check('"/build-calibration"' in nav, "PAGE_META memuat /build-calibration")
    # Fase 40c: kalibrasi kini jadi TAB di hub `/build`. Aturan aslinya tetap dijaga —
    # pintu masuknya tidak boleh muncul dua kali (dulu ada risiko item nav ganda) — hanya
    # bentuknya yang berubah: item nav sendiri ATAU tepat satu tab hub.
    # Fase 46: hub dirapikan menjadi 6 tab (dok 29 §1) dan kalibrasi menyatu dengan tab
    # "Analitik & Kalibrasi" — karena usulan kalibrasi LAHIR dari analitik keterlambatan,
    # memisahkannya membuat hubungan sebab-akibatnya hilang. Hitungan pintu masuk kini
    # mencakup komponen tab hub, bukan hanya berkas hub-nya.
    analytics_tab = read(FE / "components" / "build" / "BuildAnalyticsTab.js")
    nav_once = nav.count('path: "/build-calibration"')
    tab_once = hub.count('key: "kalibrasi"') + analytics_tab.count("<BuildCalibrationPage")
    check(nav_once + tab_once == 1,
          "pintu masuk Kalibrasi ada TEPAT satu kali (item nav atau tab hub)",
          f"nav={nav_once}, tab hub={tab_once}")
    check(app.count('path="/build-calibration"') == 1,
          "route /build-calibration terdaftar tepat satu kali")
    page = read(FE / "pages" / "BuildCalibrationPage.js")
    check(bool(page), "pages/BuildCalibrationPage.js ada")
    for f in PANELS:
        src = read(CAL_DIR / f)
        check(bool(src), f"komponen {f} ada")
        name = f[:-3]
        used_in_page = name in page
        used_elsewhere = any(name in read(CAL_DIR / o) for o in PANELS if o != f)
        check(used_in_page or used_elsewhere, f"{f} benar-benar dipakai (bukan komponen yatim)")

    ids_src = read(FE / "constants" / "testIds" / "buildCalibration.js")
    check(bool(ids_src), "constants/testIds/buildCalibration.js ada")
    check("export * from './buildCalibration'" in read(FE / "constants" / "testIds" / "index.js"),
          "testIds Fase 37 di-reexport dari index")
    values = set(re.findall(r'^\s*(\w+):\s*"([a-z0-9-]+)"', ids_src, re.M))
    body = page + "".join(read(CAL_DIR / f) for f in PANELS) \
        + read(FE / "components" / "construction" / "DelayAnalyticsPanel.js")
    dead = sorted(k for k, _v in values if f"CALIB.{k}" not in body)
    check(not dead, "tidak ada testid Fase 37 yang mati (dideklarasikan tapi tak dipakai)", dead)
    check(len(values) >= 40, "cakupan testid memadai untuk pengujian otomatis", len(values))

    # jalan masuk "sekali klik" dari Analitik Telat
    delay = read(FE / "components" / "construction" / "DelayAnalyticsPanel.js")
    check("/build-calibration" in delay and "analyticsRecCalibrate" in delay,
          "Analitik Telat punya tombol yang membawa rekomendasi ke layar Kalibrasi")
    check("q.set(\"step\"" in delay and "q.set(\"kind\"" in delay,
          "tautan dari Analitik Telat membawa langkah + jenis kalibrasi (bukan halaman kosong)")


# ------------------------------------------------------------------ B. import & state
def audit_imports_and_states():
    head("B. Import lengkap & keadaan layar (loading/error/kosong/akses ditolak)")
    files = {f: read(CAL_DIR / f) for f in PANELS}
    files["BuildCalibrationPage.js"] = read(FE / "pages" / "BuildCalibrationPage.js")
    for name, src in files.items():
        imported = set(re.findall(r"import\s+(?:\{([^}]+)\}|(\w+))[^\n]*from", src))
        names = set()
        for braces, plain in imported:
            if plain:
                names.add(plain.strip())
            for part in (braces or "").split(","):
                p = part.strip().split(" as ")[-1].strip()
                if p:
                    names.add(p)
        used = set(re.findall(r"<([A-Z]\w+)", src)) | set(re.findall(r"\b([a-z]\w+)\(", src))
        comps = {c for c in used if c[0].isupper()}
        local = set(re.findall(r"function\s+([A-Z]\w+)", src))
        missing = sorted(comps - names - local - {"React", "Fragment"})
        check(not missing, f"{name}: semua komponen yang dipakai ikut di-import", missing)
        helpers = {h for h in re.findall(r"\b(dayRange|deltaText|changeText|durationText|"
                                        r"needsDelta|"
                                        r"newClientRef|rowShift|stamp|suggestedDelta|waitText|"
                                        r"lateTone|countPending|countCalibrated|"
                                        r"targetFromDelayRow|targetFromTemplateStep)\(", src)}
        check(helpers <= names, f"{name}: pembantu calibrationUi yang dipakai ikut di-import",
              sorted(helpers - names))

    page = files["BuildCalibrationPage.js"]
    for token, label in (("LoadingCards", "keadaan memuat"), ("ErrorState", "keadaan gagal"),
                         ("AccessDenied", "keadaan akses ditolak"), ("EmptyState", None)):
        if token == "EmptyState":
            continue
        check(token in page, f"halaman Kalibrasi punya {label}")
    check("EmptyState" in files["CalibrationRecommendations.js"]
          and "EmptyState" in files["CalibrationStepTable.js"],
          "panel usulan & tabel telat punya keadaan kosong yang menjelaskan")
    check("histEmpty" in files["CalibrationHistoryPanel.js"],
          "panel riwayat punya keadaan kosong yang menjelaskan")
    check("viewerNote" in page and "canCalibrate" in files["CalibrationDialog.js"],
          "peran yang hanya boleh melihat mendapat penjelasan, bukan tombol mati tanpa sebab")


# ------------------------------------------------------------------ C. tidak menyentuh jadwal
def audit_no_schedule_writes():
    head("C. Kalibrasi tidak menyentuh jadwal/bukti yang sudah berjalan")
    be = read(BE / "build_calibration.py") + read(BE / "routers" / "build_calibration_router.py")
    for coll in ("build_items", "build_schedules"):
        bad = re.findall(rf"db\.{coll}\.(insert_one|insert_many|update_one|update_many|"
                         rf"delete_one|delete_many|replace_one|bulk_write)", be)
        check(not bad, f"backend kalibrasi tidak pernah menulis {coll}", bad[:3])
    fe = read(FE / "pages" / "BuildCalibrationPage.js") \
        + "".join(read(CAL_DIR / f) for f in PANELS)
    posts = set(re.findall(r"api\.(?:post|put|patch|delete)\(\s*[\"'`]([^\"'`]+)", fe))
    tmpl = set(re.findall(r"api\.(?:post|put|patch|delete)\(\s*`([^`]+)`", fe))
    allowed = {"/build/calibration/preview", "/build/calibration/apply"}
    stray = sorted(p for p in (posts | tmpl)
                   if not (p in allowed or p.startswith("/build/calibration/")))
    check(not stray, "layar kalibrasi hanya memanggil endpoint kalibrasi (tidak menulis jadwal)",
          stray)
    check("Geser jadwal" in read(FE / "pages" / "BuildCalibrationPage.js"),
          "layar kalibrasi menunjuk jalan resmi untuk menggeser jadwal berjalan (Fase 34)")
    check("TIDAK diubah" in read(BE / "build_calibration.py"),
          "pratinjau menyatakan terang-terangan bahwa jadwal berjalan tidak diubah")


# ------------------------------------------------------------------ D. pratinjau = hasil
def audit_single_math():
    head("D. Pratinjau = hasil (satu fungsi hitung, frontend tidak menghitung sendiri)")
    bc = read(BE / "build_calibration.py")
    check(bc.count("def plan(") == 1, "hanya ada SATU fungsi hitung kalibrasi")
    for fn in ("async def preview", "async def apply"):
        block = bc.split(fn)[1][:900] if fn in bc else ""
        check("plan(" in block, f"{fn.split()[-1]}() memakai plan() yang sama")
    fe_all = read(FE / "pages" / "BuildCalibrationPage.js") \
        + "".join(read(CAL_DIR / f) for f in PANELS) + read(FE / "utils" / "calibrationUi.js")
    check("day_from +" not in fe_all and "day_to +" not in fe_all,
          "frontend tidak menghitung ulang hari mulai/selesai (angka datang dari backend)")
    # MENAMPILKAN `shift_days` kiriman backend justru WAJIB (badge "0 hari" pada
    # `wait_into_plan` dulu menyembunyikan pergeseran 3 hari). Yang tetap dilarang:
    # frontend MENGHITUNG pergeseran sendiri.
    stripped = re.sub(r"[\"'`][^\"'`]*shift_days[^\"'`]*[\"'`]", "", fe_all)
    bad_math = re.findall(r"shift_days\s*[+\-*/]\s*\w|[+\-*/]\s*\w*\.?shift_days", stripped)
    check(not bad_math, "frontend tidak mengarang/menghitung pergeseran sendiri", bad_math[:3])
    check("changeText" in read(FE / "utils" / "calibrationUi.js"),
          "ada satu pembantu changeText() supaya perubahan hari dibaca sama di semua panel")
    for f in ("CalibrationRecommendations.js", "CalibrationStepTable.js",
              "CalibrationTemplatePanel.js", "CalibrationHistoryPanel.js"):
        src = read(CAL_DIR / f)
        check("deltaText(" not in src,
              f"{f}: badge/riwayat memakai changeText() (bukan delta_days mentah yang "
              f"berbunyi '0 hari' pada wait_into_plan)")
    dlg = read(CAL_DIR / "CalibrationDialog.js")
    check("/build/calibration/preview" in dlg and "/build/calibration/apply" in dlg,
          "dialog memakai pratinjau DAN eksekusi dari backend yang sama")
    check("wait_into_plan" not in dlg or "needsDelta" in dlg,
          "jumlah hari untuk 'masukkan waktu tunggu ke rencana' dihitung sistem, "
          "tidak diketik pengguna")


# ------------------------------------------------------------------ E. SSOT
def audit_ssot():
    head("E. SSOT jenis & alasan kalibrasi sinkron mesin ↔ kamus data ↔ UI")
    sys.path.insert(0, str(BE))
    import build_calibration as bcx  # noqa: PLC0415
    import reference as ref  # noqa: PLC0415
    import reference_p37 as r37  # noqa: PLC0415
    check(tuple(bcx.KINDS) == tuple(r37.CALIBRATION_KINDS),
          "jenis kalibrasi mesin = kamus data", bcx.KINDS)
    check(set(ref.values("calibration_kind")) == set(r37.CALIBRATION_KINDS),
          "grup calibration_kind tergabung ke reference.GROUPS")
    check(set(ref.values("calibration_cause")) == set(r37.CALIBRATION_CAUSES),
          "grup calibration_cause tergabung ke reference.GROUPS")
    check("pembatalan_kalibrasi" in r37.CALIBRATION_CAUSES,
          "alasan pembatalan tersedia sebagai nilai SSOT (bukan teks bebas)")
    check(37 in ref._PHASES, "fase 37 terdaftar di reference._PHASES")
    fe_all = read(FE / "pages" / "BuildCalibrationPage.js") \
        + "".join(read(CAL_DIR / f) for f in PANELS) + read(FE / "utils" / "calibrationUi.js")
    for kind in r37.CALIBRATION_KINDS:
        label = r37.KIND_LABEL[kind]
        check(label not in fe_all, f"label '{label[:28]}…' tidak dihardcode di frontend")
    check('group="calibration_kind"' in fe_all and 'group="calibration_cause"' in fe_all,
          "UI memakai dropdown/label SSOT untuk jenis & alasan kalibrasi")


# ------------------------------------------------------------------ F. penjaga model
def audit_model_guards():
    head("F. Alasan & catatan diwajibkan di MODEL (curl pun tidak bisa menerobos)")
    src = read(BE / "models_p37.py")
    check("class CalibrationApplyIn" in src, "model eksekusi terpisah dari model pratinjau")
    block = src.split("class CalibrationApplyIn")[1] if "CalibrationApplyIn" in src else ""
    check(re.search(r"cause:\s*str\s*=\s*Field\(", block) is not None,
          "alasan dinyatakan WAJIB (bukan Optional yang validatornya tidak jalan)")
    check(re.search(r"note:\s*str\s*=\s*Field\(", block) is not None,
          "catatan dinyatakan WAJIB dengan panjang minimal")
    check("NOTE_MIN" in src and "10" in src, "panjang minimal catatan ditegakkan model")
    check("class CalibrationRollbackIn" in src and "note: str" in src,
          "pembatalan kalibrasi juga wajib beralasan")
    router = read(BE / "routers" / "build_calibration_router.py")
    check("CONFIG_ROLES" in router and "project_manager" in router,
          "hanya admin/direksi/Manajer Proyek boleh mengubah template")
    check(router.count("audit_log(") >= 2,
          "apply & rollback keduanya menulis jejak audit", router.count("audit_log("))
    check("require_permission(\"construction\", \"view\")" in router,
          "melihat usulan cukup izin baca konstruksi (pelaksana tetap bisa melihat)")


# ------------------------------------------------------------------ G. runtime
def audit_runtime():
    head("G. Kontrak runtime: payload jujur terhadap template & jejak yang tersimpan")
    pm = login("pm@sipro.co.id")
    r = requests.get(f"{BASE}/build/calibration/candidates", headers=pm, timeout=90)
    if not check(r.status_code == 200, "GET /build/calibration/candidates 200", r.text[:160]):
        return
    d = r.json()["data"]
    tpl_rows = {t["code"]: t for t in mdb.build_templates.find({}, {"_id": 0})}
    for t in d["templates"]:
        row = tpl_rows.get(t["code"])
        if not check(bool(row), f"template {t['code']} ada di database"):
            continue
        steps = {s["code"]: s for s in row.get("steps") or []}
        check(t["steps_count"] == len(steps),
              f"{t['code']}: jumlah langkah pada payload = database", (t["steps_count"], len(steps)))
        check(int(t["version"]) == int(row.get("version") or 1),
              f"{t['code']}: versi template pada payload = database")
        bad = [s["code"] for s in t["steps"]
               if s["day_from"] != int(steps[s["code"]]["day_from"])
               or s["day_to"] != int(steps[s["code"]]["day_to"])
               or int(s["wait_days"] or 0) != int(steps[s["code"]].get("wait_days") or 0)]
        check(not bad, f"{t['code']}: angka setiap langkah pada payload = angka tersimpan", bad[:4])
        check(t["total_days"] == max(int(s["day_to"]) for s in steps.values()),
              f"{t['code']}: total hari kerja dihitung dari langkah terakhir")

    # tanda "sudah dikalibrasi" tidak boleh bohong
    active = list(mdb.build_calibrations.find(
        {"rolled_back_at": None, "rollback_of": None}, {"_id": 0}))
    marked = {(t["id"], s["code"]) for t in d["templates"] for s in t["steps"] if s.get("applied")}
    for cal in active:
        check((cal["template_id"], cal["step_code"]) in marked,
              f"kalibrasi aktif {cal['step_code']} ditandai pada daftar langkah template",
              cal["id"])
        row = next((r2 for r2 in cal.get("rows") or [] if r2.get("is_target")), None)
        check(bool(row) and bool(cal.get("cause")) and len(str(cal.get("note") or "")) >= 10
              and bool(cal.get("actor")),
              f"kalibrasi {cal['id'][:8]} menyimpan sebelum→sesudah + alasan + pelaku")
        tpl = mdb.build_templates.find_one({"id": cal["template_id"]}, {"_id": 0, "steps": 1})
        cur = next((s for s in (tpl or {}).get("steps") or []
                    if s.get("code") == cal["step_code"]), None)
        check(bool(cur) and int(cur["day_to"]) == int(row["after"]["day_to"]),
              f"kalibrasi aktif {cal['step_code']} benar-benar tercermin di template",
              cur and (cur.get("day_to"), row["after"]["day_to"]))
    if not active:
        check(True, "tidak ada kalibrasi aktif saat gate berjalan (tidak ada tanda palsu)")

    idx = [i["name"] for i in mdb.build_calibrations.list_indexes()] \
        if "build_calibrations" in mdb.list_collection_names() else []
    check("uq_calibration_client_ref" in idx or not idx,
          "indeks unik client_ref aktif (klik ganda tidak jadi dua kalibrasi)", idx)

    # RBAC runtime: sales tidak boleh melihat, pelaksana tidak boleh mengubah
    site = login("site@sipro.co.id")
    rs = requests.get(f"{BASE}/build/calibration/candidates", headers=site, timeout=60)
    check(rs.status_code == 200 and rs.json()["can"]["calibrate"] is False,
          "pelaksana boleh melihat tapi tidak boleh mengalibrasi", rs.status_code)
    sales = login("sales@sipro.co.id")
    rsl = requests.get(f"{BASE}/build/calibration/candidates", headers=sales, timeout=60)
    check(rsl.status_code == 403, "sales ditolak sopan (403)", rsl.status_code)


def main():
    audit_wiring()
    audit_imports_and_states()
    audit_no_schedule_writes()
    audit_single_math()
    audit_ssot()
    audit_model_guards()
    audit_runtime()
    print("\n" + "-" * 58)
    print(f"HASIL verify_37: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        print("GATE FASE 37 GAGAL")
        sys.exit(1)
    print("GATE FASE 37 PASSED")


if __name__ == "__main__":
    main()
