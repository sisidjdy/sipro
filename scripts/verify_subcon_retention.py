#!/usr/bin/env python3
"""verify_subcon_retention.py — GATE 35 (Fase 48C/48D).

Menjaga uang subkon: uang muka, potongan, retensi, dan gerbang pencairannya.

  R1  Uang muka > 30% nilai kontrak ditolak (kebijakan tertulis, bukan kebiasaan).
  R2  Uang muka masuk ASET `1-1800` saat dibayar (bukan biaya) — tidak dihitung dua kali.
  R3  Hanya `finance_manager` yang boleh MEMUTUSKAN uang muka (finance biasa 403).
  R4  Angsuran melebihi sisa uang muka ditolak.
  R5  Termin disetujui: net = bruto − retensi − potongan, dan JURNALNYA SEIMBANG dengan
      baris kredit `1-1800` (angsuran) & `4-1200` (denda).
  R6  Retensi otomatis masuk daftar; gerbang menahan selama masa pemeliharaan berjalan atau
      punch list lingkup SPK masih terbuka.
  R7  Pengaju pencairan tidak boleh mencairkan sendiri; pencairan memindahkan `2-1200` →
      `2-1100` dan tidak bisa dua kali.
  R8  Evaluasi subkon berbukti / honest-null.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture48 as fx  # noqa: E402

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


def main() -> int:
    print("=" * 78)
    print("GATE 35 — subkon: uang muka, potongan, retensi bergerbang")
    print("=" * 78)
    pm = fx.login("pm@sipro.co.id")
    fin = fx.login("finance@sipro.co.id")
    finlead = fx.login("finlead@sipro.co.id")
    proj = fx.make_project("Gate48 Subkon", f"G35-{fx.new_id()[:4].upper()}")
    sub = fx.make_subcontractor(f"G35-{fx.new_id()[:4].upper()}", "CV Gate35 Subkon")
    spk = fx.make_spk(proj, sub, 100_000_000, retention_pct=5, maintenance_days=0, end_offset=-1)
    try:
        too_big = fx.api("POST", "/subcon/advances", pm, json={
            "spk_id": spk["id"], "amount": 40_000_000,
            "reason": "uang muka melebihi kebijakan agar penolakannya teruji"})
        check(too_big.status_code == 400, "R1 uang muka > 30% kontrak ditolak", too_big.text[:90])

        adv = fx.api("POST", "/subcon/advances", pm, json={
            "spk_id": spk["id"], "amount": 20_000_000,
            "reason": "mobilisasi alat dan upah minggu pertama di lokasi"}).json()["data"]
        by_fin = fx.api("POST", f"/subcon/advances/{adv['id']}/decision", fin,
                        json={"approve": True, "reason": "coba diputus finance biasa"})
        check(by_fin.status_code == 403, "R3 finance biasa tidak boleh memutuskan uang muka",
              by_fin.text[:90])
        fx.api("POST", f"/subcon/advances/{adv['id']}/decision", finlead,
               json={"approve": True, "reason": "sesuai kontrak uang muka 20% mobilisasi"})
        paid = fx.api("POST", f"/subcon/advances/{adv['id']}/pay", fin, json={})
        je = fx.db.journal_entries.find_one({"source_id": adv["id"],
                                             "source_type": "subcon_advance"}, {"_id": 0})
        dr = {ln["account_code"]: ln["debit"] for ln in (je or {}).get("lines", [])}
        check(paid.ok and dr.get("1-1800") == 20_000_000,
              "R2 uang muka dibayar masuk aset 1-1800", str(dr)[:90])

        over = fx.api("POST", "/subcon/deductions", pm, json={
            "spk_id": spk["id"], "kind": "advance", "advance_id": adv["id"],
            "amount": 90_000_000, "reason": "angsuran melebihi sisa agar penolakannya teruji"})
        check(over.status_code == 400, "R4 angsuran melebihi sisa uang muka ditolak",
              over.text[:90])
        fx.api("POST", "/subcon/deductions", pm, json={
            "spk_id": spk["id"], "kind": "advance", "advance_id": adv["id"],
            "amount": 5_000_000, "reason": "angsuran uang muka ke-1 sesuai jadwal di SPK"})
        fx.api("POST", "/subcon/deductions", pm, json={
            "spk_id": spk["id"], "kind": "penalty", "amount": 1_000_000,
            "reason": "denda keterlambatan dua hari kalender pekerjaan struktur"})

        claim = fx.api("POST", "/subcon/claims", pm, json={
            "spk_id": spk["id"], "period": "Termin 1", "progress_pct": 50,
            "due_date": fx.day(14)}).json()["data"]
        approved = fx.api("POST", f"/subcon/claims/{claim['id']}/approve", fin)
        c = approved.json().get("data", {}) if approved.ok else {}
        gross, ret_held = int(c.get("gross", 0)), int(c.get("retention_held", 0))
        ded, net = int(c.get("deduction_total", 0)), int(c.get("net", 0))
        check(approved.ok and gross == 50_000_000 and ret_held == 2_500_000
              and ded == 6_000_000 and net == gross - ret_held - ded,
              "R5a net = bruto − retensi − potongan",
              f"{gross}/{ret_held}/{ded}/{net} · {approved.text[:60]}")
        fx.settle()
        bje = fx.wait_journal(c.get("ap_bill_id"), "ap_bill")
        lines = {ln["account_code"]: (ln["debit"], ln["credit"])
                 for ln in (bje or {}).get("lines", [])}
        tdr = sum(ln["debit"] for ln in (bje or {}).get("lines", []))
        tcr = sum(ln["credit"] for ln in (bje or {}).get("lines", []))
        check(bool(bje) and tdr == tcr == gross
              and lines.get("1-1800", (0, 0))[1] == 5_000_000
              and lines.get("4-1200", (0, 0))[1] == 1_000_000,
              "R5b jurnal termin seimbang + potongan ke akun yang benar", str(lines)[:120])

        rets = fx.api("GET", "/subcon/retentions", pm, params={"spk_id": spk["id"]}).json()
        ret = (rets.get("data") or [{}])[0]
        check(rets.get("total") == 1 and int(ret.get("amount", 0)) == ret_held,
              "R6a retensi otomatis masuk daftar", str(rets.get("summary"))[:90])

        punch = fx.make_punch(proj["id"], title="temuan gate35")
        blocked = fx.api("POST", f"/subcon/retentions/{ret['id']}/request-release", pm,
                         json={"reason": "pekerjaan sudah selesai dan diserahterimakan"})
        check(blocked.status_code == 400 and "punch" in blocked.text.lower(),
              "R6b punch list terbuka menahan pencairan", blocked.text[:100])
        fx.db.punch_items.update_one({"id": punch["id"]}, {"$set": {"status": "closed"}})

        req = fx.api("POST", f"/subcon/retentions/{ret['id']}/request-release", pm,
                     json={"reason": "masa pemeliharaan lewat dan temuan sudah ditutup"})
        check(req.ok, "R7a pencairan bisa diajukan setelah syarat terpenuhi", req.text[:90])
        self_rel = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", pm,
                          json={"reason": "mencoba mencairkan retensi yang saya ajukan sendiri"})
        check(self_rel.status_code in (400, 403), "R7b pengaju tidak boleh mencairkan sendiri (RBAC)",
              self_rel.text[:90])
        # R7b2 — SoD di LAPISAN SERVICE, diuji dengan pengguna yang MEMANG berwenang
        # mencairkan. Tanpa uji ini, aturan "pengaju ≠ pencair" tertutup oleh penolakan RBAC
        # (peran lapangan memang tidak punya izin `manage`), sehingga uji-mutasi melaporkan
        # aturan itu "lolos" padahal gate tidak pernah benar-benar mengujinya.
        fx.db.subcon_retentions.update_one({"id": ret["id"]},
                                           {"$set": {"requested_by": "finlead@sipro.co.id"}})
        same_person = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", finlead,
                             json={"reason": "pengaju dan pencair adalah orang yang sama"})
        check(same_person.status_code == 400,
              "R7b2 yang berwenang pun tidak boleh mencairkan pengajuannya sendiri",
              same_person.text[:100])
        fx.db.subcon_retentions.update_one({"id": ret["id"]},
                                           {"$set": {"requested_by": "pm@sipro.co.id"}})
        rel = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", finlead,
                     json={"reason": "masa pemeliharaan selesai tanpa temuan tersisa"})
        rje = fx.db.journal_entries.find_one({"source_id": ret["id"],
                                              "source_type": "subcon_retention"}, {"_id": 0})
        rl = {ln["account_code"]: (ln["debit"], ln["credit"]) for ln in (rje or {}).get("lines", [])}
        check(rel.ok and rl.get("2-1200", (0, 0))[0] == ret_held
              and rl.get("2-1100", (0, 0))[1] == ret_held,
              "R7c pencairan memindahkan 2-1200 → 2-1100", str(rl)[:100])
        twice = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", finlead,
                       json={"reason": "mencoba mencairkan retensi yang sama dua kali"})
        check(twice.status_code == 400, "R7d retensi tidak bisa dicairkan dua kali",
              twice.text[:90])

        ev = fx.api("GET", f"/subcon/subcontractors/{sub['id']}/evaluation", pm).json()["data"]
        check(ev["state"] in ("complete", "missing_data")
              and (ev["score"] is not None or ev["grade"] == "missing_data"),
              "R8 evaluasi subkon berbukti / honest-null", str(ev)[:100])
    finally:
        fx.settle()
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 35 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 35 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
