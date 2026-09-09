#!/usr/bin/env python3
"""verify_bank_recon.py — GATE REKONSILIASI BANK (Fase 47A).

Janji yang dijaga gate ini (semuanya lahir dari cacat NYATA repo ini):

  B1  **Pratinjau tidak menulis apa pun.** Dry-run hanya melaporkan; jumlah mutasi di
      database TIDAK berubah sedikit pun.
  B2  **Impor idempoten.** Berkas yang sama diimpor ulang = `unchanged`, bukan mutasi kembar
      (dijaga kunci alami + index unik). Baris cacat DITOLAK beserta alasannya — tidak ada
      baris yang hilang tanpa jejak, karena baris hilang = selisih yang tak bisa dijelaskan.
  B3  **Mutasi belum cocok BUKAN pelunasan.** Selama berstatus “belum dicocokkan”, tagihan
      pembeli tidak berubah sedikit pun (uji negatif inti fase ini).
  B4  **Pencocokan memakai jalur resmi.** Match ke termin AR melahirkan KUITANSI lewat
      `finance_engine.apply_receipt` (bukan rumus kedua) dan jurnalnya menunjuk KUITANSI itu
      (`source_type=receipt`, `source_id=<id kuitansi>`). Dulu `source_id` diisi deal_id
      sehingga jurnal pembalik tidak bisa dipasangkan dengan aslinya — inilah yang membuat
      tie-out 2-1400 tidak bisa direkonstruksi.
  B5  **Pembatalan beralasan & berbalik utuh.** Alasan pendek ditolak; setelah unmatch,
      tagihan kembali PERSIS, kuitansi berstatus batal, dan dampak bersih di akun 2-1400
      kembali NOL.
  B6  **Mengabaikan mutasi wajib beralasan** dan mutasi yang sudah cocok tidak bisa
      diabaikan (harus dibatalkan lebih dulu).
  B7  **Selisih dijelaskan sejujurnya.** Ringkasan menyebut penyebab; bagian selisih yang
      TIDAK dijelaskan oleh mutasi belum cocok dinyatakan sebagai `unexplained` — tidak
      disembunyikan di balik satu angka besar.
  B8  **RBAC bergigi.** Sales tidak boleh melihat mutasi rekening; MEMBATALKAN pencocokan
      (membalik pembukuan) lebih ketat daripada mencocokkan — finance biasa 403, supervisor
      keuangan 200.
  B9  **Bahan uji habis pakai dibersihkan** dan TIDAK meninggalkan jurnal menggantung.

Bahan uji dibuat sendiri (unit/lead/deal + rekening `8888GATE47`) lalu dibuang, sehingga gate
bisa dijalankan berulang kali. Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_47.py`.
"""
import pathlib
import re
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _fixture47 as fx  # noqa: E402

BASE = fx.BASE
db = fx.db
fails = []
ACCOUNT_NO = "8888GATE47"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def head(title):
    print(f"\n{title}\n" + "-" * len(title))


def csv_text(term_amount: int, *, with_balance=True, changed_desc=False) -> str:
    """CSV uji: 1 baris senilai termin (agar usulan muncul), 1 biaya bank, 1 baris cacat."""
    day = fx.now_iso()[:10]
    saldo = ";900.000.000" if with_balance else ""
    head_row = "tanggal;keterangan;referensi;debet;kredit" + (";saldo" if with_balance else "")
    desc = "TRANSFER MASUK GATE47 (koreksi berita)" if changed_desc else "TRANSFER MASUK GATE47"
    rows = [
        f"{day};{desc};TRFGATE47/001;;{term_amount:,}".replace(",", ".") + saldo,
        f"{day};BIAYA ADM GATE47;ADMGATE47;15.000;" + (";899.985.000" if with_balance else ""),
        f"{day};;TANPAKETERANGAN;;250.000" + (";1.000.000" if with_balance else ""),
    ]
    return "\n".join([head_row] + rows) + "\n"


