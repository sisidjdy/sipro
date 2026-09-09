"""Fase 78 — PENCAIRAN KPR TERKONFIGURASI: skema tahapan per bank → tahapan tergenerasi di
kontrak → tiap pencairan DIPILIH dari tahapan (bukan angka bebas), divalidasi, dibukukan sebagai
kuitansi metode `kpr` + jurnal; pembatalan = jurnal balik + status `dibatalkan` (tanpa hapus)."""
import bank_match
import finance_engine as fe
from core_utils import new_id, now_iso
from db import db
from engine import add_activity

CONDITIONS = ("akad", "serah_terima", "sertifikat")
CANCEL_ROLES = ("finance_manager", "super_admin", "owner")  # = pemegang izin finance:manage


async def _may_correct(role: str) -> bool:
    from rbac import can
    return await can(role, "finance", "manage")
DEFAULT_SCHEME = {"code": "BANK_STD", "bank": "", "name": "Standar (100% saat akad)",
                  "tolerance_pct": 1.0,
                  "tranches": [{"code": "T1", "name": "Pencairan akad", "pct": 100, "amount": 0,
                                "condition": "akad"}]}


def _rp(v):
    return f"Rp {int(v or 0):,}".replace(",", ".")


def validate_scheme(payload: dict) -> dict:
    tr = payload.get("tranches") or []
    if not tr:
        raise ValueError("Skema pencairan wajib punya minimal satu tahap.")
    pct = sum(float(t.get("pct") or 0) for t in tr)
    nominal = sum(int(t.get("amount") or 0) for t in tr)
    if nominal == 0 and abs(pct - 100) > 0.01:
        raise ValueError(f"Total persentase tahapan harus 100% (sekarang {pct:g}%).")
    codes = set()
    for t in tr:
        if not t.get("code") or not t.get("name"):
            raise ValueError("Setiap tahap wajib kode & nama.")
        if t["code"] in codes:
            raise ValueError(f"Kode tahap {t['code']} ganda.")
        codes.add(t["code"])
        if t.get("condition") not in CONDITIONS:
            raise ValueError(f"Syarat tahap '{t.get('condition')}' tidak dikenal ({', '.join(CONDITIONS)}).")
    return {"bank": payload.get("bank") or "", "name": payload.get("name") or "Skema pencairan",
            "code": (payload.get("code") or "").upper() or None,
            "tolerance_pct": float(payload.get("tolerance_pct") if payload.get("tolerance_pct") is not None else 1.0),
            "tranches": [{"code": t["code"], "name": t["name"], "pct": float(t.get("pct") or 0),
                          "amount": int(t.get("amount") or 0), "condition": t["condition"]} for t in tr],
            "is_active": True if payload.get("is_active") is None else bool(payload.get("is_active"))}


async def ensure_default(org: str):
    await db.kpr_disbursement_schemes.update_one(
        {"org_id": org, "code": DEFAULT_SCHEME["code"]},
        {"$setOnInsert": {"id": new_id(), "org_id": org, "is_active": True, "created_at": now_iso(),
                          **DEFAULT_SCHEME}}, upsert=True)


def build_tranches(scheme: dict, plafon: int) -> list:
    out, acc = [], 0
    tr = scheme.get("tranches") or []
    for i, t in enumerate(tr):
        if int(t.get("amount") or 0):
            amt = int(t["amount"])
        elif i == len(tr) - 1:
            amt = int(plafon) - acc
        else:
            amt = int(round(int(plafon) * float(t.get("pct") or 0) / 100))
        acc += amt
        out.append({"code": t["code"], "name": t["name"], "pct": t.get("pct"), "amount": amt,
                    "condition": t["condition"], "status": "open", "disbursement_id": None})
    return out


async def assign_scheme(org: str, contract: dict, app: dict, scheme_id: str, actor: str) -> dict:
    sch = await db.kpr_disbursement_schemes.find_one({"org_id": org, "id": scheme_id}, {"_id": 0})
    if not sch:
        raise ValueError("Skema pencairan tidak ditemukan.")
    if any(d.get("status") != "dibatalkan" for d in app.get("disbursements") or []):
        raise ValueError("Skema tidak bisa diganti: sudah ada pencairan tercatat.")
    plafon = int(app.get("approved_plafon") or app.get("plafon") or 0)
    if plafon <= 0:
        raise ValueError("Plafon (SP3K) belum tercatat — skema pencairan butuh plafon sebagai dasar tahapan.")
    tranches = build_tranches(sch, plafon)
    await db.financing_apps.update_one({"id": app["id"]}, {"$set": {
        "disbursement_scheme_id": sch["id"], "disbursement_scheme_name": sch["name"],
        "disbursement_tolerance_pct": float(sch.get("tolerance_pct") or 0), "tranches": tranches,
        "updated_at": now_iso()}})
    await add_activity(entity_type="customer", entity_id=contract.get("customer_id"), type="system",
                       actor=actor, org_id=org,
                       body=f"Skema pencairan KPR '{sch['name']}' dipilih — {len(tranches)} tahap dari plafon {_rp(plafon)}.")
    return await db.financing_apps.find_one({"id": app["id"]}, {"_id": 0})


