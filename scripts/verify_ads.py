#!/usr/bin/env python3
"""verify_ads.py — GATE KAMPANYE, BIAYA IKLAN & ATRIBUSI/CAPI (Fase 43).

Janji yang dijaga (`docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §1–§6 + plan Fase 43):

  1. **Dua menu benar-benar dibuka** (`/campaigns`, `/attribution`) — punya route, PAGE_META,
     dan tercatat di ledger pintu resmi `docs/v2/40_PETA_NAV_V2.md` §7.
  2. **Impor CSV tidak pernah menghitung uang dua kali.** Kunci natural
     `(org_id, platform, campaign_id, adset_id, ad_id, date)` dijaga index UNIK di database,
     dan impor berkas yang sama untuk kedua kalinya menghasilkan `unchanged` — bukan baris
     kedua. Gate MEMBUKTIKANNYA dengan benar-benar mengimpor 2×, bukan membaca kode.
  3. **Dry-run adalah pratinjau, bukan penulisan.** Sesudah dry-run TIDAK BOLEH ada satu pun
     baris biaya tersimpan, dan tiap baris yang ditolak WAJIB menyebut alasannya.
  4. **Angka biaya tidak berbohong.** Kampanye tanpa biaya pada rentang → `cost_status`
     `missing` dan CPL/CAC/ROAS **null**, bukan 0 (0 membuat kampanye yang biayanya belum
     diinput tampak paling efisien). Sebagian hari terisi → `partial` dengan jumlah harinya.
  5. **Perubahan angka meninggalkan jejak.** Impor ulang dengan nominal berbeda MEMPERBARUI
     baris dan menyimpan nilai lama di `history`.
  6. **CAPI siap-live & bisa di-dedup.** Setiap `conversion_events` punya `event_id`
     deterministik (32 heks) + `user_data` ter-hash SHA-256, tanpa PII mentah, dan index unik
     menolak event kembar. Status mode simulasi = `simulated`, bukan `sent`.
  7. **Kredensial tidak pernah keluar dari server.** `/api/ads/health` hanya melaporkan
     `filled: true|false`; `POST /api/ads/sync` di mode simulasi MENOLAK dengan alasan +
     menyebut env yang belum diisi (bukan sukses palsu).
  8. **Kosakata dari SSOT.** Label enum iklan (platform, status biaya, asal angka, mode
     integrasi, status CAPI) tidak boleh diketik ulang di layar.
  9. **RBAC `ads` ditegakkan server**, bukan hanya disembunyikan tombolnya: sales & manajer
     proyek 403; keuangan boleh MELIHAT tetapi tidak boleh menulis; staf DM tidak boleh
     `manage` (menyentuh sistem luar); supervisor DM boleh.

Semua bukti diambil dari API/DB yang benar-benar berjalan. Data uji milik gate dibuang lagi
di akhir (kampanye + baris biaya + laporan impor bertanda `UJI GATE ADS`).

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_43.py`.
"""
import json
import os
import pathlib
import re
import sys

import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FE = ROOT / "frontend" / "src"
LEDGER_DOC = ROOT / "docs" / "v2" / "40_PETA_NAV_V2.md"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
fails = []

# Data uji milik gate (dibuang di akhir). Tanggal SENGAJA di masa lalu & di luar rentang
# bawaan 30 hari supaya layar demo tidak berubah karenanya.
MARK = "UJI GATE ADS — hapus bila tertinggal"
GATE_EXT = "gate-ads-43"
D1, D2, D3 = "2026-03-02", "2026-03-03", "2026-03-04"
EMPTY_FROM, EMPTY_TO = "2026-01-05", "2026-01-07"
CSV_HEAD = "date,platform,campaign_name,spend,impressions,clicks,leads_platform,currency"
UI_FILES = sorted([p for p in (FE / "components" / "ads").glob("*.js")]) + \
    [FE / "pages" / "CampaignsPage.js", FE / "pages" / "AttributionPage.js"]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def read(rel):
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def get(headers, path, **params):
    return requests.get(f"{BASE}{path}", headers=headers, params=params or None, timeout=60)


def post(headers, path, body=None):
    return requests.post(f"{BASE}{path}", headers=headers, json=body or {}, timeout=90)


def cleanup():
    """Buang data uji gate. Dijalankan di awal DAN di akhir supaya sisa jalannya yang
    terputus tidak pernah menabrak index unik nama kampanye pada jalan berikutnya."""
    ids = [c["id"] for c in db.campaigns.find({"name": MARK}, {"_id": 0, "id": 1})]
    if ids:
        db.ad_spend.delete_many({"campaign_id": {"$in": ids}})
        db.campaigns.delete_many({"id": {"$in": ids}})
    db.ads_imports.delete_many({"filename": "uji-gate-ads.csv"})
    db.audit_logs.delete_many({"entity_id": {"$in": ids}}) if ids else None


