#!/usr/bin/env python3
"""verify_analytics.py — GATE ANALITIK & BI (Fase 44), acuan `docs/v2/31_ANALYTICS_BI_SPEC.md` §9.

Janji yang dijaga (dan cacat nyata yang dicegah):

  1. **Menu `/bi` dibuka jujur** — punya route, PAGE_META, dan tercatat di ledger pintu resmi.
  2. **Satu metrik = satu rumus.** Kamus metrik lengkap (kode, nama, RUMUS, satuan, persona,
     kebutuhan data) dan setiap dashboard benar-benar berisi metrik yang ada di kamus.
  3. **0 ≠ belum ada data.** Untuk SETIAP metrik: bila inputnya tidak ada, `value` WAJIB null
     dan status `kosong`. Ini aturan yang paling mudah dilanggar diam-diam saat orang
     "merapikan" tampilan dengan `?? 0`.
  4. **BI tidak menghitung ulang dengan rumus sendiri.** Angka marketing WAJIB sama dengan
     `/api/ads/performance`; angka penjualan/lead/kas WAJIB sama dengan hitungan langsung atas
     koleksi mentah. Kalau berbeda, ada dua kebenaran di aplikasi — dan itu kegagalan.
  5. **Angka = daftar.** Metrik yang punya drill-down berbasis hitungan (LED-14) HARUS sama
     dengan jumlah baris daftar yang ditunjuk tautannya.
  6. **Bisa dihitung ulang (INV-14).** Snapshot bukan kebenaran: setelah `rebuild`, nilai
     snapshot harus sama dengan hitungan langsung.
  7. **RBAC + row-scope**: peran ber-`view_own` (sales) hanya melihat datanya sendiri
     (dipaksakan server), tidak boleh menghitung ulang snapshot, dan tanpa token = 401.
  8. **Layar tidak menuliskan kosakata sendiri** (`metric_state`/`metric_unit` dari SSOT) dan
     tidak menjatuhkan nilai metrik ke 0.

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_44.py`.
"""
import json
import os
import pathlib
import re
import sys

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FE = ROOT / "frontend" / "src"
LEDGER_DOC = ROOT / "docs" / "v2" / "40_PETA_NAV_V2.md"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
fails = []
BI_FILES = sorted((FE / "components" / "bi").glob("*.js")) + [FE / "pages" / "BiPage.js"]
FULL = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(headers, path, **params):
    return requests.get(f"{BASE}{path}", headers=headers, params=params or None, timeout=90)


def read(rel):
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def section_nav(routes):
    print("\n1. Menu Analitik & BI dibuka (bukan halaman kosong)")
    nav = read("config/navigationConfig.js")
    body = nav.split("export const NAV_STRUCTURE", 1)[-1].split("export function", 1)[0]
    meta = nav.split("PAGE_META", 1)[-1].split("const ALL", 1)[0]
    blocks = [b for b in re.split(r"\n\s{4,6}\{", body) if 'id: "bi"' in b]
    if check("item menu 'bi' ada tepat satu", len(blocks) == 1, f"{len(blocks)}"):
        check("menu Analitik & BI TIDAK lagi 'Segera Hadir'", "comingSoon" not in blocks[0])
        check("menu Analitik & BI menunjuk /bi", 'path: "/bi"' in blocks[0])
    check("route /bi terdaftar di App.js", "/bi" in routes)
    check("/bi punya PAGE_META", '"/bi"' in meta)
    raw = re.search(r"<!-- NAV_DOOR_LEDGER -->\s*```json\s*(.*?)```",
                    LEDGER_DOC.read_text(encoding="utf-8"), re.S)
    ledger = json.loads(raw.group(1)) if raw else []
    check("/bi tercatat di ledger pintu resmi (docs/v2/40 §7)",
          any(d.get("route") == "/bi" for d in ledger), f"{len(ledger)} pintu")


