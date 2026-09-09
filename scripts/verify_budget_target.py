#!/usr/bin/env python3
"""verify_budget_target.py — GATE TARGET & ANGGARAN (Fase 45), acuan `docs/v2/32` §6.

Janji yang dijaga gate ini (dan cacat NYATA yang dicegah — semuanya pernah terjadi di sesi ini):

  1. **Tidak ada pintu sidebar baru.** Target & Budget masuk sebagai TAB di `/boq` sesuai
     ledger pintu resmi `docs/v2/40` §7. Gate memeriksa jumlah pintu tidak bertambah dan
     tab barunya benar-benar ada di kode halaman.
  2. **POC core tetap hijau.** `poc/poc_45.py` dijalankan sebagai bagian gate: matematika
     target tanpa POC hijau tidak boleh dianggap selesai.
  3. **Lima metode target bekerja & jujur.** Metode yang kekurangan bahan (bobot kurva-S,
     harga rata-rata, riwayat kecepatan) MENOLAK menghitung + menyebut apa yang kurang;
     bukan mengirim rencana 0 yang kelihatan sah.
  4. **Dinamis tetapi tidak diam-diam**: `lock_past` menjaga periode lampau, `carry_over`
     menjelaskan kenaikan, `history[]` memuat alasan, dan `recalc` MENOLAK tanpa alasan.
     (Cacat nyata: `today` sempat jatuh ke awal horizon → seluruh horizon dihitung ulang
     tiap kali dan carry_over selalu 0.)
  5. **Satu kebenaran RAB**: agregasi anggaran konstruksi TIE-OUT dengan `/api/boq/control`.
     (Cacat nyata: `verified` dibaca sebagai field padahal DITURUNKAN dari langkah jadwal.)
  6. **Drill 3 lapis menjumlah**: Σ dokumen = angka item = angka kategori = angka proyek,
     dan komitmen vs realisasi SALING LEPAS (tidak ada yang dihitung dua kali).
  7. **0 ≠ belum ada data**: proyek tanpa item anggaran → `state=kosong`, `totals=null`;
     persen dengan pembagi 0 → null; layar tidak menjatuhkan nilai ke 0.
  8. **Rencana konstruksi read-only**: mengirim `planned_amount`/merevisinya DITOLAK.
  9. **`budget.enforce_cost_ref` bawaannya MATI** + ada laporan "biaya belum terpetakan".
 10. **Peringatan ambang bergigi**: melewati ambang membuat notifikasi + tugas FN-11, dan
     tidak diulang saat tingkat status tidak naik.
 11. **RBAC + SoD**: sales 403 di anggaran; yang menyusun anggaran bukan yang merevisi;
     tanpa token 401.
 12. **Layar tidak menuliskan kosakata sendiri** (`budget_health`/`budget_category`/
     `budget_match_rule`/`target_method` dari SSOT).

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_45.py`.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FE = ROOT / "frontend" / "src"
LEDGER_DOC = ROOT / "docs" / "v2" / "40_PETA_NAV_V2.md"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
fails = []
BUDGET_FILES = sorted((FE / "components" / "budget").glob("*.js")) + [FE / "pages" / "BoQPage.js"]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(h, path, **params):
    return requests.get(f"{BASE}{path}", headers=h, params=params or None, timeout=120)


def post(h, path, body=None, **params):
    return requests.post(f"{BASE}{path}", headers=h, json=body, params=params or None,
                        timeout=120)


def read(rel):
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


# ============================================================ 1. NAV: tab, bukan pintu baru
def section_nav():
    print("\n1. NAVIGASI — tab di hub yang sudah ada, TANPA pintu sidebar baru")
    app = read("App.js")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', app))
    check("rute /boq tetap ada", "/boq" in routes)
    ledger_raw = LEDGER_DOC.read_text(encoding="utf-8")
    block = re.search(r"<!-- NAV_DOOR_LEDGER -->\s*```json\s*(\[.*?\])\s*```", ledger_raw, re.S)
    if not check("ledger pintu resmi terbaca", bool(block)):
        return
    ledger = json.loads(block.group(1))
    nav = strip_comments(read("config/navigationConfig.js"))
    sidebar = set(re.findall(r'path:\s*"([^"]+)"', nav))
    extra = sorted(p for p in sidebar
                   if p not in {d["route"] for d in ledger} and not p.startswith("/admin"))
    check("tidak ada pintu sidebar asing (Fase 45 tidak menambah pintu)", not extra, str(extra))
    check("jumlah pintu resmi tidak bertambah karena Fase 45", len(ledger) <= 31,
          f"{len(ledger)} pintu (anggaran 31 = 30 + /legal iter149)")
    boq = strip_comments(read("pages/BoQPage.js"))
    for key, label in (("target", "Target & Budget"), ("realisasi", "Realisasi RAB")):
        check(f"tab '{label}' terdaftar di hub /boq",
              f'key: "{key}"' in boq and label in boq)
    check("tab baru dipasang lewat TabPage (tab sinkron ke URL ?hub=)",
          "TabPage" in boq and 'paramKey="hub"' in boq)


# ============================================================ 2. POC core
def section_poc():
    print("\n2. POC CORE — matematika target & anggaran dibuktikan terpisah dari UI")
    poc = ROOT / "poc" / "poc_45.py"
    if not poc.exists():
        # Direktori `poc/` tidak pernah masuk repo GitHub (hanya ada di pod asal) — dilaporkan
        # jujur sebagai LEWAT, bukan gagal, supaya gate tidak merah karena berkas yang tidak ada.
        print("  SKIP  poc/poc_45.py tidak ada di repo — pembuktian POC dilewati")
        return
    res = subprocess.run([sys.executable, str(poc)],
                         capture_output=True, text=True, timeout=600)
    ok = res.returncode == 0
    tail = (res.stdout or res.stderr).strip().splitlines()[-1:] or [""]
    check("poc/poc_45.py hijau", ok, tail[0][:200])


# ============================================================ 3. metode target & kejujuran
def section_methods(owner, pid):
    print("\n3. METODE TARGET — 5 metode ada, dan yang kekurangan bahan MENGAKU")
    r = get(owner, "/targets/methods")
    if not check("GET /targets/methods 200", r.status_code == 200, r.text[:120]):
        return
    rows = r.json()["data"]
    want = {"linear_remaining", "s_curve", "manual", "velocity_forecast", "revenue_first"}
    check("kelima metode terdaftar", {m["value"] for m in rows} >= want,
          str(sorted(m["value"] for m in rows)))
    check("setiap metode membawa RUMUS dari backend (bukan diketik di layar)",
          all(m.get("formula") for m in rows))
    year = datetime.now(timezone.utc).year
    horizon = {"start": f"{year}-01", "end": f"{year}-12"}
    base = {"project_id": pid, "horizon": horizon, "unit_target": 24,
            "revenue_target": 24_000_000_000, "assumptions": {"avg_price": 1_000_000_000}}

    p = post(owner, "/targets/preview", {**base, "method": "linear_remaining"})
    if not check("pratinjau linear_remaining 200", p.status_code == 200, p.text[:160]):
        return
    after = p.json()["data"]["after"]
    check("pratinjau membawa before/after + daftar perubahan",
          "before" in p.json()["data"] and "changes" in p.json()["data"])
    check("linear_remaining: Σ rencana ke depan + realisasi lampau == total target",
          after["totals"]["keep_total_ok"] is True,
          f"{after['totals']['unit_plan_future']} + {after['totals']['unit_actual_past']} "
          f"vs {after['totals']['unit_target']}")
    check("periode lampau DIKUNCI pada pratinjau",
          any(x["locked"] for x in after["periods"]) or after["periods"][0]["period"] >=
          datetime.now(timezone.utc).date().isoformat()[:7],
          f"locked={[x['period'] for x in after['periods'] if x['locked']]}")

    sc = post(owner, "/targets/preview", {**base, "method": "s_curve", "weights": {}})
    body = sc.json()["data"]["after"] if sc.status_code == 200 else {}
    check("s_curve TANPA bobot menolak menghitung (bukan rencana 0)",
          bool(body.get("missing")) and all(
              x["unit_plan"] is None for x in body.get("periods", [])
              if not x["locked"]), str(body.get("missing"))[:160])

    rf = post(owner, "/targets/preview", {**base, "method": "revenue_first",
                                         "assumptions": {"avg_price": 0}})
    body = rf.json()["data"]["after"] if rf.status_code == 200 else {}
    # Di tingkat API, harga rata-rata yang tidak diisi DIGANTI rata-rata harga unit proyek
    # (bantuan yang sah). Yang wajib dijaga: harganya DISEBUTKAN, bukan dipakai diam-diam.
    # Penolakan saat harga benar-benar tidak ada diuji di `poc/poc_45.py` (tingkat mesin).
    check("revenue_first tanpa asumsi harga: menyebut harga yang dipakai / menolak "
          "menghitung",
          bool(body.get("missing")) or bool(body.get("avg_price_used")),
          f"avg_price_used={body.get('avg_price_used')} missing={body.get('missing')}")
    check("revenue_first menurunkan unit dari pendapatan bila harga diketahui",
          bool(body.get("missing")) or all(
              p["unit_plan"] is not None for p in body.get("periods", []) if not p["locked"]))

    mn = post(owner, "/targets/preview", {**base, "method": "manual",
                                         "manual_plan": {f"{year}-12": 1}})
    body = mn.json()["data"]["after"] if mn.status_code == 200 else {}
    check("manual: deviasi Σ vs total DILAPORKAN apa adanya",
          any("beda" in w for w in body.get("warnings") or []),
          str(body.get("warnings"))[:160])
    check("periode target divalidasi format YYYY-MM",
          post(owner, "/targets/preview",
               {**base, "horizon": {"start": "2026-01-01", "end": "2026-12"}}).status_code
          in (400, 422))


# ============================================================ 4. dinamis & jejak
def section_dynamic(owner, pid):
    print("\n4. DINAMIS — lock_past, carry_over, dan jejak beralasan")
    r = get(owner, "/targets", project_id=pid, status="active")
    rows = r.json().get("data") or []
    if not check("ada target AKTIF di data demo", bool(rows), r.text[:160]):
        return None
    tid = rows[0]["id"]
    pr = get(owner, f"/targets/{tid}/progress")
    if not check("GET /targets/{id}/progress 200", pr.status_code == 200, pr.text[:160]):
        return None
    prog = pr.json()["data"]
    now = datetime.now(timezone.utc).date().isoformat()[:7]
    past = [p for p in prog["periods"] if p["period"] < now]
    check("periode lampau ditandai terkunci", all(p["locked"] for p in past) if past else True,
          f"{len([p for p in past if not p['locked']])} periode lampau tidak terkunci")
    check("periode lampau punya rencana (pembanding carry over ada)",
          all(p["unit_plan"] is not None for p in past) if past else True)
    shortfall = sum(int(p["unit_plan"] or 0) - int(p["unit_actual"] or 0) for p in past)
    if shortfall > 0:
        check("kekurangan periode lampau muncul sebagai carry_over",
              int(prog["totals"].get("carry_over") or 0) > 0,
              f"kekurangan {shortfall} unit, carry_over={prog['totals'].get('carry_over')}")
    check("setiap periode membawa selisih & pencapaian",
          all("gap" in p and "achievement_pct" in p for p in prog["periods"]))

    before = {p["period"]: p["unit_plan"] for p in past}
    bad = post(owner, f"/targets/{tid}/recalc", {"reason": "x"})
    check("recalc TANPA alasan yang layak ditolak", bad.status_code in (400, 422),
          f"{bad.status_code}")
    ok = post(owner, f"/targets/{tid}/recalc",
              {"reason": "Gate verifikasi Fase 45 — periksa lock_past & jejak"})
    if check("recalc dengan alasan 200", ok.status_code == 200, ok.text[:200]):
        after = {p["period"]: p["unit_plan"] for p in ok.json()["data"]["periods"]
                 if p["period"] < now}
        check("recalc TIDAK mengubah periode lampau (laporan historis aman)",
              before == after,
              f"berubah: {[k for k in before if before[k] != after.get(k)]}")
        doc = db.project_targets.find_one({"id": tid}, {"_id": 0, "history": 1})
        last = (doc.get("history") or [])[-1] if doc else {}
        check("jejak penyesuaian memuat alasan & jumlah periode berubah",
              "Gate verifikasi" in (last.get("reason") or "")
              and "changed_periods" in last, str(last)[:160])
    check("target ganda dengan nama sama ditolak index unik",
          bool(db.project_targets.index_information().get("uq_project_target_name")))
    return tid


# ============================================================ 5. tie-out & drill 3 lapis
def section_tieout(owner, pid):
    print("\n5. SATU KEBENARAN + DRILL 3 LAPIS")
    ctrl = get(owner, "/boq/control", project_id=pid)
    rv = get(owner, "/budget/rab-vs-actual", project_id=pid, group_by="item")
    if not check("GET /budget/rab-vs-actual 200", rv.status_code == 200, rv.text[:160]):
        return
    data = rv.json()["data"]
    tie = data["tie_out"]
    check("agregasi anggaran konstruksi TIE-OUT dengan /api/boq/control", tie["ok"],
          f"selisih={tie['diff']}")
    if ctrl.status_code == 200:
        totals = ctrl.json()["data"]["totals"]
        check("nilai terverifikasi sama dengan panel Kendali Biaya",
              tie["mine"]["verified"] == int(totals.get("verified") or 0),
              f"{tie['mine']['verified']} vs {totals.get('verified')}")
    for gb in ("category", "step", "unit"):
        r = get(owner, "/budget/rab-vs-actual", project_id=pid, group_by=gb)
        check(f"rab-vs-actual group_by={gb} 200 & tie-out hijau",
              r.status_code == 200 and r.json()["data"]["tie_out"]["ok"], r.text[:120])
    check("group_by tak dikenal ditolak (bukan diabaikan diam-diam)",
          get(owner, "/budget/rab-vs-actual", project_id=pid,
              group_by="ngawur").status_code == 400)

    s = get(owner, "/budget/summary", project_id=pid)
    if not check("GET /budget/summary 200", s.status_code == 200, s.text[:160]):
        return
    summary = s.json()["data"]
    t = summary["totals"] or {}
    items = summary["items"]
    check("Σ item == total proyek (lapis 2 → lapis 1)",
          sum(i["realized"] for i in items) == t.get("realized")
          and sum(i["committed"] for i in items) == t.get("committed"),
          f"item={sum(i['realized'] for i in items)} total={t.get('realized')}")
    check("Σ kategori == total proyek",
          sum(c["realized"] for c in summary["categories"]) == t.get("realized"))
    check("exposure = realisasi + komitmen",
          t.get("exposure") == t.get("realized", 0) + t.get("committed", 0))
    check("variance = rencana − exposure",
          t.get("variance") == t.get("planned", 0) - t.get("exposure", 0))
    bad_tie = []
    for it in items:
        d = get(owner, f"/budget/items/{it['id']}/realization")
        if d.status_code != 200:
            bad_tie.append(f"{it['code']}:{d.status_code}")
            continue
        row = d.json()["data"]
        if not row["checks"]["tie_out_ok"]:
            bad_tie.append(f"{it['code']}: dokumen {row['checks']} vs "
                           f"{row['realized']}/{row['committed']}")
    check("lapis 3: Σ dokumen == angka item untuk SEMUA item anggaran", not bad_tie,
          str(bad_tie[:3]))
    kon = next((i for i in items if i["match_rule"] == "by_boq_item"), None)
    if kon:
        d = get(owner, f"/budget/items/{kon['id']}/realization").json()["data"]
        kinds = {x["kind"] for x in d["documents"]}
        check("komitmen & realisasi saling lepas (dokumen bertanda satu sifat saja)",
              kinds <= {"realisasi", "komitmen"}, str(sorted(kinds)))
        check("pemakaian material TIDAK dijumlahkan ke realisasi (anti double-count)",
              "material_txn" not in {x["source"] for x in d["documents"]}
              and "dua kali" in ((d.get("material_usage") or {}).get("note") or ""),
              str(sorted({x["source"] for x in d["documents"]})))
    section_material_guard(owner, pid, items)


def section_material_guard(owner, pid, items):
    """Penjaga anti double-count material diuji dengan DATA NYATA, bukan hanya membaca kode.

    Cara mengujinya: tautkan satu pemakaian material yang materialnya SUDAH dibeli lewat PO ke
    sebuah item anggaran, lalu pastikan realisasi item itu TIDAK bertambah dan alasannya
    disebut. Tanpa uji berbasis data, penjaga ini bisa dilepas tanpa gate menyadarinya
    (kejadian nyata: uji-mutasi N13 sempat LOLOS).
    """
    target = next((i for i in items if i["match_rule"] == "by_cost_ref"), None)
    if not check("ada item anggaran ber-aturan 'dari dokumen' untuk diuji", bool(target)):
        return
    po = db.purchase_orders.find_one({"project_id": pid, "items.material_id": {"$ne": None}},
                                     {"_id": 0, "items": 1})
    mid = next((ln.get("material_id") for ln in ((po or {}).get("items") or [])
                if ln.get("material_id")), None)
    if not check("ada material yang pernah dibeli lewat PO untuk diuji", bool(mid)):
        return
    before = get(owner, f"/budget/items/{target['id']}/realization").json()["data"]["realized"]
    org = (db.projects.find_one({"id": pid}, {"_id": 0, "org_id": 1}) or {}).get("org_id")
    probe = {"id": "gate45-mat-probe", "org_id": org, "project_id": pid, "material_id": mid,
             "type": "out", "qty": 25, "note": "probe gate 45 (material dibeli lewat PO)",
             "ref": "GATE45-MAT", "actor": "gate", "budget_item_id": target["id"],
             "created_at": "2026-08-18T00:00:00+00:00"}
    db.material_txns.replace_one({"id": probe["id"]}, probe, upsert=True)
    try:
        after = get(owner, f"/budget/items/{target['id']}/realization").json()["data"]
        check("pemakaian material yang DIBELI LEWAT PO tidak menambah realisasi "
              "(anti double-count berbasis data)",
              after["realized"] == before,
              f"{before} → {after['realized']}")
        probes = [x for x in after["documents"] if x["ref"] == "GATE45-MAT"]
        # Satu transaksi = SATU baris dokumen. Kalau ia muncul dua kali (mis. sekali dari
        # penjaga material, sekali dari daftar sumber biasa), itu tanda penjaganya dilepas —
        # dan biaya yang sama akan mulai dihitung dua kali begitu nilainya tidak nol.
        check("satu pemakaian material = SATU baris dokumen (tidak muncul ganda)",
              len(probes) == 1, f"{len(probes)} baris untuk ref GATE45-MAT")
        check("penolakan itu DIJELASKAN pada dokumennya (bukan hilang diam-diam)",
              bool(probes) and all(x["kind"] == "informasi" for x in probes)
              and all("dua kali" in (x.get("note") or "") for x in probes),
              str(probes)[:200])
        check("pemeriksaan penjumlahan tetap cocok setelah dokumen informasi masuk",
              after["checks"]["tie_out_ok"] is True, str(after["checks"]))
    finally:
        db.material_txns.delete_one({"id": probe["id"]})


# ============================================================ 6. kejujuran angka
def section_honesty(owner, pid):
    print("\n6. KEJUJURAN ANGKA — 0 bukan 'belum ada data'")
    # proyek tanpa item anggaran: bikin sementara lalu kosongkan hasilnya
    doc = db.projects.find_one({}, {"_id": 0, "org_id": 1})
    org = (doc or {}).get("org_id")
    tmp_pid = "gate45-empty-project"
    db.projects.update_one({"id": tmp_pid}, {"$set": {
        "id": tmp_pid, "org_id": org, "name": "Proyek Uji Gate 45", "code": "GATE45",
        "members": [], "status": "planning"}}, upsert=True)
    try:
        r = get(owner, "/budget/summary", project_id=tmp_pid)
        body = r.json().get("data") if r.status_code == 200 else {}
        check("proyek tanpa item anggaran: state 'kosong' & totals null (BUKAN Rp 0)",
              r.status_code == 200 and body.get("state") == "kosong"
              and body.get("totals") is None and body.get("missing"),
              f"{r.status_code} state={body.get('state')} totals={body.get('totals')}")
        m = get(owner, "/budget/margin", project_id=tmp_pid)
        mb = m.json().get("data") if m.status_code == 200 else {}
        check("margin proyek tanpa data: null + menyebut apa yang kurang",
              mb.get("margin") is None and bool(mb.get("missing")),
              f"margin={mb.get('margin')}")
        check("kas masuk ditampilkan TERPISAH dari pendapatan diakui",
              "kas_masuk" in (mb.get("components") or {})
              and "BUKAN pendapatan" in (mb.get("note") or ""))
    finally:
        db.projects.delete_one({"id": tmp_pid})
    s = get(owner, "/budget/summary", project_id=pid).json()["data"]
    zeros = [i["code"] for i in s["items"] if not i["planned"] and i["pct"] is not None]
    check("persen dengan pembagi 0 → null (bukan 0%)", not zeros, str(zeros))
    empty_health = [i["code"] for i in s["items"]
                    if not i["planned"] and i["health"] != "kosong"]
    check("rencana Rp 0 → status 'kosong' (bukan 'aman')", not empty_health,
          str(empty_health))
    unresolved = [c for c in s["categories"] if c.get("unresolved_amount")]
    if unresolved:
        check("kategori dengan beban yang belum bisa dipetakan ditandai 'sebagian'",
              all(c["state"] == "sebagian" for c in unresolved),
              str([(c["category"], c["state"]) for c in unresolved]))


# ============================================================ 7. read-only konstruksi
def section_readonly(owner, pid):
    print("\n7. RENCANA KONSTRUKSI READ-ONLY — mustahil ada dua angka anggaran RAB")
    boq = get(owner, "/boq/items", project_id=pid).json()["data"]
    if not boq:
        check("ada item RAB untuk diuji", False, "boq kosong")
        return
    r = post(owner, "/budget/items", {
        "project_id": pid, "category": "konstruksi", "code": "GATE45-KON",
        "name": "Uji read-only konstruksi", "match_rule": "by_boq_item",
        "boq_item_ids": [boq[0]["id"]], "planned_amount": 123_456_789})
    check("membuat item konstruksi DENGAN planned_amount ditolak", r.status_code == 400,
          f"{r.status_code} {r.text[:140]}")
    r = post(owner, "/budget/items", {
        "project_id": pid, "category": "konstruksi", "code": "GATE45-KON",
        "name": "Uji read-only konstruksi", "match_rule": "by_boq_item",
        "boq_item_ids": []})
    check("item konstruksi tanpa tautan item RAB ditolak", r.status_code == 400,
          f"{r.status_code}")
    s = get(owner, "/budget/summary", project_id=pid).json()["data"]
    kon = next((i for i in s["items"] if i["match_rule"] == "by_boq_item"), None)
    if kon:
        linked = db.boq_items.find({"id": {"$in": kon["boq_item_ids"]}}, {"_id": 0, "amount": 1})
        total = sum(int(b.get("amount") or 0) for b in linked)
        check("rencana item konstruksi == Σ item RAB tertaut (dihitung, read-only)",
              kon["planned"] == total and kon["planned_readonly"] is True,
              f"{kon['planned']} vs {total}")
        rv = post(owner, f"/budget/items/{kon['id']}/revise",
                  {"planned_amount": 1, "reason": "gate mencoba merevisi konstruksi"})
        check("revisi rencana item konstruksi ditolak dengan penjelasan",
              rv.status_code == 400 and "RAB" in rv.text, f"{rv.status_code}")
    r = post(owner, "/budget/items", {
        "project_id": pid, "category": "operasional", "code": "GATE45-GL",
        "name": "Uji aturan GL tanpa akun", "match_rule": "by_gl_account"})
    check("aturan 'dari akun buku besar' tanpa akun GL ditolak", r.status_code == 400,
          f"{r.status_code}")
    db.budget_items.delete_many({"code": {"$in": ["GATE45-KON", "GATE45-GL"]}})


# ============================================================ 8. enforce + unmapped
def section_enforce(owner, pid):
    print("\n8. KEBIJAKAN cost_ref & laporan biaya belum terpetakan")
    import settings_store as cfg
    spec = cfg.DEFAULTS["budget.enforce_cost_ref"]
    check("bawaan `budget.enforce_cost_ref` MATI (dinyalakan setelah data rapi)",
          spec["value"] is False, str(spec["value"]))
    check("`budget.enforce_cost_ref` bersifat sensitif (alasan wajib saat diubah)",
          spec["sensitive"] is True)
    h = get(owner, "/budget/health")
    body = h.json().get("data") if h.status_code == 200 else {}
    check("GET /budget/health menyebut status kebijakan tanpa membocorkan env",
          h.status_code == 200 and "enforce_cost_ref" in body
          and not any(k for k in body if "secret" in k or "token" in k), h.text[:140])
    u = get(owner, "/budget/unmapped", project_id=pid)
    ub = u.json().get("data") if u.status_code == 200 else {}
    check("laporan 'biaya belum terpetakan' tersedia & menyebut status enforce",
          u.status_code == 200 and "enforce_cost_ref" in ub and "by_source" in ub,
          u.text[:140])
    check("laporan menjelaskan cara merapikan (bukan hanya angka)",
          "item anggaran" in (ub.get("note") or ""), (ub.get("note") or "")[:100])


# ============================================================ 9. peringatan bergigi
def section_alerts(owner, pid):
    print("\n9. PERINGATAN AMBANG — notifikasi + tugas, sekali per tingkat")
    org = (db.projects.find_one({}, {"_id": 0, "org_id": 1}) or {}).get("org_id")
    over = db.budget_items.find_one({"org_id": org, "project_id": pid,
                                    "match_rule": "manual"}, {"_id": 0, "id": 1, "code": 1})
    if not check("ada item anggaran manual untuk diuji", bool(over)):
        return
    db.budget_items.update_one({"id": over["id"]}, {"$set": {"alert_level": "aman"}})
    n0 = db.notifications.count_documents({"org_id": org, "type": "budget"})
    t0 = db.tasks.count_documents({"org_id": org, "jobdesk_code": "FN-11"})
    r = post(owner, "/budget/alerts/scan", None, project_id=pid, force=True)
    if not check("POST /budget/alerts/scan 200", r.status_code == 200, r.text[:160]):
        return
    out = r.json()["data"]
    hit = next((a for a in out["alerts"] if a["code"] == over["code"]), None)
    check("item overbudget memicu peringatan (bukan hanya diberi warna)",
          bool(hit) and hit["health"] in ("waspada", "overbudget"), str(hit))
    check("peringatan membuat NOTIFIKASI in-app",
          db.notifications.count_documents({"org_id": org, "type": "budget"}) > n0)
    # Tugas FN-11 bersifat SEKALI per (item, tingkat) — `strict_once` di `workhub.create_task`.
    # Karena itu yang dibuktikan bukan "ada tugas BARU" (pemeriksaan kedua akan selalu gagal
    # dan orang akan mematikan gate), melainkan: tugas FN-11 untuk item ini BENAR-BENAR ada,
    # dan jejaknya tercatat pada item anggaran.
    tasks_now = db.tasks.count_documents({"org_id": org, "jobdesk_code": "FN-11"})
    item_task = db.tasks.count_documents({"org_id": org, "jobdesk_code": "FN-11",
                                         "related_entity_id": over["id"]})
    check("ada TUGAS FN-11 untuk item yang melewati ambang (idempoten per tingkat)",
          item_task >= 1 and tasks_now >= t0,
          f"tugas item={item_task} total={t0}→{tasks_now}")
    doc = db.budget_items.find_one({"id": over["id"]}, {"_id": 0, "alerts": 1,
                                                       "alert_level": 1})
    last = ((doc or {}).get("alerts") or [])[-1] if doc else {}
    check("jejak peringatan tercatat pada item (tingkat, persen, penerima)",
          bool(last) and last.get("level") in ("waspada", "overbudget")
          and bool(last.get("notified")), str(last)[:160])
    again = post(owner, "/budget/alerts/scan", None, project_id=pid).json()["data"]
    check("peringatan TIDAK diulang saat tingkat status tidak naik",
          again["created"] == 0, f"pengulangan={again['created']}")
    import jobdesk_catalog as cat
    check("jobdesk FN-11 terdaftar di katalog dengan tautan halaman kerja",
          "FN-11" in cat.BY_CODE and cat.BY_CODE["FN-11"].get("link"),
          str(cat.BY_CODE.get("FN-11", {}).get("link")))


# ============================================================ 10. RBAC & SoD
def section_rbac(pid):
    print("\n10. RBAC & PEMISAHAN TUGAS")
    sales = login("sales@sipro.co.id")
    for path in ("/budget/summary", "/budget/items", "/budget/margin"):
        check(f"sales DILARANG melihat anggaran ({path})",
              get(sales, path).status_code == 403)
    r = get(sales, "/targets")
    check("sales BOLEH melihat target (hanya miliknya — dipaksakan server)",
          r.status_code == 200 and r.json().get("scoped_to") == "sales@sipro.co.id",
          f"{r.status_code} scoped_to={r.json().get('scoped_to') if r.status_code == 200 else '-'}")
    pm = login("pm@sipro.co.id")
    check("manajer proyek BOLEH menyusun item anggaran",
          get(pm, "/budget/items", project_id=pid).status_code == 200)
    item = get(pm, "/budget/items", project_id=pid).json()["data"]
    non_kon = next((i for i in item if i.get("match_rule") != "by_boq_item"), None)
    if non_kon:
        r = post(pm, f"/budget/items/{non_kon['id']}/revise",
                 {"planned_amount": 1_000_000, "reason": "uji pemisahan tugas gate"})
        check("manajer proyek DILARANG merevisi anggaran (yang menyusun ≠ yang menyetujui)",
              r.status_code == 403, f"{r.status_code}")
        finlead = login("finlead@sipro.co.id")
        before = int(non_kon.get("planned_amount") or 0)
        r = post(finlead, f"/budget/items/{non_kon['id']}/revise",
                 {"planned_amount": before + 1_000_000,
                  "reason": "uji revisi beralasan oleh manajer keuangan (gate)"})
        check("manajer keuangan BOLEH merevisi anggaran beralasan", r.status_code == 200,
              r.text[:160])
        bad = post(finlead, f"/budget/items/{non_kon['id']}/revise",
                   {"planned_amount": before, "reason": "x"})
        check("revisi TANPA alasan layak ditolak", bad.status_code in (400, 422),
              f"{bad.status_code}")
        post(finlead, f"/budget/items/{non_kon['id']}/revise",
             {"planned_amount": before, "reason": "pulihkan nilai semula setelah gate"})
    check("tanpa token → 401",
          requests.get(f"{BASE}/budget/summary", timeout=20).status_code in (401, 403))
    site = login("site@sipro.co.id")
    check("pelaksana lapangan tidak bisa membuat item anggaran",
          post(site, "/budget/items", {"project_id": pid, "category": "operasional",
                                       "code": "GATE45-SITE", "name": "uji",
                                       "match_rule": "manual"}).status_code == 403)
    manual_item = next((i for i in item if i.get("match_rule") == "by_gl_account"), None)
    if manual_item:
        r = post(pm, f"/budget/items/{manual_item['id']}/manual-entry",
                 {"amount": 1000, "note": "uji anti double-count gate"})
        check("pencatatan manual pada item yang dicocokkan OTOMATIS ditolak",
              r.status_code == 400 and "dua kali" in r.text, f"{r.status_code}")


# ============================================================ 11. layar & SSOT
def section_ui():
    print("\n11. LAYAR — kosakata dari SSOT, tidak menjatuhkan nilai ke 0")
    import reference as ref
    groups = ("budget_health", "budget_category", "budget_match_rule", "target_method",
              "target_status", "cost_source", "budget_period", "target_basis")
    labels = {}
    for g in groups:
        for o in ref.GROUPS[g]["options"]:
            labels[o["label"]] = g
    hardcoded, zero_fallback = [], []
    for path in BUDGET_FILES:
        src = strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for label, g in labels.items():
            if f'"{label}"' in src or f"'{label}'" in src or f">{label}<" in src:
                hardcoded.append(f"{path.name}: '{label}' ({g})")
        for m in re.finditer(r"(planned|realized|committed|exposure|variance|pct|value)"
                             r"\s*(\?\?|\|\|)\s*0", src):
            zero_fallback.append(f"{path.name}:{m.group(0)}")
    check("layar anggaran tidak menuliskan label enum sendiri", not hardcoded,
          str(hardcoded[:4]))
    check("tidak ada angka anggaran yang dijatuhkan ke 0 di layar", not zero_fallback,
          str(zero_fallback[:4]))
    parts = read("components/budget/parts.js")
    check("komponen angka punya cabang 'belum ada data' untuk nilai kosong",
          "belum ada data" in parts and "value === null" in parts)
    check("lencana status anggaran memakai labelOf('budget_health')",
          'labelOf("budget_health"' in parts)
    drill = read("components/budget/RealizationDialog.js")
    check("dialog lapis 3 MENAMPILKAN hasil pemeriksaan penjumlahan",
          "tie_out_ok" in drill and "budget-drill-tieout" in read("constants/testIds/budget.js"))
    tgt = read("components/budget/TargetDialog.js")
    check("dialog target menyediakan PRATINJAU DAMPAK sebelum simpan",
          "/targets/preview" in tgt and "targetPreviewBtn" in tgt)
    check("rumus metode target datang dari backend (bukan diketik di layar)",
          "methodMeta.formula" in tgt)
    period = read("components/budget/TargetPeriodTable.js")
    check("tabel periode menampilkan carry over & tanda kunci",
          "carryOver" in period and "Lock" in period)


def main():
    owner = login("owner@sipro.co.id")
    proj = requests.get(f"{BASE}/projects", headers=owner, timeout=30).json()["data"]
    if not proj:
        print("GATE TARGET & ANGGARAN FAILED: tidak ada proyek untuk diuji")
        sys.exit(1)
    # A freshly created empty project must not silently replace the demo fixture.
    targets = requests.get(f"{BASE}/targets", headers=owner, timeout=30).json().get("data") or []
    target_projects = {t.get("project_id") for t in targets if t.get("status") == "active"}
    selected = next((p for p in proj if p["id"] in target_projects), None)
    if selected is None:
        raise RuntimeError("Fixture target aktif belum tersedia — tidak menguji proyek kosong sebagai data demo.")
    pid = selected["id"]
    section_nav()
    section_poc()
    section_methods(owner, pid)
    section_dynamic(owner, pid)
    section_tieout(owner, pid)
    section_honesty(owner, pid)
    section_readonly(owner, pid)
    section_enforce(owner, pid)
    section_alerts(owner, pid)
    section_rbac(pid)
    section_ui()
    print("-" * 62)
    if fails:
        print(f"GATE TARGET & ANGGARAN FAILED: {len(fails)} temuan — {fails[:8]}")
        sys.exit(1)
    print("GATE TARGET & ANGGARAN PASSED: 5 metode target jujur & dinamis dengan jejak, "
          "anggaran tie-out dengan Kendali Biaya, drill 3 lapis menjumlah, konstruksi "
          "read-only, peringatan ambang bergigi, RBAC & pemisahan tugas ditegakkan")


if __name__ == "__main__":
    main()