def csv_of(rows: list) -> str:
    return CSV_HEAD + "\n" + "\n".join(rows) + "\n"


def spend_rows(campaign_id: str) -> list:
    return list(db.ad_spend.find({"campaign_id": campaign_id}, {"_id": 0}))


# ============================================================== 1. menu & rute
def section_nav(routes: set):
    print("\n1. Dua menu Fase 43 benar-benar dibuka (bukan halaman kosong)")
    nav = read("config/navigationConfig.js")
    body = nav.split("export const NAV_STRUCTURE", 1)[-1].split("export function", 1)[0]
    meta = nav.split("PAGE_META", 1)[-1].split("const ALL", 1)[0]
    ledger_raw = re.search(r"<!-- NAV_DOOR_LEDGER -->\s*```json\s*(.*?)```",
                           LEDGER_DOC.read_text(encoding="utf-8", errors="ignore"), re.S)
    ledger = json.loads(ledger_raw.group(1)) if ledger_raw else []
    ledger_routes = {d.get("route") for d in ledger}
    for item_id, path in (("campaigns", "/campaigns"), ("attribution", "/attribution")):
        blocks = [b for b in re.split(r"\n\s{4,6}\{", body) if f'id: "{item_id}"' in b]
        if check(f"item menu '{item_id}' ada tepat satu", len(blocks) == 1, f"{len(blocks)}"):
            check(f"menu '{item_id}' TIDAK lagi 'Segera Hadir'", "comingSoon" not in blocks[0])
            check(f"menu '{item_id}' menunjuk {path}", f'path: "{path}"' in blocks[0])
        check(f"route {path} terdaftar di App.js", path in routes)
        check(f"{path} punya PAGE_META (judul TopBar resolve)", f'"{path}"' in meta)
        check(f"{path} tercatat di ledger pintu resmi (docs/v2/40 §7)", path in ledger_routes)


# ======================================================= 2. SSOT kosakata iklan
def section_ssot(dmlead):
    print("\n2. Kosakata iklan dari SSOT — tidak ada label enum yang diketik ulang di layar")
    r = get(dmlead, "/reference")
    if not check("GET /reference menjawab 200", r.status_code == 200, f"got {r.status_code}"):
        return
    groups = (r.json() or {}).get("data") or {}
    wajib = ["ad_platform", "campaign_objective", "campaign_status", "ad_spend_source",
             "ads_import_status", "ads_row_status", "ads_period", "ads_cost_status",
             "ads_attribution_level", "ads_channel_group", "capi_event_name", "capi_status",
             "integration_mode", "integration_target"]
    for g in wajib:
        check(f"grup SSOT '{g}' tersedia di /reference", bool(groups.get(g)))
    # Label yang paling sering diketik ulang orang: bila SALAH SATU muncul sebagai literal di
    # layar iklan, layar itu akan berbeda dengan kamus data begitu labelnya diubah admin.
    risky = ("ad_platform", "ads_cost_status", "ad_spend_source", "integration_mode",
             "capi_status", "ads_row_status", "ads_channel_group", "campaign_status")
    labels = {}
    for g in risky:
        for opt in (groups.get(g) or {}).get("options") or []:
            if len(str(opt.get("label") or "")) >= 6:
                labels.setdefault(opt["label"], g)
    hardcoded = []
    for path in UI_FILES:
        src = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        for label, group in labels.items():
            if f'"{label}"' in src or f"'{label}'" in src or f">{label}<" in src:
                hardcoded.append(f"{path.name}: '{label}' ({group})")
    check("layar iklan tidak menuliskan label enum sendiri", not hardcoded,
          f"{len(hardcoded)} kemunculan: {hardcoded[:4]}" if hardcoded
          else f"{len(labels)} label diperiksa di {len(UI_FILES)} berkas")
    # Metrik biaya WAJIB lewat CostMetric (yang menampilkan "belum lengkap"), bukan `?? 0`.
    cost = read("components/ads/CostStatus.js")
    check("CostMetric menolak menggambar 0 untuk nilai kosong",
          "value === null" in cost and "belum lengkap" in cost)
    zero_fallback = []
    for path in UI_FILES:
        src = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        for m in re.finditer(r"(cpl|cac|roas|cost_per_qualified|spend)\s*(\?\?|\|\|)\s*0", src):
            zero_fallback.append(f"{path.name}:{m.group(0)}")
    check("tidak ada metrik biaya yang dijatuhkan ke 0 di layar", not zero_fallback,
          f"{zero_fallback[:4]}")


