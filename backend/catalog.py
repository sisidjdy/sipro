"""KATALOG MASTER (Fase 39): tipe unit, spek tambahan (add-on), komponen biaya.

Kenapa perlu? Sebelum ini harga unit adalah satu angka tanpa penjelasan, "tipe" hanya teks
enum, dan biaya-biaya transaksi (BPHTB, notaris, bank, hook, kelebihan tanah, promo) sama
sekali tidak ada di data — padahal SEMUA angka itu tercantum di SPR/SPKT milik owner.

Tiga master di sini menjadi sumber angka tunggal untuk: reservasi/SPR (Fase 42), kontrak &
rencana bayar (Fase 43), dokumen yang di-generate (Fase 42), dan analitik biaya (Fase 49).

Prinsip: perlakuan keuangan tiap komponen (`finance_treatment`) DIKONFIGURASI, tidak
dikeraskan di kode — sehingga kebijakan akuntansi (mis. BPHTB sebagai titipan pelanggan vs
pendapatan jasa) bisa diubah admin tanpa deploy.
"""
import logging

import numbering as nb
import reference as ref
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.catalog")

# --------------------------------------------------------------- default seed data
# Angka bertanda DOC berasal dari dokumen legal owner (docs/source_templates/).
DEFAULT_PRICE_COMPONENTS = [
    {"code": "UNIT_PRICE", "label": "Harga unit (tipe)", "group": "harga",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "from_unit",
     "finance_treatment": "revenue", "gl_account": "4-1100", "order": 10,
     "note": "Diambil dari harga unit (tipe + premium cluster/blok)."},
    {"code": "ADDON_SPEC", "label": "Spek tambahan (add-on)", "group": "tambahan",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "from_addons",
     "finance_treatment": "revenue", "gl_account": "4-1100", "order": 20,
     "note": "Total add-on yang dipilih saat reservasi/booking — komponen terpisah."},
    {"code": "EXCESS_LAND", "label": "Kelebihan tanah", "group": "tambahan",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "from_addons",
     "finance_treatment": "revenue", "gl_account": "4-1100", "order": 30,
     "note": "Wajib SPKT. Estimasi sampai ada hasil ukur akhir (DOC)."},
    {"code": "HOOK_FEE", "label": "Biaya hook / posisi sudut", "group": "tambahan",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "from_addons",
     "finance_treatment": "revenue", "gl_account": "4-1100", "order": 40,
     "note": "DOC: contoh Rp3.000.000."},
    {"code": "BOOKING_FEE", "label": "Booking fee", "group": "harga",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "setting",
     "percent_of": "booking_fee.default_amount", "finance_treatment": "deposit",
     "gl_account": "2-1450", "order": 50, "note": "DOC: Rp1.000.000 saat keep unit."},
    {"code": "BPHTB", "label": "BPHTB", "group": "biaya",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "manual",
     "finance_treatment": "pass_through", "gl_account": "2-1450", "order": 60,
     "note": "DOC: Rp4.000.000–4.300.000 tergantung skema/proyek."},
    {"code": "NOTARY_FEE", "label": "Biaya notaris / akad", "group": "biaya",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "manual",
     "finance_treatment": "pass_through", "gl_account": "2-1450", "order": 70,
     "note": "DOC: SKMHT, PPJB, AJB, cek sertifikat, balik nama."},
    {"code": "BANK_FEE", "label": "Biaya bank (provisi, admin, blokir, materai)",
     "group": "biaya", "applies_schemes": ["kpr"], "calc": "manual",
     "finance_treatment": "pass_through", "gl_account": "2-1450", "order": 80,
     "note": "DOC: contoh Rp10.500.000 (hanya KPR)."},
    {"code": "INSURANCE", "label": "Asuransi jiwa & kebakaran", "group": "biaya",
     "applies_schemes": ["kpr"], "calc": "manual", "finance_treatment": "pass_through",
     "gl_account": "2-1450", "order": 90, "note": "Umum pada KPR; nominal dari bank."},
    {"code": "PPH_SELLER", "label": "PPh penjual", "group": "pajak",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "manual",
     "finance_treatment": "tax_out", "gl_account": "2-1300", "order": 100,
     "note": "DOC: pada contoh Rp0 (tergantung kebijakan & objek pajak)."},
    {"code": "PROMO_DISCOUNT", "label": "Promo / potongan all-in", "group": "potongan",
     "applies_schemes": ["cash_keras", "cash_bertahap", "kpr"], "calc": "manual",
     "finance_treatment": "discount", "gl_account": "4-1200", "order": 110,
     "note": "DOC: contoh potongan all in Rp2.000.000."},
    {"code": "PLAFON_KREDIT", "label": "Plafon kredit bank", "group": "pembiayaan",
     "applies_schemes": ["kpr"], "calc": "manual", "finance_treatment": "info",
     "order": 120, "note": "Informasi plafon KPR — bukan tagihan ke pembeli."},
]

