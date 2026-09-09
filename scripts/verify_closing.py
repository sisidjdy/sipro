#!/usr/bin/env python3
"""verify_closing.py — GATE 37 (Fase 49A/49B/49C/49D).

Menjaga penutupan buku tetap BERGIGI dan laporan direksi tetap jujur:

  K1  Daftar periksa tutup buku menyebut item + keadaan + sebab (bukan "gagal" tanpa alasan).
  K2  Mutasi bank yang belum dicocokkan MENAHAN penutupan, termasuk pada tanggal terakhir
      bulan (cacat off-by-one yang pernah meloloskan penutupan).
  K3  Penutupan tanpa terobosan DITAHAN 409 + sebab satu per satu.
  K4  Menerobos butuh izin `gl:close_override` (finance biasa 403) DAN alasan ≥10 huruf.
  K5  Terobosan tercatat: siapa, alasannya, pemeriksaan yang dilewati, potret daftar periksa,
      jejak audit, dan TUGAS tinjauan.
  K6  Periode tertutup benar-benar menolak jurnal manual.
  K7  Tutup tahun: jurnal penutup SEIMBANG, bertanggal 31 Desember, laba pindah ke Laba
      Ditahan, IDEMPOTEN (tidak ada jurnal kedua), dan finance biasa 403.
  K8  Buka tahun kembali: alasan wajib ≥10 huruf, jurnal penutup DIBALIK (berjejak), dan
      Laba Ditahan pulih ke posisi sebelumnya.
  K9  Arus kas per proyek TIE-OUT ke konsolidasi + baris "tidak teralokasi" ditampilkan.
  K10 Paket laporan owner membawa status penutupan (termasuk alasan terobosan) dan menyatakan
      bagian yang belum ada datanya sebagai `missing`, bukan Rp 0.

Seluruh bahan uji memakai tahun 2024 (kosong di data demo) lalu dibuang bersih.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture49 as fx  # noqa: E402

FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = ""):
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return ok


def rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def body(resp) -> dict:
    try:
        return resp.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def detail_of(resp) -> str:
    try:
        return str(resp.json().get("detail"))[:110]
    except Exception:  # noqa: BLE001
        return resp.text[:110]


def closing_checks(fin, lead, owner) -> None:
    per = fx.PERIOD
    fx.journal(lead, "gate37 pendapatan", [
        {"account_code": "1-1200", "debit": 500_000_000, "credit": 0},
        {"account_code": "4-1100", "debit": 0, "credit": 500_000_000}])
    fx.journal(lead, "gate37 beban", [
        {"account_code": "6-1200", "debit": 200_000_000, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": 200_000_000}])

    chk = body(fx.api("GET", "/gl/periods/close-check", lead, params={"period": per}))
    labels = [i.get("label") for i in chk.get("items", [])]
    check(len(chk.get("items", [])) >= 8 and all(labels)
          and chk["net_income"] == 300_000_000,
          "K1 daftar periksa lengkap berlabel manusia + laba periode dari jurnal nyata",
          f"{len(labels)} pemeriksaan, laba {rp(chk.get('net_income'))}")
    check(chk["can_close"] is True and not chk["blocking"],
          "K1b bulan bersih boleh ditutup", chk.get("detail", ""))

    fx.make_bank_txn(f"{per}-31", 750_000_000, "TRANSFER MASUK belum jelas (gate37)")
    chk2 = body(fx.api("GET", "/gl/periods/close-check", lead, params={"period": per}))
    bank = next((i for i in chk2["items"] if i["code"] == "bank_belum_dicocokkan"), {})
    check(bank.get("state") == "blocking" and chk2["can_close"] is False
          and "750.000.000" in bank.get("detail", "") and bank.get("link"),
          "K2 mutasi bank tanggal TERAKHIR bulan menahan + sebab bernilai + tautan sumber",
          bank.get("detail", "")[:100])

    hold = fx.api("POST", "/gl/periods/close", fin, json={"period": per})
    check(hold.status_code == 409 and "DITAHAN" in hold.text,
          "K3 penutupan tanpa terobosan DITAHAN (409) + sebab disebut", detail_of(hold))

    forb = fx.api("POST", "/gl/periods/close", fin, json={
        "period": per, "override": True, "override_reason": "alasan cukup panjang untuk uji"})
    short = fx.api("POST", "/gl/periods/close", lead, json={
        "period": per, "override": True, "override_reason": "buru2"})
    check(forb.status_code == 403 and short.status_code == 400,
          "K4 terobosan: finance 403, alasan <10 huruf 400",
          f"{forb.status_code}/{short.status_code}")

    reason = "Gate 37: mutasi bank dicocokkan bulan depan sesuai memo direksi."
    res = fx.api("POST", "/gl/periods/close", lead, json={
        "period": per, "override": True, "override_reason": reason})
    doc = body(res)
    task = fx.db.tasks.find_one({"source_event": f"closing.override:{fx.ORG}:{per}"})
    audit = fx.db.audit_logs.find_one({"entity_id": per, "action": "close"})
    check(doc.get("status") == "closed" and doc.get("override_reason") == reason
          and "bank_belum_dicocokkan" in (doc.get("override_items") or [])
          and len(doc.get("checklist") or []) == len(chk2["items"])
          and bool(task) and bool(audit),
          "K5 terobosan tercatat lengkap + tugas tinjauan + jejak audit",
          f"{doc.get('override_by')} melewati {doc.get('override_items')}")

    late = fx.journal(lead, "gate37 jurnal terlambat", [
        {"account_code": "6-1200", "debit": 1_000_000, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": 1_000_000}])
    check(late.status_code == 400 and "ditutup" in late.text.lower(),
          "K6 periode tertutup menolak jurnal manual", detail_of(late))

    pack = body(fx.api("GET", "/gl/reports/owner-pack", owner, params={"period": per}))
    check(pack.get("status") == "closed" and pack.get("override_reason") == reason
          and "TERTUTUP" in (pack.get("trust_note") or ""),
          "K10 paket owner membawa status & alasan terobosan apa adanya",
          (pack.get("trust_note") or "")[:80])
    kosong = body(fx.api("GET", "/gl/reports/owner-pack", owner, params={"period": "2019-03"}))
    check(set(kosong.get("missing") or []) >= {"laba_rugi", "arus_kas"}
          and "belum ada datanya" in (kosong.get("detail") or ""),
          "K10b periode tanpa data menyebut bagian yang BELUM ADA DATANYA (bukan Rp 0)",
          (kosong.get("detail") or "")[:90])
    hist = body(fx.api("GET", "/gl/reports/closing-history", owner, params={"limit": 24}))
    check(per in (hist.get("overridden") or []),
          "K10c riwayat penutupan menandai bulan yang DITEROBOS",
          str(hist.get("overridden"))[:80])


def year_checks(fin, lead) -> None:
    year = fx.YEAR
    before_re = fx.account_balance("3-1900")
    chk = body(fx.api("GET", "/gl/year/check", lead, params={"year": year}))
    check(chk.get("can_close") is True and not chk.get("open_months")
          and chk["pl"]["net_income"] == 300_000_000,
          "K7a tahun boleh ditutup setelah semua bulan bertransaksi ditutup",
          f"bulan {chk.get('months')} laba {rp(chk['pl']['net_income'])}")

    forb = fx.api("POST", "/gl/year/close", fin, json={"year": year})
    check(forb.status_code == 403, "K7b finance biasa tidak boleh menutup tahun buku",
          detail_of(forb))

    doc = body(fx.api("POST", "/gl/year/close", lead, json={"year": year, "note": "gate37"}))
    je = fx.db.journal_entries.find_one({"id": doc.get("entry_id")}, {"_id": 0}) or {}
    after_re = fx.account_balance("3-1900")
    check(doc.get("state") == "closed" and je.get("total_debit") == je.get("total_credit")
          and str(je.get("date", "")).startswith(f"{year}-12-31")
          and after_re - before_re == 300_000_000,
          "K7c jurnal penutup seimbang, bertanggal 31-12, laba pindah ke Laba Ditahan",
          f"{doc.get('entry_no')} — {rp(after_re - before_re)}")

    doc2 = body(fx.api("POST", "/gl/year/close", lead, json={"year": year}))
    n_je = fx.db.journal_entries.count_documents(
        {"source_event": f"year_close:{fx.ORG}:{year}"})
    check(doc2.get("idempotent") is True and n_je == 1
          and fx.account_balance("3-1900") == after_re,
          "K7d tutup tahun kedua kali IDEMPOTEN (tidak ada jurnal kedua)",
          f"jurnal penutup: {n_je}")

    noreason = fx.api("POST", "/gl/year/reopen", lead, json={"year": year})
    short = fx.api("POST", "/gl/year/reopen", lead, json={"year": year, "reason": "salah"})
    check(noreason.status_code == 400 and short.status_code == 400,
          "K8a buka tahun tanpa alasan / alasan <10 huruf ditolak",
          f"{noreason.status_code}/{short.status_code}")
    rsn = "Gate 37: koreksi pendapatan 2024 ditemukan saat audit internal."
    rdoc = body(fx.api("POST", "/gl/year/reopen", lead, json={"year": year, "reason": rsn}))
    check(rdoc.get("state") == "reopened" and rdoc.get("reversal_entry_no")
          and fx.account_balance("3-1900") == before_re,
          "K8b buka tahun membalik jurnal penutup (berjejak) & Laba Ditahan pulih",
          f"{rdoc.get('entry_no')} dibalik {rdoc.get('reversal_entry_no')}")


def project_cash_checks(owner) -> None:
    span = {"date_from": fx.day(-400), "date_to": fx.day(1)}
    data = body(fx.api("GET", "/gl/reports/cash-flow-projects", owner, params=span))
    tie = data.get("tie_out") or {}
    total = sum(r["net_change"] for r in data.get("rows") or [])
    total += (data.get("unassigned") or {}).get("net_change", 0)
    check(tie.get("matches") is True and tie.get("diff") == 0
          and total == tie.get("consolidated_net_change"),
          "K9 arus kas per proyek TIE-OUT ke konsolidasi (bisa dijumlah pembaca)",
          f"Σ {rp(total)} vs konsolidasi {rp(tie.get('consolidated_net_change'))}")
    check(data.get("unassigned") is not None
          and "Tidak teralokasi" in (data["unassigned"].get("project_name") or ""),
          "K9b baris 'tidak teralokasi' ditampilkan apa adanya",
          (data.get("unassigned") or {}).get("project_name", "-"))


def main() -> int:
    print("=" * 78)
    print("GATE 37 — penutupan buku bergigi, tutup tahun reversible, laporan owner jujur")
    print("=" * 78)
    fin = fx.login("finance@sipro.co.id")
    lead = fx.login("finlead@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    try:
        closing_checks(fin, lead, owner)
        year_checks(fin, lead)
        project_cash_checks(owner)
    finally:
        fx.settle()
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 37 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 37 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
