"""Deals + Units — atomic booking (anti double-booking). Slice A."""
from fastapi import APIRouter, Depends, HTTPException

import listing as lst
import settings_store as cfg
import stage_clock as clock
import sequences as seq
from db import db, ORG_ID, BOOKING_HOLD_DAYS
from core_utils import new_id, now_iso, serialize_doc, parse_pagination, due_in
from rbac import can, require_permission, scope_query, is_scoped_sales, audit_log, has_role
import lead_lifecycle as lc
from engine import emit, add_activity, auto_create_task, dispatch_pending
from models import DealReserve, DealAction, PpjbSign, AjbSign

router = APIRouter(tags=["deals"])


async def _bind_unit(org: str, unit_id: str):
    """Fase 31: simpan ikatan unit → deal → lead → pembeli pada dokumen unit & jadwalnya."""
    import build_engine as be
    try:
        await be.sync_unit_binding(org, unit_id)
    except Exception:  # noqa: BLE001  (ikatan denormalisasi tidak boleh menggagalkan deal)
        pass


# ----------------------------- Units -----------------------------
UNIT_SORTS = {"code": "code", "type": "type", "status": "status", "price": "price",
              "construction_progress": "construction_progress", "block": "block",
              "cluster_code": "cluster_code", "payment_status": "payment_status",
              "created_at": "created_at", "updated_at": "updated_at"}


