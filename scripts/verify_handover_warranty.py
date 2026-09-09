#!/usr/bin/env python3
"""verify_handover_warranty.py — GATE 39 (Fase 50A).

Menjaga serah terima unit tetap BERGIGI dan janji garansi tetap bisa dipertanggungjawabkan:

  H1  Daftar periksa serah terima menyebut item + keadaan + SEBAB, dengan label dari kamus
      data (bukan "gagal" tanpa alasan).
  H2  Temuan punch yang masih terbuka, progres belum selesai, kewajiban pembayaran, dan
      inspeksi serah terima yang belum lolos MENAHAN penerbitan BAST (409 + sebab).
  H3  Menerobos butuh kewenangan `handover:override` (Manajer Proyek 403) DAN alasan ≥10 huruf.
  H4  Terobosan tercatat: siapa, alasannya, pemeriksaan yang dilewati, potret daftar periksa,
      dan TUGAS tinjauan.
  H5  BAST idempoten (tidak ada serah terima kedua atas rumah yang sama) + berkas PDF nyata.
  H6  Masa garansi per bagian dihitung dari Pusat Konfigurasi, bukan angka mati.
  H7  Pembatalan BAST beralasan, tidak bisa dua kali, mengembalikan status rumah, dan tidak
      boleh dilakukan saat masih ada klaim berjalan.
  H8  Klaim bagian yang masa garansinya LEWAT tercatat & ditolak dengan menyebut tanggal
      habisnya (tidak hilang diam-diam).
  H9  Klaim yang diterima melahirkan PEKERJAAN perbaikan nyata; "selesai" wajib berbukti
      foto; pemeriksa tidak boleh orang yang mengerjakan; penutupan butuh pengakuan pembeli.
  H10 Rekap klaim tie-out (Σ per status = jumlah klaim) dan mengaku "belum ada data" untuk
      masa tanpa klaim (bukan rata-rata 0 hari).

Seluruh bahan uji dibuat sendiri (bertanda `gate50`) lalu dibuang bersih.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture50 as fx  # noqa: E402

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


def body(resp) -> dict:
    try:
        return resp.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def detail_of(resp) -> str:
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            return " | ".join([str(d.get("message") or "")]
                              + [str(x) for x in (d.get("reasons") or [])])[:400]
        return str(d or "")[:400]
    except Exception:  # noqa: BLE001
        return resp.text[:250]


def hold_checks(fin, pm, blocked):
    unit = blocked["unit"]
    chk = body(fx.api("GET", "/handover/check", fin, params={"unit_id": unit["id"]}))
    items = {i["code"]: i for i in chk.get("items", [])}
    check(len(items) >= 6 and all(i.get("label") and i.get("state_label")
                                 for i in items.values()),
          "H1 daftar periksa memakai label & keadaan dari kamus data", str(list(items)[:3]))
    blocking = {b["code"] for b in chk.get("blocking", [])}
    check({"punch_terbuka", "pembangunan_selesai", "pelunasan_belum",
           "inspeksi_serah_terima"} <= blocking,
          "H2a empat sebab nyata menahan serah terima", str(sorted(blocking)))
    check("Keramik" in items["punch_terbuka"]["detail"]
          and "120.000.000" in items["pelunasan_belum"]["detail"],
          "H2b sebab menyebut temuan & nominal, bukan hanya jumlah",
          items["punch_terbuka"]["detail"][:90])
    res = fx.api("POST", "/handover/issue", fin, json={"unit_id": unit["id"]})
    check(res.status_code == 409 and "DITAHAN" in detail_of(res),
          "H2c penerbitan BAST DITAHAN 409 + sebab satu per satu", detail_of(res)[:110])
    after = fx.db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1})
    check(after.get("status") != "handed_over",
          "H2d status rumah tidak berubah setelah penerbitan ditahan", str(after))

    res = fx.api("POST", "/handover/issue", pm, json={
        "unit_id": unit["id"], "override": True,
        "override_reason": "Mencoba menerobos tanpa kewenangan yang cukup."})
    check(res.status_code == 403, "H3a Manajer Proyek tidak boleh menerobos (403)",
          detail_of(res)[:90])
    return chk


def override_checks(lead, fin, blocked):
    unit = blocked["unit"]
    res = fx.api("POST", "/handover/issue", lead, json={
        "unit_id": unit["id"], "override": True, "override_reason": "cepat"})
    check(res.status_code in (400, 422) and "10" in detail_of(res),
          "H3b alasan terobosan < 10 huruf ditolak kontrak permintaan", detail_of(res)[:90])

    reason = "Pembeli sudah menempati rumah atas persetujuan direksi."
    doc = body(fx.api("POST", "/handover/issue", lead, json={
        "unit_id": unit["id"], "override": True, "override_reason": reason}))
    check(doc.get("number", "").startswith("BAST/") and doc.get("override_by")
          and doc.get("override_reason") == reason and len(doc.get("override_items") or []) >= 3,
          "H4a terobosan tercatat: nomor, siapa, alasan, pemeriksaan yang dilewati",
          f"{doc.get('number')} · {len(doc.get('override_items') or [])} dilewati")
    check(len(doc.get("checklist") or []) >= 6,
          "H4b potret daftar periksa tersimpan di dokumen (bisa diaudit ulang)",
          f"{len(doc.get('checklist') or [])} baris")
    task = fx.db.tasks.find_one({"related_entity_type": "unit_handover",
                                 "related_entity_id": doc.get("id")}, {"_id": 0, "title": 1})
    check(bool(task), "H4c terobosan melahirkan TUGAS tinjauan",
          (task or {}).get("title", "")[:70])
    audit = fx.db.audit_logs.count_documents({"entity_id": doc.get("id")})
    check(audit >= 1, "H4d jejak audit penerbitan tersimpan", f"{audit} baris audit")

    dup = fx.api("POST", "/handover/issue", fin, json={"unit_id": unit["id"]})
    check(dup.status_code == 200 and body(dup).get("number") == doc.get("number"),
          "H5a penerbitan kedua IDEMPOTEN (tidak ada BAST kembar)",
          str(body(dup).get("number")))
    return doc


def clean_checks(fin, ready, day=None):
    unit = ready["unit"]
    payload = {"unit_id": unit["id"], "received_by": "Penerima gate 39", "keys_handed": 2,
               "client_ref": f"{fx.TAG}-gate39-{unit['code']}"}
    if day:
        payload["handed_over_at"] = day
    doc = body(fx.api("POST", "/handover/issue", fin, json=payload))
    check(doc.get("number", "").startswith("BAST/") and not doc.get("override_by"),
          "H5b rumah bersih terbit BAST tanpa terobosan", doc.get("number"))
    pdf = fx.api("GET", f"/handover/{doc['id']}/pdf", fin)
    check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
          "H5c BAST bisa dicetak jadi PDF nyata", f"{len(pdf.content)} bytes")

    plan = {p["category"]: p for p in
            (fx.api("GET", "/handover/warranty/plan", fin).json().get("data") or [])}
    w = {x["category"]: x for x in doc.get("warranties", [])}
    same = all(w[c]["months"] == plan[c]["months"] for c in w)
    check(same and w["struktur"]["months"] != w["finishing"]["months"],
          "H6 masa garansi per bagian mengikuti Pusat Konfigurasi (bukan angka mati)",
          f"struktur {w['struktur']['months']} vs finishing {w['finishing']['months']} bulan")
    st = body(fx.api("GET", "/handover/warranty/unit", fin, params={"unit_id": unit["id"]}))
    check(st.get("missing") is False and len(st.get("rows") or []) == len(w),
          "H6b keadaan tiap bagian garansi bisa dibaca layar", st.get("detail", "")[:80])
    return doc


def cancel_checks(lead, fin, doc):
    res = fx.api("POST", f"/handover/{doc['id']}/cancel", fin,
                 json={"reason": "Mencoba membatalkan tanpa kewenangan."})
    check(res.status_code == 403, "H7a pembatalan BAST butuh kewenangan khusus (403)",
          detail_of(res)[:80])
    res = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={"reason": "salah"})
    check(res.status_code in (400, 422), "H7b alasan pembatalan < 10 huruf ditolak",
          detail_of(res)[:80])
    res = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={
        "reason": "Salah unit; yang benar rumah sebelahnya."})
    out = body(res)
    check(res.status_code == 200 and out.get("state") == "cancelled" and out.get("cancel_reason"),
          "H7c pembatalan beralasan tercatat (dokumen tidak dihapus)",
          f"{out.get('number')} → {out.get('state')}")
    unit = fx.db.units.find_one({"id": doc["unit_id"]}, {"_id": 0, "status": 1,
                                                         "handover_number": 1})
    check(unit.get("status") != "handed_over" and not unit.get("handover_number"),
          "H7d status rumah dikembalikan setelah pembatalan", str(unit))
    again = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={
        "reason": "Membatalkan dokumen yang sama dua kali."})
    check(again.status_code == 400, "H7e pembatalan kedua ditolak", detail_of(again)[:80])


def claim_checks(pm, site, owner, sales, old_unit):
    expired = body(fx.api("POST", "/handover/claims", sales, json={
        "unit_id": old_unit["id"], "category": "finishing", "source": "komplain_cs",
        "title": "Cat mengelupas di ruang tamu"}))
    check(expired.get("state") == "ditolak"
          and expired.get("reject_reason") == "lewat_masa_garansi"
          and str(expired.get("warranty_expires_at")) in (expired.get("reject_detail") or ""),
          "H8 klaim lewat masa garansi TERCATAT & ditolak dengan tanggal habisnya",
          (expired.get("reject_detail") or "")[:110])

    claim = body(fx.api("POST", "/handover/claims", sales, json={
        "unit_id": old_unit["id"], "category": "struktur", "source": "komplain_cs",
        "title": "Retak diagonal pada kolom"}))
    check(claim.get("state") == "diajukan", "H9a klaim dalam masa garansi masuk daftar kerja",
          f"{claim.get('number')} · sisa {claim.get('days_left_at_submit')} hari")
    res = fx.api("POST", f"/handover/claims/{claim['id']}/decide", sales, json={"accept": True})
    check(res.status_code == 403, "H9b pengaju klaim tidak boleh memutuskan sendiri (403)",
          detail_of(res)[:80])
    accepted = body(fx.api("POST", f"/handover/claims/{claim['id']}/decide", pm, json={
        "accept": True, "assigned_to": "site@sipro.co.id",
        "reason": "Retak struktur diperiksa dan diperbaiki segera."}))
    punch = fx.db.punch_items.find_one({"id": accepted.get("punch_id")},
                                       {"_id": 0, "source": 1, "title": 1})
    check(accepted.get("state") == "dikerjakan" and punch
          and punch.get("source") == "warranty_claim",
          "H9c klaim diterima melahirkan pekerjaan perbaikan nyata",
          (punch or {}).get("title", "")[:80])
    res = fx.api("POST", f"/handover/claims/{claim['id']}/complete", site,
                 json={"photo_file_ids": []})
    check(res.status_code in (400, 422),
          "H9d 'selesai' tanpa bukti foto DITOLAK", detail_of(res)[:90])
    photo = fx.upload_photo(site)
    done = body(fx.api("POST", f"/handover/claims/{claim['id']}/complete", site, json={
        "photo_file_ids": [photo], "note": "Disuntik epoxy."}))
    check(done.get("state") == "selesai" and done.get("fix_photos") == [photo],
          "H9e bukti perbaikan tersimpan pada klaim", done.get("state_label"))
    res = fx.api("POST", f"/handover/claims/{claim['id']}/verify", site, json={"passed": True})
    check(res.status_code == 403, "H9f pelaksana tidak berhak menyatakan lulus (403)",
          detail_of(res)[:80])
    # pemisahan tugas di DATA: yang menyelesaikan tidak boleh memverifikasi
    photo2 = fx.upload_photo(pm)
    fx.api("POST", f"/handover/claims/{claim['id']}/verify", pm, json={
        "passed": False, "reason": "Acian belum rata, mohon dihaluskan."})
    fx.api("POST", f"/handover/claims/{claim['id']}/complete", pm, json={
        "photo_file_ids": [photo2], "note": "Diperbaiki ulang."})
    res = fx.api("POST", f"/handover/claims/{claim['id']}/verify", pm, json={"passed": True})
    check(res.status_code == 400 and "mengerjakan" in detail_of(res).lower(),
          "H9g pemeriksa tidak boleh orang yang mengerjakan (dijaga di data)",
          detail_of(res)[:100])
    ver = body(fx.api("POST", f"/handover/claims/{claim['id']}/verify", owner, json={
        "passed": True, "note": "Rapi."}))
    check(ver.get("state") == "diverifikasi" and ver.get("verified_by"),
          "H9h pemeriksaan oleh orang lain diterima & tercatat", ver.get("verified_by"))
    closed = body(fx.api("POST", f"/handover/claims/{claim['id']}/close", owner, json={
        "ack_by": "Pembeli gate 39", "ack_note": "Sudah saya periksa."}))
    check(closed.get("state") == "ditutup" and closed.get("ack_by"),
          "H9i penutupan butuh pengakuan pembeli", closed.get("ack_by"))
    punch_now = fx.db.punch_items.find_one({"id": accepted.get("punch_id")},
                                            {"_id": 0, "status": 1})
    check((punch_now or {}).get("status") == "closed",
          "H9j pekerjaan perbaikannya ikut ditutup (tidak menggantung)",
          str((punch_now or {}).get("status")))
    return claim


def cancel_blocked_by_claim(pm, sales, lead, old, old_doc):
    """H7f/H7g/H7h — pembatalan BAST DITAHAN selama klaim garansinya masih berjalan.

    Kalau dokumen serah terima boleh dibatalkan sementara klaim garansi masih dikerjakan,
    pekerjaan perbaikan itu kehilangan dasarnya (masa garansi ikut hilang) dan pembeli
    ditinggal tanpa jawaban. Karena itu urutannya dipaksa: tuntaskan klaimnya lebih dulu.
    """
    live = body(fx.api("POST", "/handover/claims", sales, json={
        "unit_id": old["unit"]["id"], "category": "struktur", "source": "komplain_cs",
        "title": "Retak baru di dinding penyekat (klaim berjalan)"}))
    check(live.get("state") == "diajukan",
          "H7f bahan uji: satu klaim garansi dibiarkan BERJALAN", str(live.get("state_label")))
    res = fx.api("POST", f"/handover/{old_doc['id']}/cancel", lead, json={
        "reason": "Mencoba membatalkan padahal klaim garansinya masih berjalan."})
    check(res.status_code == 400 and "klaim garansi berjalan" in detail_of(res).lower(),
          "H7g pembatalan DITOLAK selama klaim garansi masih berjalan", detail_of(res)[:120])
    still = fx.db.unit_handovers.find_one({"id": old_doc["id"]}, {"_id": 0, "state": 1})
    check((still or {}).get("state") == "issued",
          "H7h dokumen tetap berlaku setelah pembatalan ditolak", str(still))
    fx.api("POST", f"/handover/claims/{live['id']}/decide", pm, json={
        "accept": False, "reject_reason": "kelalaian_pemakaian",
        "reason": "Retak berasal dari pembongkaran sekat oleh pemilik sendiri."})
    done = fx.api("POST", f"/handover/{old_doc['id']}/cancel", lead, json={
        "reason": "Dokumen salah unit; klaim garansinya sudah dituntaskan lebih dulu."})
    check(done.status_code == 200 and body(done).get("state") == "cancelled",
          "H7i setelah klaim dituntaskan, pembatalan bisa dilakukan",
          str(body(done).get("state_label") or detail_of(done)[:80]))


def report_checks(pm, project):
    rep = body(fx.api("GET", "/handover/claims/report", pm,
                      params={"project_id": project["id"]}))
    tie = rep.get("tie_out") or {}
    check(tie.get("matches") is True and tie.get("sum_per_state") == rep.get("total"),
          "H10a rekap klaim tie-out (Σ per status = jumlah klaim)",
          f"{tie.get('sum_per_state')} = {tie.get('total')}")
    empty = body(fx.api("GET", "/handover/claims/report", pm, params={
        "project_id": project["id"], "period": "2019-03"}))
    check(empty.get("missing") is True and empty.get("avg_days_to_close") is None
          and "belum ada data" in (empty.get("avg_days_note") or "").lower(),
          "H10b masa tanpa klaim mengaku 'belum ada data' (bukan 0 hari)",
          (empty.get("avg_days_note") or "")[:90])


def main():
    print("=" * 78)
    print("GATE 39 — SERAH TERIMA UNIT, MASA GARANSI & KLAIM PASCA-HUNI (Fase 50A)")
    print("=" * 78)
    fin = fx.login("finance@sipro.co.id")
    lead = fx.login("finlead@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    sales = fx.login("manager@sipro.co.id")

    project = fx.make_project("Proyek Gate 39", "GATE39")
    blocked = fx.blocked_unit(project, "G39-TAHAN", "Pembeli Gate Tertahan")
    ready = fx.ready_unit(project, "G39-SIAP", "Pembeli Gate Siap")
    old = fx.ready_unit(project, "G39-LAMA", "Pembeli Gate Lama")
    try:
        hold_checks(fin, pm, blocked)
        doc = override_checks(lead, fin, blocked)
        clean_checks(fin, ready)
        old_doc = clean_checks(fin, old, day=fx.days_ago(400))
        claim_checks(pm, site, owner, sales, old["unit"])
        report_checks(pm, project)
        # Pembatalan diuji dua kali: (a) dokumen tanpa klaim berjalan, (b) dokumen yang
        # klaim garansinya MASIH berjalan — yang kedua wajib DITOLAK.
        cancel_checks(lead, fin, doc)
        cancel_blocked_by_claim(pm, sales, lead, old, old_doc)
    finally:
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 39 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 39 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