def section_catalog(owner):
    print("\n2. Kamus metrik: satu metrik = satu rumus, dashboard terisi")
    r = get(owner, "/analytics/metrics")
    if not check("GET /analytics/metrics menjawab 200", r.status_code == 200, f"{r.status_code}"):
        return {}, {}
    body = r.json()
    catalog = {m["code"]: m for m in body.get("data") or []}
    dashboards = body.get("dashboards") or {}
    check("kamus metrik berisi minimal 40 metrik", len(catalog) >= 40, f"{len(catalog)} metrik")
    tanpa_rumus = [c for c, m in catalog.items() if not m.get("formula")]
    tanpa_butuh = [c for c, m in catalog.items() if not m.get("requires")]
    check("setiap metrik menyebut rumusnya", not tanpa_rumus, f"{tanpa_rumus[:5]}")
    check("setiap metrik menyebut data yang dibutuhkannya", not tanpa_butuh, f"{tanpa_butuh[:5]}")
    check("kelima dashboard persona terdaftar", len(dashboards) == 5, f"{sorted(dashboards)}")
    kosong = [p for p, codes in dashboards.items() if len(codes) < 5]
    check("setiap dashboard punya minimal 5 metrik", not kosong, f"{kosong}")
    asing = [f"{p}:{c}" for p, codes in dashboards.items() for c in codes if c not in catalog]
    check("dashboard tidak memakai kode metrik yang tidak ada di kamus", not asing, f"{asing[:5]}")
    return catalog, dashboards


def section_honesty(owner, catalog):
    print("\n3. Kejujuran angka: input tidak ada -> null + status 'kosong' (bukan 0)")
    states = {o["value"] for o in
              (get(owner, "/reference").json()["data"].get("metric_state") or {}).get("options")
              or []}
    check("SSOT metric_state tersedia", states == {"lengkap", "sebagian", "kosong"}, f"{states}")
    lying, bad_state, no_drill, sample = [], [], [], {}
    for code in catalog:
        r = get(owner, f"/analytics/metric/{code}", **FULL)
        if r.status_code != 200:
            lying.append(f"{code}:HTTP{r.status_code}")
            continue
        m = r.json()["data"]
        sample[code] = m
        if m.get("state") not in states:
            bad_state.append(f"{code}={m.get('state')}")
        if m.get("missing") and not m.get("coverage") and m.get("value") is not None:
            lying.append(f"{code}={m.get('value')} missing={m['missing'][:1]}")
        if m.get("state") == "kosong" and m.get("value") is not None:
            lying.append(f"{code} state kosong tapi value={m.get('value')}")
        if not m.get("drill"):
            no_drill.append(code)
    check("TIDAK ADA metrik yang mengirim angka tanpa input", not lying, f"{lying[:4]}")
    check("status kelengkapan tiap metrik dari kosakata SSOT", not bad_state, f"{bad_state[:4]}")
    check("setiap metrik punya tautan drill-down (KPI tanpa drill = belum selesai)",
          not no_drill, f"{no_drill[:5]}")
    kosong = [c for c, m in sample.items() if m.get("state") == "kosong"]
    tanpa_alasan = [c for c in kosong if not sample[c].get("missing")]
    check("metrik berstatus 'kosong' menyebutkan APA yang belum ada", not tanpa_alasan,
          f"{tanpa_alasan[:4]}" if tanpa_alasan else f"{len(kosong)} metrik kosong beralasan")
    # CAKUPAN TIDAK BOLEH DISEMBUNYIKAN. Ini diperiksa dengan FAKTA DATABASE, bukan dengan
    # percaya pada apa yang dilaporkan metrik: bila ada lead tanpa riwayat tahap, metrik yang
    # bergantung pada riwayat WAJIB berstatus `sebagian` + menyebutkan berapa baris yang
    # dipakai. Menyembunyikan cakupan membuat angka terlihat final padahal tidak.
    #
    # PENTING (cacat perangkat uji yang ditemukan saat Fase 50): hitung ulang HARUS memakai
    # saringan tanggal yang SAMA dengan metriknya. Metrik lead selalu dibatasi periode
    # (`_leads(org, date_from, date_to)`), jadi membandingkannya dengan hitungan SELURUH
    # koleksi membuat gate merah begitu ada satu lead di luar periode — mis. pembeli demo
    # Fase 50 yang rumahnya diserahterimakan 400 hari lalu (leadnya tahun sebelumnya).
    # Itu bukan ketidakjujuran metrik, melainkan pembanding yang salah.
    in_range = {"created_at": {"$gte": FULL["date_from"], "$lte": f"{FULL['date_to']}T23:59:59"}}
    total_lead = db.leads.count_documents(in_range)
    berriwayat = db.leads.count_documents(
        {**in_range, "stage_history": {"$exists": True, "$nin": [None, []]}})
    if total_lead and berriwayat < total_lead:
        for code in ("LED-02", "LED-04"):
            m = sample.get(code) or {}
            cov = m.get("coverage") or {}
            check(f"{code} mengaku dihitung dari sebagian data ({berriwayat}/{total_lead} lead)",
                  m.get("state") == "sebagian" and cov.get("rows") == berriwayat
                  and cov.get("total") == total_lead,
                  f"state={m.get('state')} coverage={cov}")
    punya_respons = db.leads.count_documents({**in_range,
                                              "response_time_minutes": {"$ne": None}})
    if total_lead and punya_respons < total_lead:
        m = sample.get("LED-06") or {}
        cov = m.get("coverage") or {}
        check(f"LED-06 mengaku cakupannya ({punya_respons}/{total_lead} lead punya waktu respons)",
              m.get("state") == "sebagian" and cov.get("rows") == punya_respons,
              f"state={m.get('state')} coverage={cov}")
    return sample