@router.get("/units")
async def list_units(project_id: str = None, status: str = None, q: str = None,
                     type: str = None, cluster_id: str = None, block_id: str = None,
                     construction_status: str = None, payment_status: str = None,
                     customer_id: str = None, lead_id: str = None,
                     sort: str = None, direction: str = None,
                     skip: int = 0, limit: int = 200,
                     user: dict = Depends(require_permission("units", "view"))):
    """Daftar unit: cari kode + filter multi (status/tipe/cluster/blok) + sort (Fase 40)."""
    skip, limit = parse_pagination(skip, limit)
    org = user.get("org_id", ORG_ID)
    q_base = {"org_id": org}
    if project_id:
        q_base["project_id"] = project_id
    lst.apply_in(q_base, "status", status)
    lst.apply_in(q_base, "type", type)
    lst.apply_in(q_base, "cluster_id", cluster_id)
    lst.apply_in(q_base, "block_id", block_id)
    lst.apply_in(q_base, "construction_status", construction_status)
    lst.apply_in(q_base, "payment_status", payment_status)
    lst.apply_in(q_base, "customer_id", customer_id)
    lst.apply_in(q_base, "lead_id", lead_id)
    lst.apply_search(q_base, q, ("code", "type", "block", "cluster_code", "lead_name"))
    total = await db.units.count_documents(q_base)
    rows = await (db.units.find(q_base, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, UNIT_SORTS, ("code", 1)))
                  .skip(skip).limit(limit).to_list(limit))
    projects = await db.projects.find({"org_id": org}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    pmap = {p["id"]: p["name"] for p in projects}
    for u in rows:
        u["project_name"] = pmap.get(u.get("project_id"))
    lst.attach_aging(rows, history_field="status_history")
    # Hitungan status memakai filter yang sama MINUS filter status sendiri, supaya angka pada
    # chip filter tidak berubah menjadi 0 begitu satu status dipilih (dulu membingungkan).
    base_no_status = {k: v for k, v in q_base.items() if k != "status"}
    counts = {}
    for st in ("available", "reserved", "booked", "sold"):
        counts[st] = await db.units.count_documents({**base_no_status, "status": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


# ----------------------------- Deals -----------------------------
DEAL_SORTS = {"unit_code": "unit_code", "status": "status", "price": "price",
              "booking_fee": "booking_fee", "assigned_to": "assigned_to",
              "reserved_at": "reserved_at", "created_at": "created_at",
              "updated_at": "updated_at", **clock.SORTS}


@router.get("/deals")
async def list_deals(status: str = None, q: str = None, assigned_to: str = None,
                     project_id: str = None, lead_id: str = None, unit_id: str = None,
                     sort: str = None, direction: str = None, sla: str = None,
                     created_from: str = None, created_to: str = None,
                     skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("deals", "view"))):
    """Daftar deal: cari + filter multi + sort server-side + umur status (Fase 40) +
    filter umur status/SLA dari Pusat Konfigurasi (Fase 41)."""
    skip, limit = parse_pagination(skip, limit)
    base = {}
    lst.apply_in(base, "status", status)
    lst.apply_in(base, "assigned_to", assigned_to)
    lst.apply_in(base, "project_id", project_id)
    lst.apply_in(base, "lead_id", lead_id)
    lst.apply_in(base, "unit_id", unit_id)
    clock.apply_sla_filter(base, "deal", sla)
    lst.apply_range(base, "created_at", created_from, created_to)
    lst.apply_search(base, q, ("unit_code", "notes"))
    query = scope_query(user, base)
    total = await db.deals.count_documents(query)
    rows = await (db.deals.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, DEAL_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    await clock.attach(rows, "deal", org_id=user.get("org_id", ORG_ID))
    counts = {}
    for st in ("reserved", "booked", "cancelled", "closed"):
        counts[st] = await db.deals.count_documents({**scope_query(user, {}), "status": st})
    # enrich
    for d in rows:
        unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0, "code": 1, "type": 1})
        lead = await db.leads.find_one({"id": d.get("lead_id")}, {"_id": 0, "name": 1})
        d["unit_code"] = unit.get("code") if unit else None
        d["unit_type"] = unit.get("type") if unit else None
        d["lead_name"] = lead.get("name") if lead else None
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


@router.get("/deals/{deal_id}")
async def get_deal(deal_id: str, user: dict = Depends(require_permission("deals", "view"))):
    d = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    if is_scoped_sales(user) and d.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan deal Anda")
    return {"data": serialize_doc(d)}


_COST_KEYS = ("bphtb", "notary_fee", "bank_fee", "insurance", "pph_seller", "promo_discount")


def _clean_costs(costs) -> dict:
    """Hanya angka ≥0 yang diisi manusia + penanda all-in; kosong = belum diketahui."""
    out = {}
    for k in _COST_KEYS:
        v = (costs or {}).get(k)
        if v not in (None, "") and int(v) >= 0:
            out[k] = int(v)
    if (costs or {}).get("all_in_by_developer"):
        out["all_in_by_developer"] = True
    return out


@router.post("/deals/reserve")
async def reserve_unit(payload: DealReserve,
                       user: dict = Depends(require_permission("deals", "create"))):
    """Reservasi unit — memakai SATU jalur reservasi bersama (`sales_reserve.reserve`).

    Fase 53: isi fungsi ini dipindah ke `sales_reserve.py` supaya jalur dari PENAWARAN
    (`quotation_engine.convert`) tidak lagi membuat deal berbentuk lain. Dulu deal hasil
    penawaran ditulis `{"stage": "reserved", "status": "active"}` sehingga `POST
    /deals/{id}/book` menolaknya, tahap lead tidak maju, unit tidak terikat pembeli, dan
    masa keep unit tidak pernah diset.
    """
    import sales_reserve as sr
    org = user.get("org_id", ORG_ID)
    unit = await db.units.find_one({"id": payload.unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan")
    lead = await db.leads.find_one({"id": payload.lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")
    if is_scoped_sales(user) and lead.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan lead Anda")
    # `reservation.max_active_per_lead` + `reservation.override_roles` (Pusat Konfigurasi).
    max_active = int(await cfg.get("reservation.max_active_per_lead", org_id=org) or 1)
    active_cnt = await db.deals.count_documents(
        {"org_id": org, "lead_id": lead["id"], "status": {"$in": ["reserved", "booked"]}})
    if active_cnt >= max_active:
        override_roles = list(await cfg.get("reservation.override_roles", org_id=org) or [])
        reason = (payload.limit_override_reason or "").strip()
        if not has_role(user, *override_roles) or len(reason) < 10:
            raise HTTPException(status_code=409, detail=(
                f"Lead ini sudah memegang {active_cnt} unit aktif (batas {max_active}). "
                "Hanya peran " + ", ".join(override_roles or ["-"])
                + " yang boleh melewati batas, dengan alasan (≥10 karakter)."))
        await audit_log(user, "override", "deals", None,
                        {"limit_override": True, "reason": reason, "active": active_cnt})
    # Fase 69: reservasi langsung memakai MESIN HARGA yang sama dengan penawaran — rincian
    # (harga dasar, add-on, skema diskon/promo/kupon, termin) tersimpan pada deal.
    import quotation_engine as qe
    import pricing_engine as pe
    try:
        calc = await qe.simulate(org, unit_id=unit["id"], addons=payload.addons,
                                 scheme_id=payload.scheme_id, kpr=payload.kpr,
                                 discount_scheme_id=payload.discount_scheme_id,
                                 promo_id=payload.promo_id, coupon_code=payload.coupon_code,
                                 lead_id=lead["id"], booking_fee=payload.booking_fee,
                                 allin_scheme_id=payload.allin_scheme_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if calc["needs_discount_approval"]:
        raise HTTPException(status_code=400, detail=(
            "Potongan ini memerlukan persetujuan manajer — buat PENAWARAN lebih dulu, "
            "lalu konversi menjadi reservasi setelah disetujui."))
    # Fase 77E: add-on berharga master 0 memblokir reservasi. Override sales_manager+ dengan
    # alasan → dicatat sebagai add-on HARGA + DISKON 100% (pendapatan & piutang tetap utuh).
    zero = [a for a in calc.get("addons") or [] if not int(a.get("unit_price") or 0)
            and (a.get("finance_treatment") or "revenue") != "info"]
    if zero:
        ov = payload.addon_zero_override or {}
        prices = {k: int(v) for k, v in (ov.get("prices") or {}).items() if int(v or 0) > 0}
        if (not await can(user.get("role"), "pricing", "approve")
                or len((ov.get("reason") or "").strip()) < 10
                or any(a["code"] not in prices for a in zero)):
            raise HTTPException(status_code=409, detail=(
                "Add-on berharga Rp 0 di master: " + ", ".join(a["code"] for a in zero)
                + ". Isi harganya di master, atau sales manager mengisi harga + alasan (dicatat "
                "sebagai diskon 100%, bukan harga nol)."))
        for a in zero:
            a["unit_price"] = prices[a["code"]]
            a["amount"] = prices[a["code"]]
            a["formula"] = "harga override manajer"
            # Potongan bersasaran ADD-ON: tidak menyentuh harga unit / termin / KPR.
            calc["discount_lines"].append({
                "source": "override", "source_label": "Override add-on", "rule_id": a["code"],
                "code": a["code"], "name": f"Gratis {a.get('name') or a['code']}", "amount": a["amount"],
                "target": "addon", "target_component": a["code"], "target_label": "add-on",
                "formula": "diskon 100%", "requires_approval": False, "reason": ov["reason"].strip(),
                "by": user.get("email")})
            calc["addon_total"] = int(calc.get("addon_total") or 0) + a["amount"]
        await audit_log(user, "override", "deals", None,
                        {"addon_zero": [a["code"] for a in zero], "reason": ov["reason"].strip()})
    # Fase 76: biaya dari SKEMA all-in (snapshot komponen — SUDAH dihitung `simulate` dengan
    # potongan bersasaran komponen), atau manual oleh finance + alasan.
    import allin_engine as ae
    costs = _clean_costs(payload.costs)
    try:
        if payload.allin_scheme_id:
            snap = dict(calc["costs"] or {})
            costs = {k: v for k, v in costs.items() if k in ("pph_seller", "promo_discount")}
            costs.update(snap)
        elif payload.costs_manual is not None:
            if not await ae.may_manual(user):  # MANUAL_ROLES = pemegang finance:manage
                raise HTTPException(status_code=403, detail=(
                    "Input biaya manual hanya untuk finance_manager/superadmin — pilih skema all-in."))
            costs.update(ae.manual_components(payload.costs_manual, payload.costs_manual_reason,
                                              user.get("email")))
            await audit_log(user, "override", "deal_costs", None,
                            {"reason": payload.costs_manual_reason, "items": payload.costs_manual})
            qe.attach_costs(calc, costs)
        elif any(k in costs for k in ("bphtb", "notary_fee", "bank_fee", "insurance")):
            if not await ae.may_manual(user):
                raise HTTPException(status_code=403, detail=(
                    "Input biaya bebas sudah ditutup — pilih skema all-in dari master."))
            costs["components"] = ae.legacy_components(costs)
            costs["scheme_code"], costs["scheme_name"] = "LEGACY", "Legacy (input bebas)"
            qe.attach_costs(calc, costs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Fase 88C: potongan bersasaran komponen biaya yang tidak menemukan komponennya = pending.
    pending = [x for x in calc["discount_lines"] if x.get("pending")]
    if pending:
        raise HTTPException(status_code=400, detail=(
            "Potongan " + ", ".join(x["code"] for x in pending)
            + " menyasar komponen biaya yang tidak ada pada transaksi ini — pilih skema all-in "
            "yang memuat komponennya, atau pilih promo lain."))
    # Booking fee bersih setelah promo bersasaran booking fee.
    booking_fee_net = int(calc.get("booking_fee_net") if calc.get("booking_fee_net") is not None
                          else (payload.booking_fee or 0))
    qe.refresh_totals(calc)
    try:
        deal = await sr.reserve(org, lead=lead, unit=unit, actor=user.get("email"),
                                booking_fee=booking_fee_net, notes=payload.notes,
                                extra={"price": int(calc["net_price"]),
                                       "discount": int(calc["discount_amount"] or 0),
                                       "addons": calc["addons"],
                                       "scheme_id": (calc.get("scheme") or {}).get("id"),
                                       # Jalur 1: skema yang DIPILIH sales mengunci jenis kontrak;
                                       # skema bawaan (tidak dipilih) boleh diganti saat konversi.
                                       "scheme_explicit": bool(payload.scheme_id),
                                       "pricing": qe.pricing_snapshot(calc),
                                       "costs": costs})
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if calc.get("coupon_code"):
        await pe.redeem_coupon(org, calc["coupon_code"], unit=unit, lead=lead,
                               ref_type="deal", ref_id=deal["id"],
                               amount=int((calc.get("coupon") or {}).get("amount") or 0),
                               actor=user.get("email"))
    return {"data": serialize_doc(deal)}


@router.get("/deals/{deal_id}/delete-check")
async def deal_delete_check(deal_id: str, user: dict = Depends(require_permission("deals", "view"))):
    import force_delete as fd
    d = await _get_deal_editable(deal_id, user)
    org = user.get("org_id", ORG_ID)
    fp = await fd.footprint(org, deal_id)
    can_force = fd.may_force(user)
    return {"data": {"can_delete": can_force, "can_force": can_force, "blockers": fp,
                     "note": "Hapus deal menghapus SELURUH transaksinya (AR, kuitansi, jurnal, booking fee, "
                             "biaya all-in, kontrak, komisi). Unit kembali tersedia." if can_force
                     else "Hanya Direksi/Super Admin yang boleh menghapus deal beserta transaksinya."}}


@router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, reason: str = None,
                      user: dict = Depends(require_permission("deals", "update"))):
    """HAPUS PAKSA deal + seluruh turunannya (akses penuh + alasan). Unit kembali `available`."""
    import force_delete as fd
    d = await _get_deal_editable(deal_id, user)
    org = user.get("org_id", ORG_ID)
    if not fd.may_force(user):
        raise HTTPException(status_code=403, detail="Hapus deal beserta transaksinya hanya untuk Direksi/Super Admin.")
    if len((reason or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Hapus deal wajib alasan (minimal 10 huruf).")
    out = await fd.delete_deal_cascade(org, d, user.get("email"))
    await _bind_unit(org, d["unit_id"])
    await audit_log(user, "force_delete", "deals", deal_id,
                    {"reason": reason.strip(), "unit_code": d.get("unit_code"), "removed": out["removed"]})
    return {"data": out}


async def _get_deal_editable(deal_id: str, user: dict) -> dict:
    d = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    if is_scoped_sales(user) and d.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan deal Anda")
    return d


@router.post("/deals/{deal_id}/book")
async def book_deal(deal_id: str, payload: DealAction,
                    user: dict = Depends(require_permission("deals", "update"))):
    d = await _get_deal_editable(deal_id, user)
    if d.get("status") != "reserved":
        raise HTTPException(status_code=400, detail="Deal harus berstatus 'reserved' untuk di-booking.")
    org = user.get("org_id", ORG_ID)
    import booking_fee as bf
    blocked = await bf.block_booking_reason(org, d)
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    ts = now_iso()
    await db.deals.update_one({"id": deal_id}, {"$set": {
        "status": "booked", "booked_at": ts, "updated_at": ts,
        **await clock.patch_for("deal", "booked", org_id=org, at=ts)}})
    await db.units.update_one({"id": d["unit_id"]}, {"$set": {
        "status": "booked", "booked_by_deal": deal_id, "payment_status": "booking_fee", "updated_at": ts}})
    # Fase 31 (perbaikan cacat): ikatan unit → deal → lead → pembeli disimpan pada unit,
    # supaya progres pembangunan, portal pembeli, dan laporan tidak bergantung pencarian
    # berlapis yang mudah putus.
    await _bind_unit(org, d["unit_id"])
    await emit("deal.booked", "deal", deal_id, {"unit_id": d["unit_id"]}, org_id=org)
    await add_activity(entity_type="lead", entity_id=d["lead_id"], type="system",
                       body="Deal dikonfirmasi (booked).", actor=user.get("email"), org_id=org)
    await dispatch_pending()  # process deal.booked now -> generate AR schedule + commission (Finance)
    fresh = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


@router.post("/deals/{deal_id}/cancel")
async def cancel_deal(deal_id: str, payload: DealAction,
                      user: dict = Depends(require_permission("deals", "update"))):
    d = await _get_deal_editable(deal_id, user)
    if d.get("status") in ("cancelled", "expired", "completed"):
        raise HTTPException(status_code=400, detail="Deal sudah selesai/batal.")
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    await db.deals.update_one({"id": deal_id}, {"$set": {
        "status": "cancelled", "updated_at": ts,
        **await clock.patch_for("deal", "cancelled", org_id=org, at=ts)}})
    await db.units.update_one({"id": d["unit_id"]}, {"$set": {
        "status": "available", "reserved_by_deal": None, "booked_by_deal": None,
        "payment_status": "none", "updated_at": ts}})
    await _bind_unit(org, d["unit_id"])
    import pricing_engine as pe
    import booking_fee as bf
    await pe.release_coupon(org, ref_type="deal", ref_id=deal_id, actor=user.get("email"))
    await bf.cancel(org, deal_id, user.get("email"))
    await emit("deal.cancelled", "deal", deal_id, {"unit_id": d["unit_id"]}, org_id=org)
    await add_activity(entity_type="lead", entity_id=d["lead_id"], type="system",
                       body=f"Deal dibatalkan{': ' + payload.note if payload.note else ''}. Unit dilepas.",
                       actor=user.get("email"), org_id=org)
    fresh = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


# ----------------------------- Legal chain (EPIC 1.4): PPJB -> AJB -> sold -----------------------------
async def _deal_payment_summary(deal_id: str, org: str, price: int) -> dict:
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    total = int(inv.get("total", price)) if inv else int(price or 0)
    paid = int(inv.get("paid", 0)) if inv else 0
    outstanding = int(inv.get("outstanding", total - paid)) if inv else total
    pct = round(paid / total * 100) if total > 0 else 0
    return {"price": int(price or 0), "total": total, "paid": paid,
            "outstanding": outstanding, "paid_pct": pct, "ar_status": (inv or {}).get("status")}


async def _legal_number(org: str, prefix: str, deal: dict = None) -> str:
    field = "ppjb" if prefix == "PPJB" else "ajb"
    d = deal or {}
    return await seq.next_number(f"legal:{field}", org, prefix=prefix, context={
        "stage": prefix, "project_id": d.get("project_id"), "unit_id": d.get("unit_id"),
        "customer_id": d.get("customer_id"), "customer_name": d.get("customer_name")})


@router.get("/deals/{deal_id}/legal")
async def deal_legal(deal_id: str, user: dict = Depends(require_permission("deals", "view"))):
    d = await _get_deal_editable(deal_id, user)
    org = user.get("org_id", ORG_ID)
    unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0, "code": 1, "status": 1}) or {}
    lead = await db.leads.find_one({"id": d.get("lead_id")}, {"_id": 0, "name": 1}) or {}
    fin = await db.financing_apps.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    payment = await _deal_payment_summary(deal_id, org, d.get("price", 0))
    return {"data": {
        "deal_id": deal_id, "status": d.get("status"), "legal_stage": d.get("legal_stage"),
        "unit_code": unit.get("code"), "unit_status": unit.get("status"), "lead_name": lead.get("name"),
        "reserved_at": d.get("reserved_at"), "booked_at": d.get("booked_at"),
        "ppjb": d.get("ppjb"), "ajb": d.get("ajb"), "sold_at": d.get("sold_at"),
        "payment": payment,
        "financing": ({"bank": fin.get("bank_name"), "status": fin.get("status"),
                       "plafon": fin.get("plafon"), "tenor": fin.get("tenor_months")} if fin else None),
    }}


@router.post("/deals/{deal_id}/ppjb")
async def sign_ppjb(deal_id: str, payload: PpjbSign,
                    user: dict = Depends(require_permission("deals", "update"))):
    d = await _get_deal_editable(deal_id, user)
    if d.get("status") != "booked":
        raise HTTPException(status_code=400, detail="PPJB hanya untuk deal berstatus 'booked'.")
    if d.get("legal_stage") in ("ppjb", "ajb"):
        raise HTTPException(status_code=400, detail="PPJB sudah ditandatangani untuk deal ini.")
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    lead = await db.leads.find_one({"id": d.get("lead_id")}, {"_id": 0, "name": 1}) or {}
    unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0, "code": 1}) or {}
    pay = await _deal_payment_summary(deal_id, org, d.get("price", 0))
    ppjb = {"number": payload.number or await _legal_number(org, "PPJB", d),
            "signed_date": payload.signed_date or ts[:10], "signed_by": lead.get("name"),
            "dp_paid": pay["paid"], "dp_pct": pay["paid_pct"], "note": payload.note, "created_at": ts}
    await db.deals.update_one({"id": deal_id, "org_id": org},
                              {"$set": {"legal_stage": "ppjb", "ppjb": ppjb, "updated_at": ts}})
    await emit("deal.ppjb", "deal", deal_id, {"unit_id": d["unit_id"], "number": ppjb["number"]}, org_id=org)
    await auto_create_task(
        source_event=f"deal.ajb:{deal_id}",
        title=f"Jadwalkan AJB (notaris): {lead.get('name')} / unit {unit.get('code')}",
        type="follow_up", related_entity_type="deal", related_entity_id=deal_id,
        assigned_to=d.get("assigned_to"), due_date=due_in(days=14), priority="medium", org_id=org)
    await add_activity(entity_type="lead", entity_id=d["lead_id"], type="system",
                       body=f"PPJB {ppjb['number']} ditandatangani untuk unit {unit.get('code')}.",
                       actor=user.get("email"), org_id=org)
    fresh = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


@router.post("/deals/{deal_id}/ajb")
async def sign_ajb(deal_id: str, payload: AjbSign,
                   user: dict = Depends(require_permission("deals", "update"))):
    d = await _get_deal_editable(deal_id, user)
    if d.get("legal_stage") != "ppjb":
        raise HTTPException(status_code=400, detail="AJB memerlukan PPJB yang sudah ditandatangani.")
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    lead = await db.leads.find_one({"id": d.get("lead_id")}, {"_id": 0, "name": 1}) or {}
    unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0, "code": 1}) or {}
    pay = await _deal_payment_summary(deal_id, org, d.get("price", 0))
    ajb = {"number": payload.number or await _legal_number(org, "AJB", d),
           "notary": payload.notary, "signed_date": payload.signed_date or ts[:10],
           "buyer": lead.get("name"), "outstanding_at_ajb": pay["outstanding"],
           "note": payload.note, "created_at": ts}
    await db.deals.update_one({"id": deal_id, "org_id": org}, {"$set": {
        "legal_stage": "ajb", "ajb": ajb, "status": "completed", "sold_at": ts,
        "updated_at": ts, **await clock.patch_for("deal", "completed", org_id=org, at=ts)}})
    await db.units.update_one({"id": d["unit_id"], "org_id": org}, {"$set": {
        "status": "sold", "sold_at": ts, "sold_by_deal": deal_id, "updated_at": ts}})
    await _bind_unit(org, d["unit_id"])
    await emit("deal.ajb", "deal", deal_id, {"unit_id": d["unit_id"], "number": ajb["number"]}, org_id=org)
    await emit("deal.sold", "deal", deal_id, {"unit_id": d["unit_id"]}, org_id=org)
    await add_activity(entity_type="lead", entity_id=d["lead_id"], type="system",
                       body=f"AJB {ajb['number']} ditandatangani — unit {unit.get('code')} SOLD.",
                       actor=user.get("email"), org_id=org)
    fresh = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}