# Daftar KASAR sesuai permintaan owner ("buatkan daftar kasar, saya tambah sendiri").
# Harga 0 = belum ditetapkan; admin mengisi di Pusat Konfigurasi › Harga & Biaya.
DEFAULT_ADDONS = [
    {"code": "ADD-HOOK", "name": "Biaya hook / posisi sudut", "category": "posisi_unit",
     "pricing_mode": "lump_sum", "unit_price": 3000000, "uom": "unit",
     "note": "DOC: contoh Rp3.000.000. Otomatis diusulkan bila unit ditandai hook."},
    {"code": "ADD-TANAH", "name": "Kelebihan tanah", "category": "kelebihan_tanah",
     "pricing_mode": "per_m2", "unit_price": 2000000, "uom": "m2",
     "requires_document": "SPKT", "negotiable": True,
     "note": "DOC: harga list Rp2.000.000/m²; harga disepakati diisi per unit (nego)."},
    {"code": "ADD-KANOPI", "name": "Kanopi carport", "category": "spek_bangunan",
     "pricing_mode": "lump_sum", "unit_price": 12500000, "uom": "unit",
     "note": "Harga contoh (list) — sesuaikan di Pusat Konfigurasi › Add-on."},
    {"code": "ADD-PAGAR", "name": "Pagar depan", "category": "spek_bangunan",
     "pricing_mode": "lump_sum", "unit_price": 9500000, "uom": "unit"},
    {"code": "ADD-KERAMIK", "name": "Upgrade keramik / lantai", "category": "spek_bangunan",
     "pricing_mode": "per_m2", "unit_price": 350000, "uom": "m2"},
    {"code": "ADD-KAMAR", "name": "Tambah kamar", "category": "spek_bangunan",
     "pricing_mode": "lump_sum", "unit_price": 45000000, "uom": "unit"},
    {"code": "ADD-DAPUR", "name": "Kitchen set", "category": "interior",
     "pricing_mode": "lump_sum", "unit_price": 18500000, "uom": "set"},
    {"code": "ADD-PLAFON", "name": "Upgrade plafon", "category": "spek_bangunan",
     "pricing_mode": "lump_sum", "unit_price": 7500000, "uom": "unit"},
    {"code": "ADD-LISTRIK", "name": "Tambah daya listrik", "category": "utilitas",
     "pricing_mode": "lump_sum", "unit_price": 3500000, "uom": "titik"},
    {"code": "ADD-AIR", "name": "Sumur bor / instalasi air", "category": "utilitas",
     "pricing_mode": "lump_sum", "unit_price": 6500000, "uom": "unit"},
    {"code": "ADD-TAMAN", "name": "Taman & lansekap", "category": "lansekap",
     "pricing_mode": "lump_sum", "unit_price": 8000000, "uom": "unit"},
]


def _clean(payload) -> dict:
    return {k: v for k, v in payload.model_dump(exclude_none=True).items()}


# --------------------------------------------------------------- tipe unit
async def list_unit_types(org: str = ORG_ID, q: str = None, active: bool = None) -> list:
    query = {"org_id": org}
    if active is not None:
        query["active"] = active
    if q:
        query["$or"] = [{"code": {"$regex": q, "$options": "i"}},
                        {"name": {"$regex": q, "$options": "i"}}]
    rows = await db.unit_types.find(query, {"_id": 0}).sort("code", 1).to_list(500)
    for r in rows:
        r["units_count"] = await db.units.count_documents(
            {"org_id": org, "unit_type_code": r["code"]})
    return rows


