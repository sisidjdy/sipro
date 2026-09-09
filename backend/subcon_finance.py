"""subcon_finance.py — uang muka, potongan/denda, dan retensi subkon (Fase 48C).

Sampai Fase 47, uang subkon hanya bisa mengalir SATU arah: termin disetujui → tagihan AP.
Tiga hal yang selalu terjadi di proyek nyata belum ada modelnya:

1. **Uang muka (mobilisasi).** Dibayar di muka lalu DIANGSUR dari termin berikutnya. Tanpa
   ini, uang muka dicatat sebagai "tagihan biasa" sehingga biaya proyek dihitung dua kali
   (sekali saat uang muka, sekali saat termin).
2. **Potongan & denda.** Denda keterlambatan, bon material dari gudang kami, dan potongan
   lain harus mengurangi PEMBAYARAN tanpa mengurangi NILAI PEKERJAAN yang diakui — karena
   itu potongan dicatat sebagai baris tersendiri di tagihan, bukan dengan mengecilkan gross.
3. **Retensi yang bisa dicairkan.** `retention_held` dulu hanya menumpuk di tagihan tanpa
   daftar, tanpa masa pemeliharaan, dan tanpa jalan pencairan. Sekarang setiap termin yang
   disetujui melahirkan baris di **daftar retensi**, dan pencairannya BERGERBANG: masa
   pemeliharaan harus lewat DAN punch list proyek harus bersih. Gerbang diperiksa dua kali
   (saat pengajuan dan saat pencairan) supaya mematikan satu lapis saja tidak meloloskan uang.

Jurnal: uang muka Dr 1-1800/Cr 1-1200; potongan menjadi baris kredit pada jurnal tagihan
(lihat `gl_engine._gl_ap_approved` + `reference_p48.DEDUCTION_GL`); pencairan retensi
memindahkan Dr 2-1200 → Cr 2-1100 lalu dibayar lewat jalur AP biasa (Dr 2-1100/Cr 1-1200).
"""
from datetime import date, timedelta

import gl_engine as gl
import reference as ref
import sequences as seq
from db import db
from core_utils import new_id, now_iso, today_iso_date
from reference_p48 import (GL_AP, GL_BANK, GL_RETENTION_PAYABLE, GL_SUBCON_ADVANCE,
                          MAINTENANCE_DAYS_DEFAULT)


def _rp(n) -> str:
    return f"Rp {int(n or 0):,}"