def section_tieout(owner, sample):
    print("\n4. Tie-out: BI tidak punya rumus kedua")
    perf = get(owner, "/ads/performance", **FULL).json()["data"]["totals"]
    check("MKT-01 biaya iklan = total laporan kampanye",
          sample["MKT-01"]["value"] == perf["spend"],
          f"{sample['MKT-01']['value']} vs {perf['spend']}")
    check("MKT-03 ROAS = ROAS laporan kampanye (null pun harus sama)",
          sample["MKT-03"]["value"] == perf.get("roas"),
          f"{sample['MKT-03']['value']} vs {perf.get('roas')}")
    units = list(db.units.find({}, {"_id": 0, "status": 1}))
    terjual = len([u for u in units if u.get("status") in ("booked", "sold")])
    check("SLS-01 unit terjual = hitung ulang koleksi units",
          sample["SLS-01"]["value"] == terjual, f"{sample['SLS-01']['value']} vs {terjual}")
    deals = list(db.deals.find({"status": {"$in": ["reserved", "booked", "completed"]}},
                               {"_id": 0, "price": 1}))
    nilai = sum(int(d.get("price") or 0) for d in deals)
    check("SLS-03 nilai penjualan = Σ harga deal aktif",
          sample["SLS-03"]["value"] == nilai, f"{sample['SLS-03']['value']} vs {nilai}")
    kas = sum(int(r.get("amount") or 0)
              for r in db.receipts.find({}, {"_id": 0, "amount": 1}))
    check("SLS-05 kas masuk = Σ kuitansi", sample["SLS-05"]["value"] == kas,
          f"{sample['SLS-05']['value']} vs {kas}")
    leads = db.leads.count_documents(
        {"created_at": {"$gte": FULL["date_from"], "$lte": f"{FULL['date_to']}T23:59:59"}})
    check("LED-01 lead masuk = jumlah lead di database (periode yang sama)",
          sample["LED-01"]["value"] == leads, f"{sample['LED-01']['value']} vs {leads}")
    spend = sum(int(r.get("spend") or 0) for r in db.ad_spend.find({}, {"_id": 0, "spend": 1}))
    check("LED-09 CPL memakai biaya iklan yang sama dengan database",
          sample["LED-09"]["inputs"]["biaya"] == spend,
          f"{sample['LED-09']['inputs']['biaya']} vs {spend}")


def section_drill(owner, sample):
    print("\n5. Angka = daftar (drill-down bukan tautan hiasan)")
    led14 = get(owner, "/analytics/metric/LED-14").json()["data"]
    drill = led14.get("drill") or ""
    check("LED-14 menunjuk daftar lead lewat SLA", drill == "/leads?sla=over", drill)
    r = get(owner, "/leads", sla="over", limit=1)
    total = (r.json() or {}).get("total")
    check("jumlah LED-14 = jumlah baris daftar yang ditunjuk tautannya",
          led14["value"] == total, f"metrik={led14['value']} daftar={total}")
    aging = get(owner, "/analytics/leads/aging").json()["data"]
    tua = next((b["value"] for b in aging["breakdown"] if b["key"] == ">7 hari"), None)
    check("LED-05 nilai = ember '>7 hari' pada rinciannya (angka & rincian tidak berbeda)",
          aging["value"] == tua, f"{aging['value']} vs {tua}")


