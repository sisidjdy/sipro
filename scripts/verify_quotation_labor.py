#!/usr/bin/env python3
"""verify_quotation_labor.py — GATE PENAWARAN & UPAH HARIAN (Fase 47C + 47D).

PENAWARAN (47C) — janji yang dijaga:
  Q1  **Tidak ada rumus kedua.** Σ termin penawaran = harga penawaran, dan termin lahir dari
      mesin AR (`finance_engine.compute_scheme_items`) — bukan hitungan layar.
  Q2  **Simulasi KPR jujur.** Tanpa tenor/bunga/DP, hasilnya `missing_data` beserta daftar
      apa yang kurang — BUKAN Rp 0 yang terbaca “tanpa angsuran”. Dengan data, angsurannya
      sama dengan rumus anuitas yang bisa dihitung ulang tangan.
  Q3  **Diskon berjenjang.** Di atas kewenangan: wajib beralasan, berstatus menunggu
      persetujuan, TIDAK bisa dikonversi sebelum diputuskan, dan keputusan wajib beralasan.
  Q4  **Revisi = versi baru**; versi lama tetap terbaca sebagai “diganti”.
  Q5  **Konversi sekali saja** dan menghasilkan reservasi unit yang nyata.
  Q6  **RBAC**: sales tidak boleh menyetujui diskonnya sendiri; lapangan tidak punya akses.

UPAH HARIAN (47D) — janji yang dijaga:
  L1  Absensi masa depan & orang kembar DITOLAK; koreksi hari yang sama MEMPERBARUI baris
      (berjejak), bukan melahirkan baris kembar.
  L2  Upah bisa dihitung ulang tangan: hari × tarif + lembur × (tarif/jam) × pengali;
      setengah hari = 0,5 × tarif.
  L3  Rekap upah TIE-OUT dengan absensi; periode bertumpang DITOLAK; absensi pada periode
      yang sudah direkap TERKUNCI.
  L4  Selisih dengan buku harian DILAPORKAN apa adanya (tidak menimpa salah satu).
  L5  Pemisahan tugas: yang mencatat MENGAJUKAN, keuangan MENYETUJUI & MEMBAYAR; bayar
      sebelum disetujui ditolak; pembayaran melahirkan jurnal seimbang & tidak bisa dobel.
  L6  **RBAC**: sales tidak punya akses absensi/upah.

Bahan uji dibuat sendiri (unit/lead/pekerja bertanda `gate47`) lalu dibuang.
Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_47.py`.
"""
import pathlib
import sys
from datetime import date, timedelta

import requests
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _fixture47 as fx  # noqa: E402

BASE = fx.BASE
db = fx.db
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def head(title):
    print(f"\n{title}\n" + "-" * len(title))


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def anuitas(pokok: int, tenor: int, rate_pct: float) -> int:
    i = rate_pct / 100.0 / 12.0
    if i <= 0:
        return int(round(pokok / tenor))
    factor = (1 + i) ** tenor
    return int(round(pokok * i * factor / (factor - 1)))