# ================================================ 3. dry-run + 4. idempotensi
def section_import(dmlead, campaign):
    print("\n3. Dry-run impor CSV: menolak beralasan & TIDAK menulis apa pun")
    besok = "2027-01-01"
    rows = [
        f"{D1},Meta Ads,{MARK},1.250.000,41000,820,7,IDR",
        f"{D2},meta,{MARK},900000,30000,610,5,",
        f"{D1},meta,Kampanye Yang Tidak Terdaftar,500000,,,,",
        f"{besok},meta,{MARK},100000,,,,",
        f"{D3},meta,{MARK},100,,,,USD",
        f"{D3},meta,{MARK},seribu rupiah,,,,",
        f"{D1},Meta Ads,{MARK},1.250.000,41000,820,7,IDR",
    ]
    text = csv_of(rows)
    r = post(dmlead, "/ads/spend/import", {"csv_text": text, "filename": "uji-gate-ads.csv",
                                           "dry_run": True})
    if not check("POST /ads/spend/import (dry_run) menjawab 200", r.status_code == 200,
                 f"got {r.status_code} {r.text[:160]}"):
        return None
    doc = (r.json() or {}).get("data") or {}
    summ = doc.get("summary") or {}
    check("laporan dry-run berstatus 'preview' (belum tersimpan)", doc.get("status") == "preview",
          f"status={doc.get('status')}")
    check("laporan menandai dirinya dry_run", doc.get("dry_run") is True)
    check("7 baris terbaca", summ.get("total") == 7, f"total={summ.get('total')}")
    check("2 baris sah dihitung sebagai baris baru", summ.get("new") == 2, f"new={summ.get('new')}")
    check("5 baris cacat DITOLAK", summ.get("rejected") == 5, f"rejected={summ.get('rejected')}")
    reasons = " | ".join(str(x.get("reason") or "") for x in doc.get("rows") or [])
    for kata, arti in (("belum terdaftar", "kampanye tak dikenal"),
                       ("masa depan", "tanggal di masa depan"),
                       ("mata uang", "mata uang bukan IDR"),
                       ("bukan angka", "nominal bukan bilangan"),
                       ("kembar", "baris kembar di dalam berkas")):
        check(f"alasan penolakan menyebut {arti}", kata in reasons.lower())
    check("dry-run TIDAK menulis satu pun baris biaya", len(spend_rows(campaign["id"])) == 0,
          f"{len(spend_rows(campaign['id']))} baris tertulis")

    print("\n4. Komit laporan pratinjau = tepat yang sudah dilihat pemakai (idempoten)")
    r = post(dmlead, f"/ads/spend/import/{doc['id']}/commit")
    if not check("commit laporan pratinjau menjawab 200", r.status_code == 200,
                 f"got {r.status_code} {r.text[:160]}"):
        return doc
    body = r.json() or {}
    first = (body.get("data") or {})
    applied = first.get("applied") or {}
    check("2 baris tersimpan (inserted)", applied.get("inserted") == 2, f"applied={applied}")
    check("status laporan menjadi 'committed'", first.get("status") == "committed")
    check("baris biaya di database = 2", len(spend_rows(campaign["id"])) == 2,
          f"{len(spend_rows(campaign['id']))} baris")
    r2 = post(dmlead, f"/ads/spend/import/{doc['id']}/commit")
    check("commit KEDUA dikenali sudah pernah dikomit",
          r2.status_code == 200 and (r2.json() or {}).get("already_committed") is True,
          f"got {r2.status_code} {r2.text[:120]}")
    check("commit kedua TIDAK menambah baris", len(spend_rows(campaign["id"])) == 2,
          f"{len(spend_rows(campaign['id']))} baris")
    # Laporan impor adalah CATATAN AUDIT: commit kedua tidak boleh menulis ulang hasil commit
    # pertama. Tanpa pemeriksaan ini, hilangnya penjaga "sudah dikomit" tidak terlihat —
    # barisnya memang tidak berlipat (kunci natural menahannya), tetapi riwayat berubah
    # menjadi "0 baris baru, 2 tidak berubah" sehingga bukti apa yang dulu terjadi hilang.
    ulang = db.ads_imports.find_one({"id": doc["id"]}, {"_id": 0}) or {}
    check("commit kedua TIDAK menulis ulang hasil commit pertama (audit utuh)",
          (ulang.get("applied") or {}) == applied
          and ulang.get("committed_at") == first.get("committed_at"),
          f"applied {applied} -> {ulang.get('applied')}; "
          f"committed_at {first.get('committed_at')} -> {ulang.get('committed_at')}")

    total_awal = sum(int(x["spend"]) for x in spend_rows(campaign["id"]))
    r = post(dmlead, "/ads/spend/import", {"csv_text": text, "filename": "uji-gate-ads.csv",
                                           "dry_run": False})
    applied = ((r.json() or {}).get("data") or {}).get("applied") or {}
    check("impor ulang berkas yang SAMA = unchanged (uang tidak dihitung dua kali)",
          r.status_code == 200 and applied.get("unchanged") == 2 and not applied.get("inserted"),
          f"applied={applied}")
    check("total biaya tidak berubah setelah impor ulang",
          sum(int(x["spend"]) for x in spend_rows(campaign["id"])) == total_awal,
          f"{total_awal} -> {sum(int(x['spend']) for x in spend_rows(campaign['id']))}")

    naik = [rows[0].replace("1.250.000", "1.500.000")] + rows[1:]
    r = post(dmlead, "/ads/spend/import", {"csv_text": csv_of(naik),
                                           "filename": "uji-gate-ads.csv", "dry_run": False})
    applied = ((r.json() or {}).get("data") or {}).get("applied") or {}
    check("nominal berubah = MEMPERBARUI baris lama, bukan baris kedua",
          applied.get("updated") == 1 and len(spend_rows(campaign["id"])) == 2,
          f"applied={applied} baris={len(spend_rows(campaign['id']))}")
    row_d1 = next((x for x in spend_rows(campaign["id"]) if x["date"] == D1), {})
    hist = row_d1.get("history") or []
    check("nilai lama tersimpan di history (biaya tidak berubah diam-diam)",
          bool(hist) and any("spend" in str(h.get("changes")) for h in hist),
          f"revisions={row_d1.get('revisions')} history={len(hist)}")
    check("baris hasil impor berlabel sumber 'csv'", row_d1.get("source") == "csv",
          f"source={row_d1.get('source')}")

    print("\n5. Kunci natural dijaga DATABASE (bukan hanya kode)")
    info = db.ad_spend.index_information().get("uq_ad_spend_natural") or {}
    keys = [k for k, _ in info.get("key") or []]
    check("index unik uq_ad_spend_natural ada & unik",
          bool(info.get("unique")) and keys == ["org_id", "platform", "campaign_id", "adset_id",
                                                "ad_id", "date"],
          f"unique={info.get('unique')} keys={keys}")
    try:
        db.ad_spend.insert_one({**{k: row_d1.get(k) for k in
                                   ("org_id", "platform", "campaign_id", "adset_id", "ad_id",
                                    "date")}, "id": "gate-dup", "spend": 1})
        db.ad_spend.delete_one({"id": "gate-dup"})
        check("database MENOLAK baris kembar pada kunci natural", False, "insert kembar LOLOS")
    except DuplicateKeyError:
        check("database MENOLAK baris kembar pada kunci natural", True)

    print("\n6. Entri manual harian idempoten + berlabel sumber 'manual'")
    payload = {"campaign_id": campaign["id"], "date": D3, "spend": "750000"}
    r1 = post(dmlead, "/ads/spend", payload)
    r2 = post(dmlead, "/ads/spend", payload)
    r3 = post(dmlead, "/ads/spend", {**payload, "spend": "800000"})
    check("entri manual pertama = inserted",
          r1.status_code == 200 and (r1.json() or {}).get("result") == "inserted",
          f"{r1.status_code} {(r1.json() or {}).get('result')}")
    check("entri manual yang SAMA = unchanged (bukan baris kedua)",
          r2.status_code == 200 and (r2.json() or {}).get("result") == "unchanged",
          f"{(r2.json() or {}).get('result')}")
    check("nominal berbeda pada tanggal sama = updated",
          r3.status_code == 200 and (r3.json() or {}).get("result") == "updated",
          f"{(r3.json() or {}).get('result')}")
    manual = next((x for x in spend_rows(campaign["id"]) if x["date"] == D3), {})
    check("baris manual berlabel sumber 'manual'", manual.get("source") == "manual",
          f"source={manual.get('source')}")
    check("baris biaya kampanye uji = 3 hari", len(spend_rows(campaign["id"])) == 3,
          f"{len(spend_rows(campaign['id']))} baris")
    return doc