def _condition_met(contract: dict, app: dict, cond: str) -> bool:
    legal = contract.get("legal") or {}
    if cond == "akad":
        return bool((app.get("akad") or {}).get("date") or legal.get("akad_kredit"))
    if cond == "serah_terima":
        return bool(legal.get("bast"))
    return bool(legal.get("sertifikat"))


async def disburse(org: str, contract: dict, app: dict, payload: dict, user: dict) -> dict:
    """Catat satu pencairan dari tahapan. Validasi: tagihan sudah terbit, ≤ outstanding, ≤ plafon,
    tahap tidak 2×, koreksi nominal dalam toleransi (finance saja)."""
    actor = user.get("email")
    role = user.get("role")
    if not (app.get("akad") or {}).get("date"):
        raise ValueError("Pencairan butuh akad kredit yang sudah tercatat.")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": contract["deal_id"]}, {"_id": 0})
    if not inv:
        raise LookupError("Jadwal tagihan (AR) belum terbit untuk kontrak ini — terbitkan/aktifkan kontrak dulu. "
                          "Pencairan tidak boleh masuk sebagai titipan diam-diam.")
    # Hanya termin UNIT yang dilunasi bank — baris add-on (`kpr_excluded`) ditagih terpisah.
    outstanding = fe.kpr_outstanding(inv)
    if outstanding <= 0:
        raise LookupError("Sisa piutang unit sudah 0 — tidak ada tagihan yang bisa dilunasi pencairan ini.")
    tranches = app.get("tranches") or []
    tranche = None
    if tranches:
        code = payload.get("tranche_code")
        if not code:
            raise ValueError("Pilih tahap pencairan dari skema (nominal terisi dari tahapan).")
        tranche = next((t for t in tranches if t["code"] == code), None)
        if not tranche:
            raise ValueError(f"Tahap {code} tidak ada pada skema pencairan kontrak ini.")
        if tranche.get("status") == "dicairkan":
            raise ValueError(f"Tahap {tranche['name']} sudah dicairkan — tidak bisa dicatat 2×.")
        if not _condition_met(contract, app, tranche["condition"]):
            raise ValueError(f"Syarat tahap {tranche['name']} ({tranche['condition']}) belum terpenuhi.")
        base = int(tranche["amount"])
        amount = int(payload.get("amount") or base)
        tol = float(app.get("disbursement_tolerance_pct") or 0)
        if amount != base:
            if not await _may_correct(role):
                raise PermissionError("Koreksi nominal tahap hanya boleh oleh finance_manager/superadmin.")
            if abs(amount - base) > base * tol / 100:
                raise ValueError(f"Koreksi {_rp(amount)} di luar toleransi ±{tol:g}% dari {_rp(base)}.")
    else:
        amount = int(payload.get("amount") or 0)
        if amount <= 0:
            raise ValueError("Nominal pencairan bank wajib diisi — dana ini melunasi piutang pembeli "
                             "dan harus tercatat di kuitansi & buku besar.")
    plafon = int(app.get("approved_plafon") or 0)
    disbursed = sum(int(d["amount"]) for d in app.get("disbursements") or [] if d.get("status") != "dibatalkan")
    if plafon and disbursed + amount > plafon:
        raise ValueError(f"Total pencairan {_rp(disbursed + amount)} melebihi plafon SP3K {_rp(plafon)}.")
    allow_deposit = False
    if amount > outstanding:
        if payload.get("allow_deposit") and await _may_correct(role) and len((payload.get("reason") or "").strip()) >= 10:
            allow_deposit = True
        else:
            raise ValueError(f"Pencairan {_rp(amount)} melebihi sisa piutang {_rp(outstanding)} — DITOLAK. "
                             "Kelebihan hanya boleh masuk titipan oleh finance (centang + alasan).")
    ts = now_iso()
    rc = await fe.apply_receipt(contract["deal_id"], amount, "kpr",
                                f"Pencairan KPR {app.get('bank_name') or ''} "
                                f"{(tranche or {}).get('name') or ''} ({payload.get('date') or ts[:10]})".strip(),
                                actor, org_id=org, allow_overpay=allow_deposit,
                                cash_account_id=payload.get("cash_account_id"))
    receipt = rc.get("receipt") or {}
    did = new_id()
    entry = {"id": did, "amount": amount, "date": payload.get("date") or ts[:10],
             "tranche_code": (tranche or {}).get("code"), "tranche_name": (tranche or {}).get("name"),
             "milestone": (tranche or {}).get("condition") or "akad_kredit",
             "note": payload.get("note"), "file_id": payload.get("file_id"),
             "receipt_id": receipt.get("id"), "receipt_no": receipt.get("receipt_no"),
             "cash_account_id": receipt.get("cash_account_id"),
             "cash_account_name": receipt.get("cash_account_name"),
             "deposit_excess": int(receipt.get("deposit_amount") or 0), "status": "dicatat",
             "created_by": actor, "created_at": ts}
    setter = {"kpr_stage": "pencairan", "updated_at": ts,
              "disbursed_total": disbursed + amount,
              "disbursement": {"date": entry["date"], "amount": amount, "file_id": entry["file_id"], "at": ts,
                               "by": actor, "receipt_id": receipt.get("id"), "receipt_no": receipt.get("receipt_no"),
                               "deposit_excess": entry["deposit_excess"]},
              "status": "done" if plafon and disbursed + amount >= plafon else "disbursing"}
    if tranche:
        setter["tranches"] = [{**t, "status": "dicairkan", "disbursement_id": did} if t["code"] == tranche["code"] else t
                              for t in tranches]
    await db.financing_apps.update_one({"id": app["id"]}, {
        "$set": setter, "$push": {"disbursements": entry,
                                   "stage_history": {"from": app.get("kpr_stage"), "to": "pencairan", "at": ts,
                                                     "actor": actor, "reason": payload.get("note"),
                                                     "evidence": [entry["file_id"]] if entry["file_id"] else []}}})
    await add_activity(entity_type="customer", entity_id=contract.get("customer_id"), type="finance",
                       actor=actor, org_id=org,
                       body=f"Pencairan KPR {_rp(amount)} dicatat → kuitansi {receipt.get('receipt_no')} (piutang berkurang).")
    return await db.financing_apps.find_one({"id": app["id"]}, {"_id": 0})


