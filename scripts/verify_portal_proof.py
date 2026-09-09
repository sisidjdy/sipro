#!/usr/bin/env python3
"""verify_portal_proof.py — GATE BUKTI TRANSFER PELANGGAN (Fase 47B).

Janji yang dijaga:

  P1  **Pelanggan punya jalan resmi melampirkan bukti.** Portal punya endpoint unggah
      sendiri; `/api/files/upload` milik STAF tidak bisa dipakai token portal. Tanpa ini
      `POST /portal/payments/proof` mustahil dipenuhi (bukti wajib ≥ 1 berkas) — fitur yang
      tidak bisa dicapai sama dengan tidak ada.
  P2  **Bukti = KLAIM, bukan pelunasan.** Setelah bukti terkirim, sisa tagihan pelanggan
      TIDAK berubah sedikit pun sampai finance memverifikasi (uji negatif inti fase ini).
  P3  **Bukti kembar ditolak** (sidik jari berkas/sha256), dan berkas milik akun lain tidak
      bisa dipakai sebagai bukti.
  P4  **Penolakan wajib beralasan** — alasannya DIBACA PELANGGAN di portal, bukan catatan
      internal; penolakan tidak menyentuh tagihan.
  P5  **Verifikasi mengubah tagihan TEPAT SEKALI** lewat jalur resmi (`apply_receipt`), dan
      bukti yang sudah diverifikasi tidak bisa diverifikasi ulang.
  P6  **Jejak audit bisa ditelusuri.** Pengirim bukti adalah PELANGGAN: `created_by` tidak
      boleh berisi alamat email yang bukan pengguna sistem (temuan forensik HIGH), dan
      identitas pelanggan disimpan pada `submitted_by` yang menunjuk `customers.id`.
  P7  **RBAC**: sales tidak boleh melihat bukti transfer; lapangan tidak boleh memverifikasi.

Bahan uji dibuat sendiri (deal + pelanggan + akun portal) lalu dibuang. Exit !=0 bila ada FAIL.
"""
import pathlib
import sys
import uuid

import requests

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


def png_bytes(seed: str) -> bytes:
    """PNG 1x1 + komentar unik supaya sha256-nya berbeda tiap kebutuhan uji."""
    base = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082")
    return base + seed.encode()


def portal_token(phone: str) -> dict:
    requests.post(f"{BASE}/portal/auth/request-otp", json={"identifier": phone}, timeout=25)
    r = requests.post(f"{BASE}/portal/auth/verify-otp", timeout=25,
                      json={"identifier": phone, "code": "000000"})
    r.raise_for_status()
    body = r.json()
    return {"Authorization": f"Bearer {body.get('token') or body.get('access_token')}"}