def quotation_part(manager, sales, site, ctx) -> None:
    lead_id = ctx["lead"]["id"]
    unit = db.units.find_one({"org_id": fx.ORG, "status": "available", fx.TAG: True},
                             {"_id": 0}) or {}

    head("Q1. Termin penawaran TIE-OUT dengan mesin AR (tidak ada rumus kedua)")
    sim = requests.post(f"{BASE}/quotations/simulate", headers=manager, timeout=40, json={
        "unit_id": unit["id"], "addons": [], "discount_amount": 0})
    d = sim.json().get("data", {}) if sim.ok else {}
    terms_total = sum(int(t["amount"]) for t in d.get("terms") or [])
    check("Σ termin = harga penawaran", sim.ok and terms_total == int(d.get("net_price") or -1),
          f"{terms_total} vs {d.get('net_price')}")
    check("setiap termin punya label & jatuh tempo (bisa dibaca pembeli)",
          bool(d.get("terms")) and all(t.get("label") and t.get("due_date")
                                       for t in d["terms"]),
          str(len(d.get("terms") or [])))

    head("Q2. Simulasi KPR jujur (kosong = belum ada data, terisi = anuitas yang bisa diulang)")
    check("tanpa tenor/bunga/DP: state 'missing_data' + daftar yang kurang (bukan Rp 0)",
          (d.get("kpr") or {}).get("state") == "missing_data"
          and len((d["kpr"] or {}).get("missing") or []) >= 2
          and (d["kpr"] or {}).get("monthly_installment") is None,
          str((d.get("kpr") or {}).get("missing")))
    sim2 = requests.post(f"{BASE}/quotations/simulate", headers=manager, timeout=40, json={
        "unit_id": unit["id"], "discount_amount": 0,
        "kpr": {"tenor_months": 180, "annual_rate_pct": 9.5, "dp_pct": 20}})
    k = sim2.json().get("data", {}).get("kpr", {}) if sim2.ok else {}
    manual = anuitas(int(k.get("loan_amount") or 0), 180, 9.5) if k else -1
    check("angsuran = rumus anuitas yang bisa dihitung ulang tangan",
          abs(int(k.get("monthly_installment") or 0) - manual) <= 1,
          f"{k.get('monthly_installment')} vs {manual}")

    head("Q3. Diskon di atas kewenangan: beralasan, menunggu persetujuan, tak bisa dikonversi")
    # Fase 69: diskon TIDAK diketik bebas — lahir dari SKEMA DISKON yang dikonfigurasi.
    manual = requests.post(f"{BASE}/quotations", headers=manager, timeout=40, json={
        "lead_id": lead_id, "unit_id": unit["id"], "discount_amount": 1000})
    check("diskon manual (angka ketikan) DITOLAK", manual.status_code == 400,
          str(manual.json().get("detail"))[:90])
    big = int(int(unit["price"]) * 0.10)
    tag = fx.TAG.upper().replace("_", "")
    requests.post(f"{BASE}/pricing/discount-schemes", headers=manager, timeout=30, json={
        "code": f"{tag}-BIG", "name": "Diskon besar bahan uji gate", "kind": "amount",
        "value": big, "note": "bahan uji gate — dibuang otomatis"})
    requests.post(f"{BASE}/pricing/discount-schemes", headers=manager, timeout=30, json={
        "code": f"{tag}-OVER", "name": "Diskon melebihi harga bahan uji gate", "kind": "amount",
        "value": int(int(unit["price"]) * 2), "note": "bahan uji gate — dibuang otomatis"})
    schemes = {s["code"]: s["id"] for s in requests.get(
        f"{BASE}/pricing/discount-schemes", headers=manager, timeout=30).json().get("data", [])}
    big_id, over_id = schemes.get(f"{tag}-BIG"), schemes.get(f"{tag}-OVER")
    no_reason = requests.post(f"{BASE}/quotations", headers=manager, timeout=40, json={
        "lead_id": lead_id, "unit_id": unit["id"], "discount_scheme_id": big_id})
    check("diskon besar tanpa alasan DITOLAK", no_reason.status_code == 400,
          str(no_reason.json().get("detail"))[:90])
    over = requests.post(f"{BASE}/quotations", headers=manager, timeout=40, json={
        "lead_id": lead_id, "unit_id": unit["id"], "discount_scheme_id": over_id})
    check("diskon melebihi harga DITOLAK", over.status_code == 400, f"got {over.status_code}")
    q = requests.post(f"{BASE}/quotations", headers=manager, timeout=40, json={
        "lead_id": lead_id, "unit_id": unit["id"], "discount_scheme_id": big_id,
        "discount_reason": "Unit slow moving; margin masih di atas ambang (bahan uji gate)."})
    doc = q.json().get("data", {}) if q.ok else {}
    check("penawaran berdiskon besar berstatus MENUNGGU PERSETUJUAN",
          q.ok and doc.get("state") == "awaiting_approval", str(doc.get("state")))
    check("rincian potongan tersimpan dari SKEMA (bukan angka ketikan)",
          bool(doc.get("discount_lines")) and doc["discount_lines"][0].get("source")
          == "discount_scheme" and int(doc.get("discount_amount") or 0) == big,
          str(doc.get("discount_amount")))
    db.discount_schemes.delete_many({"code": {"$in": [f"{tag}-BIG", f"{tag}-OVER"]}})
    qid = doc.get("id")
    early = requests.post(f"{BASE}/quotations/{qid}/convert", headers=manager, timeout=40)
    check("konversi sebelum diskon disetujui DITOLAK", early.status_code == 400,
          str(early.json().get("detail"))[:90])
    short = requests.post(f"{BASE}/quotations/{qid}/decision", headers=manager, timeout=30,
                          json={"approve": True, "reason": "ok"})
    check("keputusan diskon tanpa dasar yang layak DITOLAK", short.status_code in (400, 422),
          f"got {short.status_code}")
    ok = requests.post(f"{BASE}/quotations/{qid}/decision", headers=manager, timeout=30,
                       json={"approve": True,
                             "reason": "Disetujui: unit slow moving, margin masih sehat."})
    check("manajer menyetujui diskon + alasannya tersimpan",
          ok.status_code == 200
          and bool((db.quotations.find_one({"id": qid}, {"_id": 0}) or {}).get("decision_reason")),
          ok.text[:110])

    head("Q4/Q5. Revisi = versi baru; konversi sekali saja")
    rev = requests.post(f"{BASE}/quotations/{qid}/revise", headers=manager, timeout=40, json={
        "lead_id": lead_id, "unit_id": unit["id"], "discount_amount": 0})
    new = rev.json().get("data", {}) if rev.ok else {}
    old = db.quotations.find_one({"id": qid}, {"_id": 0}) or {}
    check("revisi membuat versi baru & versi lama menjadi 'diganti'",
          new.get("version") == 2 and old.get("state") == "superseded",
          f"v{new.get('version')} lama={old.get('state')}")
    pdf = requests.get(f"{BASE}/quotations/{new.get('id')}/pdf", headers=manager, timeout=40)
    check("PDF penawaran bisa diunduh (berisi angka yang tersimpan)",
          pdf.status_code == 200 and "pdf" in pdf.headers.get("content-type", "")
          and len(pdf.content) > 800,
          f"{pdf.status_code} {pdf.headers.get('content-type')} {len(pdf.content)}B")
    send = requests.post(f"{BASE}/quotations/{new.get('id')}/send", headers=manager, timeout=40,
                         json={"channel": "whatsapp"})
    check("pengiriman ke pembeli tercatat (mode simulasi bila kredensial belum ada)",
          send.status_code == 200, send.text[:110])
    conv = requests.post(f"{BASE}/quotations/{new.get('id')}/convert", headers=manager,
                         timeout=60)
    check("konversi membuat reservasi unit yang NYATA",
          conv.status_code == 200 and bool(conv.json()["data"]["deal"]["id"]),
          conv.text[:110])
    unit_after = db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1}) or {}
    check("unit menjadi 'reserved' setelah konversi", unit_after.get("status") == "reserved",
          str(unit_after.get("status")))
    twice = requests.post(f"{BASE}/quotations/{new.get('id')}/convert", headers=manager,
                          timeout=40)
    check("penawaran yang sudah dikonversi tidak bisa dikonversi lagi",
          twice.status_code == 400, f"got {twice.status_code}")

    head("Q6. RBAC penawaran")
    s_dec = requests.post(f"{BASE}/quotations/{new.get('id')}/decision", headers=sales,
                          timeout=30, json={"approve": True, "reason": "Saya setujui sendiri"})
    check("sales TIDAK boleh menyetujui diskon (403)", s_dec.status_code == 403,
          f"got {s_dec.status_code}")
    site_q = requests.get(f"{BASE}/quotations", headers=site, timeout=25)
    check("peran lapangan tidak punya akses penawaran (403)", site_q.status_code == 403,
          f"got {site_q.status_code}")


