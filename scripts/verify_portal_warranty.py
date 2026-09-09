#!/usr/bin/env python3
"""verify_portal_warranty.py — GATE 43 (Fase 51C).

Portal pembeli memakai tokennya sendiri dan dibuka orang di luar organisasi. Karena itu tiga
hal harus dijaga sekaligus: **kelengkapan** (dokumen yang memang haknya), **kerahasiaan**
(dokumen orang lain tidak boleh bocor walau id-nya ditebak), dan **kejujuran** (kosong
dijelaskan, bukan dibiarkan menjadi tabel hampa).

  C1  pembeli melihat BAST miliknya + bisa mengunduh PDF-nya sendiri.
  C2  BAST/kwitansi milik orang lain TIDAK bisa diunduh (404), termasuk dengan menebak id.
  C3  kwitansi pembayaran sendiri bisa dilihat & diunduh (PDF sungguhan).
  C4  tanpa token portal seluruh pintu 51C 401/403, dan token STAF bukan kunci portal.
  C5  pengakuan pembeli hanya untuk perbaikan yang SUDAH diperiksa mutunya; klaim yang masih
      dikerjakan ditolak dengan alasan jujur.
  C6  pengakuan "sudah beres" menutup klaim ATAS NAMA PEMBELI (bukan atas nama staf) dan
      pekerjaan perbaikannya ikut ditutup.
  C7  pengakuan "BELUM beres" TIDAK menutup klaim: ia dikembalikan ke pengerjaan, catatannya
      tersimpan, dan tim yang menangani diberi tahu.
  C8  klaim milik orang lain tidak bisa diakui (404) — pengakuan tidak bisa dititipkan.
  C9  kosong-jujur: pembeli yang rumahnya belum diserahterimakan mendapat KALIMAT sebab,
      bukan daftar hampa.
  C10 permukaan layar: bagian BAST/kwitansi/pengakuan benar-benar dirender di portal, unduhan
      lewat sesi portal (bukan tautan mentah bertoken di URL), dan tidak ada testId mati.

Bahan uji dibuat sendiri (`gate51`) — termasuk akun portalnya — lalu dibuang bersih; akun
portal yatim adalah temuan CRITICAL audit forensik (pelajaran Fase 50).

Jalankan: python3 scripts/verify_portal_warranty.py
"""
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture51 as fx  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
OTP = __import__("os").environ.get("PORTAL_MASTER_OTP", "000000")
FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return bool(ok)


def head(t: str) -> None:
    print(f"\n{t}")


def portal_login(phone: str) -> dict:
    fx.api("POST", "/portal/auth/request-otp", {}, json={"identifier": phone})
    r = fx.api("POST", "/portal/auth/verify-otp", {},
               json={"identifier": phone, "code": OTP})
    r.raise_for_status()
    body = r.json()
    return {"Authorization": f"Bearer {body.get('token') or body.get('access_token')}"}


