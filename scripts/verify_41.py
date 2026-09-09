#!/usr/bin/env python3
"""verify_41.py — GATE JAM TAHAP & SLA (Fase 41).

Cacat NYATA yang dijaga gate ini (semuanya pernah ada di repo ini sampai Fase 40):

  1. **Umur tahap hanya turunan saat baca.** `listing.attach_aging` menghitung ulang
     `stage_entered_at` dari `stage_history` di setiap request → tidak bisa difilter, tidak
     bisa diagregasi, tidak bisa diberi index. Gate menuntut field TERSIMPAN pada 7 koleksi
     dan menuntut jam tahap SELALU sinkron dengan status nyata.
  2. **Ambang SLA angka mati di komponen** (72/48/168/336/720). Gate menolak literal
     `slaHours={<angka>}` di frontend DAN membuktikan lewat API bahwa mengubah setting SLA
     mengubah angka yang dipakai baris (kalau tidak, Pusat Konfigurasi cuma hiasan).
  3. **"Lewat SLA" tidak bisa difilter.** Gate menuntut `?sla=over` dieksekusi di database
     dan angkanya SAMA dengan laporan; nilai filter tak dikenal wajib mengosongkan hasil,
     bukan diabaikan diam-diam.
  4. **Angka laporan tidak bisa ditelusuri.** Setiap baris laporan wajib punya tautan drill
     ke rute yang benar-benar ada, dan jumlah per tahap wajib sama dengan hasil filter daftar.
  5. **RBAC**: semua peran boleh MELIHAT umur tahap; hanya admin/owner boleh menjalankan
     pemeliharaan `reconcile`.

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_41_42.py`.
"""
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
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
fails = []

ENTITIES = {
    "lead": ("leads", "stage"), "deal": ("deals", "status"), "task": ("tasks", "status"),
    "complaint": ("complaints", "status"), "customer": ("customers", "kyc_status"),
    "ar_invoice": ("ar_invoices", "status"), "document": ("documents", "status"),
}
SLA_KEYS = ["lead.sla_hours", "deal.sla_hours", "task.sla_hours", "complaint.sla_hours",
            "customer.sla_hours", "ar.sla_hours", "document.sla_hours"]
# Berkas yang menampilkan umur: tidak boleh lagi menuliskan ambang SLA sendiri.
AGING_USERS = ["pages/LeadsPage.js", "pages/LeadProfilePage.js", "components/work/TasksListTab.js",
               "components/complaints/ComplaintsListTab.js", "components/sales/DealsListTab.js",
               "components/customers/CustomersListTab.js", "components/finance/ArPanel.js"]


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


def code_only(src: str) -> str:
    """Buang baris komentar supaya pemeriksaan "tidak ada angka mati" menilai KODE,
    bukan penjelasan sejarahnya.

    Komponen umur tahap SENGAJA mendokumentasikan angka mati yang dulu dipakai
    (72/48/168/336/720) supaya perubahan Fase 41 bisa ditelusuri. Tanpa penyaring ini
    gate akan memerah karena KOMENTARNYA, bukan karena kodenya — persis jenis
    kegagalan palsu yang membuat gate tidak dipercaya lalu diabaikan.
    """
    out = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("*", "//", "/*")):
            continue
        out.append(line)
    return "\n".join(out)