# =========================================================== 7. kejujuran angka
def section_honesty(dmlead, campaign, partial_seen: dict):
    print("\n7. Kejujuran angka: 'belum lengkap' bukan 0")
    check("kampanye uji sempat berstatus 'partial' saat baru 2 dari 3 hari terisi",
          partial_seen.get("status") == "partial",
          f"status={partial_seen.get('status')} hari={partial_seen.get('days')}"
          f"/{partial_seen.get('expected')}")
    r = get(dmlead, "/ads/performance", date_from=D1, date_to=D3)
    if not check("GET /ads/performance menjawab 200", r.status_code == 200, f"{r.status_code}"):
        return
    data = (r.json() or {}).get("data") or {}
    row = next((x for x in data.get("rows") or [] if x.get("name") == MARK), None)
    if check("kampanye uji muncul di laporan kinerja", bool(row)):
        check("3 hari terisi → cost_status 'complete'", row.get("cost_status") == "complete",
              f"{row.get('cost_status')} ({row.get('spend_days')}/{row.get('expected_days')})")
        check("biaya kampanye uji = jumlah baris yang tersimpan",
              row.get("spend") == sum(int(x["spend"]) for x in spend_rows(campaign["id"])),
              f"laporan={row.get('spend')}")
        check("tanpa lead, CPL/CAC/ROAS null (bukan 0)",
              row.get("leads") == 0 and row.get("cpl") is None and row.get("cac") is None
              and row.get("roas") is None,
              f"leads={row.get('leads')} cpl={row.get('cpl')} cac={row.get('cac')}")
        check("label sumber angka ikut dilaporkan", "csv" in (row.get("sources") or []),
              f"sources={row.get('sources')}")
    kosong = [x for x in data.get("rows") or [] if x.get("cost_status") == "missing"]
    check("ada kampanye lain yang biayanya belum diinput pada rentang ini", bool(kosong),
          f"{len(kosong)} kampanye")
    bohong = [x["name"] for x in kosong
              if any(x.get(k) == 0 for k in ("cpl", "cac", "roas", "cost_per_qualified"))]
    check("kampanye tanpa biaya TIDAK ditulis 0 untuk metrik biaya", not bohong, f"{bohong[:3]}")
    check("kampanye tanpa biaya membawa penjelasan (cost_note)",
          all(x.get("cost_note") for x in kosong), "ada baris tanpa cost_note")
    totals = data.get("totals") or {}
    check("total laporan menyatakan kelengkapan biaya",
          totals.get("cost_status") in ("partial", "missing", "complete")
          and totals.get("campaigns_without_cost") == len(kosong),
          f"{totals.get('cost_status')} tanpa_biaya={totals.get('campaigns_without_cost')}")

    r = get(dmlead, "/ads/performance", date_from=EMPTY_FROM, date_to=EMPTY_TO)
    data = (r.json() or {}).get("data") or {}
    row = next((x for x in data.get("rows") or [] if x.get("name") == MARK), None)
    if check("rentang tanpa biaya tetap menampilkan kampanyenya", bool(row)):
        check("rentang tanpa biaya → cost_status 'missing'", row.get("cost_status") == "missing",
              f"{row.get('cost_status')}")
        check("rentang tanpa biaya → semua metrik biaya null",
              all(row.get(k) is None for k in ("cpl", "cac", "roas", "cost_per_qualified")),
              f"cpl={row.get('cpl')} cac={row.get('cac')} roas={row.get('roas')}")
        check("rentang tanpa biaya → spend 0 hari", row.get("spend_days") == 0,
              f"{row.get('spend_days')}")