def section_snapshot(owner):
    print("\n6. Snapshot bisa dihitung ulang (INV-14): rebuild MEMPERBAIKI, bukan menumpuk")
    # Uji SELF-HEALING dengan bukti langsung: satu baris snapshot sengaja dirusak nilainya,
    # lalu `rebuild` HARUS mengembalikannya ke hitungan langsung. Ini membuktikan snapshot
    # bukan kebenaran kedua yang bisa hidup sendiri. (Pelajaran uji-mutasi N7: memeriksa
    # "snapshot == hitungan langsung" SESUDAH rebuild saja tidak membuktikan apa pun, karena
    # rebuild-lah yang baru saja membuat keduanya sama.)
    probe = "SLS-01"
    fresh_before = get(owner, f"/analytics/metric/{probe}").json()["data"]
    db.metric_snapshots.update_one({"code": probe},
                                   {"$set": {"value": -424242, "state": "lengkap"}})
    r = requests.post(f"{BASE}/analytics/snapshots/rebuild", headers=owner, timeout=180)
    if not check("POST /analytics/snapshots/rebuild menjawab 200", r.status_code == 200,
                 f"{r.status_code} {r.text[:120]}"):
        return
    written = (r.json().get("data") or {}).get("metrics") or 0
    check("snapshot menulis metrik", written >= 10, f"{written} metrik")
    row = db.metric_snapshots.find_one({"code": probe}, {"_id": 0}) or {}
    day = row.get("date") or ""
    ulang = get(owner, f"/analytics/metric/{probe}", date_from=f"{day[:4]}-01-01",
                date_to=day).json()["data"] if day else {}
    check("nilai snapshot yang dirusak DIPERBAIKI rebuild (snapshot bukan kebenaran ke-2)",
          bool(row) and row.get("value") == ulang.get("value") and row.get("value") != -424242,
          f"snapshot={row.get('value')} langsung={ulang.get('value')} "
          f"(nilai metrik sekarang={fresh_before.get('value')})")
    idx = db.metric_snapshots.index_information().get("uq_metric_snapshot") or {}
    check("index unik snapshot ada (satu metrik satu baris per periode)",
          bool(idx.get("unique")), f"{idx or 'tidak ada'}")
    before = db.metric_snapshots.count_documents({})
    requests.post(f"{BASE}/analytics/snapshots/rebuild", headers=owner, timeout=180)
    check("hitung ulang KEDUA tidak menumpuk baris snapshot",
          db.metric_snapshots.count_documents({}) == before,
          f"{before} -> {db.metric_snapshots.count_documents({})}")
    snap = get(owner, "/analytics/snapshots").json().get("data") or {}
    beda = []
    for code, srow in list(snap.items())[:8]:
        sday = srow.get("date")
        val = get(owner, f"/analytics/metric/{code}", date_from=f"{sday[:4]}-01-01",
                  date_to=sday).json()["data"]
        if val.get("value") != srow.get("value"):
            beda.append(f"{code}: snapshot={srow.get('value')} langsung={val.get('value')}")
    check("sesudah rebuild, snapshot sama dengan hitungan langsung", not beda, f"{beda[:3]}")



def section_rbac(owner):
    print("\n7. RBAC + row-scope ditegakkan server")
    sales = login("sales@sipro.co.id")
    site = login("site@sipro.co.id")
    r = get(sales, "/analytics/users/daily")
    if check("sales boleh melihat dashboard tim", r.status_code == 200, f"{r.status_code}"):
        data = r.json()["data"]
        check("data sales DIBATASI ke dirinya sendiri (dipaksa server)",
              data.get("scoped_to") == "sales@sipro.co.id", f"{data.get('scoped_to')}")
        own = get(sales, "/analytics/sales/funnel").json()["data"]
        led01_sales = next((m for m in own["metrics"] if m["code"] == "LED-01"), {})
        led01_owner = get(owner, "/analytics/metric/LED-01").json()["data"]
        check("angka lead sales LEBIH KECIL dari angka organisasi (bukan data orang lain)",
              (led01_sales.get("value") or 0) < (led01_owner.get("value") or 0),
              f"sales={led01_sales.get('value')} org={led01_owner.get('value')}")
    r = requests.post(f"{BASE}/analytics/snapshots/rebuild", headers=sales, timeout=60)
    check("sales DITOLAK menghitung ulang snapshot (menyentuh seluruh koleksi)",
          r.status_code == 403, f"{r.status_code}")
    check("pelaksana lapangan boleh MELIHAT metrik (angka = alat kerja)",
          get(site, "/analytics/project/schedule-health").status_code == 200)
    r = requests.get(f"{BASE}/analytics/executive", timeout=30)
    check("tanpa token = 401 (bukan data bocor)", r.status_code == 401, f"{r.status_code}")


