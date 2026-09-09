#!/usr/bin/env python3
"""verify_f26_money.py — POC/verifikasi INTI Fase 26: kebenaran uang & validasi SSOT.

Menguji lewat HTTP (bukan akses DB langsung) semua perbaikan temuan:
  A. Validasi enum SSOT -> 400 dengan pesan Indonesia yang bisa dibaca (bukan 422 [object Object])
  B. Kelebihan bayar DITOLAK secara default (pesan menyebut sisa tagihan & nominal kelebihan)
  C. Pencairan KPR dibukukan sebagai penerimaan AR (piutang turun + jurnal kas)
  D. Titipan di muka -> saldo titipan + jurnal Dr 1-1200 / Cr 2-1450
  E. Pakai titipan untuk termin -> Dr 2-1450 / Cr 2-1400 (tanpa kas baru)
  F. Kembalikan titipan -> Dr 2-1450 / Cr 1-1200
  G. Kelebihan bayar DENGAN persetujuan -> masuk titipan (kas GL = kas nyata)
  H. Bayar AP melebihi sisa tagihan DITOLAK
  I. Gate invarian bisnis LULUS setelah semua transaksi di atas

CATATAN: posting GL berjalan lewat event bus (job `dispatch_pending` tiap 8 detik),
jadi pemeriksaan buku besar memakai polling `wait_gl`, bukan asumsi seketika.

Jalankan: python3 scripts/verify_f26_money.py   (butuh backend hidup di :8001)
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8001/api"
PASS, FAIL = [], []


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"detail": raw}


def check(name, cond, info=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  → {info}" if info else ""))


def rp(n):
    return f"Rp {int(n):,}"


def gl_balance(token, code):
    """(debit, kredit) kumulatif akun dari neraca saldo."""
    _s, r = call("GET", "/gl/trial-balance", token)
    # Fase 82: 1-1100/1-1200 adalah akun induk; saldo kas/bank = Σ sub-akun rekening di bawahnya.
    parent = code in ("1-1100", "1-1200")
    dr = cr = 0
    for row in (r.get("data") or {}).get("rows", []):
        rc = str(row.get("code") or "")
        if rc == code or (parent and rc.startswith(code[:4]) and rc != code):
            dr += int(row.get("debit", 0))
            cr += int(row.get("credit", 0))
    return dr, cr


def wait_gl(token, code, side, target, timeout=30):
    """Tunggu sampai saldo akun mencapai target (posting GL asinkron lewat event bus)."""
    idx = 0 if side == "debit" else 1
    deadline = time.time() + timeout
    val = gl_balance(token, code)[idx]
    while val != target and time.time() < deadline:
        time.sleep(2)
        val = gl_balance(token, code)[idx]
    return val


def main():
    print("=" * 74)
    print("VERIFIKASI FASE 26 — KEBENARAN UANG & VALIDASI SSOT")
    print("=" * 74)

    s, r = call("POST", "/auth/login", body={"email": "finance@sipro.co.id", "password": "Sipro#2026"})
    tok = (r.get("data") or {}).get("access_token") or r.get("access_token")
    check("Login finance", s == 200 and bool(tok), f"status={s}")
    if not tok:
        return 1
    s, r = call("POST", "/auth/login", body={"email": "owner@sipro.co.id", "password": "Sipro#2026"})
    otok = (r.get("data") or {}).get("access_token") or r.get("access_token")

    # ---------------- A. validasi enum SSOT ----------------
    print("\nA. Validasi enum SSOT (nilai liar harus ditolak 400 + pesan jelas)")
    s, r = call("GET", "/financing", tok)
    fapps = r.get("data") or []
    fid = fapps[0]["id"] if fapps else None
    if fid:
        s, r = call("PUT", f"/financing/{fid}", tok, {"status": "ngaco"})
        det = str(r.get("detail"))
        check("Status KPR liar ditolak", s == 400 and "tidak dikenal" in det, f"{s} · {det[:90]}")
    # materials/QC memerlukan peran proyek (RBAC), jadi pakai token PM di dua cek ini.
    s, r = call("POST", "/auth/login", body={"email": "pm@sipro.co.id", "password": "Sipro#2026"})
    ptok = (r.get("data") or {}).get("access_token") or r.get("access_token")
    s, r = call("GET", "/projects", ptok)
    proj = (r.get("data") or [{}])[0]
    s, r = call("GET", f"/materials/project/{proj.get('id')}", ptok)
    mats = r.get("data") or []
    mid = mats[0]["id"] if mats else "x"
    s, r = call("POST", "/materials/txn", ptok,
                {"project_id": proj.get("id"), "material_id": mid, "type": "masuk", "qty": 1})
    det = str(r.get("detail"))
    check("Mutasi stok 'masuk' (bukan in/out) ditolak", s == 400 and "tidak dikenal" in det,
          f"{s} · {det[:90]}")
    s, r = call("POST", "/construction/qc", ptok,
                {"project_id": proj.get("id"), "result": "lulus"})
    check("Hasil QC 'lulus' (bukan pass/fail) ditolak",
          s == 400 and "tidak dikenal" in str(r.get("detail")), f"{s} · {str(r.get('detail'))[:80]}")
    s, r = call("GET", "/reference/stock_movement", tok)
    check("Grup SSOT baru tersedia di /reference", s == 200 and len(r.get("data", {}).get("options", [])) == 2)

    # ---------------- konteks AR ----------------
    s, r = call("GET", "/finance/ar", tok)
    ars = r.get("data") or []
    check("Ada jadwal AR untuk diuji", bool(ars))
    if not ars:
        return 1
    inv = ars[0]
    deal_id = inv["deal_id"]
    out0 = int(inv["outstanding"])
    bank_dr0, _ = gl_balance(tok, "1-1200")
    liab_cr0 = gl_balance(tok, "2-1400")[1]
    print(f"     deal={deal_id[:8]} unit={inv.get('unit_code')} sisa tagihan={rp(out0)} "
          f"kas GL={rp(bank_dr0)}")

    # ---------------- B. kelebihan bayar ditolak ----------------
    print("\nB. Kelebihan bayar tanpa persetujuan → 400")
    s, r = call("POST", "/finance/ar/receipts", tok,
                {"deal_id": deal_id, "amount": out0 + 5_000_000, "method": "transfer"})
    det = str(r.get("detail"))
    check("Ditolak dengan pesan menyebut kelebihan", s == 400 and "melebihi sisa tagihan" in det,
          f"{s} · {det[:120]}")
    s, r = call("GET", "/finance/ar", tok)
    check("Tidak ada perubahan data setelah penolakan",
          int((r.get("data") or [{}])[0]["outstanding"]) == out0)

    # ---------------- C. pencairan KPR dibukukan ke AR ----------------
    print("\nC. Pencairan KPR → penerimaan AR + jurnal kas")
    s, r = call("POST", f"/financing/{fid}/disburse", tok,
                {"amount": 100_000_000, "milestone": "Termin I (uji Fase 26)", "min_progress": 0})
    booking = r.get("ar_booking") or {}
    check("Pencairan berhasil & dibukukan", s == 200 and booking.get("booked") is True,
          f"{s} · {json.dumps(booking)[:120]}")
    s, r = call("GET", "/finance/ar", tok)
    out1 = int((r.get("data") or [{}])[0]["outstanding"])
    check("Piutang berkurang sebesar pencairan", out1 == out0 - 100_000_000, f"{rp(out0)} → {rp(out1)}")
    bank_dr1 = wait_gl(tok, "1-1200", "debit", bank_dr0 + 100_000_000)
    check("Kas/bank di GL bertambah", bank_dr1 - bank_dr0 == 100_000_000,
          f"Δ={rp(bank_dr1 - bank_dr0)}")
    s, r = call("GET", f"/finance/ar/{deal_id}", tok)
    kpr_receipt = [x for x in (r.get("receipts") or []) if x.get("method") == "kpr"]
    check("Penerimaan metode 'kpr' tercatat", len(kpr_receipt) == 1)

    # ---------------- D. titipan di muka ----------------
    print("\nD. Titipan di muka (Dr 1-1200 / Cr 2-1450)")
    dep_cr0, dep_dr0 = gl_balance(tok, "2-1450")[1], gl_balance(tok, "2-1450")[0]
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit", tok,
                {"amount": 10_000_000, "note": "Setoran di muka pembeli"})
    dep = ((r.get("data") or {}).get("deposit") or {})
    check("Titipan 10jt tercatat", s == 200 and int(dep.get("balance", 0)) == 10_000_000,
          f"{s} · saldo={rp(dep.get('balance', 0))}")
    dep_cr1 = wait_gl(tok, "2-1450", "credit", dep_cr0 + 10_000_000)
    check("Kewajiban titipan 2-1450 bertambah", dep_cr1 - dep_cr0 == 10_000_000,
          f"Δkredit={rp(dep_cr1 - dep_cr0)}")
    bank_dr2 = gl_balance(tok, "1-1200")[0]
    check("Kas GL naik sebesar titipan", bank_dr2 - bank_dr1 == 10_000_000, f"Δ={rp(bank_dr2 - bank_dr1)}")
    s, r = call("GET", "/finance/ar/deposits", tok)
    check("Endpoint daftar titipan bekerja", s == 200 and int(r.get("balance_total", 0)) == 10_000_000)
    s, r = call("GET", "/finance/summary", tok)
    check("KPI ringkasan finance memuat titipan",
          int((r.get("data") or {}).get("customer_deposits", -1)) == 10_000_000)

    # ---------------- E. pakai titipan ----------------
    print("\nE. Pakai titipan untuk termin (Dr 2-1450 / Cr 2-1400, tanpa kas baru)")
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit/apply", tok, {"amount": 4_000_000})
    d = (r.get("data") or {})
    check("Titipan 4jt dipakai", s == 200 and int(d.get("deposit", {}).get("balance", -1)) == 6_000_000,
          f"{s} · saldo={rp(d.get('deposit', {}).get('balance', 0))}")
    out2 = int(d.get("invoice", {}).get("outstanding", -1))
    check("Piutang berkurang 4jt", out2 == out1 - 4_000_000, f"{rp(out1)} → {rp(out2)}")
    dep_dr1 = wait_gl(tok, "2-1450", "debit", dep_dr0 + 4_000_000)
    check("2-1450 didebit saat titipan dipakai", dep_dr1 - dep_dr0 == 4_000_000, f"Δdebit={rp(dep_dr1 - dep_dr0)}")
    bank_dr3 = gl_balance(tok, "1-1200")[0]
    check("Tidak ada kas baru masuk saat pakai titipan", bank_dr3 == bank_dr2,
          f"{rp(bank_dr2)} → {rp(bank_dr3)}")
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit/apply", tok, {"amount": 99_000_000})
    check("Pakai titipan melebihi saldo ditolak", s == 400 and "melebihi saldo titipan" in str(r.get("detail")),
          str(r.get("detail"))[:90])

    # ---------------- F. kembalikan titipan ----------------
    print("\nF. Kembalikan titipan (Dr 2-1450 / Cr 1-1200)")
    bank_cr0 = gl_balance(tok, "1-1200")[1]
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit/refund", tok, {"amount": 6_000_000, "note": "uji"})
    check("Titipan dikembalikan penuh",
          s == 200 and int((r.get("data") or {}).get("deposit", {}).get("balance", -1)) == 0, f"{s}")
    bank_cr1 = wait_gl(tok, "1-1200", "credit", bank_cr0 + 6_000_000, timeout=20)
    check("Kas GL berkurang (kredit) sebesar refund", bank_cr1 - bank_cr0 == 6_000_000,
          f"Δkredit kas={rp(bank_cr1 - bank_cr0)}")
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit/refund", tok, {"amount": 1_000_000})
    check("Refund tanpa saldo ditolak", s == 400 and "Tidak ada saldo" in str(r.get("detail")))

    # ---------------- G. kelebihan bayar disetujui ----------------
    print("\nG. Kelebihan bayar DENGAN persetujuan → jadi titipan")
    s, r = call("GET", "/finance/ar", tok)
    out3 = int((r.get("data") or [{}])[0]["outstanding"])
    s, r = call("POST", "/finance/ar/receipts", tok,
                {"deal_id": deal_id, "amount": out3 + 3_000_000, "method": "transfer",
                 "allow_overpay": True})
    rec = ((r.get("data") or {}).get("receipt") or {})
    check("Penerimaan diterima & kelebihan dipisah",
          s == 200 and int(rec.get("deposit_amount", 0)) == 3_000_000
          and int(rec.get("applied", 0)) == out3,
          f"{s} · applied={rp(rec.get('applied', 0))} titipan={rp(rec.get('deposit_amount', 0))}")
    check("AR menjadi lunas", (r.get("data") or {}).get("paid_off") is True)
    s, r = call("GET", "/finance/ar/deposits", tok)
    check("Saldo titipan = kelebihan", int(r.get("balance_total", 0)) == 3_000_000)
    s, r = call("POST", f"/finance/ar/{deal_id}/deposit/apply", tok, {"amount": 1_000_000})
    check("Pakai titipan saat sudah lunas ditolak", s == 400 and "lunas" in str(r.get("detail")))
    s, r = call("GET", "/units?status=booked", tok)
    unit = next((u for u in (r.get("data") or []) if u.get("id") == inv.get("unit_id")), {})
    check("Status pembayaran unit jadi lunas", unit.get("payment_status") == "paid_off",
          str(unit.get("payment_status")))

    # ---------------- H. guard AP ----------------
    print("\nH. Bayar AP melebihi sisa tagihan → 400")
    s, r = call("GET", "/finance/ap/bills", tok)
    bills = [b for b in (r.get("data") or []) if b.get("status") in ("approved", "partial")]
    if not bills:
        s, r = call("POST", "/finance/ap/bills", tok,
                    {"vendor": "PT Uji Fase 26", "claimed": 50_000_000, "retention_pct": 5,
                     "due_date": "2026-12-01", "note": "uji guard"})
        bid = (r.get("data") or {}).get("id")
        s2, _r2 = call("POST", f"/finance/ap/bills/{bid}/approve", otok or tok)
        s, r = call("GET", "/finance/ap/bills", tok)
        bills = [b for b in (r.get("data") or []) if b.get("status") in ("approved", "partial")]
        print(f"     (buat+setujui tagihan uji: approve status={s2})")
    if bills:
        b = bills[0]
        sisa = int(b["net"]) - int(b.get("paid", 0))
        s, r = call("POST", f"/finance/ap/bills/{b['id']}/pay", tok, {"amount": sisa + 1_000_000})
        check("Pembayaran berlebih ditolak", s == 400 and "melebihi sisa tagihan" in str(r.get("detail")),
              f"{s} · {str(r.get('detail'))[:90]}")
        s, r = call("POST", f"/finance/ap/bills/{b['id']}/pay", tok, {"amount": sisa})
        check("Pembayaran tepat sisa diterima", s == 200,
              f"{s} · status={(r.get('data') or {}).get('status')}")
    else:
        check("Tagihan AP tersedia untuk uji guard", False, "tidak ada tagihan approved")

    # ---------------- I. gate invarian ----------------
    print("\nI. Gate invarian bisnis (subledger ↔ buku besar) — tunggu event bus selesai")
    time.sleep(12)
    p = subprocess.run([sys.executable, "/app/scripts/verify_business_invariants.py"],
                       capture_output=True, text=True)
    check("verify_business_invariants LULUS", p.returncode == 0)
    if p.returncode != 0:
        print(p.stdout[-4000:])

    print("\n" + "=" * 74)
    print(f"HASIL: {len(PASS)} PASS · {len(FAIL)} FAIL")
    for f in FAIL:
        print(f"  - GAGAL: {f}")
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