# ================================================================ 8. atribusi
def section_attribution(dmlead):
    print("\n8. Atribusi & campuran kanal = hitungan dari lead, bukan angka yang diketik")
    r = get(dmlead, "/ads/attribution", level="campaign")
    if not check("GET /ads/attribution menjawab 200", r.status_code == 200, f"{r.status_code}"):
        return
    data = (r.json() or {}).get("data") or {}
    rows, totals = data.get("rows") or [], data.get("totals") or {}
    rng = data.get("range") or {}
    lead_count = db.leads.count_documents({"created_at": {"$gte": rng.get("from", ""),
                                                          "$lte": rng.get("to", "") + "T23:59:59"}})
    check("jumlah baris atribusi > 0 (funnel terbentuk)", bool(rows), f"{len(rows)} baris")
    check("total lead atribusi = jumlah baris per (sumber, kampanye)",
          totals.get("leads") == sum(int(x.get("leads") or 0) for x in rows),
          f"totals={totals.get('leads')}")
    check("total lead atribusi = jumlah lead pada rentang di database (tie-out)",
          totals.get("leads") == lead_count,
          f"laporan={totals.get('leads')} database={lead_count}")
    mix = data.get("channel_mix") or []
    ssot = [g["value"] for g in (get(dmlead, "/reference").json()["data"]
                                .get("ads_channel_group") or {}).get("options") or []]
    check("kelompok kanal memakai kosakata SSOT",
          bool(mix) and all(g.get("channel_group") in ssot for g in mix),
          f"{[g.get('channel_group') for g in mix]}")
    check("lead di campuran kanal = total lead (tidak ada yang hilang)",
          sum(int(g.get("leads") or 0) for g in mix) == totals.get("leads"),
          f"mix={sum(int(g.get('leads') or 0) for g in mix)} totals={totals.get('leads')}")
    unknown = [x for x in rows if not x.get("campaign_known")]
    check("kampanye lead yang belum terdaftar DILAPORKAN (bukan dibuang)", bool(unknown),
          f"{len(unknown)} baris tanpa kampanye terdaftar")
    r = get(dmlead, "/ads/attribution", level="adset")
    sub = (r.json() or {}).get("data") or {}
    tebak = [x for x in sub.get("rows") or [] if x.get("spend") is not None]
    check("biaya TIDAK dibagi-bagi ke tingkat adset (tidak mengarang rincian)", not tebak,
          f"{len(tebak)} baris adset membawa biaya")
    check("tingkat adset menjelaskan mengapa biayanya kosong",
          all(x.get("spend_note") for x in sub.get("rows") or []))