def strip_comments(src: str) -> str:
    """Buang komentar sebelum memeriksa kosakata hardcode.

    Komentar TIDAK PERNAH sampai ke layar, jadi menuduhnya \"label hardcode\" adalah cacat
    palsu — dan cacat palsu memaksa orang menulis komentar yang kabur hanya demi menyenangkan
    gate (kejadian nyata: penjelasan \"kenapa label diambil dari SSOT\" ikut tertuduh karena
    menyebut contoh labelnya).
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def section_ui(owner):
    print("\n8. Layar BI: kosakata dari SSOT, tanpa menjatuhkan nilai ke 0")
    groups = get(owner, "/reference").json()["data"]
    labels = {}
    for g in ("metric_state", "metric_unit", "metric_persona", "analytics_period"):
        for opt in (groups.get(g) or {}).get("options") or []:
            if len(str(opt.get("label") or "")) >= 6:
                labels.setdefault(opt["label"], g)
    hardcoded, zero_fallback = [], []
    for path in BI_FILES:
        src = strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for label, group in labels.items():
            if f'"{label}"' in src or f"'{label}'" in src or f">{label}<" in src:
                hardcoded.append(f"{path.name}: '{label}' ({group})")
        for m in re.finditer(r"(metric\.value|value)\s*(\?\?|\|\|)\s*0", src):
            zero_fallback.append(f"{path.name}:{m.group(0)}")
    check("layar BI tidak menuliskan label enum sendiri", not hardcoded, f"{hardcoded[:4]}")
    check("tidak ada nilai metrik yang dijatuhkan ke 0 di layar", not zero_fallback,
          f"{zero_fallback[:4]}")
    val = read("components/bi/MetricValue.js")
    check("MetricValue punya cabang 'belum ada data' untuk nilai kosong",
          "belum ada data" in val and ("value === null" in val or "text === null" in val))
    # Bukan sekadar \"kata formula ada di berkas\": rumusnya harus BENAR-BENAR dirender secara
    # kondisional pada kartu. Uji-mutasi N12 membuktikan pemeriksaan longgar (`\"formula\" in src`)
    # tetap hijau walau kartu berhenti menampilkan rumus (`{false ? (`).
    card = read("components/bi/MetricCard.js")
    check("kartu metrik benar-benar merender rumus metrik (angka bisa didebat dengan data)",
          "{metric.formula ? (" in card and "BI.cardFormula" in card)
    check("dashboard memberi peringatan bila ada metrik belum lengkap",
          "incompleteBanner" in read("components/bi/DashboardShell.js"))
    r = get(owner, "/analytics/export/LED-01", **FULL)
    check("ekspor CSV metrik bekerja", r.status_code == 200 and "text/csv" in
          r.headers.get("content-type", ""), f"{r.status_code} {r.headers.get('content-type')}")
    check("ekspor CSV menyebut kelengkapan datanya", "kelengkapan" in r.text,
          r.text[:80].replace("\n", " | "))


def main():
    owner = login("owner@sipro.co.id")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', read("App.js")))
    section_nav(routes)
    catalog, _dash = section_catalog(owner)
    if not catalog:
        print("GATE ANALITIK FAILED: kamus metrik tidak bisa dibaca")
        sys.exit(1)
    sample = section_honesty(owner, catalog)
    section_tieout(owner, sample)
    section_drill(owner, sample)
    section_snapshot(owner)
    section_rbac(owner)
    section_ui(owner)
    print("-" * 60)
    if fails:
        print(f"GATE ANALITIK FAILED: {len(fails)} temuan — {fails[:8]}")
        sys.exit(1)
    print("GATE ANALITIK PASSED: kamus metrik lengkap, angka cocok dengan sumbernya, metrik "
          "tanpa data mengaku, snapshot bisa dihitung ulang, RBAC & row-scope ditegakkan")


if __name__ == "__main__":
    main()