def labor_part(pm, finance, sales, project_id) -> None:
    head("L1. Master tenaga kerja & absensi yang tidak bisa dobel")
    made = []
    for name, role, wage in (("Uji Mandor Gate47", "mandor", 200_000),
                             ("Uji Tukang Gate47", "tukang", 160_000)):
        r = requests.post(f"{BASE}/labor/workers", headers=pm, timeout=30, json={
            "name": name, "role": role, "daily_wage": wage,
            "project_ids": [project_id], "note": "bahan uji gate 47D"})
        if r.ok:
            db.workers.update_one({"id": r.json()["data"]["id"]}, {"$set": {fx.TAG: True}})
            made.append(r.json()["data"])
    check("tenaga kerja bisa didaftarkan beserta tarif hariannya", len(made) == 2,
          f"{len(made)} dibuat")
    bad_role = requests.post(f"{BASE}/labor/workers", headers=pm, timeout=30, json={
        "name": "Uji Peran Ngawur", "role": "pesulap", "daily_wage": 100_000})
    check("peran di luar kamus SSOT DITOLAK", bad_role.status_code in (400, 422),
          f"got {bad_role.status_code}")
    zero = requests.post(f"{BASE}/labor/workers", headers=pm, timeout=30, json={
        "name": "Uji Tarif Nol", "role": "tukang", "daily_wage": 0})
    check("tarif harian nol DITOLAK (upah harus bisa dihitung)",
          zero.status_code in (400, 422), f"got {zero.status_code}")
    if len(made) < 2:
        return
    w1, w2 = made
    d0 = day(-42)
    future = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=30, json={
        "project_id": project_id, "work_date": day(3),
        "entries": [{"worker_id": w1["id"], "status": "full"}]})
    check("absensi untuk tanggal yang BELUM terjadi DITOLAK", future.status_code == 400,
          str(future.json().get("detail"))[:80])
    twin = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=30, json={
        "project_id": project_id, "work_date": d0,
        "entries": [{"worker_id": w1["id"], "status": "full"},
                    {"worker_id": w1["id"], "status": "half"}]})
    check("satu orang dua kali dalam satu kiriman DITOLAK", twin.status_code == 400,
          str(twin.json().get("detail"))[:80])

    head("L2. Upah bisa dihitung ulang tangan")
    a = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=40, json={
        "project_id": project_id, "work_date": d0, "entries": [
            {"worker_id": w1["id"], "status": "full", "overtime_hours": 2},
            {"worker_id": w2["id"], "status": "half"}]})
    check("absensi tersimpan", a.status_code == 200, a.text[:110])
    rates = requests.get(f"{BASE}/labor/rates", headers=pm, timeout=25).json()["data"]
    row1 = db.labor_attendance.find_one({"worker_id": w1["id"], "work_date": d0}, {"_id": 0})
    row2 = db.labor_attendance.find_one({"worker_id": w2["id"], "work_date": d0}, {"_id": 0})
    hourly = w1["daily_wage"] / rates["normal_hours"]
    manual = int(round(w1["daily_wage"] + 2 * hourly * rates["overtime_multiplier"]))
    check("hari penuh + lembur = rumus yang bisa diulang tangan",
          int((row1 or {}).get("total") or 0) == manual,
          f"{(row1 or {}).get('total')} vs {manual} · {(row1 or {}).get('formula')}")
    check("setengah hari = 0,5 × tarif (bukan penuh, bukan nol)",
          int((row2 or {}).get("total") or 0) == int(round(w2["daily_wage"] * 0.5)),
          str((row2 or {}).get("total")))
    fix = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=40, json={
        "project_id": project_id, "work_date": d0,
        "entries": [{"worker_id": w2["id"], "status": "full"}]})
    rows_same_day = db.labor_attendance.count_documents(
        {"project_id": project_id, "work_date": d0, "worker_id": w2["id"]})
    fixed = db.labor_attendance.find_one({"worker_id": w2["id"], "work_date": d0}, {"_id": 0})
    check("koreksi hari yang sama = DIPERBARUI + berjejak (bukan baris kembar)",
          fix.status_code == 200 and rows_same_day == 1 and bool(fixed.get("history")),
          f"{rows_same_day} baris")
    dup_err = None
    try:
        db.labor_attendance.insert_one({**{k: v for k, v in fixed.items() if k != "id"},
                                        "id": fx.new_id()})
    except DuplicateKeyError as e:
        dup_err = e
    check("index UNIK database menolak absensi kembar (bukan hanya cek aplikasi)",
          dup_err is not None, "index (project, tanggal, pekerja) belum unik")

    head("L3/L4. Rekap upah tie-out, periode terkunci, selisih buku harian dilaporkan")
    dc = requests.get(f"{BASE}/labor/attendance/diary-check", headers=pm, timeout=25,
                      params={"project_id": project_id, "work_date": d0})
    dcd = dc.json().get("data", {}) if dc.ok else {}
    check("selisih/ketiadaan buku harian DILAPORKAN apa adanya",
          dc.ok and dcd.get("state") in ("match", "mismatch", "missing_diary")
          and (dcd.get("state") == "match" or bool(dcd.get("detail"))),
          f"{dcd.get('state')} · {str(dcd.get('detail'))[:60]}")
    pr = requests.post(f"{BASE}/labor/payrolls", headers=pm, timeout=60, json={
        "project_id": project_id, "period_start": d0, "period_end": d0,
        "note": "bahan uji gate 47D"})
    p = pr.json().get("data", {}) if pr.ok else {}
    if p:
        db.labor_payrolls.update_one({"id": p["id"]}, {"$set": {fx.TAG: True}})
    att_total = sum(int(r.get("total") or 0) for r in db.labor_attendance.find(
        {"project_id": project_id, "work_date": d0,
         "worker_id": {"$in": [w1["id"], w2["id"]]}}, {"_id": 0, "total": 1}))
    check("rekap upah TIE-OUT dengan absensi (bisa dilacak per orang per hari)",
          pr.ok and int(p.get("total") or 0) == att_total and p.get("worker_count") == 2,
          f"rekap {p.get('total')} vs absensi {att_total}")
    clash = requests.post(f"{BASE}/labor/payrolls", headers=pm, timeout=40, json={
        "project_id": project_id, "period_start": d0, "period_end": day(-41)})
    check("periode rekap yang BERTUMPANG DITOLAK (upah tak boleh dibayar dua kali)",
          clash.status_code == 400, str(clash.json().get("detail"))[:90])
    empty = requests.post(f"{BASE}/labor/payrolls", headers=pm, timeout=40, json={
        "project_id": project_id, "period_start": day(-90), "period_end": day(-89)})
    check("rekap tanpa absensi berupah DITOLAK (tidak ada dokumen kosong)",
          empty.status_code == 400, f"got {empty.status_code}")

    head("L5. Pemisahan tugas & pembayaran yang berjurnal")
    early = requests.post(f"{BASE}/labor/payrolls/{p['id']}/pay", headers=finance, timeout=40,
                          json={})
    check("bayar sebelum DISETUJUI DITOLAK", early.status_code == 400,
          str(early.json().get("detail"))[:80])
    locked = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=40, json={
        "project_id": project_id, "work_date": d0,
        "entries": [{"worker_id": w1["id"], "status": "absent"}]})
    sub = requests.post(f"{BASE}/labor/payrolls/{p['id']}/submit", headers=pm, timeout=40)
    locked2 = requests.post(f"{BASE}/labor/attendance", headers=pm, timeout=40, json={
        "project_id": project_id, "work_date": d0,
        "entries": [{"worker_id": w1["id"], "status": "absent"}]})
    check("absensi pada periode yang sudah DIAJUKAN terkunci",
          locked.status_code == 200 and sub.status_code == 200 and locked2.status_code == 400,
          f"sebelum {locked.status_code} / sesudah {locked2.status_code}")
    self_ok = requests.post(f"{BASE}/labor/payrolls/{p['id']}/decision", headers=pm, timeout=40,
                            json={"approve": True})
    check("yang MENGAJUKAN tidak boleh menyetujui pembayarannya sendiri (403)",
          self_ok.status_code == 403, f"got {self_ok.status_code}")
    no_reason = requests.post(f"{BASE}/labor/payrolls/{p['id']}/decision", headers=finance,
                              timeout=40, json={"approve": False})
    check("penolakan rekap upah wajib beralasan", no_reason.status_code in (400, 422),
          f"got {no_reason.status_code}")
    appr = requests.post(f"{BASE}/labor/payrolls/{p['id']}/decision", headers=finance,
                         timeout=40, json={"approve": True})
    check("keuangan menyetujui rekap (200)", appr.status_code == 200, appr.text[:110])
    paid = requests.post(f"{BASE}/labor/payrolls/{p['id']}/pay", headers=finance, timeout=60,
                         json={})
    check("pembayaran upah dijawab 200", paid.status_code == 200, paid.text[:110])
    fresh = db.labor_payrolls.find_one({"id": p["id"]}, {"_id": 0}) or {}
    je = db.journal_entries.find_one({"source_id": p["id"], "source_type": "labor_payroll"},
                                     {"_id": 0})
    codes = {ln["account_code"] for ln in (je or {}).get("lines", [])}
    codes |= {"1-1200" for c in codes if c.startswith("1-12")}  # Fase 82: sub-akun rekening bank
    check("jurnal upah seimbang (Dr pekerjaan dalam proses / Cr bank) & tertaut rekapnya",
          bool(je) and je["total_debit"] == je["total_credit"] == int(fresh.get("total") or 0)
          and {"1-1600", "1-1200"} <= codes,
          f"{(je or {}).get('entry_no')} {sorted(codes)}")
    check("status rekap menjadi 'sudah dibayar' + nomor jurnal tercatat",
          fresh.get("state") == "paid" and bool(fresh.get("journal_no") or fresh.get("journal_id")),
          str(fresh.get("state")))
    twice = requests.post(f"{BASE}/labor/payrolls/{p['id']}/pay", headers=finance, timeout=40,
                          json={})
    check("rekap yang sudah dibayar tidak bisa dibayar lagi", twice.status_code == 400,
          f"got {twice.status_code}")

    head("L6. RBAC absensi & upah")
    s1 = requests.get(f"{BASE}/labor/workers", headers=sales, timeout=25)
    s2 = requests.post(f"{BASE}/labor/attendance", headers=sales, timeout=25, json={
        "project_id": project_id, "work_date": d0,
        "entries": [{"worker_id": w1["id"], "status": "full"}]})
    check("sales tidak punya akses tenaga kerja/absensi (403)",
          s1.status_code == 403 and s2.status_code == 403,
          f"{s1.status_code}/{s2.status_code}")
    anon = requests.get(f"{BASE}/labor/payrolls", timeout=25)
    check("tanpa token = 401", anon.status_code == 401, f"got {anon.status_code}")


def main():
    print("=" * 78)
    print("GATE FASE 47C+47D — PENAWARAN (harga yang bisa direkonstruksi) & UPAH HARIAN")
    print("=" * 78)
    fx.purge()
    manager = fx.login("manager@sipro.co.id")
    finance = fx.login("finance@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")

    made = fx.make_unit("GATE47-03", 850_000_000)
    lead = fx.make_lead("Calon Uji Gate47 Penawaran", "+628119947003")
    ctx = {"unit": made["unit"], "project": made["project"], "lead": lead}
    try:
        quotation_part(manager, sales, site, ctx)
        labor_part(pm, finance, sales, made["project"]["id"])
    finally:
        head("Bahan uji dibersihkan tanpa sisa menggantung")
        fx.purge()
        left = fx.orphans()
        check("tidak ada sisa menggantung setelah gate selesai",
              not any(left.values()), str(left))

    print("\n" + "-" * 50)
    if fails:
        print(f"GATE PENAWARAN & UPAH GAGAL: {len(fails)} temuan")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("GATE PENAWARAN & UPAH PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
