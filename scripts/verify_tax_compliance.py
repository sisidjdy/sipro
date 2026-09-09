#!/usr/bin/env python3
"""verify_tax_compliance.py — GATE 38 (Fase 49E/49F/49G).

Menjaga berkas pajak tidak pernah dibuat setengah lengkap dan potongan PPh selalu bisa
dibuktikan:

  T1  Ekspor e-Faktur DITAHAN bila NPWP perusahaan belum diisi (sebab disebut + tempat isinya).
  T2  Ekspor DITAHAN dan MENYEBUT faktur mana yang identitas pembelinya belum lengkap;
      unduhannya benar-benar 409, bukan berkas berkolom kosong.
  T3  Faktur pengganti: alasan ≥10 huruf, nomor BARU berkode status pengganti, jejak dua arah.
  T4  Setelah identitas lengkap, faktur itu tidak lagi menahan ekspor; berkas XML/CSV berisi
      nomor faktur & NPWP pemungut.
  T5  Pembatalan faktur: alasan wajib, tidak bisa dua kali, dan faktur batal tidak bisa diganti.
  T6  Rekap SPT Masa PPN bisa direkonstruksi: net = keluaran − masukan, faktur batal & diganti
      TERBACA jumlahnya tetapi tidak dihitung sebagai PPN keluaran.
  T7  Bayar tagihan dengan potong PPh: vendor terima NETO, potongan menjadi Utang Pajak
      (2-1300), jurnal seimbang, dan bukti potong bernomor terbit OTOMATIS.
  T8  Bukti potong: idempoten per referensi, pembetulan memakai NOMOR TETAP (versi naik),
      pembatalan beralasan, dan bukti yang dibatalkan tidak bisa dibetulkan lagi.
  T9  Tie-out bukti potong vs potongan NYATA dilaporkan apa adanya; PDF bisa dicetak.
  T10 RBAC: peran sales tidak bisa melihat maupun menerbitkan bukti potong (403).

Seluruh bahan uji dibuat lewat API resmi, ditandai, lalu dibuang bersih.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture49 as fx  # noqa: E402

FAIL = []
PASSED = 0
RESTORE = {}


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
        return str(resp.json().get("detail"))[:120]
    except Exception:  # noqa: BLE001
        return resp.text[:120]


def faktur_checks(fin, owner) -> dict:
    """49E — pengganti, pembatalan, dan ekspor yang menahan diri."""
    cands = fx.api("GET", "/tax/faktur-candidates", fin).json().get("data") or []
    if not check(bool(cands), "T2a ada deal ber-AR yang belum berfaktur sebagai bahan uji",
                 "tidak ada kandidat faktur"):
        return {}
    cur = fx.api("GET", "/settings/effective", owner,
                 params={"keys": "tax.company_npwp"}).json()["data"]
    RESTORE["tax.company_npwp"] = cur.get("tax.company_npwp")
    # Posisi AWAL rekap PPN masa ini: yang dibuktikan nanti adalah PERUBAHANNYA, sehingga
    # gate tetap sah walau database sudah punya faktur lain (bukan angka absolut yang
    # kebetulan benar di database kosong).
    base_vat = body(fx.api("GET", "/tax/compliance/vat-return", fin,
                           params={"period": fx.this_period()}))
    fx.api("PUT", "/settings/tax.company_npwp", owner,
           json={"value": "", "reason": "Gate 38 menguji gerbang ekspor tanpa identitas pemungut"})

    fak = body(fx.api("POST", "/tax/faktur", fin, json={"deal_id": cands[0]["deal_id"]}))
    fx.db.faktur_pajak.update_one({"id": fak["id"]},
                                  {"$set": {fx.TAG: True, "buyer_npwp": None}})
    per = fak["period"]
    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": per}))
    check(chk["can_export"] is False
          and any(b["scope"] == "perusahaan" for b in chk["blocking"]),
          "T1 ekspor DITAHAN saat NPWP perusahaan belum diisi",
          next((b["reason"] for b in chk["blocking"] if b["scope"] == "perusahaan"), "-")[:90])

    fx.api("PUT", "/settings/tax.company_npwp", owner, json={
        "value": "0012345678901000", "reason": "Gate 38 mengisi identitas pemungut untuk uji"})
    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": per}))
    mine = [b for b in chk["blocking"] if b.get("number") == fak["number"]]
    held = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                  params={"period": per, "format": "coretax_xml"})
    check(bool(mine) and held.status_code == 409 and "ditahan" in held.text.lower(),
          "T2 ekspor menyebut faktur yang identitasnya kurang + unduhan ditolak 409",
          detail_of(held))

    short = fx.api("POST", f"/tax/compliance/faktur/{fak['id']}/replace", fin,
                   json={"reason": "salah"})
    rep = body(fx.api("POST", f"/tax/compliance/faktur/{fak['id']}/replace", fin, json={
        "reason": "NPWP pembeli belum terisi saat faktur pertama diterbitkan.",
        "buyer_npwp": "0012345678901000"}))
    fx.db.faktur_pajak.update_one({"id": rep["id"]}, {"$set": {fx.TAG: True}})
    old = fx.db.faktur_pajak.find_one({"id": fak["id"]}, {"_id": 0}) or {}
    check(short.status_code == 400 and rep["number"] != fak["number"]
          and rep["transaction_code"].endswith("1")
          and old.get("status") == "replaced"
          and old.get("replaced_by_number") == rep["number"]
          and rep.get("replaces_number") == fak["number"],
          "T3 faktur pengganti: alasan wajib, nomor baru berkode pengganti, jejak dua arah",
          f"{fak['number']} → {rep['number']}")

    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": per}))
    still = [b for b in chk["blocking"] if b.get("number") in (fak["number"], rep["number"])]
    check(not still, "T4a faktur uji tidak lagi menahan ekspor setelah identitas dilengkapi",
          str(still)[:100])
    if chk["can_export"]:
        xml = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                     params={"period": per, "format": "coretax_xml"})
        csv_ = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                      params={"period": per, "format": "excel_csv"})
        check(xml.status_code == 200 and rep["number"] in xml.text
              and "0012345678901000" in xml.text,
              "T4b berkas XML berisi nomor faktur & NPWP pemungut", f"{len(xml.content)} bita")
        check(csv_.status_code == 200 and ";" in csv_.text,
              "T4c berkas CSV (template Excel) tersedia", f"{len(csv_.content)} bita")
    else:
        others = [b.get("number") for b in chk["blocking"]]
        check(bool(others),
              "T4b ekspor masih ditahan HANYA karena faktur lain yang datanya kurang",
              str(others)[:100])

    shortc = fx.api("POST", f"/tax/compliance/faktur/{rep['id']}/cancel", fin,
                    json={"reason": "batal"})
    canc = body(fx.api("POST", f"/tax/compliance/faktur/{rep['id']}/cancel", fin, json={
        "reason": "Gate 38: transaksi dibatalkan pembeli sebelum penyerahan unit."}))
    twice = fx.api("POST", f"/tax/compliance/faktur/{rep['id']}/cancel", fin, json={
        "reason": "Percobaan membatalkan faktur yang sudah batal untuk uji gerbang."})
    rep_after = fx.api("POST", f"/tax/compliance/faktur/{rep['id']}/replace", fin, json={
        "reason": "Percobaan mengganti faktur yang sudah dibatalkan untuk uji gerbang."})
    check(shortc.status_code == 400 and canc.get("status") == "cancelled"
          and twice.status_code == 400 and rep_after.status_code == 400,
          "T5 pembatalan beralasan, tidak bisa dua kali, dan faktur batal tidak bisa diganti",
          f"{shortc.status_code}/{twice.status_code}/{rep_after.status_code}")

    vat = body(fx.api("GET", "/tax/compliance/vat-return", fin, params={"period": per}))
    check(vat["net"] == vat["ppn_keluaran"] - vat["ppn_masukan"]
          and vat["faktur_cancelled"] >= 1 and vat["faktur_replaced"] >= 1
          and bool(vat.get("reconstruct")) and bool(vat.get("state_label")),
          "T6 rekap SPT PPN bisa direkonstruksi; faktur batal & diganti terbaca jumlahnya",
          f"{rp(vat['ppn_keluaran'])} − {rp(vat['ppn_masukan'])} = {rp(vat['net'])}")
    check(vat["ppn_keluaran"] == base_vat.get("ppn_keluaran", 0),
          "T6c faktur uji yang DIGANTI & DIBATALKAN tidak menambah PPN keluaran sepeser pun",
          f"{rp(base_vat.get('ppn_keluaran'))} → {rp(vat['ppn_keluaran'])}")
    empty = body(fx.api("GET", "/tax/compliance/vat-return", fin, params={"period": "2019-02"}))
    check(empty["state"] == "missing_data" and "belum ada data" in empty["detail"],
          "T6b masa tanpa data mengaku 'belum ada data' (bukan nihil)", empty["detail"][:80])
    return {"period": per}


def withholding_checks(fin, sales, project_id) -> None:
    """49F — potong, buktikan, betulkan, batalkan, ekspor."""
    per = fx.this_period()
    bill = fx.make_bill(fin, "PT Uji Gate38 Potong PPh", project_id, 100_000_000)
    tax_before = fx.account_balance("2-1300")
    over = fx.api("POST", f"/finance/ap/bills/{bill['id']}/pay-withholding", fin, json={
        "bill_id": bill["id"], "amount": 1_000_000, "base": 1_000_000, "kind": "pph23",
        "rate": 100})
    check(over.status_code == 400 and "melebihi" in over.text,
          "T7a potongan yang menghabiskan seluruh pembayaran DITOLAK", detail_of(over))

    pay = body(fx.api("POST", f"/finance/ap/bills/{bill['id']}/pay-withholding", fin, json={
        "bill_id": bill["id"], "amount": 50_000_000, "base": 50_000_000,
        "kind": "pph4_2_konstruksi", "rate": 1.75, "object_code": "28-409-22",
        "note": "Gate 38 termin dengan potongan PPh final"}))
    fx.settle()
    bupot = pay.get("withholding") or {}
    je = fx.db.journal_entries.find_one({"source_id": bill["id"], "source_type": "ap_bill",
                                        "memo": "Pembayaran tagihan AP"}, {"_id": 0}) or {}
    codes = {ln["account_code"]: ln for ln in je.get("lines", [])}
    for c, ln in list(codes.items()):  # Fase 82: sub-akun rekening bank (1-12xx) mewakili 1-1200
        if c.startswith("1-12") and c != "1-1200":
            codes.setdefault("1-1200", ln)
    check(pay.get("withheld") == 875_000 and pay.get("cash_out") == 49_125_000
          and fx.account_balance("2-1300") - tax_before == 875_000
          and je.get("total_debit") == je.get("total_credit")
          and codes.get("2-1300", {}).get("credit") == 875_000
          and codes.get("1-1200", {}).get("credit") == 49_125_000,
          "T7 vendor terima NETO, potongan jadi Utang Pajak, jurnal SEIMBANG",
          f"kas {rp(pay.get('cash_out'))} · potongan {rp(pay.get('withheld'))}")
    check(len(bupot.get("number", "")) == 10 and bupot.get("amount") == 875_000
          and bupot.get("object_code") == "28-409-22",
          "T7b bukti potong bernomor 10 digit terbit OTOMATIS dari pembayaran",
          f"{bupot.get('number')} — {rp(bupot.get('amount'))}")

    same = body(fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph4_2_konstruksi", "basis": "ap_payment", "party_name": bill["vendor"],
        "base": 50_000_000, "rate": 1.75, "ref_id": bupot.get("ref_id")}))
    check(same.get("idempotent") is True and same.get("number") == bupot.get("number"),
          "T8a bukti potong untuk referensi yang sama tidak bisa dobel", same.get("number", "-"))

    shortc = fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin,
                    json={"reason": "salah"})
    cor = body(fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin, json={
        "reason": "Gate 38: dasar pengenaan dikoreksi karena ada bagian material.",
        "base": 40_000_000}))
    check(shortc.status_code == 400 and cor.get("number") == bupot.get("number")
          and cor.get("version") == 2 and cor.get("amount") == 700_000
          and len(cor.get("history") or []) == 1,
          "T8b PEMBETULAN memakai NOMOR TETAP, versi naik, nilai lama tersimpan",
          f"{cor.get('number')} v{cor.get('version')} — {rp(cor.get('amount'))}")

    tie = fx.api("GET", "/tax/compliance/withholding", fin,
                 params={"period": per}).json()["tie_out"]
    check(tie["unproven"] == tie["actual"] - tie["issued"] and tie["matches"] is False,
          "T9 selisih potongan nyata vs bukti dilaporkan APA ADANYA", tie["detail"][:100])

    canc = body(fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/cancel", fin, json={
        "reason": "Gate 38: pembayaran dibatalkan bank sehingga potongan tidak terjadi."}))
    after = fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin, json={
        "reason": "Percobaan membetulkan bukti yang sudah dibatalkan untuk uji gerbang."})
    reissue = body(fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph4_2_konstruksi", "basis": "ap_payment", "party_name": bill["vendor"],
        "party_npwp": "0012345678904210", "base": 50_000_000, "rate": 1.75,
        "object_code": "28-409-22", "ref_id": bupot.get("ref_id"),
        "ref_label": f"Pembayaran tagihan {bill['vendor']}"}))
    check(canc.get("state") == "cancelled" and after.status_code == 400
          and reissue.get("idempotent") is False
          and reissue.get("number") != bupot.get("number"),
          "T8c pembatalan beralasan; bukti batal tak bisa dibetulkan; bukti baru bernomor baru",
          f"{bupot.get('number')} → {reissue.get('number')}")

    pdf = fx.api("GET", f"/tax/compliance/withholding/{reissue['id']}/pdf", fin)
    check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
          "T9b bukti potong bisa dicetak jadi PDF", f"{len(pdf.content)} bita")

    chk = body(fx.api("GET", "/tax/compliance/withholding-export/check", fin,
                      params={"period": per}))
    check(bool(chk.get("detail")) and isinstance(chk.get("blocking"), list),
          "T9c kesiapan ekspor bukti potong dijelaskan (blokir/peringatan/siap)",
          chk.get("detail", "")[:90])
    if chk.get("can_export"):
        xml = fx.api("GET", "/tax/compliance/withholding-export/file", fin,
                     params={"period": per, "format": "coretax_xml"})
        check(xml.status_code == 200 and reissue["number"] in xml.text,
              "T9d berkas XML bukti potong berisi nomor yang benar", f"{len(xml.content)} bita")

    forb = fx.api("GET", "/tax/compliance/withholding", sales)
    forb2 = fx.api("POST", "/tax/compliance/withholding/issue", sales, json={
        "kind": "pph23", "party_name": "PT Uji RBAC", "base": 1_000_000, "rate": 2})
    check(forb.status_code == 403 and forb2.status_code == 403,
          "T10 peran sales tidak bisa melihat maupun menerbitkan bukti potong (403)",
          f"{forb.status_code}/{forb2.status_code}")


def main() -> int:
    print("=" * 78)
    print("GATE 38 — kepatuhan pajak: e-Faktur, e-Bupot, dan rekap SPT Masa PPN")
    print("=" * 78)
    fin = fx.login("finance@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")
    proj = fx.make_project("Gate38 Pajak", f"G38-{fx.new_id()[:4].upper()}")
    try:
        faktur_checks(fin, owner)
        withholding_checks(fin, sales, proj["id"])
    finally:
        if "tax.company_npwp" in RESTORE:
            fx.api("PUT", "/settings/tax.company_npwp", owner, json={
                "value": RESTORE["tax.company_npwp"] or "",
                "reason": "Gate 38 selesai: nilai setelan dikembalikan seperti sebelum uji"})
        fx.settle()
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 38 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 38 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