# ==================================================================== 9. CAPI
def section_capi(dmlead, finance):
    print("\n9. CAPI V2: event_id dedup + identitas ter-hash + status jujur")
    import capi  # noqa: PLC0415 — sengaja: id event harus dihitung dengan fungsi produksi
    rows = list(db.conversion_events.find({}, {"_id": 0}))
    check("ada event konversi tercatat", bool(rows), f"{len(rows)} baris")
    tanpa_id = [r.get("id") for r in rows if not r.get("event_id")]
    check("SETIAP event punya event_id (kalau tidak, platform tak bisa men-dedup)",
          not tanpa_id, f"{len(tanpa_id)} baris tanpa event_id")
    bentuk = [r.get("event_id") for r in rows
              if r.get("event_id") and not re.fullmatch(r"[0-9a-f]{32}", str(r["event_id"]))]
    check("event_id berbentuk 32 heks (kontrak platform)", not bentuk, f"{bentuk[:3]}")
    salah = []
    for r in rows:
        want = capi.event_id_for(org_id=r.get("org_id"), event_name=r.get("event_name"),
                                lead_id=r.get("lead_id"), deal_id=r.get("deal_id"))
        if r.get("event_id") != want:
            salah.append(f"{r.get('event_name')}/{str(r.get('event_id'))[:8]}")
    check("event_id DETERMINISTIK dari (org, event, lead, deal) — retry tidak dihitung ulang",
          not salah, f"{len(salah)} baris menyimpang: {salah[:3]}")
    dupe = [g["_id"] for g in db.conversion_events.aggregate([
        {"$match": {"event_id": {"$ne": None}}},
        {"$group": {"_id": {"o": "$org_id", "e": "$event_id"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}])]
    check("tidak ada event kembar tersimpan", not dupe, f"{len(dupe)} pasang kembar")
    idx = db.conversion_events.index_information().get("uq_conversion_event_id") or {}
    check("index unik event_id ada (dedup dijaga database)", bool(idx.get("unique")),
          f"{idx or 'index tidak ada'}")
    check("kode CAPI memeriksa event_id sebelum menulis (dedup di jalur tulis)",
          'find_one({"org_id": org_id, "event_id": event_id}'
          in (ROOT / "backend" / "capi.py").read_text(encoding="utf-8"))
    pii = []
    for r in rows:
        for k, v in (r.get("user_data") or {}).items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(v)):
                pii.append(f"{k}={str(v)[:14]}")
    check("user_data hanya berisi hash SHA-256 (tanpa PII mentah)", not pii, f"{pii[:3]}")
    berhash = [r for r in rows if (r.get("user_data") or {})]
    check("event punya identitas ter-hash (siap-live)", len(berhash) == len(rows),
          f"{len(berhash)}/{len(rows)} baris")
    bohong = [r.get("id") for r in rows
              if r.get("transport") == "simulation" and r.get("status") == "sent"]
    check("mode simulasi TIDAK berstatus 'Terkirim'", not bohong, f"{len(bohong)} baris")

    r = get(finance, "/ads/capi/events")
    if check("GET /ads/capi/events menjawab 200 untuk keuangan", r.status_code == 200,
             f"{r.status_code}"):
        body = r.json() or {}
        api_rows = body.get("data") or []
        check("API tidak mengirim user_data mentah ke layar",
              all("user_data" not in x for x in api_rows))
        check("layar hanya menerima potongan hash sebagai bukti",
              all(str(v).endswith("…") for x in api_rows
                  for v in (x.get("user_data_preview") or {}).values()))
        check("ringkasan event ikut dikirim (audit bisa dibaca tanpa hitung manual)",
              bool(body.get("summary", {}).get("by_status")))
    row_id = rows[0]["id"] if rows else "none"
    r = post(finance, f"/ads/capi/events/{row_id}/resend")
    check("keuangan DITOLAK mengirim ulang event (aksi ke sistem luar = manage)",
          r.status_code == 403, f"got {r.status_code}")
    r = post(dmlead, f"/ads/capi/events/{row_id}/resend")
    check("supervisor DM ditolak dengan ALASAN mode simulasi (bukan sukses palsu)",
          r.status_code == 400 and "simulasi" in r.text.lower(),
          f"got {r.status_code} {r.text[:120]}")


# ==================================================== 10. kesiapan integrasi
def section_health(dmlead, finance):
    print("\n10. Kesiapan integrasi: jujur soal mode, TIDAK membocorkan kredensial")
    r = get(finance, "/ads/health")
    if not check("GET /ads/health menjawab 200", r.status_code == 200, f"{r.status_code}"):
        return
    raw = r.text
    data = (r.json() or {}).get("data") or {}
    rows = data.get("rows") or []
    check("kesiapan dilaporkan per integrasi", len(rows) >= 5, f"{len(rows)} baris")
    for row in rows:
        env = row.get("env") or []
        bad_keys = [e for e in env if set(e.keys()) != {"name", "filled"}]
        bad_type = [e for e in env if not isinstance(e.get("filled"), bool)]
        check(f"[{row.get('target')}] env hanya melaporkan terisi/tidak",
              not bad_keys and not bad_type,
              f"kunci asing={bad_keys[:2]} tipe salah={bad_type[:2]}")
        check(f"[{row.get('target')}] mode konsisten dengan env yang kosong",
              (row.get("mode") == "simulation") == bool(row.get("missing_env")),
              f"mode={row.get('mode')} missing={len(row.get('missing_env') or [])}")
        check(f"[{row.get('target')}] mode simulasi menyebut jalan keluarnya (fallback)",
              row.get("mode") == "live" or bool(row.get("fallback")))
    secrets = [v for k, v in os.environ.items()
               if k in ("JWT_SECRET", "PORTAL_MASTER_OTP") and v and len(v) > 5]
    bocor = [k for k in ("JWT_SECRET",) if os.environ.get(k) and os.environ[k] in raw]
    check("jawaban health tidak memuat nilai rahasia dari environment",
          not bocor and not any(s in raw for s in secrets), f"{bocor}")
    r = post(dmlead, "/ads/sync", {"platform": "meta"})
    check("POST /ads/sync di mode simulasi DITOLAK (bukan sinkronisasi palsu)",
          r.status_code == 400, f"got {r.status_code} {r.text[:120]}")
    check("penolakan sync menyebut mode simulasi + env yang belum diisi",
          "simulasi" in r.text.lower() and "META_" in r.text,
          f"{r.text[:160]}")


# ======================================================================= 11. RBAC
def section_rbac(dmlead, finance, campaign):
    print("\n11. RBAC ads ditegakkan SERVER (bukan hanya tombol yang disembunyikan)")
    sales = login("sales@sipro.co.id")
    pm = login("pm@sipro.co.id")
    dm = login("dm@sipro.co.id")
    probes = [
        ("sales", sales, "GET", "/ads/campaigns", None, 403, "anggaran iklan bukan urusan sales"),
        ("manajer proyek", pm, "GET", "/ads/performance", None, 403, "di luar domainnya"),
        ("keuangan", finance, "GET", "/ads/campaigns", None, 200, "beban yang dia bukukan"),
        ("keuangan", finance, "POST", "/ads/campaigns",
         {"name": "coba", "platform": "meta"}, 403, "tidak boleh mengarang kampanye"),
        ("keuangan", finance, "POST", "/ads/spend",
         {"campaign_id": campaign["id"], "date": D1, "spend": "1"}, 403,
         "tidak boleh mengisi biaya"),
        ("staf DM", dm, "GET", "/ads/spend", None, 200, "mengisi biaya harian"),
        ("staf DM", dm, "POST", "/ads/sync", {"platform": "meta"}, 403,
         "manage dicabut: tidak menyentuh sistem luar"),
        ("supervisor DM", dmlead, "GET", "/ads/health", None, 200, "pemilik anggaran"),
    ]
    for who, hdr, method, path, body, want, why in probes:
        r = post(hdr, path, body) if method == "POST" else get(hdr, path)
        check(f"{who} {method} {path} → {want} ({why})", r.status_code == want,
              f"got {r.status_code} {r.text[:90]}")
    # Bukti bahwa 403 di atas BUKAN karena payload/nama salah: peran yang berhak dijawab
    # BUKAN 403 pada endpoint yang sama.
    r = post(dmlead, "/ads/spend", {"campaign_id": campaign["id"], "date": D1, "spend": "1"})
    check("supervisor DM pada endpoint yang sama BUKAN 403 (bukti probe sah)",
          r.status_code != 403, f"got {r.status_code}")
    r = post(dmlead, "/ads/sync", {"platform": "meta"})
    check("supervisor DM boleh memanggil sync (ditolak karena mode, bukan izin)",
          r.status_code != 403, f"got {r.status_code}")


def main():
    cleanup()
    dmlead = login("dmlead@sipro.co.id")
    finance = login("finance@sipro.co.id")
    app = read("App.js")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', app))

    section_nav(routes)
    section_ssot(dmlead)

    r = post(dmlead, "/ads/campaigns", {
        "name": MARK, "platform": "meta", "objective": "leads", "status": "active",
        "external_id": GATE_EXT, "start_date": D1, "end_date": D3, "budget_total": 5000000,
        "audience_note": "Kampanye milik gate verify_ads.py — dibuang otomatis."})
    if not check("kampanye uji bisa dibuat supervisor DM", r.status_code == 200,
                 f"got {r.status_code} {r.text[:160]}"):
        print("-" * 60)
        print("GATE ADS FAILED: kampanye uji tidak bisa dibuat — sisanya tidak bisa dibuktikan")
        sys.exit(1)
    campaign = (r.json() or {}).get("data") or {}
    dupe = post(dmlead, "/ads/campaigns", {"name": MARK, "platform": "meta"})
    check("nama kampanye kembar per platform DITOLAK (biaya CSV tidak jadi ambigu)",
          dupe.status_code == 400, f"got {dupe.status_code}")

    partial_seen = {}
    try:
        section_import(dmlead, campaign)
        # Status 'partial' diperiksa dari kondisi NYATA di tengah alur: sesudah impor 2 hari
        # dan SEBELUM entri manual hari ketiga, laporan harus mengatakan "belum lengkap".
        # (Rekaman diambil di dalam section_import lewat pemanggilan ini.)
        r = get(dmlead, "/ads/performance", date_from=D1, date_to=D2)
        row = next((x for x in ((r.json() or {}).get("data") or {}).get("rows") or []
                    if x.get("name") == MARK), {})
        partial_seen = {"status": row.get("cost_status"), "days": row.get("spend_days"),
                        "expected": row.get("expected_days")}
        # Rentang D1..D2 hanya 2 hari dan keduanya terisi -> complete. Yang membuktikan
        # 'partial' adalah rentang D1..D3 sebelum hari ke-3 diisi; karena itu dibaca ulang
        # dengan menyembunyikan sementara baris manual hari ke-3 dari perhitungan.
        manual = db.ad_spend.find_one({"campaign_id": campaign["id"], "date": D3}, {"_id": 0})
        if manual:
            db.ad_spend.update_one({"id": manual["id"]}, {"$set": {"date": "2026-03-09"}})
            r = get(dmlead, "/ads/performance", date_from=D1, date_to=D3)
            row = next((x for x in ((r.json() or {}).get("data") or {}).get("rows") or []
                        if x.get("name") == MARK), {})
            partial_seen = {"status": row.get("cost_status"), "days": row.get("spend_days"),
                            "expected": row.get("expected_days")}
            db.ad_spend.update_one({"id": manual["id"]}, {"$set": {"date": D3}})
        section_honesty(dmlead, campaign, partial_seen)
        section_attribution(dmlead)
        section_capi(dmlead, finance)
        section_health(dmlead, finance)
        section_rbac(dmlead, finance, campaign)
    finally:
        cleanup()

    print("-" * 60)
    if fails:
        print(f"GATE ADS FAILED: {len(fails)} temuan — {fails[:8]}")
        sys.exit(1)
    print("GATE ADS PASSED: impor idempoten & beralasan, metrik biaya jujur, atribusi cocok "
          "dengan lead, CAPI siap-live tanpa PII, kredensial tidak bocor, RBAC ditegakkan")


if __name__ == "__main__":
    main()