def main():
    print("=" * 78)
    print("GATE FASE 47B — BUKTI TRANSFER PELANGGAN (klaim vs pelunasan)")
    print("=" * 78)
    fx.purge()
    manager = fx.login("manager@sipro.co.id")
    finance = fx.login("finance@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")
    site = fx.login("site@sipro.co.id")

    phone = "+628119947002"
    ctx = fx.booked_deal("GATE47-02", phone, "Pembeli Uji Gate47 Portal", manager)
    deal_id = ctx["deal"]["id"]
    before = fx.outstanding(deal_id, finance)
    pu = portal_token(phone)

    try:
        head("P1. Pelanggan bisa mengunggah bukti (dan hanya jenis berkas yang wajar)")
        deals = requests.get(f"{BASE}/portal/payments", headers=pu, timeout=25)
        check("portal melihat tagihannya sendiri",
              deals.ok and any(d["deal_id"] == deal_id for d in deals.json().get("data") or []),
              deals.text[:120])
        staff_only = requests.post(f"{BASE}/files/upload", headers=pu, timeout=25,
                                   files={"file": ("x.png", png_bytes("a"), "image/png")},
                                   data={"owner_type": "generic"})
        check("endpoint unggah STAF menolak token portal", staff_only.status_code in (401, 403),
              f"got {staff_only.status_code}")
        up = requests.post(f"{BASE}/portal/payments/proof/upload", headers=pu, timeout=40,
                           files={"file": ("bukti.png", png_bytes("gate47-1"), "image/png")},
                           data={"deal_id": deal_id})
        check("pelanggan berhasil mengunggah bukti (200)", up.status_code == 200, up.text[:150])
        fid = up.json()["data"]["id"] if up.ok else None
        bad_type = requests.post(f"{BASE}/portal/payments/proof/upload", headers=pu, timeout=40,
                                 files={"file": ("virus.exe", b"MZ\x00", "application/x-msdownload")},
                                 data={"deal_id": deal_id})
        check("berkas selain gambar/PDF DITOLAK dengan penjelasan",
              bad_type.status_code == 400 and "PDF" in bad_type.text,
              f"got {bad_type.status_code}")
        other = requests.post(f"{BASE}/portal/payments/proof/upload", headers=pu, timeout=40,
                              files={"file": ("b.png", png_bytes("x"), "image/png")},
                              data={"deal_id": str(uuid.uuid4())})
        check("unggah untuk transaksi milik orang lain DITOLAK (404)",
              other.status_code == 404, f"got {other.status_code}")

        head("P2. Bukti terkirim TIDAK mengubah tagihan (uji negatif inti)")
        sub = requests.post(f"{BASE}/portal/payments/proof", headers=pu, timeout=40, json={
            "deal_id": deal_id, "amount": 25_000_000, "transfer_date": fx.now_iso()[:10],
            "bank_name": "BCA", "file_ids": [fid], "note": "Bahan uji gate 47B"})
        check("bukti terkirim (200) & berstatus menunggu verifikasi",
              sub.status_code == 200 and sub.json()["data"]["state"] == "pending",
              sub.text[:150])
        intake_id = sub.json()["data"]["id"] if sub.ok else None
        check("sisa tagihan TIDAK berubah setelah bukti dikirim",
              fx.outstanding(deal_id, finance) == before,
              f"{before} -> {fx.outstanding(deal_id, finance)}")
        mine = requests.get(f"{BASE}/portal/payments/submissions", headers=pu, timeout=25)
        check("pelanggan bisa memantau status bukti kirimannya",
              mine.ok and any(s["id"] == intake_id for s in mine.json().get("data") or []),
              mine.text[:100])
        f = requests.get(f"{BASE}/portal/files/{fid}", headers=pu, timeout=25)
        check("pelanggan bisa membuka kembali berkas buktinya", f.status_code == 200,
              f"got {f.status_code}")

        head("P3. Bukti kembar & berkas bukan milik sendiri ditolak")
        dup = requests.post(f"{BASE}/portal/payments/proof", headers=pu, timeout=40, json={
            "deal_id": deal_id, "amount": 25_000_000, "transfer_date": fx.now_iso()[:10],
            "file_ids": [fid]})
        check("berkas bukti yang SAMA tidak bisa dipakai dua kali", dup.status_code == 400,
              str(dup.json().get("detail"))[:110])
        alien = requests.post(f"{BASE}/portal/payments/proof", headers=pu, timeout=40, json={
            "deal_id": deal_id, "amount": 1_000_000, "transfer_date": fx.now_iso()[:10],
            "file_ids": [str(uuid.uuid4())]})
        check("berkas yang bukan milik akun ini DITOLAK", alien.status_code == 400,
              f"got {alien.status_code}")

        head("P4. Penolakan wajib beralasan & alasannya dibaca pelanggan")
        short = requests.post(f"{BASE}/payment-intakes/{intake_id}/reject", headers=finance,
                              timeout=30, json={"reason": "salah"})
        check("alasan penolakan terlalu pendek DITOLAK", short.status_code in (400, 422),
              f"got {short.status_code}")
        up2 = requests.post(f"{BASE}/portal/payments/proof/upload", headers=pu, timeout=40,
                            files={"file": ("bukti2.png", png_bytes("gate47-2"), "image/png")},
                            data={"deal_id": deal_id})
        sub2 = requests.post(f"{BASE}/portal/payments/proof", headers=pu, timeout=40, json={
            "deal_id": deal_id, "amount": 7_500_000, "transfer_date": fx.now_iso()[:10],
            "file_ids": [up2.json()["data"]["id"]]})
        id2 = sub2.json()["data"]["id"] if sub2.ok else None
        reason = "Nominal pada bukti tidak sama dengan mutasi yang kami terima di rekening."
        rej = requests.post(f"{BASE}/payment-intakes/{id2}/reject", headers=finance, timeout=30,
                            json={"reason": reason})
        check("penolakan beralasan dijawab 200", rej.status_code == 200, rej.text[:120])
        check("penolakan TIDAK menyentuh tagihan", fx.outstanding(deal_id, finance) == before,
              f"{before} -> {fx.outstanding(deal_id, finance)}")
        seen = requests.get(f"{BASE}/portal/payments/submissions", headers=pu, timeout=25)
        row2 = next((s for s in seen.json().get("data") or [] if s["id"] == id2), {})
        check("pelanggan MEMBACA alasan penolakannya di portal",
              row2.get("state") == "rejected" and row2.get("reject_reason") == reason,
              str(row2.get("reject_reason"))[:80])

        head("P5. Verifikasi mengubah tagihan tepat sekali")
        v = requests.post(f"{BASE}/payment-intakes/{intake_id}/verify", headers=finance,
                          timeout=60, json={"note": "Cocok dengan mutasi rekening (uji gate)."})
        check("verifikasi dijawab 200", v.status_code == 200, v.text[:150])
        check("tagihan berkurang PERSIS senilai bukti (25.000.000)",
              fx.outstanding(deal_id, finance) == before - 25_000_000,
              f"{before} -> {fx.outstanding(deal_id, finance)}")
        again = requests.post(f"{BASE}/payment-intakes/{intake_id}/verify", headers=finance,
                              timeout=30, json={})
        check("bukti yang sudah diverifikasi tidak bisa diverifikasi ulang",
              again.status_code == 400, f"got {again.status_code}")
        rec_id = (db.payment_intakes.find_one({"id": intake_id}, {"_id": 0}) or {}).get("receipt_id")
        je = fx.wait_journal(rec_id, "receipt")
        check("kuitansi resmi + jurnal penerimaan yang menunjuk kuitansinya",
              bool(rec_id) and bool(je), f"receipt={str(rec_id)[:8]}")

        head("P6. Jejak audit bukti bisa ditelusuri (temuan forensik HIGH ditutup)")
        row = db.payment_intakes.find_one({"id": intake_id}, {"_id": 0}) or {}
        check("`created_by` bukan alamat email karangan (pengirim = pelanggan, bukan pengguna)",
              "@" not in str(row.get("created_by") or ""), str(row.get("created_by")))
        sb = row.get("submitted_by") or {}
        check("identitas pelanggan tersimpan & menunjuk data pelanggan yang NYATA",
              bool(sb.get("customer_id"))
              and db.customers.count_documents({"id": sb["customer_id"]}) == 1,
              str(sb)[:110])
        emails = {u["email"] for u in db.users.find({}, {"_id": 0, "email": 1})}
        stray = [n["user_email"] for n in db.notifications.find(
            {"related_entity_id": {"$in": [intake_id, id2]}}, {"_id": 0, "user_email": 1})
            if "@" in str(n.get("user_email")) and n["user_email"] not in emails]
        check("tidak ada notifikasi in-app yang dikirim ke alamat bukan pengguna sistem",
              not stray, str(stray)[:110])

        head("P7. RBAC: siapa boleh melihat & memutuskan")
        s = requests.get(f"{BASE}/payment-intakes", headers=sales, timeout=25)
        check("sales TIDAK boleh melihat bukti transfer (403)", s.status_code == 403,
              f"got {s.status_code}")
        up3 = requests.post(f"{BASE}/portal/payments/proof/upload", headers=pu, timeout=40,
                            files={"file": ("b3.png", png_bytes("gate47-3"), "image/png")},
                            data={"deal_id": deal_id})
        sub3 = requests.post(f"{BASE}/portal/payments/proof", headers=pu, timeout=40, json={
            "deal_id": deal_id, "amount": 3_000_000, "transfer_date": fx.now_iso()[:10],
            "file_ids": [up3.json()["data"]["id"]]})
        id3 = sub3.json()["data"]["id"] if sub3.ok else None
        sv = requests.post(f"{BASE}/payment-intakes/{id3}/verify", headers=site, timeout=30,
                           json={})
        check("pelaksana lapangan TIDAK boleh memverifikasi uang (403)", sv.status_code == 403,
              f"got {sv.status_code}")
        anon = requests.get(f"{BASE}/portal/payments/submissions", timeout=25)
        check("portal tanpa token = 401", anon.status_code == 401, f"got {anon.status_code}")
    finally:
        head("P8. Bahan uji dibersihkan tanpa sisa menggantung")
        fx.purge()
        left = fx.orphans()
        check("tidak ada sisa menggantung setelah gate selesai",
              not any(left.values()), str(left))

    print("\n" + "-" * 50)
    if fails:
        print(f"GATE BUKTI TRANSFER PORTAL GAGAL: {len(fails)} temuan")
        for f2 in fails:
            print(f"  - {f2}")
        return 1
    print("GATE BUKTI TRANSFER PORTAL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