async def cancel(org: str, contract: dict, app: dict, disbursement_id: str, reason: str, user: dict) -> dict:
    if not await _may_correct(user.get("role")):
        raise PermissionError("Pembatalan pencairan hanya oleh finance_manager/superadmin.")
    if len((reason or "").strip()) < 10:
        raise ValueError("Alasan pembatalan minimal 10 huruf.")
    ds = app.get("disbursements") or []
    d = next((x for x in ds if x["id"] == disbursement_id), None)
    if not d:
        raise ValueError("Pencairan tidak ditemukan.")
    if d.get("status") == "dibatalkan":
        raise ValueError("Pencairan ini sudah dibatalkan.")
    if d.get("receipt_id"):
        await bank_match.void_receipt(org, d["receipt_id"], user.get("email"), reason)
    ts = now_iso()
    new_ds = [{**x, "status": "dibatalkan", "cancel_reason": reason.strip(), "cancelled_by": user.get("email"),
               "cancelled_at": ts} if x["id"] == disbursement_id else x for x in ds]
    total = sum(int(x["amount"]) for x in new_ds if x.get("status") != "dibatalkan")
    setter = {"disbursements": new_ds, "disbursed_total": total, "updated_at": ts,
              "status": "disbursing" if total else "approved"}
    if d.get("tranche_code"):
        setter["tranches"] = [{**t, "status": "open", "disbursement_id": None} if t["code"] == d["tranche_code"] else t
                              for t in app.get("tranches") or []]
        # reset penanda pengingat tahap agar finance diingatkan lagi bila tahap kembali siap cair
        await db.notifications.update_many(
            {"org_id": org, "related_entity_type": "kpr_tranche", "related_entity_id": f"{app['id']}:{d['tranche_code']}"},
            {"$set": {"related_entity_type": "kpr_tranche_cancelled"}})
    active = [x for x in new_ds if x.get("status") != "dibatalkan"]
    if active:
        last = active[-1]
        setter["disbursement"] = {"date": last["date"], "amount": last["amount"], "file_id": last.get("file_id"),
                                  "at": last["created_at"], "by": last.get("created_by"),
                                  "receipt_id": last.get("receipt_id"), "receipt_no": last.get("receipt_no"),
                                  "deposit_excess": last.get("deposit_excess", 0)}
    else:
        setter["disbursement"] = {}
    await db.financing_apps.update_one({"id": app["id"]}, {"$set": setter})
    await add_activity(entity_type="customer", entity_id=contract.get("customer_id"), type="finance",
                       actor=user.get("email"), org_id=org,
                       body=f"Pencairan KPR {_rp(d['amount'])} DIBATALKAN (jurnal balik) — {reason.strip()}")
    return await db.financing_apps.find_one({"id": app["id"]}, {"_id": 0})
