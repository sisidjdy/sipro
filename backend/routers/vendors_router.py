"""vendors_router.py — master vendor, daftar harga, pembanding harga, evaluasi (Fase 48A/48D).

Rute:
  GET/POST         /api/vendors                     daftar & pendaftaran vendor
  GET              /api/vendors/price-list           daftar harga (filter vendor/material)
  POST             /api/vendors/price-list           catat/koreksi harga (berjejak)
  GET              /api/vendors/price-compare        pembanding harga lintas vendor
  GET              /api/vendors/evaluations          rapor semua vendor (berbukti)
  GET/PUT          /api/vendors/{vid}                detail & koreksi master
  GET              /api/vendors/{vid}/evaluation     rapor satu vendor + penilaian manusia
  POST             /api/vendors/{vid}/assessment     penilaian manusia (1..5 + alasan)

Semua tulisan uang bilangan bulat rupiah; keadaan "belum ada data" dikembalikan APA ADANYA
(`state="missing_data"`) supaya layar tidak pernah menampilkan skor 0 karangan.
"""
from fastapi import APIRouter, Depends, HTTPException

import vendor_engine as ve
from db import db, ORG_ID
from core_utils import serialize_doc
from models_p48 import AssessmentIn, PriceIn, VendorIn, VendorUpdate
from rbac import require_permission, audit_log

router = APIRouter(prefix="/vendors", tags=["vendors"])


async def _vendor_or_404(org: str, vid: str) -> dict:
    v = await ve.get_vendor(org, vid)
    if not v:
        raise HTTPException(status_code=404, detail="Vendor tidak ditemukan.")
    return v


@router.get("")
async def list_vendors(q: str = None, category: str = None, active: bool = None,
                       user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    fq = {"org_id": org}
    if category:
        fq["category"] = category
    if active is not None:
        fq["is_active"] = active
    if q:
        fq["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                     {"code": {"$regex": q, "$options": "i"}}]
    rows = await db.vendors.find(fq, {"_id": 0}).sort("name", 1).to_list(500)
    for r in rows:
        r["usage"] = await ve.vendor_usage(org, r)
    return {"data": serialize_doc(rows), "total": len(rows), "summary": {
        "total": len(rows),
        "active": sum(1 for r in rows if r.get("is_active", True)),
        "with_po": sum(1 for r in rows if r["usage"]["po_count"] > 0),
        "po_value": sum(r["usage"]["po_value"] for r in rows),
    }}


@router.post("")
async def create_vendor(payload: VendorIn,
                        user: dict = Depends(require_permission("vendors", "create"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await ve.create_vendor(org, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "vendor", doc["id"], {"code": doc["code"], "name": doc["name"]})
    return {"data": serialize_doc(doc)}


@router.get("/price-list")
async def price_list(vendor_id: str = None, material_id: str = None, active_only: bool = False,
                     user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await ve.list_prices(org, vendor_id=vendor_id, material_id=material_id,
                               only_active=active_only)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/price-list")
async def add_price(payload: PriceIn,
                    user: dict = Depends(require_permission("vendors", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await ve.add_price(org, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "vendor_price", doc["id"],
                    {"vendor": doc.get("vendor_name"), "unit_price": doc.get("unit_price")})
    return {"data": serialize_doc(doc)}


@router.get("/price-compare")
async def price_compare(material_id: str = None, item_name: str = None, qty: float = 1,
                        user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    if not material_id and not item_name:
        # Tanpa barang yang diminta, jawabannya BUKAN galat melainkan keadaan jujur:
        # belum ada yang bisa dibandingkan. (Endpoint sweep memanggil semua rute GET
        # tanpa parameter; galat 400 di sini dulu tampak seperti rute rusak.)
        return {"data": {"state": "missing_data", "rows": [], "best": None,
                         "detail": "Pilih material atau ketik nama barang untuk membandingkan "
                                   "harga antar vendor."}}
    return {"data": await ve.compare_prices(org, material_id=material_id,
                                            item_name=item_name, qty=qty)}


@router.get("/price-check")
async def price_check(material_id: str = None, unit_price: int = 0, vendor_id: str = None,
                      user: dict = Depends(require_permission("vendors", "view"))):
    """Uji satu harga terhadap acuan — dipakai layar PO sebelum menyimpan."""
    org = user.get("org_id", ORG_ID)
    if not material_id or not unit_price:
        return {"data": {"state": "no_reference", "reference_price": None,
                         "variance_pct": None,
                         "detail": "Sebutkan material dan harga satuan yang ingin diuji."}}
    return {"data": await ve.price_check(org, material_id, int(unit_price), vendor_id)}


@router.get("/evaluations")
async def evaluations(user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    vendors = await db.vendors.find({"org_id": org}, {"_id": 0}).sort("name", 1).to_list(300)
    rows = [await ve.evaluate_vendor(org, v) for v in vendors]
    graded = [r for r in rows if r["score"] is not None]
    return {"data": serialize_doc(rows), "total": len(rows), "summary": {
        "total": len(rows), "graded": len(graded),
        "missing_data": len(rows) - len(graded),
        "avg_score": round(sum(r["score"] for r in graded) / len(graded), 1) if graded else None,
        "detail": ("Skor hanya dihitung untuk vendor yang punya bukti transaksi."
                   if graded else "Belum ada vendor dengan bukti transaksi yang bisa dinilai."),
    }}


@router.get("/{vid}")
async def get_vendor(vid: str, user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    v = await _vendor_or_404(org, vid)
    v["usage"] = await ve.vendor_usage(org, v)
    prices = await ve.list_prices(org, vendor_id=vid)
    pos = await db.purchase_orders.find(
        {"org_id": org, "$or": [{"vendor_id": vid}, {"vendor": v.get("name")}]},
        {"_id": 0, "id": 1, "po_number": 1, "total": 1, "status": 1, "project_name": 1,
         "created_at": 1, "due_date": 1}).sort("created_at", -1).to_list(100)
    return {"data": serialize_doc(v), "prices": serialize_doc(prices), "pos": serialize_doc(pos)}


@router.put("/{vid}")
async def update_vendor(vid: str, payload: VendorUpdate,
                        user: dict = Depends(require_permission("vendors", "update"))):
    org = user.get("org_id", ORG_ID)
    await _vendor_or_404(org, vid)
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    doc = await ve.update_vendor(org, vid, patch)
    await audit_log(user, "update", "vendor", vid, {"fields": list(patch.keys())})
    return {"data": serialize_doc(doc)}


@router.get("/{vid}/evaluation")
async def evaluation(vid: str, user: dict = Depends(require_permission("vendors", "view"))):
    org = user.get("org_id", ORG_ID)
    v = await _vendor_or_404(org, vid)
    return {"data": serialize_doc(await ve.evaluate_vendor(org, v)),
            "assessments": serialize_doc(await ve.list_assessments(org, "vendor", vid))}


@router.post("/{vid}/assessment")
async def assess(vid: str, payload: AssessmentIn,
                 user: dict = Depends(require_permission("vendors", "update"))):
    org = user.get("org_id", ORG_ID)
    v = await _vendor_or_404(org, vid)
    doc = await ve.save_assessment(org, {"type": "vendor", "id": vid, "name": v.get("name")},
                                   payload.model_dump(), user.get("email"))
    await audit_log(user, "create", "vendor_assessment", doc["id"],
                    {"vendor": v.get("name"), "average": doc.get("average")})
    return {"data": serialize_doc(doc)}