def main():
    admin = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")
    # Jam tahap disamakan lebih dulu: sweeper berjalan tiap 60 detik, jadi tanpa langkah ini
    # gate bisa memerah hanya karena kebetulan dijalankan di dalam jendela itu. Yang diuji
    # adalah INVARIANNYA: setelah disamakan, TIDAK BOLEH ada satu pun baris yang tidak sinkron.
    requests.post(f"{BASE}/aging/reconcile", headers=admin, timeout=180)

    print("\n1. Jam tahap = FIELD TERSIMPAN (bukan turunan per request)")
    for entity, (col, field) in ENTITIES.items():
        total = db[col].count_documents({})
        if not total:
            print(f"  SKIP  {entity}: koleksi kosong")
            continue
        stamped = db[col].count_documents({"stage_entered_at": {"$ne": None}})
        check(f"{entity}: semua baris punya stage_entered_at", stamped == total,
              f"{stamped}/{total}")
        mismatch = db[col].count_documents(
            {"$expr": {"$ne": ["$stage_clock_stage", f"${field}"]}})
        check(f"{entity}: jam tahap sinkron dengan {field} nyata", mismatch == 0,
              f"{mismatch} baris tidak sinkron")
        with_sla = db[col].find_one({"stage_sla_hours": {"$ne": None}}, {"_id": 0})
        if with_sla:
            check(f"{entity}: baris ber-SLA punya stage_due_at", bool(with_sla.get("stage_due_at")))
    idx = [i["name"] for i in db.leads.list_indexes()]
    check("index umur tahap dibuat (filter bukan collection scan)",
          any("stage_due_at" in n or "stage_entered_at" in n for n in idx), ", ".join(idx[:6]))

    print("\n2. Ambang SLA berasal dari Pusat Konfigurasi, bukan angka mati di layar")
    src = code_only(read("components/patterns/AgingCell.js"))
    check("AgingCell tidak punya ambang bawaan", not re.search(r"slaHours\s*=\s*\d", src))
    # Keadaan SLA (`sla_state`) LAHIR di server dan MENGALIR lewat prop `state`. Karena itu
    # nama field-nya dibuktikan di sisi PEMANGGIL (loop di bawah), bukan di dalam sel:
    # mencari string "sla_state" di dalam AgingCell dulu bikin gate ini hijau hanya karena
    # ada KOMENTAR yang menyebutnya — bukti palsu. Yang wajib benar di sel: (a) keadaan
    # datang sebagai prop, (b) prop itu jadi sumber UTAMA, hitungan lokal cuma cadangan.
    check("AgingCell menerima keadaan SLA sebagai prop",
          bool(re.search(r"function\s+AgingCell\(\{[^}]*\bstate\b", src)))
    check("AgingCell memakai keadaan server sebagai sumber utama (bukan hitung sendiri)",
          bool(re.search(r"=\s*state\s*\|\|", src)))
    for rel in AGING_USERS:
        body = code_only(read(rel))
        if not check(f"{rel} ada", bool(body)):
            continue
        bad = re.findall(r"slaHours=\{\s*\d[^}]*\}", body)
        check(f"{pathlib.Path(rel).name} tidak menulis ambang SLA sendiri", not bad, str(bad[:2]))
        check(f"{pathlib.Path(rel).name} memakai ambang dari baris",
              "stage_sla_hours" in body)
        check(f"{pathlib.Path(rel).name} meneruskan keadaan SLA server ke sel umur",
              bool(re.search(r"state=\{[^}]*sla_state", body)))
    r = requests.get(f"{BASE}/settings/effective", headers=admin,
                     params={"keys": ",".join(SLA_KEYS)}, timeout=20)
    check("7 kebijakan SLA terdaftar di Pusat Konfigurasi",
          r.status_code == 200 and all(k in r.json()["data"] for k in SLA_KEYS), r.text[:120])

    print("\n3. Mengubah kebijakan SLA LANGSUNG berlaku pada baris yang sudah ada")
    pol = requests.get(f"{BASE}/aging/policy", headers=admin, timeout=20).json()["data"]
    base_pol = dict(pol["lead"]["sla_hours"])
    probe = {**base_pol, "nurturing": 3}
    requests.put(f"{BASE}/settings/lead.sla_hours", headers=admin,
                 json={"value": probe, "reason": "gate verify_41"}, timeout=60)
    rows = requests.get(f"{BASE}/leads", headers=admin,
                        params={"stage": "nurturing", "limit": 5}, timeout=30).json()["data"]
    if rows:
        check("baris memakai ambang SLA terbaru",
              all(float(x.get("stage_sla_hours") or 0) == 3 for x in rows),
              str([x.get("stage_sla_hours") for x in rows]))
        first = rows[0]
        due_ok = (bool(first.get("stage_due_at"))
                  and first["stage_due_at"] > first["stage_entered_at"])
        check("jatuh tempo dihitung ulang dari kebijakan baru", due_ok,
              f"{first.get('stage_entered_at')} → {first.get('stage_due_at')}")
    else:
        print("  SKIP  tidak ada lead nurturing untuk diuji")
    requests.put(f"{BASE}/settings/lead.sla_hours", headers=admin,
                 json={"value": base_pol, "reason": "gate verify_41 pulih"}, timeout=60)
    back = requests.get(f"{BASE}/aging/policy", headers=admin, timeout=20).json()["data"]
    check("kebijakan dipulihkan setelah uji",
          back["lead"]["sla_hours"].get("nurturing") == base_pol.get("nurturing"),
          str(back["lead"]["sla_hours"].get("nurturing")))

    print("\n4. Transisi tahap NYATA menulis jam tahap seketika")
    lead = db.leads.find_one({"stage": {"$in": ["nurturing", "appointment"]}}, {"_id": 0})
    if lead:
        before = lead.get("stage_entered_at")
        target = "appointment" if lead["stage"] == "nurturing" else "nurturing"
        r = requests.post(f"{BASE}/leads/{lead['id']}/stage/override", headers=admin,
                          json={"stage": target, "reason": "gate verify_41 transisi"}, timeout=30)
        check("override tahap = 200", r.status_code == 200, r.text[:120])
        fresh = db.leads.find_one({"id": lead["id"]}, {"_id": 0})
        check("stage_entered_at berubah saat pindah tahap",
              fresh.get("stage_entered_at") and fresh["stage_entered_at"] != before,
              f"{before} → {fresh.get('stage_entered_at')}")
        check("jam tahap menyebut tahap barunya",
              fresh.get("stage_clock_stage") == fresh.get("stage"),
              f"{fresh.get('stage_clock_stage')} vs {fresh.get('stage')}")
        check("asal jam tahap = transisi (bukan tebakan sweeper)",
              fresh.get("stage_clock_source") == "transition",
              str(fresh.get("stage_clock_source")))
    else:
        print("  SKIP  tidak ada lead yang bisa dipindah tahap")

    print("\n5. 'Lewat SLA' bisa DIFILTER di database & angkanya konsisten")
    report = requests.get(f"{BASE}/aging/report", headers=admin, params={"entity": "lead"},
                          timeout=30).json()["data"]
    over = requests.get(f"{BASE}/leads", headers=admin, params={"sla": "over", "limit": 1},
                        timeout=30).json()
    check("jumlah 'lewat SLA' daftar = laporan",
          over.get("total") == report["totals"]["over_sla"],
          f"daftar {over.get('total')} vs laporan {report['totals']['over_sla']}")
    over2 = requests.get(f"{BASE}/leads", headers=admin, params={"sla": "over2", "limit": 1},
                         timeout=30).json()
    check("jumlah 'lewat 2× SLA' daftar = laporan",
          over2.get("total") == report["totals"]["over2_sla"],
          f"{over2.get('total')} vs {report['totals']['over2_sla']}")
    junk = requests.get(f"{BASE}/leads", headers=admin, params={"sla": "ngawur", "limit": 1},
                        timeout=30).json()
    check("filter SLA tak dikenal → hasil kosong (tidak diabaikan diam-diam)",
          junk.get("total") == 0, str(junk.get("total")))
    rows = requests.get(f"{BASE}/leads", headers=admin, params={"sla": "over", "limit": 5},
                        timeout=30).json()["data"]
    check("setiap baris hasil filter memang berkeadaan lewat SLA",
          all(x.get("sla_state") in ("over", "over2") for x in rows),
          str([x.get("sla_state") for x in rows]))

    print("\n6. Laporan umur tahap bisa ditelusuri sampai barisnya")
    app_src = read("App.js")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', app_src))
    for row in report["rows"]:
        n = requests.get(f"{BASE}/leads", headers=admin,
                         params={"stage": row["stage"], "limit": 1}, timeout=30).json()
        check(f"jumlah tahap '{row['stage']}' laporan = hasil filter daftar",
              n.get("total") == row["count"], f"{row['count']} vs {n.get('total')}")
        check(f"drill '{row['drill']}' menuju route yang ada",
              row["drill"].split("?")[0] in routes)
    ovw = requests.get(f"{BASE}/aging/overview", headers=admin, timeout=60).json()
    check("ringkasan lintas domain memuat 7 objek", len(ovw.get("data") or []) == 7,
          f"{len(ovw.get('data') or [])} objek")
    for row in ovw.get("data") or []:
        check(f"ringkasan '{row['entity']}' punya tautan drill",
              row["drill"].split("?")[0] in routes, row["drill"])

    print("\n7. Permukaan UI: laporan umur tahap benar-benar bisa dibuka pemakai")
    tasks_page = read("pages/TasksPage.js")
    tab = read("components/work/AgingReportTab.js")
    check("tab 'Umur Tahap & SLA' terpasang di hub Kerja",
          "AgingReportTab" in tasks_page and "<AgingReportTab" in tasks_page)
    check("tab memakai endpoint aging (bukan hitung ulang di browser)",
          '"/aging/report"' in tab and '"/aging/overview"' in tab)
    check("tab memakai tautan drill dari backend", "r.drill" in tab and "drill_over" in tab)
    check("tombol pemeliharaan jam tahap ada untuk admin", '"/aging/reconcile"' in tab)
    check("pemakai bisa menuju Pusat Konfigurasi untuk mengubah SLA",
          "/config?group=sla" in tab)
    check("filter umur/SLA seragam dipakai daftar",
          "slaFilter" in read("pages/LeadsPage.js")
          and "slaFilter" in read("components/work/TasksListTab.js"))

    print("\n8. RBAC: semua peran melihat, hanya admin memelihara")
    r = requests.get(f"{BASE}/aging/report", headers=sales, params={"entity": "lead"}, timeout=30)
    check("sales boleh melihat laporan umur tahap", r.status_code == 200, f"got {r.status_code}")
    r = requests.post(f"{BASE}/aging/reconcile", headers=sales, timeout=60)
    check("sales TIDAK boleh menjalankan pemeliharaan", r.status_code == 403,
          f"got {r.status_code}")
    r = requests.post(f"{BASE}/aging/reconcile", headers=admin, timeout=120)
    check("admin boleh menjalankan pemeliharaan", r.status_code == 200, r.text[:120])
    r = requests.get(f"{BASE}/aging/report", headers=admin, params={"entity": "ngawur"},
                     timeout=20)
    check("objek umur tahap tak dikenal = 400", r.status_code == 400, f"got {r.status_code}")

    print("-" * 60)
    if fails:
        print(f"GATE 41 FAILED: {len(fails)} temuan — {fails[:8]}")
        sys.exit(1)
    print("GATE 41 PASSED: jam tahap tersimpan & sinkron, ambang SLA dari Pusat Konfigurasi, "
          "umur tahap bisa difilter & ditelusuri")


if __name__ == "__main__":
    main()