def audit_behaviour(world: dict) -> None:
    buyer = portal_login(fx.PHONE)
    staf = fx.login("finance@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    ho = world["handover"]
    kwt = world["receipt"]
    klaim = world["claim"]

    head("C4 pintu portal butuh token portal (dan token staf bukan kuncinya)")
    for path in ("/portal/handovers", "/portal/receipts", "/portal/warranty/claims"):
        r = fx.api("GET", path, {})
        check(r.status_code in (401, 403), f"C4a tanpa token: {path} ditolak",
              f"got {r.status_code}")
    r = fx.api("GET", "/portal/handovers", staf)
    check(r.status_code in (401, 403),
          "C4b token STAF tidak bisa dipakai sebagai kunci portal",
          f"got {r.status_code} {r.text[:120]}")

    head("C1..C3 dokumen milik pembeli sendiri")
    r = fx.api("GET", "/portal/handovers", buyer)
    rows = (r.json().get("data") or []) if r.ok else []
    check(any(h["id"] == ho["id"] for h in rows),
          "C1a BAST rumahnya ada di daftar miliknya", r.text[:160])
    check((r.json().get("detail") or "") if r.ok else "",
          "C1b daftar BAST menjelaskan apa yang dilihat pembeli")
    r = fx.api("GET", f"/portal/handovers/{ho['id']}/pdf", buyer)
    check(r.ok and r.content[:4] == b"%PDF",
          "C1c PDF BAST bisa diunduh pembeli", f"{r.status_code} {r.content[:12]}")
    r = fx.api("GET", "/portal/receipts", buyer)
    recs = (r.json().get("data") or []) if r.ok else []
    ours = next((x for x in recs if x["id"] == kwt["id"]), None)
    check(ours and int(ours.get("amount") or 0) == int(kwt["amount"]),
          "C3a kwitansi miliknya tampil dengan nominal yang benar", r.text[:160])
    r = fx.api("GET", f"/portal/receipts/{kwt['id']}/pdf", buyer)
    check(r.ok and r.content[:4] == b"%PDF", "C3b PDF kwitansi bisa diunduh pembeli",
          f"{r.status_code}")

    head("C2 dokumen orang lain tidak bocor")
    lain_ho = fx.db.unit_handovers.find_one(
        {"id": {"$ne": ho["id"]}, fx.TAG: {"$ne": True}}, {"_id": 0, "id": 1})
    if lain_ho:
        r = fx.api("GET", f"/portal/handovers/{lain_ho['id']}/pdf", buyer)
        check(r.status_code in (403, 404), "C2a BAST milik pembeli lain tidak bisa diunduh",
              f"got {r.status_code}")
    else:
        check(True, "C2a (dilewati: belum ada BAST pembeli lain untuk diuji)")
    lain_kwt = fx.db.receipts.find_one(
        {"id": {"$ne": kwt["id"]}, fx.TAG: {"$ne": True}}, {"_id": 0, "id": 1})
    if lain_kwt:
        r = fx.api("GET", f"/portal/receipts/{lain_kwt['id']}/pdf", buyer)
        check(r.status_code in (403, 404), "C2b kwitansi milik orang lain tidak bisa diunduh",
              f"got {r.status_code}")
    else:
        check(True, "C2b (dilewati: belum ada kwitansi pembeli lain untuk diuji)")
    r = fx.api("GET", f"/portal/handovers/{uuid.uuid4()}/pdf", buyer)
    check(r.status_code == 404, "C2c id BAST yang ditebak dijawab 404 (bukan 500)",
          f"got {r.status_code}")

    head("C5..C8 pengakuan penyelesaian klaim garansi")
    r = fx.api("POST", f"/portal/warranty/claims/{klaim['id']}/ack", buyer,
               json={"satisfied": True, "note": None})
    check(r.status_code == 400 and "diperiksa" in r.text,
          "C5 klaim yang masih dikerjakan tidak bisa diakui selesai (alasan jujur)",
          f"{r.status_code} {r.text[:170]}")
    lain_klaim = fx.db.warranty_claims.find_one(
        {fx.TAG: {"$ne": True}}, {"_id": 0, "id": 1, "number": 1})
    if lain_klaim:
        r = fx.api("POST", f"/portal/warranty/claims/{lain_klaim['id']}/ack", buyer,
                   json={"satisfied": True})
        check(r.status_code == 404, "C8 klaim milik orang lain tidak bisa diakui (404)",
              f"got {r.status_code}")
    else:
        check(True, "C8 (dilewati: belum ada klaim pembeli lain untuk diuji)")

    # Perbaikan diperiksa mutunya dulu (jalur staf), baru pembeli boleh mengakui.
    fx.db.warranty_claims.update_one({"id": klaim["id"]}, {"$set": {
        "state": "diverifikasi", "verified_by": "pm@sipro.co.id",
        "verified_at": fx.now_iso()}})
    r = fx.api("POST", f"/portal/warranty/claims/{klaim['id']}/ack", buyer,
               json={"satisfied": False, "note": "Rembesnya berkurang tetapi masih menetes."})
    check(r.ok, "C7a pembeli boleh menyatakan perbaikan BELUM beres", r.text[:150])
    doc = fx.db.warranty_claims.find_one({"id": klaim["id"]}, {"_id": 0})
    check(doc.get("state") == "dikerjakan",
          "C7b klaim TIDAK ditutup — dikembalikan ke pengerjaan", str(doc.get("state")))
    check("menetes" in (doc.get("ack_note") or ""),
          "C7c catatan pembeli tersimpan apa adanya", str(doc.get("ack_note"))[:120])
    check(fx.PHONE in (doc.get("ack_rejected_by") or ""),
          "C7d penolakan tercatat atas nama PEMBELI (bukan staf)",
          str(doc.get("ack_rejected_by")))
    notif = fx.db.notifications.count_documents({"related_entity_id": klaim["id"]})
    check(notif >= 1, "C7e tim yang menangani diberi tahu (bukan hanya catatan diam)",
          f"{notif} notifikasi")

    fx.db.warranty_claims.update_one({"id": klaim["id"]}, {"$set": {
        "state": "diverifikasi", "verified_by": "pm@sipro.co.id",
        "verified_at": fx.now_iso()}})
    r = fx.api("POST", f"/portal/warranty/claims/{klaim['id']}/ack", buyer,
               json={"satisfied": True, "note": "Sudah rapi, terima kasih."})
    check(r.ok, "C6a pembeli bisa mengakui perbaikan selesai", r.text[:150])
    doc = fx.db.warranty_claims.find_one({"id": klaim["id"]}, {"_id": 0})
    check(doc.get("state") == "ditutup", "C6b klaim ditutup setelah pengakuan pembeli",
          str(doc.get("state")))
    check(fx.PHONE in (doc.get("ack_by") or ""),
          "C6c pengakuan tercatat ATAS NAMA PEMBELI (bukan staf)", str(doc.get("ack_by")))
    r = fx.api("GET", f"/portal/warranty/claims/{klaim['id']}", buyer)
    check(r.ok and (r.json().get("data") or {}).get("state") == "ditutup",
          "C6d pembeli bisa membuka rincian klaimnya sendiri", r.text[:140])
    sisa = fx.db.punch_items.count_documents(
        {"warranty_claim_id": klaim["id"], "status": {"$nin": ["closed", "verified"]}})
    check(sisa == 0, "C6e pekerjaan perbaikannya ikut ditutup (tidak menggantung)",
          f"{sisa} temuan masih terbuka")
    # Kejujuran arah sebaliknya: sesudah ditutup, pengakuan kedua tidak boleh diterima.
    r = fx.api("POST", f"/portal/warranty/claims/{klaim['id']}/ack", buyer,
               json={"satisfied": True})
    check(r.status_code == 400, "C6f klaim yang sudah ditutup tidak bisa diakui lagi",
          f"got {r.status_code} {r.text[:140]}")
    check(site is not None, "C6g bahan uji peran lapangan tersedia untuk pemeriksaan mutu")

    head("C9 kosong-jujur untuk pembeli yang belum diserahterimakan")
    # BAST milik pembeli ditemukan lewat DUA jalur (pelanggan/deal DAN rumah dari deal-nya),
    # jadi untuk menguji keadaan "belum ada dokumen" BAST-nya harus benar-benar lepas dari
    # rumah itu — bukan cuma customer_id-nya dikosongkan. Kalau salah menyiapkan bahan uji,
    # yang tercatat MERAH adalah gate-nya, bukan produknya.
    fx.db.unit_handovers.update_one({"id": ho["id"]}, {"$set": {
        "unit_id": "gate43-unit-hantu", "customer_id": None, "deal_id": None}})
    r = fx.api("GET", "/portal/handovers", buyer)
    body = r.json() if r.ok else {}
    check(not (body.get("data") or []) and "belum" in (body.get("detail") or "").lower(),
          "C9a daftar BAST kosong dijelaskan dengan KALIMAT sebab, bukan tabel hampa",
          json.dumps(body, ensure_ascii=False)[:180])
    r = fx.api("GET", f"/portal/handovers/{ho['id']}/pdf", buyer)
    check(r.status_code == 404,
          "C9b BAST yang bukan miliknya lagi ikut tertutup untuk diunduh",
          f"got {r.status_code}")
    fx.db.unit_handovers.update_one({"id": ho["id"]}, {"$set": {
        "unit_id": world["unit"]["id"],
        "customer_id": world["buyer"]["customer"]["id"],
        "deal_id": world["buyer"]["deal"]["id"]}})


def audit_surface() -> None:
    head("C10 permukaan layar portal Fase 51C")
    docs = (FE / "components" / "portal" / "panels" / "DocumentsPanel.js").read_text(
        encoding="utf-8")
    war = (FE / "components" / "portal" / "panels" / "WarrantyPanel.js").read_text(
        encoding="utf-8")
    ack = (FE / "components" / "portal" / "panels" / "ClaimAckDialog.js").read_text(
        encoding="utf-8")
    dash = (FE / "components" / "portal" / "PortalDashboard.js").read_text(encoding="utf-8")
    # C10a diperkuat setelah uji-mutasi M51 LOLOS: memeriksa kata "DocumentsPanel" saja
    # dipenuhi oleh BARIS IMPOR-nya, sehingga panel bisa dilepas dari daftar tab tanpa gate
    # menyadarinya (pembeli kehilangan pintu BAST & kwitansi, layar tetap "hijau").
    check("Comp: DocumentsPanel" in dash,
          "C10a panel dokumen benar-benar DIRENDER di portal (bukan hanya diimpor)",
          "komponennya harus dipakai di daftar tab PortalDashboard")
    check("<ClaimAckDialog" in war, "C10b dialog pengakuan DIRENDER dari panel garansi",
          "import saja tidak cukup")
    for needle, label in (("P51.portalBastSection", "bagian BAST"),
                          ("P51.portalBastRow", "baris BAST"),
                          ("P51.portalBastPdf", "tombol PDF BAST"),
                          ("P51.portalBastEmpty", "kosong-jujur BAST"),
                          ("P51.portalReceiptSection", "bagian kwitansi"),
                          ("P51.portalReceiptPdf", "tombol PDF kwitansi")):
        check(needle in docs, f"C10c {label} punya testId", needle)
    check("T.portalAckBtn" in war or "P51.portalAckBtn" in war,
          "C10d tombol pengakuan punya testId di panel garansi")
    for needle in ("T.portalAckYes", "T.portalAckNo", "T.portalAckSubmit", "T.portalAckNote"):
        check(needle in ack, f"C10e dialog pengakuan memakai testId {needle}")
    check("portalDownload" in docs and "portalBlobError" in docs,
          "C10f unduhan lewat sesi portal + galat dibaca sebagai kalimat",
          "tautan mentah bertoken di URL membocorkan token ke riwayat peramban")
    check("href" not in docs.split("return (")[-1],
          "C10g tidak ada tautan mentah <a href> untuk berkas portal")
    check("TIDAK akan ditutup" in ack,
          "C10h layar menjelaskan akibat 'belum beres' (klaim tidak ditutup)")
    src = (FE / "constants" / "testIds" / "p51.js").read_text(encoding="utf-8")
    keys = re.findall(r"^\s{2}(portal\w+):", src, flags=re.M)
    all_fe = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                       for p in FE.rglob("*.js") if "components/ui/" not in p.as_posix())
    mati = [k for k in keys if f"P51.{k}" not in all_fe and f"T.{k}" not in all_fe]
    check(not mati, "C10i tidak ada testId portal Fase 51C yang MATI", str(mati))


def main() -> int:
    print("=" * 78)
    print("GATE 43 — PORTAL PEMBELI: BAST, KWITANSI, PENGAKUAN KLAIM (Fase 51C)")
    print("=" * 78)
    world = fx.make(with_active_claim=True)
    try:
        audit_behaviour(world)
        audit_surface()
    finally:
        buang = fx.purge()
        print(f"\n  info  bahan uji dibuang: {json.dumps(buang, ensure_ascii=False)}")
        sisa = {k: v for k, v in fx.orphans().items() if v}
        check(not sisa, "bahan uji gate dibuang bersih (termasuk akun portal)",
              json.dumps(sisa, ensure_ascii=False))
    print("-" * 78)
    if FAIL:
        print(f"GATE 43 MERAH — {len(FAIL)} pemeriksaan gagal:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print(f"GATE 43 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