# =============================================================== uang muka
async def create_advance(org: str, spk: dict, data: dict, actor: str) -> dict:
    if spk.get("status") not in ("draft", "active"):
        raise ValueError("Uang muka hanya untuk SPK yang masih berjalan.")
    cv = int(spk.get("contract_value", 0) or 0)
    existing = await db.subcon_advances.find(
        {"org_id": org, "spk_id": spk["id"], "state": {"$in": ["draft", "approved", "paid"]}},
        {"_id": 0, "amount": 1}).to_list(100)
    total = sum(int(x.get("amount", 0)) for x in existing) + int(data["amount"])
    if cv and total > cv * 0.3:
        raise ValueError(f"Total uang muka {_rp(total)} melebihi 30% nilai kontrak {_rp(cv)} — "
                         "kebijakan SIPRO membatasi uang muka agar risiko tidak menumpuk "
                         "di awal pekerjaan.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "advance_number": await seq.next_number("subcon_advance", org, prefix="UMK", context={
            "project_id": spk.get("project_id"), "subcon_id": spk.get("subcontractor_id")}),
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "project_id": spk["project_id"], "subcontractor_id": spk.get("subcontractor_id"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "amount": int(data["amount"]), "reason": data["reason"], "due_date": data.get("due_date"),
        "state": "draft", "amortized": 0, "outstanding": int(data["amount"]),
        "decided_by": None, "decided_at": None, "decision_reason": None,
        "paid_at": None, "paid_by": None, "journal_no": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.subcon_advances.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def decide_advance(org: str, adv: dict, approve: bool, reason: str, actor: str) -> dict:
    if adv.get("state") != "draft":
        raise ValueError("Uang muka ini sudah diputuskan sebelumnya.")
    if adv.get("created_by") == actor:
        raise ValueError("Pengaju tidak boleh menyetujui uang muka yang diajukannya sendiri "
                         "(pemisahan tugas).")
    ts = now_iso()
    await db.subcon_advances.update_one({"id": adv["id"], "org_id": org}, {"$set": {
        "state": "approved" if approve else "rejected", "decided_by": actor,
        "decided_at": ts, "decision_reason": reason, "updated_at": ts}})
    return await db.subcon_advances.find_one({"id": adv["id"]}, {"_id": 0})


async def pay_advance(org: str, adv: dict, actor: str, note: str = None) -> dict:
    if adv.get("state") != "approved":
        raise ValueError("Uang muka harus DISETUJUI lebih dulu sebelum dibayar.")
    amount = int(adv["amount"])
    ts = now_iso()
    entry = await gl.post_journal(
        org, f"Uang muka subkon {adv.get('advance_number')} — {adv.get('subcontractor_name')}",
        [{"account_code": GL_SUBCON_ADVANCE, "debit": amount, "credit": 0,
          "memo": adv.get("reason")},
         {"account_code": GL_BANK, "debit": 0, "credit": amount}],
        source_type="subcon_advance", source_id=adv["id"],
        source_event=f"subcon_advance_paid:{adv['id']}", posted_by=actor)
    await db.payments_out.insert_one({
        "id": new_id(), "org_id": org, "bill_id": None, "advance_id": adv["id"],
        "vendor": adv.get("subcontractor_name"), "amount": amount,
        "note": note or f"Uang muka {adv.get('advance_number')}", "actor": actor,
        "created_at": ts})
    await db.subcon_advances.update_one({"id": adv["id"], "org_id": org}, {"$set": {
        "state": "paid", "paid_at": ts, "paid_by": actor,
        "journal_no": entry.get("entry_no"), "updated_at": ts}})
    return await db.subcon_advances.find_one({"id": adv["id"]}, {"_id": 0})


async def list_advances(org: str, spk_id: str = None, project_ids: list = None) -> dict:
    q = {"org_id": org}
    if spk_id:
        q["spk_id"] = spk_id
    if project_ids is not None:
        q["project_id"] = {"$in": project_ids}
    rows = await db.subcon_advances.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    live = [r for r in rows if r.get("state") in ("draft", "approved", "paid")]
    return {"rows": rows, "summary": {
        "total": len(rows),
        "waiting": sum(1 for r in rows if r.get("state") == "draft"),
        "to_pay": sum(int(r["amount"]) for r in rows if r.get("state") == "approved"),
        "paid": sum(int(r["amount"]) for r in rows if r.get("state") in ("paid", "closed")),
        "outstanding": sum(int(r.get("outstanding", 0)) for r in live),
    }}


# =============================================================== potongan
async def create_deduction(org: str, spk: dict, data: dict, actor: str) -> dict:
    amount = int(data["amount"])
    adv = None
    if data["kind"] == "advance":
        if not data.get("advance_id"):
            raise ValueError("Angsuran uang muka harus menyebut uang muka mana yang diangsur.")
        adv = await db.subcon_advances.find_one(
            {"id": data["advance_id"], "org_id": org, "spk_id": spk["id"]}, {"_id": 0})
        if not adv:
            raise ValueError("Uang muka tidak ditemukan pada SPK ini.")
        if adv.get("state") != "paid":
            raise ValueError("Uang muka yang belum dibayar tidak bisa diangsur.")
        if amount > int(adv.get("outstanding", 0)):
            raise ValueError(f"Angsuran {_rp(amount)} melebihi sisa uang muka "
                             f"{_rp(adv.get('outstanding'))}.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "project_id": spk["project_id"], "subcontractor_id": spk.get("subcontractor_id"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "kind": data["kind"], "amount": amount, "reason": data["reason"],
        "advance_id": data.get("advance_id"), "state": "pending",
        "claim_id": None, "ap_bill_id": None, "applied_at": None,
        "cancelled_by": None, "cancel_reason": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.subcon_deductions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def cancel_deduction(org: str, ded: dict, reason: str, actor: str) -> dict:
    if ded.get("state") != "pending":
        raise ValueError("Hanya potongan yang belum dipotong di termin yang bisa dibatalkan.")
    ts = now_iso()
    await db.subcon_deductions.update_one({"id": ded["id"], "org_id": org}, {"$set": {
        "state": "cancelled", "cancelled_by": actor, "cancel_reason": reason, "updated_at": ts}})
    return await db.subcon_deductions.find_one({"id": ded["id"]}, {"_id": 0})


async def pending_deductions(org: str, spk_id: str) -> list:
    return await db.subcon_deductions.find(
        {"org_id": org, "spk_id": spk_id, "state": "pending"}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)


async def list_deductions(org: str, spk_id: str = None, project_ids: list = None) -> dict:
    q = {"org_id": org}
    if spk_id:
        q["spk_id"] = spk_id
    if project_ids is not None:
        q["project_id"] = {"$in": project_ids}
    rows = await db.subcon_deductions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"rows": rows, "summary": {
        "total": len(rows),
        "pending_value": sum(int(r["amount"]) for r in rows if r.get("state") == "pending"),
        "applied_value": sum(int(r["amount"]) for r in rows if r.get("state") == "applied"),
        "penalty_value": sum(int(r["amount"]) for r in rows
                             if r.get("kind") == "penalty" and r.get("state") != "cancelled"),
    }}


async def attach_deductions(org: str, bill: dict, spk: dict, claim: dict, actor: str) -> dict:
    """Tempelkan potongan yang menunggu ke tagihan SEBELUM disetujui (agar jurnal seimbang).

    Dikembalikan tagihan terbaru. Bila total potongan melebihi uang yang tersisa setelah
    retensi, seluruh proses DIBATALKAN dengan pesan yang menyebut angkanya — lebih baik
    manusia mengurangi potongan daripada sistem membayar minus.
    """
    pend = await pending_deductions(org, spk["id"])
    if not pend:
        return bill
    gross = int(bill.get("claimed", 0))
    retention = int(bill.get("retention_held", 0))
    payable = gross - retention
    total = sum(int(d["amount"]) for d in pend)
    if total > payable:
        raise ValueError(
            f"Total potongan {_rp(total)} melebihi sisa termin setelah retensi {_rp(payable)} "
            f"(termin {_rp(gross)} − retensi {_rp(retention)}). Kurangi/batalkan potongan "
            "atau tunggu termin berikutnya — pembayaran tidak boleh minus.")
    lines = [{"deduction_id": d["id"], "kind": d["kind"], "amount": int(d["amount"]),
              "reason": d["reason"], "advance_id": d.get("advance_id")} for d in pend]
    ts = now_iso()
    net = payable - total
    await db.ap_invoices.update_one({"id": bill["id"], "org_id": org}, {"$set": {
        "deductions": lines, "deduction_total": total, "net": net, "outstanding": net,
        "updated_at": ts}})
    for d in pend:
        await db.subcon_deductions.update_one({"id": d["id"], "org_id": org}, {"$set": {
            "state": "applied", "claim_id": claim.get("id"), "ap_bill_id": bill["id"],
            "applied_at": ts, "updated_at": ts}})
        if d["kind"] == "advance" and d.get("advance_id"):
            adv = await db.subcon_advances.find_one({"id": d["advance_id"], "org_id": org},
                                                    {"_id": 0})
            if adv:
                amort = int(adv.get("amortized", 0)) + int(d["amount"])
                outstanding = max(0, int(adv["amount"]) - amort)
                await db.subcon_advances.update_one({"id": adv["id"], "org_id": org}, {"$set": {
                    "amortized": amort, "outstanding": outstanding,
                    "state": "closed" if outstanding == 0 else adv.get("state"),
                    "updated_at": ts}})
    return await db.ap_invoices.find_one({"id": bill["id"], "org_id": org}, {"_id": 0})


# =============================================================== retensi
def _maintenance_until(spk: dict, base_date: str) -> str:
    days = _maintenance_days(spk)
    base = str(spk.get("end_date") or base_date)[:10]
    try:
        start = date.fromisoformat(base)
    except ValueError:
        start = date.fromisoformat(str(base_date)[:10])
    return (start + timedelta(days=days)).isoformat()


def _maintenance_days(spk: dict) -> int:
    """Masa pemeliharaan SPK. NOL adalah nilai SAH (serah terima tanpa masa pemeliharaan) —
    karena itu tidak boleh dites dengan `or`, yang diam-diam mengubah 0 menjadi 90 hari dan
    menahan uang subkon berbulan-bulan tanpa dasar kontrak."""
    days = spk.get("maintenance_days")
    return MAINTENANCE_DAYS_DEFAULT if days is None else int(days)


async def register_retention(org: str, spk: dict, claim: dict, bill: dict, actor: str) -> dict:
    """Satu termin disetujui = satu baris retensi (idempoten per tagihan)."""
    amount = int(bill.get("retention_held", 0) or 0)
    if amount <= 0:
        return None
    existing = await db.subcon_retentions.find_one(
        {"org_id": org, "ap_bill_id": bill["id"]}, {"_id": 0})
    if existing:
        return existing
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "retention_number": await seq.next_number("subcon_retention", org, prefix="RET", context={
            "project_id": spk.get("project_id"), "subcon_id": spk.get("subcontractor_id")}),
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "project_id": spk["project_id"], "subcontractor_id": spk.get("subcontractor_id"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "claim_id": claim.get("id"), "claim_number": claim.get("claim_number"),
        "ap_bill_id": bill["id"], "amount": amount,
        "retention_pct": float(bill.get("retention_pct", 0) or 0),
        "state": "held",
        "maintenance_days": _maintenance_days(spk),
        "maintenance_until": _maintenance_until(spk, str(claim.get("approved_at") or ts)),
        "requested_by": None, "requested_at": None, "request_reason": None,
        "released_by": None, "released_at": None, "release_reason": None,
        "release_bill_id": None, "journal_no": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.subcon_retentions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


WAIVABLE_BLOCKS = ("maintenance_active", "punch_open", "warranty_claim_active")
# Klaim garansi yang MASIH BERJALAN. `ditutup` dan `ditolak` sudah selesai urusannya.
ACTIVE_WARRANTY_STATES = ("diajukan", "dikerjakan", "selesai", "diverifikasi")


async def _active_warranty_claims(org: str, ret: dict) -> tuple:
    """Klaim garansi berjalan pada unit LINGKUP SPK (bukan seluruh proyek bila ada lingkup).

    Sama adilnya dengan aturan punch list: retensi milik pekerjaan ITU. SPK borongan tanpa
    lingkup unit diperlakukan konservatif — seluruh klaim berjalan di proyek menahan.
    """
    units = [u for u in await db.spk_scope_items.distinct(
        "unit_id", {"org_id": org, "spk_id": ret.get("spk_id")}) if u]
    q = {"org_id": org, "state": {"$in": list(ACTIVE_WARRANTY_STATES)}}
    if units:
        q["unit_id"] = {"$in": units}
        note = f"pada {len(units)} unit lingkup SPK ini"
    else:
        q["project_id"] = ret.get("project_id")
        note = "di proyek ini (SPK borongan tanpa lingkup unit)"
    rows = await db.warranty_claims.find(
        q, {"_id": 0, "number": 1, "title": 1, "state": 1, "unit_code": 1,
            "category": 1}).to_list(50)
    return rows, note


async def retention_gate(org: str, ret: dict) -> dict:
    """Gerbang pencairan retensi — diperiksa saat PENGAJUAN dan saat PENCAIRAN."""
    blocks = []
    if ret.get("state") == "released":
        blocks.append({"code": "already_released",
                       "detail": f"Retensi ini sudah dicairkan pada {str(ret.get('released_at'))[:10]}."})
    claim = await db.progress_claims.find_one({"id": ret.get("claim_id"), "org_id": org},
                                              {"_id": 0, "status": 1})
    if claim and claim.get("status") != "approved":
        blocks.append({"code": "claim_not_approved",
                       "detail": "Termin sumber retensi tidak berstatus disetujui."})
    today = today_iso_date()
    until = str(ret.get("maintenance_until") or "")[:10]
    if until and today < until:
        blocks.append({"code": "maintenance_active",
                       "detail": (f"Masa pemeliharaan berjalan sampai {until} "
                                  f"({ret.get('maintenance_days')} hari) — hari ini {today}.")})
    open_punch, scope_note = await _open_punch(org, ret)
    if open_punch:
        names = ", ".join(filter(None, [p.get("title") for p in open_punch[:3]]))
        blocks.append({"code": "punch_open",
                       "detail": (f"{len(open_punch)} temuan punch list masih terbuka "
                                  f"{scope_note} ({names}…) — selesaikan dulu sebelum retensi "
                                  "dicairkan.")})
    # Fase 51A — jaminan mutu tidak boleh cair saat mutunya sedang dipersoalkan.
    # Sebelum ini gerbang tidak pernah melihat `warranty_claims`, sehingga retensi bisa
    # dicairkan persis ketika rumah sedang diperbaiki karena cacat pekerjaan subkon itu.
    claims, wnote = await _active_warranty_claims(org, ret)
    if claims:
        sebut = ", ".join(f"{c.get('number')} ({c.get('title') or '-'})" for c in claims[:3])
        blocks.append({
            "code": "warranty_claim_active",
            "detail": (f"{len(claims)} klaim garansi masih berjalan {wnote}: {sebut}"
                       f"{' …' if len(claims) > 3 else ''}. Retensi adalah jaminan mutu — "
                       "tuntaskan klaimnya, atau abaikan penahanan ini dengan alasan "
                       "tertulis.")})
    # Nama penahan & apakah boleh diabaikan datang dari SSOT, bukan diketik ulang di layar.
    # Sebelum ini frontend harus menebak daftar `WAIVABLE_BLOCKS` sendiri — dua versi aturan
    # untuk satu keputusan, dan yang di layar pasti tertinggal saat aturannya berubah.
    for b in blocks:
        b["label"] = ref.label_of("retention_block", b["code"]) or b["code"]
        b["waivable"] = b["code"] in WAIVABLE_BLOCKS
    # Pengabaian (waiver) oleh Manajer Keuangan/Direksi: penahanan TETAP DITAMPILKAN supaya
    # bisa diaudit, tetapi tidak lagi menghalangi. Yang tidak bisa diabaikan tetap menahan.
    waived_codes = {w.get("code"): w for w in (ret.get("waivers") or [])}
    for b in blocks:
        w = waived_codes.get(b["code"])
        if w and b["code"] in WAIVABLE_BLOCKS:
            b["waived"] = True
            b["waived_by"] = w.get("by")
            b["waived_at"] = w.get("at")
            b["waived_reason"] = w.get("reason")
    aktif = [b for b in blocks if not b.get("waived")]
    return {"ok": not aktif, "blocks": aktif, "all_blocks": blocks,
            "waived_blocks": [b for b in blocks if b.get("waived")],
            "maintenance_until": until or None,
            # Honest-null: masa pemeliharaan yang belum dicatat BUKAN "0 hari" (0 hari
            # berarti sudah lewat — kebalikan artinya).
            "maintenance_detail": (
                f"Masa pemeliharaan {ret.get('maintenance_days')} hari sampai {until}."
                if until and ret.get("maintenance_days") is not None else
                "Masa pemeliharaan belum dicatat pada SPK ini — belum ada data, "
                "bukan nol hari."),
            "punch_scope": scope_note,
            "open_punch_count": len(open_punch),
            "warranty_claim_count": len(claims),
            "warranty_scope": wnote,
            # Nomor klaimnya dikirim supaya layar bisa MENUNJUK klaim mana yang menahan
            # (bukan hanya "ada klaim") dan menyediakan jalan ke papan garansi.
            "warranty_claims": [
                {"number": c.get("number"), "title": c.get("title"),
                 "state": c.get("state"), "unit_code": c.get("unit_code"),
                 "state_label": ref.label_of("warranty_claim_state", c.get("state")),
                 "category_label": ref.label_of("warranty_category", c.get("category"))}
                for c in claims],
            "detail": ("Syarat pencairan terpenuhi." if not aktif else
                       " ".join(b["detail"] for b in aktif))}


async def waive(org: str, ret: dict, codes: list, reason: str, actor: str) -> dict:
    """Abaikan penahanan tertentu dengan alasan tertulis (jejaknya disimpan selamanya).

    Yang TIDAK bisa diabaikan: `already_released` (dokumennya memang sudah cair) dan
    `claim_not_approved` (angkanya belum sah) — mengabaikan keduanya berarti membiarkan
    pembukuan salah, bukan mengambil risiko bisnis.
    """
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ValueError("Alasan pengabaian wajib ditulis, minimal 10 huruf — alasan ini "
                         "yang dibaca auditor kelak.")
    codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    if not codes:
        raise ValueError("Sebutkan penahanan mana yang diabaikan.")
    gate = await retention_gate(org, ret)
    aktif = {b["code"] for b in gate["blocks"]}
    tidak_dikenal = [c for c in codes if c not in WAIVABLE_BLOCKS]
    if tidak_dikenal:
        raise ValueError(
            f"Penahanan {tidak_dikenal} tidak bisa diabaikan. Yang bisa diabaikan hanya: "
            + ", ".join(WAIVABLE_BLOCKS) + ".")
    bukan_penahan = [c for c in codes if c not in aktif]
    if bukan_penahan:
        raise ValueError(f"Penahanan {bukan_penahan} tidak sedang menahan retensi ini — "
                         "tidak ada yang perlu diabaikan.")
    ts = now_iso()
    baru = [{"code": c, "reason": reason, "by": actor, "at": ts} for c in codes]
    lama = [w for w in (ret.get("waivers") or []) if w.get("code") not in set(codes)]
    await db.subcon_retentions.update_one({"id": ret["id"], "org_id": org}, {"$set": {
        "waivers": lama + baru, "updated_at": ts}})
    return await db.subcon_retentions.find_one({"id": ret["id"]}, {"_id": 0})


async def _open_punch(org: str, ret: dict) -> tuple:
    """Temuan yang MENGHALANGI pencairan retensi.

    Dibatasi pada unit yang benar-benar menjadi lingkup SPK bila ada — retensi milik
    pekerjaan ITU, bukan seluruh proyek; menahan uang subkon karena cacat pekerjaan orang
    lain sama tidak adilnya dengan membayar cacat yang belum diperbaiki. SPK borongan tanpa
    lingkup unit diperlakukan konservatif: seluruh temuan terbuka di proyek menghalangi.
    """
    units = [u for u in await db.spk_scope_items.distinct(
        "unit_id", {"org_id": org, "spk_id": ret.get("spk_id")}) if u]
    q = {"org_id": org, "project_id": ret.get("project_id"),
         "status": {"$in": ["open", "in_progress"]}}
    if units:
        q["unit_id"] = {"$in": units}
        note = f"pada {len(units)} unit lingkup SPK ini"
    else:
        note = "di proyek ini (SPK borongan tanpa lingkup unit)"
    rows = await db.punch_items.find(q, {"_id": 0, "title": 1, "unit_id": 1}).to_list(50)
    return rows, note


async def request_release(org: str, ret: dict, reason: str, actor: str) -> dict:
    if ret.get("state") != "held":
        raise ValueError("Hanya retensi berstatus 'ditahan' yang bisa diajukan pencairannya.")
    gate = await retention_gate(org, ret)
    if not gate["ok"]:
        raise ValueError("Pencairan belum bisa diajukan. " + gate["detail"])
    ts = now_iso()
    await db.subcon_retentions.update_one({"id": ret["id"], "org_id": org}, {"$set": {
        "state": "release_requested", "requested_by": actor, "requested_at": ts,
        "request_reason": reason, "updated_at": ts}})
    return await db.subcon_retentions.find_one({"id": ret["id"]}, {"_id": 0})


async def release(org: str, ret: dict, reason: str, actor: str) -> dict:
    """Cairkan retensi: Dr 2-1200 → Cr 2-1100 + tagihan AP siap bayar (sekali saja)."""
    if ret.get("state") == "released":
        raise ValueError("Retensi ini sudah dicairkan — tidak bisa dicairkan dua kali.")
    if ret.get("state") != "release_requested":
        raise ValueError("Pencairan harus DIAJUKAN lapangan/PM lebih dulu (pemisahan tugas).")
    if ret.get("requested_by") == actor:
        raise ValueError("Pengaju pencairan tidak boleh mencairkan retensi yang diajukannya "
                         "sendiri (pemisahan tugas).")
    gate = await retention_gate(org, ret)
    if not gate["ok"]:
        raise ValueError("Retensi belum boleh dicairkan. " + gate["detail"])
    amount = int(ret["amount"])
    ts = now_iso()
    bill = {
        "id": new_id(), "org_id": org, "vendor": ret.get("subcontractor_name"),
        "project_id": ret.get("project_id"), "claimed": amount, "retention_pct": 0,
        "retention_held": 0, "net": amount, "paid": 0, "outstanding": amount,
        "status": "approved", "due_date": None,
        "note": (f"Pencairan retensi {ret.get('retention_number')} atas termin "
                 f"{ret.get('claim_number')} — {reason}"),
        "bill_kind": "retention_release", "retention_id": ret["id"],
        "spk_id": ret.get("spk_id"), "subcontractor_id": ret.get("subcontractor_id"),
        "retention_released": True, "deductions": [], "deduction_total": 0,
        "approved_by": actor, "approved_at": ts, "created_by": actor,
        "created_at": ts, "updated_at": ts,
    }
    await db.ap_invoices.insert_one(dict(bill))
    entry = await gl.post_journal(
        org, f"Pencairan retensi {ret.get('retention_number')} — {ret.get('subcontractor_name')}",
        [{"account_code": GL_RETENTION_PAYABLE, "debit": amount, "credit": 0, "memo": reason},
         {"account_code": GL_AP, "debit": 0, "credit": amount}],
        source_type="subcon_retention", source_id=ret["id"],
        source_event=f"retention_released:{ret['id']}", posted_by=actor)
    await db.subcon_retentions.update_one({"id": ret["id"], "org_id": org}, {"$set": {
        "state": "released", "released_by": actor, "released_at": ts, "release_reason": reason,
        "release_bill_id": bill["id"], "journal_no": entry.get("entry_no"), "updated_at": ts}})
    return {"retention": await db.subcon_retentions.find_one({"id": ret["id"]}, {"_id": 0}),
            "bill_id": bill["id"], "journal_no": entry.get("entry_no")}


async def list_retentions(org: str, *, spk_id: str = None, state: str = None,
                          project_ids: list = None) -> dict:
    q = {"org_id": org}
    if spk_id:
        q["spk_id"] = spk_id
    if state:
        q["state"] = state
    if project_ids is not None:
        q["project_id"] = {"$in": project_ids}
    rows = await db.subcon_retentions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        r["gate"] = await retention_gate(org, r)
    return {"rows": rows, "summary": {
        "total": len(rows),
        "held_value": sum(int(r["amount"]) for r in rows if r.get("state") != "released"),
        "released_value": sum(int(r["amount"]) for r in rows if r.get("state") == "released"),
        "ready": sum(1 for r in rows if r.get("state") != "released" and r["gate"]["ok"]),
        "blocked": sum(1 for r in rows if r.get("state") != "released" and not r["gate"]["ok"]),
    }}