async def create_unit_type(payload, actor: str, org: str = ORG_ID) -> dict:
    code = payload.code or await nb.generate_unique("master:unit_type", org, "unit_types",
                                                    {"org_id": org})
    if await db.unit_types.find_one({"org_id": org, "code": code}, {"_id": 0, "id": 1}):
        raise ValueError(f"Tipe unit dengan kode '{code}' sudah ada.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **_clean(payload), "code": code,
           "created_by": actor, "created_at": ts, "updated_at": ts}
    doc.setdefault("active", True)
    await db.unit_types.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_unit_type(type_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = actor
    res = await db.unit_types.update_one({"id": type_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Tipe unit tidak ditemukan.")
    return await db.unit_types.find_one({"id": type_id}, {"_id": 0})


# --------------------------------------------------------------- add-on
async def list_addons(org: str = ORG_ID, category: str = None, active: bool = None,
                      project_id: str = None) -> list:
    query = {"org_id": org}
    if category:
        query["category"] = category
    if active is not None:
        query["active"] = active
    rows = await db.addon_items.find(query, {"_id": 0}).sort([("category", 1), ("code", 1)]).to_list(500)
    if project_id:
        rows = [r for r in rows
                if not r.get("applies_project_ids") or project_id in r["applies_project_ids"]]
    return rows


async def create_addon(payload, actor: str, org: str = ORG_ID) -> dict:
    code = payload.code or await nb.generate_unique(
        "master:addon", org, "addon_items", {"org_id": org}, context={"category": payload.category})
    if await db.addon_items.find_one({"org_id": org, "code": code}, {"_id": 0, "id": 1}):
        raise ValueError(f"Add-on dengan kode '{code}' sudah ada.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **_clean(payload), "code": code,
           "created_by": actor, "created_at": ts, "updated_at": ts}
    doc.setdefault("active", True)
    await db.addon_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_addon(addon_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = actor
    res = await db.addon_items.update_one({"id": addon_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Add-on tidak ditemukan.")
    return await db.addon_items.find_one({"id": addon_id}, {"_id": 0})


async def suggested_addons_for_unit(unit: dict, org: str = ORG_ID) -> list:
    """Usulan add-on berdasarkan ATRIBUT NYATA unit (bukan tebakan): hook & kelebihan tanah."""
    out = []
    if unit.get("corner"):
        hook = await db.addon_items.find_one(
            {"org_id": org, "category": "posisi_unit", "active": True}, {"_id": 0})
        if hook:
            out.append({**hook, "suggested_qty": 1,
                        "reason": "Unit ditandai hook/sudut."})
    excess = int(unit.get("excess_land_m2") or 0)
    if excess > 0:
        land = await db.addon_items.find_one(
            {"org_id": org, "category": "kelebihan_tanah", "active": True}, {"_id": 0})
        if land:
            price = int(land.get("unit_price") or 0)
            if not price:
                import settings_store as cfg
                price = int(await cfg.get("addon.excess_land_price_per_m2", org_id=org) or 0)
            out.append({**land, "unit_price": price, "suggested_qty": excess,
                        "reason": f"Kelebihan tanah {excess} m² tercatat pada unit."})
    return out


# --------------------------------------------------------------- komponen biaya
async def list_price_components(org: str = ORG_ID, scheme: str = None,
                                active: bool = None) -> list:
    query = {"org_id": org}
    if active is not None:
        query["active"] = active
    rows = await db.price_components.find(query, {"_id": 0}).sort("order", 1).to_list(200)
    if scheme:
        rows = [r for r in rows
                if not r.get("applies_schemes") or scheme in r["applies_schemes"]]
    return rows


async def create_price_component(payload, actor: str, org: str = ORG_ID) -> dict:
    if await db.price_components.find_one({"org_id": org, "code": payload.code},
                                          {"_id": 0, "id": 1}):
        raise ValueError(f"Komponen biaya '{payload.code}' sudah ada.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **_clean(payload),
           "created_by": actor, "created_at": ts, "updated_at": ts}
    doc.setdefault("active", True)
    await db.price_components.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_price_component(comp_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = actor
    res = await db.price_components.update_one({"id": comp_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Komponen biaya tidak ditemukan.")
    return await db.price_components.find_one({"id": comp_id}, {"_id": 0})


async def scheme_matrix(org: str = ORG_ID) -> dict:
    """Matriks komponen × skema — memperlihatkan bahwa tiap skema punya komponen berbeda."""
    comps = await list_price_components(org=org, active=True)
    schemes = [o["value"] for o in ref.GROUPS["payment_scheme"]["options"]]
    return {
        "schemes": [{"value": s, "label": ref.label_of("payment_scheme", s)} for s in schemes],
        "rows": [{
            "code": c["code"], "label": c["label"], "group": c.get("group"),
            "finance_treatment": c.get("finance_treatment"),
            "treatment_label": ref.label_of("finance_treatment", c.get("finance_treatment")),
            "gl_account": c.get("gl_account"), "calc": c.get("calc"), "value": c.get("value"),
            "applies": {s: (not c.get("applies_schemes")) or s in (c.get("applies_schemes") or [])
                        for s in schemes},
            "note": c.get("note"),
        } for c in comps],
    }


# --------------------------------------------------------------- seed idempoten
async def seed_defaults(org: str = ORG_ID) -> dict:
    """Isi master default bila kosong. Idempoten: dicek per `code`."""
    ts = now_iso()
    added = {"price_components": 0, "addons": 0}
    for c in DEFAULT_PRICE_COMPONENTS:
        if await db.price_components.find_one({"org_id": org, "code": c["code"]}, {"_id": 1}):
            continue
        await db.price_components.insert_one({
            "id": new_id(), "org_id": org, "active": True, "created_by": "seed",
            "created_at": ts, "updated_at": ts, "applies_schemes": [], "value": 0, **c})
        added["price_components"] += 1
    for a in DEFAULT_ADDONS:
        if await db.addon_items.find_one({"org_id": org, "code": a["code"]}, {"_id": 1}):
            continue
        await db.addon_items.insert_one({
            "id": new_id(), "org_id": org, "active": True, "finance_treatment": "revenue",
            "gl_account": "4-1100", "applies_project_ids": [], "applies_unit_types": [],
            "negotiable": False, "created_by": "seed", "created_at": ts, "updated_at": ts, **a})
        added["addons"] += 1
    if added["price_components"] or added["addons"]:
        logger.info("Katalog default: %s komponen biaya, %s add-on",
                    added["price_components"], added["addons"])
    return added