def main():
    print("=" * 78)
    print("GATE FASE 47A — REKONSILIASI BANK (uang di rekening vs uang di pembukuan)")
    print("=" * 78)
    fx.purge()
    manager = fx.login("manager@sipro.co.id")
    finance = fx.login("finance@sipro.co.id")
    finlead = fx.login("finlead@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")

    ctx = fx.booked_deal("GATE47-01", "+628119947001", "Calon Uji Gate47 Bank", manager)
    term = fx.first_unpaid(ctx["invoice"])
    term_amount = int(term.get("amount") or 0) - int(term.get("paid_amount") or 0)
    before = fx.outstanding(ctx["deal"]["id"], finance)

    try:
        head("B0. Rekening bank & validasinya")
        r = requests.post(f"{BASE}/bank/accounts", headers=finance, timeout=30, json={
            "name": "Rekening Uji Gate47", "bank_name": "Bank Uji",
            "account_no": ACCOUNT_NO, "holder": "PT SIPRO Land",
            "gl_account_code": "1-1200", "opening_balance": 0})
        check("rekening bisa didaftarkan finance", r.status_code == 200, r.text[:120])
        acc = r.json()["data"] if r.ok else {}
        if acc:
            db.bank_accounts.update_one({"id": acc["id"]}, {"$set": {fx.TAG: True}})
        bad = requests.post(f"{BASE}/bank/accounts", headers=finance, timeout=30, json={
            "name": "Rekening Akun Ngawur", "bank_name": "Bank Uji",
            "account_no": "7777GATE47", "gl_account_code": "9-9999"})
        check("akun GL di luar Bagan Akun DITOLAK", bad.status_code == 400,
              f"got {bad.status_code}")
        dup = requests.post(f"{BASE}/bank/accounts", headers=finance, timeout=30, json={
            "name": "Rekening Kembar", "bank_name": "Bank Uji", "account_no": ACCOUNT_NO,
            "gl_account_code": "1-1200"})
        check("nomor rekening kembar DITOLAK", dup.status_code == 409, f"got {dup.status_code}")
        if not acc:
            return 1

        head("B1. Pratinjau impor TIDAK menulis apa pun")
        n0 = db.bank_transactions.count_documents({})
        dry = requests.post(f"{BASE}/bank/statements/import", headers=finance, timeout=60, json={
            "account_id": acc["id"], "filename": "gate47.csv",
            "csv_text": csv_text(term_amount), "dry_run": True})
        check("dry-run dijawab 200", dry.status_code == 200, dry.text[:120])
        d = dry.json().get("data", {})
        check("dry-run tidak menambah satu pun mutasi di database",
              db.bank_transactions.count_documents({}) == n0,
              f"{n0} -> {db.bank_transactions.count_documents({})}")
        check("dry-run melaporkan 2 baris baru & 1 baris DITOLAK beserta alasannya",
              d.get("counts", {}).get("new") == 2 and d.get("counts", {}).get("rejected") == 1
              and bool((d.get("rejected") or [{}])[0].get("error")),
              str(d.get("counts")))
        check("format angka Indonesia dibaca benar (1.500.000 bukan 15)",
              any(int(x.get("amount") or 0) == term_amount for x in d.get("rows") or []),
              str([x.get("amount") for x in d.get("rows") or []]))

        head("B2. Impor idempoten (berkas sama = unchanged, bukan mutasi kembar)")
        c1 = requests.post(f"{BASE}/bank/statements/import", headers=finance, timeout=60, json={
            "account_id": acc["id"], "filename": "gate47.csv",
            "csv_text": csv_text(term_amount), "dry_run": False})
        check("commit menulis 2 mutasi", c1.ok and c1.json()["data"]["counts"]["new"] == 2,
              c1.text[:120])
        after1 = db.bank_transactions.count_documents({"account_id": acc["id"]})
        c2 = requests.post(
            f"{BASE}/bank/statements/import", headers=finance, timeout=60, json={
                "account_id": acc["id"], "filename": "gate47.csv",
                "csv_text": csv_text(term_amount), "dry_run": False})
        check("impor ulang = unchanged (tidak ada mutasi kembar)",
              c2.ok and c2.json()["data"]["counts"]["unchanged"] == 2
              and db.bank_transactions.count_documents({"account_id": acc["id"]}) == after1,
              str(c2.json().get("data", {}).get("counts")))
        c3 = requests.post(f"{BASE}/bank/statements/import", headers=finance, timeout=60, json={
            "account_id": acc["id"], "filename": "gate47b.csv",
            "csv_text": csv_text(term_amount, changed_desc=True), "dry_run": False})
        counts3 = c3.json().get("data", {}).get("counts", {}) if c3.ok else {}
        txn = db.bank_transactions.find_one(
            {"account_id": acc["id"], "amount": term_amount}, {"_id": 0})
        check("keterangan berubah = DIPERBARUI + tercatat di riwayat (bukan ditimpa diam-diam)",
              counts3.get("updated", 0) >= 1 and bool((txn or {}).get("history")),
              str(counts3))

        head("B3. Mutasi BELUM dicocokkan bukan pelunasan (uji negatif inti)")
        check("tagihan pembeli TIDAK berubah walau uangnya sudah ada di rekening",
              fx.outstanding(ctx["deal"]["id"], finance) == before,
              f"{before} -> {fx.outstanding(ctx['deal']['id'], finance)}")
        lst = requests.get(f"{BASE}/bank/transactions", headers=finance, timeout=30,
                           params={"account_id": acc["id"], "match_state": "unmatched"})
        check("mutasi masuk berstatus 'belum dicocokkan'",
              lst.ok and lst.json()["summary"]["unmatched"] >= 2,
              str(lst.json().get("summary") if lst.ok else lst.text[:80]))

        head("B4. Usulan pencocokan menyebut SKOR & ALASAN, lalu memakai jalur resmi")
        sug = requests.get(f"{BASE}/bank/transactions/{txn['id']}/suggest", headers=finance,
                           timeout=30)
        cands = sug.json().get("data", {}).get("candidates", []) if sug.ok else []
        ar_cand = next((c for c in cands
                        if c["kind"] == "ar_deal" and c.get("target_id") == ctx["deal"]["id"]),
                       None)
        check("termin milik deal uji muncul sebagai kandidat berskor & beralasan",
              bool(ar_cand) and ar_cand["score"] >= 50 and bool(ar_cand.get("reasons")),
              str((ar_cand or {}).get("score")))
        m = requests.post(f"{BASE}/bank/transactions/{txn['id']}/match", headers=finance,
                          timeout=60, json={"kind": "ar_deal", "target_id": ctx["deal"]["id"]})
        check("pencocokan dijawab 200", m.status_code == 200, m.text[:150])
        rec = db.receipts.find_one({"deal_id": ctx["deal"]["id"], "method": "transfer"}, {"_id": 0}, sort=[("created_at", -1)])
        check("kuitansi resmi terbentuk (bukan rumus kedua)", bool(rec),
              (rec or {}).get("id", "-"))
        check("tagihan berkurang PERSIS senilai mutasi",
              fx.outstanding(ctx["deal"]["id"], finance) == before - term_amount,
              f"{before} -> {fx.outstanding(ctx['deal']['id'], finance)}")
        je = fx.wait_journal((rec or {}).get("id"), "receipt")
        check("jurnal penerimaan MENUNJUK kuitansinya (bisa dipasangkan dengan pembalik)",
              bool(je), "source_id jurnal masih bukan id kuitansi")
        if je:
            cr = sum(int(l.get("credit") or 0) for l in je["lines"]
                     if l["account_code"] == "2-1400")
            check("jurnal seimbang & mengkredit 2-1400 sebesar mutasi",
                  je["total_debit"] == je["total_credit"] == term_amount and cr == term_amount,
                  f"{je['entry_no']} cr2-1400={cr}")

        head("B5. Pembatalan wajib beralasan & membalik dampaknya utuh")
        short = requests.post(f"{BASE}/bank/transactions/{txn['id']}/unmatch", headers=finlead,
                             timeout=30, json={"reason": "x"})
        check("alasan pembatalan terlalu pendek DITOLAK", short.status_code in (400, 422),
              f"got {short.status_code}")
        u = requests.post(f"{BASE}/bank/transactions/{txn['id']}/unmatch", headers=finlead,
                          timeout=60,
                          json={"reason": "Ternyata transfer milik pembeli lain (uji gate)."})
        check("pembatalan oleh supervisor keuangan dijawab 200", u.status_code == 200,
              u.text[:150])
        check("tagihan kembali PERSIS seperti sebelum dicocokkan",
              fx.outstanding(ctx["deal"]["id"], finance) == before,
              f"sekarang {fx.outstanding(ctx['deal']['id'], finance)} vs {before}")
        rec2 = db.receipts.find_one({"id": (rec or {}).get("id")}, {"_id": 0}) or {}
        check("kuitansi ditandai BATAL beserta alasannya (bukan dihapus)",
              rec2.get("status") == "void" and bool(rec2.get("void_reason")),
              str(rec2.get("status")))
        void_je = fx.wait_journal((rec or {}).get("id"), "receipt_void")
        fx.settle()
        net = 0
        for j in db.journal_entries.find({"source_id": (rec or {}).get("id")}, {"_id": 0}):
            for line in j["lines"]:
                if line["account_code"] == "2-1400":
                    net += int(line.get("credit") or 0) - int(line.get("debit") or 0)
        check("jurnal PEMBALIK terbentuk & dampak bersih 2-1400 = NOL",
              bool(void_je) and net == 0, f"net={net}")
        txn_after = db.bank_transactions.find_one({"id": txn["id"]}, {"_id": 0})
        check("mutasi kembali 'belum dicocokkan' + jejak pembatalan tersimpan",
              txn_after["match_state"] == "unmatched"
              and any(h.get("action") == "unmatch" for h in txn_after.get("history") or []),
              txn_after["match_state"])

        head("B6. Mengabaikan mutasi: wajib beralasan, tidak boleh menutupi yang sudah cocok")
        fee_txn = db.bank_transactions.find_one({"account_id": acc["id"], "direction": "out"},
                                              {"_id": 0})
        bad_ig = requests.post(f"{BASE}/bank/transactions/{fee_txn['id']}/ignore",
                               headers=finance, timeout=30, json={"reason": "-"})
        check("alasan pengabaian terlalu pendek DITOLAK", bad_ig.status_code in (400, 422),
              f"got {bad_ig.status_code}")
        ig = requests.post(f"{BASE}/bank/transactions/{fee_txn['id']}/ignore", headers=finance,
                           timeout=30,
                           json={"reason": "Biaya administrasi rekening pribadi (uji gate)."})
        check("pengabaian beralasan dijawab 200 & alasannya tersimpan",
              ig.status_code == 200
              and bool((db.bank_transactions.find_one({"id": fee_txn["id"]}, {"_id": 0})
                        or {}).get("ignore_reason")), ig.text[:120])
        again = requests.post(f"{BASE}/bank/transactions/{txn['id']}/match", headers=finance,
                              timeout=60,
                              json={"kind": "ar_deal", "target_id": ctx["deal"]["id"]})
        ig2 = requests.post(f"{BASE}/bank/transactions/{txn['id']}/ignore", headers=finance,
                            timeout=30, json={"reason": "Mau disembunyikan padahal sudah cocok"})
        check("mutasi yang SUDAH dicocokkan tidak bisa diabaikan",
              again.status_code == 200 and ig2.status_code == 400,
              f"match {again.status_code} / ignore {ig2.status_code}")

        head("B7. Ringkasan rekonsiliasi menjelaskan selisih sejujurnya")
        rc = requests.get(f"{BASE}/bank/reconciliation", headers=finance, timeout=30,
                          params={"account_id": acc["id"]})
        data = rc.json().get("data", {}) if rc.ok else {}
        codes = [c.get("code") for c in data.get("causes") or []]
        check("saldo buku & saldo rekening dilaporkan",
              data.get("book_balance") is not None and data.get("statement_balance") is not None,
              f"buku={data.get('book_balance')} rekening={data.get('statement_balance')}")
        check("selisih yang belum bisa dijelaskan DINYATAKAN (bukan disembunyikan)",
              "unexplained" in codes or data.get("unexplained") == 0, str(codes))
        # Cacat nyata yang dijaga: pola lama `f"...{x:,}".replace(",", ".")` diterapkan pada
        # SELURUH kalimat sehingga koma kalimat berubah menjadi titik dan penyebab selisih
        # terbaca sebagai potongan kalimat ("...rekening. transaksi kas lain..."). Yang boleh
        # diformat hanyalah ANGKANYA.
        broken = [c.get("detail") for c in data.get("causes") or []
                  if re.search(r"\.\s+[a-z]", str(c.get("detail") or ""))]
        check("penyebab selisih memakai kalimat utuh (koma kalimat tidak jadi titik)",
              not broken, str(broken)[:140])
        no_bal = requests.post(f"{BASE}/bank/statements/import", headers=finance, timeout=60,
                               json={"account_id": acc["id"], "filename": "gate47-nobal.csv",
                                     "csv_text": csv_text(1_234_567, with_balance=False),
                                     "dry_run": True})
        rows_nb = no_bal.json().get("data", {}).get("rows") or [] if no_bal.ok else []
        check("mutasi tanpa kolom saldo TIDAK dicatat bersaldo 0 (jujur: belum ada data)",
              bool(rows_nb) and all(x.get("balance") is None for x in rows_nb),
              str([x.get("balance") for x in rows_nb]))

        head("B8. RBAC: melihat kas sensitif & membalik pembukuan")
        s = requests.get(f"{BASE}/bank/transactions", headers=sales, timeout=30)
        check("sales TIDAK boleh melihat mutasi rekening (403)", s.status_code == 403,
              f"got {s.status_code}")
        anon = requests.get(f"{BASE}/bank/transactions", timeout=30)
        check("tanpa token = 401", anon.status_code == 401, f"got {anon.status_code}")
        fin_unmatch = requests.post(f"{BASE}/bank/transactions/{txn['id']}/unmatch",
                                    headers=finance, timeout=30,
                                    json={"reason": "Finance biasa mencoba membalik pembukuan"})
        check("finance biasa TIDAK boleh membatalkan pencocokan (403)",
              fin_unmatch.status_code == 403, f"got {fin_unmatch.status_code}")
        fixed = requests.post(f"{BASE}/bank/transactions/{txn['id']}/unmatch", headers=finlead,
                              timeout=60, json={"reason": "Pembersihan bahan uji gate 47A."})
        check("supervisor keuangan boleh (200) — pemisahan tugas bukan sekadar tulisan",
              fixed.status_code == 200, f"got {fixed.status_code}")
    finally:
        head("B9. Bahan uji dibersihkan tanpa meninggalkan jurnal menggantung")
        fx.purge()
        left = fx.orphans()
        check("tidak ada sisa menggantung setelah gate selesai",
              not any(left.values()), str(left))

    print("\n" + "-" * 50)
    if fails:
        print(f"GATE REKONSILIASI BANK GAGAL: {len(fails)} temuan")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("GATE REKONSILIASI BANK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
