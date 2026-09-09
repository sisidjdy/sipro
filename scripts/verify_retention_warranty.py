#!/usr/bin/env python3
"""verify_retention_warranty.py — GATE 41 (Fase 51A).

Menjaga satu janji yang mudah hilang saat kode berkembang: **jaminan mutu tidak boleh cair
saat mutunya sedang dipersoalkan.** Retensi adalah satu-satunya alat tekan yang dimiliki
pengembang terhadap subkon; kalau ia cair persis ketika rumah sedang diperbaiki karena cacat
pekerjaan subkon itu, alat tekannya hilang tepat pada saat dibutuhkan.

  R1  gerbang retensi MENYEBUT klaim garansi yang menahan (nomor + judul + status), bukan
      "ada kendala", dan menandai penahanan yang boleh diabaikan dari SSOT (`waivable`).
  R2  pengajuan pencairan DITOLAK 400 selama klaim berjalan, dengan alasan yang menyebut
      nomor klaimnya (pemakai harus tahu apa yang harus dituntaskan).
  R3  pengabaian butuh izin khusus `subcon_finance:override` — PM & finance biasa 403,
      Manajer Keuangan 200. Mencabut hak mengabaikan tidak boleh mencabut hak mencairkan.
  R4  alasan pengabaian < 10 huruf DITOLAK (dijaga dua lapis: kontrak permintaan + service).
  R5  hanya penahanan yang MEMANG menahan & memang boleh diabaikan yang bisa diabaikan;
      kode asing dan kode yang tidak menahan ditolak apa adanya.
  R6  setelah diabaikan: gerbang boleh cair, tetapi penahanannya TETAP DITAMPILKAN beserta
      siapa/kapan/kenapa (transparan untuk auditor) dan jejaknya tersimpan di dokumen.
  R7  pemisahan tugas tetap berlaku: pengaju pencairan tidak boleh mencairkan sendiri.
  R8  pencairan idempoten lewat `client_ref` (kiriman ulang = jawaban lama, bukan tagihan
      kedua) dan tidak bisa dicairkan dua kali.
  R9  penahanan garansi hilang SENDIRI begitu klaimnya ditutup — tanpa perlu diabaikan.
  R10 honest-null: retensi tanpa catatan masa pemeliharaan menulis "belum dicatat", bukan
      "0 hari" (0 hari berarti sudah lewat — kebalikan artinya).
  R11 permukaan layar: panel retensi benar-benar dirender di `/subcon`, memakai testId
      Fase 51A, dan tidak ada testId 51A yang MATI (pelajaran Fase 48: testId yang tidak
      pernah dirender membuat uji E2E salah lapor selama dua fase).
  R12 kamus penahanan dibaca dari `/api/reference` (layar tidak mengetik labelnya sendiri).
  R13 pengabaian tercatat di jejak audit + melahirkan tugas penelaahan.

Seluruh bahan uji dibuat sendiri lewat `_fixture51` (bertanda `gate51`) lalu dibuang bersih:
gate tidak boleh menumpang — apalagi menghabiskan — data demo milik manusia.

Jalankan: python3 scripts/verify_retention_warranty.py
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


def gate_of(rid: str, headers: dict) -> dict:
    r = fx.api("GET", "/subcon/retentions", headers)
    r.raise_for_status()
    for row in r.json().get("data") or []:
        if row["id"] == rid:
            return row.get("gate") or {}
    return {}


def row_of(rid: str, headers: dict) -> dict:
    r = fx.api("GET", "/subcon/retentions", headers)
    for row in r.json().get("data") or []:
        if row["id"] == rid:
            return row
    return {}


# ------------------------------------------------------------------ R1..R10 perilaku
def audit_behaviour(world: dict) -> None:
    finlead = fx.login("finlead@sipro.co.id")
    finance = fx.login("finance@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    ret = world["subcon"]["retention"]
    rid = ret["id"]
    klaim = world["claim"]

    head("R1..R2 penahanan menyebut klaimnya & pengajuan ditolak")
    g = gate_of(rid, finance)
    codes = [b["code"] for b in g.get("blocks") or []]
    check("warranty_claim_active" in codes,
          "R1a gerbang menahan karena klaim garansi berjalan", str(codes))
    detail = " ".join(b.get("detail") or "" for b in g.get("blocks") or [])
    check(klaim["number"] in detail,
          "R1b penahanan MENYEBUT nomor klaimnya (bukan 'ada kendala')", detail[:180])
    nums = [c.get("number") for c in g.get("warranty_claims") or []]
    check(klaim["number"] in nums and g.get("warranty_claim_count") == len(nums),
          "R1c daftar klaim penahan dikirim ke layar (nomor + hitungan cocok)", str(nums))
    labels = [c.get("state_label") for c in g.get("warranty_claims") or []]
    check(all(labels) and not any(str(x) in ("dikerjakan", "diajukan") for x in labels),
          "R1d status klaim dikirim sebagai LABEL Indonesia, bukan enum mentah", str(labels))
    wv = {b["code"]: b.get("waivable") for b in g.get("blocks") or []}
    check(wv.get("warranty_claim_active") is True,
          "R1e penahanan menandai sendiri apakah boleh diabaikan (SSOT, bukan tebakan layar)",
          str(wv))
    # Pengajuan pencairan adalah hak LAPANGAN/PM (`subcon_finance:create`) — pemisahan tugas
    # sejak Fase 48C. Gate harus memakai peran yang memang berhak, kalau tidak yang teruji
    # hanyalah RBAC-nya dan penahanan garansinya lolos tanpa pernah diperiksa.
    r = fx.api("POST", f"/subcon/retentions/{rid}/request-release", pm,
               json={"reason": "Masa pemeliharaan sudah lewat, minta dicairkan."})
    check(r.status_code == 400 and klaim["number"] in r.text,
          "R2 pengajuan pencairan DITOLAK & menyebut klaim penahannya",
          f"{r.status_code} {r.text[:160]}")

    head("R3..R5 pengabaian: izin khusus, alasan, dan sasaran yang sah")
    for nama, h in (("pm", pm), ("finance", finance)):
        r = fx.api("POST", f"/subcon/retentions/{rid}/waive", h,
                   json={"codes": ["warranty_claim_active"],
                         "reason": "Mencoba mengabaikan tanpa kewenangan khusus."})
        check(r.status_code == 403, f"R3 {nama} TIDAK boleh mengabaikan penahanan (403)",
              f"got {r.status_code} {r.text[:120]}")
    r = fx.api("POST", f"/subcon/retentions/{rid}/waive", finlead,
               json={"codes": ["warranty_claim_active"], "reason": "sudah ok"})
    check(r.status_code in (400, 422) and "10" in r.text,
          "R4 alasan pengabaian < 10 huruf DITOLAK", f"{r.status_code} {r.text[:140]}")
    r = fx.api("POST", f"/subcon/retentions/{rid}/waive", finlead,
               json={"codes": ["ngawur_kode"],
                     "reason": "Mencoba mengabaikan kode yang tidak dikenal sama sekali."})
    check(r.status_code == 400, "R5a kode pengabaian tak dikenal DITOLAK",
          f"{r.status_code} {r.text[:140]}")
    r = fx.api("POST", f"/subcon/retentions/{rid}/waive", finlead,
               json={"codes": ["maintenance_active"],
                     "reason": "Mencoba mengabaikan penahanan yang tidak sedang menahan."})
    check(r.status_code == 400 and "menahan" in r.text,
          "R5b kode yang TIDAK sedang menahan ditolak apa adanya",
          f"{r.status_code} {r.text[:140]}")

    head("R6 jejak pengabaian & transparansi")
    alasan = ("Adendum ADD/G41/007: perbaikan garansi ditanggung subkon lain lewat "
              "kontrak terpisah, retensi ini bukan jaminannya.")
    r = fx.api("POST", f"/subcon/retentions/{rid}/waive", finlead,
               json={"codes": ["warranty_claim_active"], "reason": alasan})
    check(r.ok, "R6a Manajer Keuangan boleh mengabaikan dengan alasan tertulis",
          f"{r.status_code} {r.text[:160]}")
    doc = fx.db.subcon_retentions.find_one({"id": rid}, {"_id": 0, "waivers": 1})
    waivers = (doc or {}).get("waivers") or []
    w = next((x for x in waivers if x.get("code") == "warranty_claim_active"), {})
    check(w.get("reason") == alasan and w.get("by") == "finlead@sipro.co.id" and w.get("at"),
          "R6b jejak pengabaian tersimpan (kode + alasan + siapa + kapan)",
          json.dumps(waivers, ensure_ascii=False)[:200])
    g = gate_of(rid, finance)
    check(g.get("ok") is True and not (g.get("blocks") or []),
          "R6c sesudah diabaikan, gerbang menyatakan boleh cair", json.dumps(g)[:160])
    waived = [b["code"] for b in g.get("waived_blocks") or []]
    check("warranty_claim_active" in waived,
          "R6d penahanan yang diabaikan TETAP DITAMPILKAN (bisa diaudit kelak)", str(waived))

    head("R7..R8 pemisahan tugas & idempotensi pencairan")
    r = fx.api("POST", f"/subcon/retentions/{rid}/request-release", pm,
               json={"reason": "Penahanan garansi sudah diabaikan Manajer Keuangan."})
    check(r.ok, "R7a pengajuan lolos sesudah pengabaian sah", f"{r.status_code} {r.text[:140]}")
    r = fx.api("POST", f"/subcon/retentions/{rid}/release", pm,
               json={"reason": "Mencoba mencairkan yang saya ajukan sendiri."})
    check(r.status_code == 403, "R7b pengaju tidak boleh mencairkan sendiri",
          f"got {r.status_code}")
    ref_kirim = f"gate41-{uuid.uuid4().hex[:8]}"
    r1 = fx.api("POST", f"/subcon/retentions/{rid}/release", finlead,
                json={"reason": "Pencairan retensi sesuai keputusan tertulis.",
                      "client_ref": ref_kirim})
    check(r1.ok, "R8a pencairan berhasil", f"{r1.status_code} {r1.text[:160]}")
    bills1 = fx.db.ap_invoices.count_documents({"retention_id": rid})
    r2 = fx.api("POST", f"/subcon/retentions/{rid}/release", finlead,
                json={"reason": "Pencairan retensi sesuai keputusan tertulis.",
                      "client_ref": ref_kirim})
    bills2 = fx.db.ap_invoices.count_documents({"retention_id": rid})
    check(r2.ok and r2.json().get("replay") is True and bills1 == bills2,
          "R8b kiriman ulang dengan penanda sama = jawaban lama (tidak ada tagihan kedua)",
          f"bills {bills1}->{bills2} | {r2.text[:140]}")
    r = fx.api("POST", f"/subcon/retentions/{rid}/release", finlead,
               json={"reason": "Mencoba mencairkan untuk kedua kalinya lewat penanda baru."})
    check(r.status_code == 400 and "dua kali" in r.text,
          "R8c retensi tidak bisa dicairkan dua kali", f"{r.status_code} {r.text[:140]}")

    head("R9 penahanan hilang sendiri saat klaim ditutup")
    kedua = fx.make_subcon_retention(world["project"], world["unit"])
    rid2 = kedua["retention"]["id"]
    g = gate_of(rid2, finance)
    check("warranty_claim_active" in [b["code"] for b in g.get("blocks") or []],
          "R9a retensi baru ikut ditahan klaim garansi yang sama",
          json.dumps(g.get("blocks"), ensure_ascii=False)[:160])
    fx.db.warranty_claims.update_one({"id": klaim["id"]}, {"$set": {"state": "ditutup"}})
    g = gate_of(rid2, finance)
    check(g.get("ok") is True and not (g.get("blocks") or []),
          "R9b klaim ditutup → penahanan hilang SENDIRI (tanpa pengabaian)",
          json.dumps(g.get("blocks"), ensure_ascii=False)[:160])
    check(not (g.get("waived_blocks") or []),
          "R9c hilangnya penahanan bukan karena pengabaian palsu", str(g.get("waived_blocks")))

    head("R10 honest-null masa pemeliharaan")
    fx.db.subcon_retentions.update_one(
        {"id": rid2}, {"$set": {"maintenance_until": None, "maintenance_days": None}})
    g = gate_of(rid2, finance)
    teks = (g.get("maintenance_detail") or "").lower()
    check("belum dicatat" in teks and "0 hari" not in teks,
          "R10 masa pemeliharaan yang belum dicatat ditulis 'belum dicatat', bukan '0 hari'",
          teks[:160])

    head("R12..R13 kamus SSOT & jejak audit")
    r = fx.api("GET", "/reference/retention_block", owner)
    opts = {o["value"]: o.get("label") for o in ((r.json().get("data") or {})
                                                 .get("options") or [])} if r.ok else {}
    check("warranty_claim_active" in opts and opts["warranty_claim_active"],
          "R12 kode penahanan + labelnya ada di Kamus Data (layar tidak mengetik sendiri)",
          str(sorted(opts))[:160])
    logs = fx.db.audit_logs.count_documents({"entity_id": rid, "action": "override"})
    check(logs >= 1, "R13a pengabaian tercatat di jejak audit", f"{logs} baris")
    tugas = fx.db.tasks.count_documents(
        {"source_event": {"$regex": f"^retention_waiver:{rid}"}})
    check(tugas >= 1, "R13b pengabaian melahirkan tugas penelaahan (bukan hanya catatan)",
          f"{tugas} tugas")


# ------------------------------------------------------------------ R11 permukaan layar
def audit_surface() -> None:
    head("R11 permukaan layar Fase 51A benar-benar dirender")
    panel = (FE / "components" / "subcon" / "RetentionsPanel.js").read_text(encoding="utf-8")
    dialog = (FE / "components" / "subcon" / "RetentionWaiveDialog.js").read_text(
        encoding="utf-8")
    page = (FE / "pages" / "SubconPage.js").read_text(encoding="utf-8")
    check("<RetentionsPanel" in page, "R11a panel retensi benar-benar DIRENDER di /subcon",
          "import saja tidak cukup — komponennya harus dipakai di JSX")
    check("<RetentionWaiveDialog" in panel,
          "R11b dialog pengabaian dirender dari panel retensi")
    for needle, label in (
        ("P51.retentionWarrantyHold", "kartu penahanan klaim garansi"),
        ("P51.retentionWarrantyClaim", "baris klaim penahan (nomor + judul)"),
        ("P51.retentionWarrantyLink", "tautan ke papan garansi"),
        ("P51.retentionWaiveBtn", "tombol abaikan penahanan"),
        ("P51.retentionWaivedBlock", "blok penahanan yang diabaikan"),
        ("P51.retentionMaintenanceNote", "keterangan masa pemeliharaan"),
    ):
        check(needle in panel, f"R11c {label} punya testId di panel", needle)
    check("gate.warranty_claims" in panel,
          "R11d layar memakai daftar klaim dari server (bukan menebak dari kalimat)")
    check("b.waivable" in dialog,
          "R11e dialog memakai penanda `waivable` dari server, bukan daftar kode sendiri")
    check("/construction?tab=warranty" in panel,
          "R11f tautan penahanan menuju papan garansi (bukan halaman buntu)")
    # testId 51A yang MATI = uji E2E salah lapor. Cek seluruh frontend, bukan satu berkas.
    src = (FE / "constants" / "testIds" / "p51.js").read_text(encoding="utf-8")
    keys = re.findall(r"^\s{2}(retention\w+):", src, flags=re.M)
    all_fe = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                       for p in FE.rglob("*.js") if "components/ui/" not in p.as_posix())
    mati = [k for k in keys if f"P51.{k}" not in all_fe and f"T.{k}" not in all_fe]
    check(not mati, "R11g tidak ada testId retensi Fase 51A yang MATI", str(mati))


def main() -> int:
    print("=" * 78)
    print("GATE 41 — RETENSI SUBKON DITAHAN KLAIM GARANSI (Fase 51A)")
    print("=" * 78)
    world = fx.make(with_active_claim=True)
    try:
        audit_behaviour(world)
        audit_surface()
    finally:
        buang = fx.purge()
        print(f"\n  info  bahan uji dibuang: {json.dumps(buang, ensure_ascii=False)}")
        sisa = {k: v for k, v in fx.orphans().items() if v}
        check(not sisa, "bahan uji gate dibuang bersih", json.dumps(sisa, ensure_ascii=False))
    print("-" * 78)
    if FAIL:
        print(f"GATE 41 MERAH — {len(FAIL)} pemeriksaan gagal:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print(f"GATE 41 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
