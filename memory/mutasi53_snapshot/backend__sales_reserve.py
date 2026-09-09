"""SATU JALUR RESERVASI (Fase 53A).

## Cacat NYATA yang ditutup berkas ini

Ada DUA tempat yang membuat baris `deals`, dan keduanya membuat bentuk yang berbeda:

| | `deals_router.reserve_unit` | `quotation_engine.convert` (sebelum Fase 53) |
|---|---|---|
| penanda status | `status="reserved"` | `stage="reserved", status="active"` |
| masa keep unit | `reserved_until` diisi | tidak ada |
| booking fee | diisi | tidak ada |
| tahap lead | maju ke `booking` (bukti reservasi) | tidak maju |
| ikatan unit→deal→lead→pembeli | `sync_unit_binding` | tidak dipanggil |
| tugas "konfirmasi booking fee" | lahir | tidak lahir |
| jam tahap (SLA) | `stage_clock.patch_for` | tidak ada |

Akibatnya deal yang lahir dari PENAWARAN adalah deal cacat: `POST /deals/{id}/book`
menolaknya ("Deal harus berstatus 'reserved'"), sehingga AR tidak pernah lahir, tahap lead
mandek, unit tidak terikat pembeli, dan reservasi itu tidak pernah kedaluwarsa. Pemakai
melihatnya sebagai "penawaran dan unit deal belum ter-wiring" — dan itu memang benar.

Sekarang KEDUA jalan memanggil `reserve()` di berkas ini. Satu aturan reservasi, satu
bentuk data. Penawaran hanya MENAMBAH jejak (`quotation_id`, add-on, diskon) pada deal yang
bentuknya sama dengan reservasi biasa.
"""
import logging

import lead_lifecycle as lc
import stage_clock as clock
from core_utils import due_in, new_id, now_iso
from db import BOOKING_HOLD_DAYS, ORG_ID, db
from engine import add_activity, auto_create_task, emit

logger = logging.getLogger("sipro.reserve")


async def _bind_unit(org: str, unit_id: str) -> None:
    """Ikatan unit → deal → lead → pembeli (dipakai portal, laporan, jadwal bangun)."""
    import build_engine as be
    try:
        await be.sync_unit_binding(org, unit_id)
    except Exception:  # noqa: BLE001 — ikatan denormalisasi tidak boleh menggagalkan reservasi
        logger.exception("sync_unit_binding gagal untuk unit %s", unit_id)


async def reserve(org: str, *, lead: dict, unit: dict, actor: str, booking_fee: int = 0,
                  notes: str = None, extra: dict = None) -> dict:
    """Tahan unit + buat deal `reserved`. SATU-SATUNYA jalan membuat reservasi.

    `extra` dipakai pemanggil untuk menempelkan jejak tambahan (mis. `quotation_id`,
    `addons`, `discount`) TANPA mengubah bentuk dasar deal.

    Mengembalikan dokumen deal. Melempar `ValueError` bila unit sudah tidak tersedia —
    pemanggil yang menerjemahkannya menjadi 409/400 sesuai lapisannya.
    """
    ts = now_iso()
    deal_id = new_id()
    reserved_until = due_in(days=BOOKING_HOLD_DAYS)
    # Penahanan ATOMIK: hanya berhasil bila unit benar-benar masih `available`.
    held = await db.units.find_one_and_update(
        {"id": unit["id"], "org_id": org, "status": "available"},
        {"$set": {"status": "reserved", "reserved_by_deal": deal_id, "updated_at": ts}})
    if held is None:
        raise ValueError(f"Unit {unit.get('code')} tidak tersedia — sudah di-reserve atau "
                         "di-booking oleh transaksi lain.")
    deal = {
        "id": deal_id, "org_id": org, "lead_id": lead["id"], "lead_name": lead.get("name"),
        "unit_id": unit["id"], "unit_code": unit.get("code"),
        "project_id": unit.get("project_id"),
        "assigned_to": lead.get("assigned_to") or actor,
        "status": "reserved", "price": int(unit.get("price") or 0),
        "booking_fee": int(booking_fee or 0),
        "reserved_at": ts, "reserved_until": reserved_until, "booked_at": None,
        "notes": notes, "customer_id": None, "contract_id": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    deal.update(extra or {})
    await db.deals.insert_one({**deal, **await clock.patch_for("deal", "reserved",
                                                              org_id=org, at=ts)})
    await _bind_unit(org, unit["id"])
    # Tahap "booking" lahir dari BUKTI reservasi unit (Fase 29b) — bukan pilihan manual.
    await lc.advance_on_deal({"id": deal_id, "lead_id": lead["id"], "status": "draft",
                             "org_id": org}, stage="booking", actor=actor,
                            reason=f"Reservasi unit {unit.get('code')}")
    await emit("deal.reserved", "deal", deal_id, {"unit_id": unit["id"]}, org_id=org)
    await auto_create_task(
        source_event=f"deal.bookingfee:{deal_id}", jobdesk_code="SM-05",
        title=f"Konfirmasi booking fee: {lead.get('name')} / unit {unit.get('code')}",
        type="follow_up", related_entity_type="deal", related_entity_id=deal_id,
        assigned_to=deal["assigned_to"], due_date=due_in(days=1), priority="high", org_id=org)
    await add_activity(entity_type="lead", entity_id=lead["id"], type="system",
                       body=(f"Reservasi unit {unit.get('code')} dibuat "
                             f"(hold s/d {reserved_until[:10]})."),
                       actor=actor, org_id=org)
    deal.pop("_id", None)
    return deal


async def unit_or_error(org: str, unit_id: str) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise ValueError("Unit tidak ditemukan.")
    return unit


async def lead_or_error(org: str, lead_id: str) -> dict:
    lead = await db.leads.find_one({"id": lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise ValueError("Lead tidak ditemukan.")
    return lead


async def active_deal_of_lead(org: str, lead_id: str) -> dict:
    """Deal yang masih hidup untuk satu lead (reserved/booked/completed — bukan batal)."""
    return await db.deals.find_one(
        {"org_id": org, "lead_id": lead_id,
         "status": {"$in": ["reserved", "booked", "completed"]}},
        {"_id": 0}, sort=[("created_at", -1)])
