"""stock_control.py — transfer antar proyek, batas stok minimum, dan nilai persediaan (Fase 48E).

Tiga lubang yang ditutup:

1. **Tidak ada transfer antar proyek.** Dulu satu-satunya cara memindahkan material adalah
   `out` di proyek A lalu `in` di proyek B secara manual — dua transaksi yang tidak terikat,
   sehingga barang bisa "tercipta" atau "hilang" tanpa jejak. `transfer()` menulis SEPASANG
   mutasi bertaut satu nomor (TRF/…) dan menolak bila stok asal tidak cukup.
2. **Tidak ada batas stok minimum.** Gudang tidak pernah diperingatkan sebelum barang habis.
   `alerts()` membandingkan stok buku dengan `min_qty`; material yang batasnya BELUM
   ditetapkan dilaporkan `no_min` — bukan dianggap aman.
3. **Nilai persediaan tidak diketahui.** `valuation()` memakai **harga rata-rata bergerak**
   dari mutasi masuk yang punya harga. Mutasi lama tanpa harga TIDAK dikarang: material
   seperti itu dilaporkan `missing_price` dan tidak ikut menambah nilai, serta porsi yang
   berharga ditulis apa adanya (`priced_share_pct`).
"""
import sequences as seq
from db import db
from core_utils import new_id, now_iso
from engine import material_book_stock


async def _material(org: str, material_id: str) -> dict | None:
    return await db.materials.find_one({"id": material_id, "org_id": org}, {"_id": 0})


async def _twin_material(org: str, src: dict, to_project_id: str) -> tuple:
    """Material kembar di proyek tujuan (dibuat bila belum ada, kode/nama/satuan sama)."""
    found = await db.materials.find_one(
        {"org_id": org, "project_id": to_project_id, "code": src["code"]}, {"_id": 0})
    if found:
        return found, False
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "project_id": to_project_id, "code": src["code"],
           "name": src["name"], "uom": src.get("uom"), "boq_item_id": None, "budget_qty": 0,
           "min_qty": src.get("min_qty", 0), "consumed_qty": 0, "over_budget": False,
           "created_at": ts, "updated_at": ts}
    await db.materials.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc, True


async def transfer(org: str, data: dict, actor: str) -> dict:
    if data["from_project_id"] == data["to_project_id"]:
        raise ValueError("Proyek asal dan tujuan tidak boleh sama.")
    src = await _material(org, data["material_id"])
    if not src:
        raise ValueError("Material tidak ditemukan.")
    if src.get("project_id") != data["from_project_id"]:
        raise ValueError("Material itu bukan milik proyek asal yang dipilih.")
    qty = float(data["qty"])
    stock = await material_book_stock(data["from_project_id"], src["id"], org)
    if qty > stock + 1e-9:
        raise ValueError(f"Stok {src['name']} di proyek asal hanya {stock:g} {src.get('uom')} "
                        f"— tidak cukup untuk memindahkan {qty:g}.")
    dst, created = await _twin_material(org, src, data["to_project_id"])
    ts = now_iso()
    number = await seq.next_number("material_transfer", org, prefix="TRF",
                                   context={"project_id": data["from_project_id"]})
    unit_price = await average_cost(org, data["from_project_id"], src["id"])
    tid = new_id()
    common = {"org_id": org, "transfer_id": tid, "ref": number, "actor": actor,
              "created_at": ts, "requisition_id": None, "phase_id": None, "task_id": None}
    price_fields = {} if unit_price is None else {
        "unit_price": int(unit_price), "amount": int(round(qty * unit_price))}
    await db.material_txns.insert_many([
        {"id": new_id(), **common, "project_id": data["from_project_id"], "material_id": src["id"],
         "type": "out", "qty": qty, **price_fields,
         "note": f"Transfer keluar {number} → proyek tujuan: {data['reason']}"},
        {"id": new_id(), **common, "project_id": data["to_project_id"], "material_id": dst["id"],
         "type": "in", "qty": qty, **price_fields,
         "note": f"Transfer masuk {number} ← proyek asal: {data['reason']}"},
    ])
    doc = {
        "id": tid, "org_id": org, "transfer_number": number,
        "from_project_id": data["from_project_id"], "to_project_id": data["to_project_id"],
        "material_id": src["id"], "material_code": src["code"], "material_name": src["name"],
        "target_material_id": dst["id"], "uom": src.get("uom"), "qty": qty,
        "unit_price": None if unit_price is None else int(unit_price),
        "value": None if unit_price is None else int(round(qty * unit_price)),
        "target_material_created": created, "reason": data["reason"],
        "created_by": actor, "created_at": ts,
    }
    await db.material_transfers.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["stock_from_after"] = await material_book_stock(data["from_project_id"], src["id"], org)
    doc["stock_to_after"] = await material_book_stock(data["to_project_id"], dst["id"], org)
    return doc


async def list_transfers(org: str, project_id: str = None) -> list:
    q = {"org_id": org}
    if project_id:
        q = {"org_id": org, "$or": [{"from_project_id": project_id}, {"to_project_id": project_id}]}
    rows = await db.material_transfers.find(q, {"_id": 0}).sort("created_at", -1).to_list(300)
    names = {p["id"]: p["name"] for p in await db.projects.find(
        {"org_id": org}, {"_id": 0, "id": 1, "name": 1}).to_list(300)}
    for r in rows:
        r["from_project_name"] = names.get(r.get("from_project_id"))
        r["to_project_name"] = names.get(r.get("to_project_id"))
    return rows


async def set_min_qty(org: str, material_id: str, min_qty: float) -> dict:
    mat = await _material(org, material_id)
    if not mat:
        raise ValueError("Material tidak ditemukan.")
    await db.materials.update_one({"id": material_id, "org_id": org}, {"$set": {
        "min_qty": float(min_qty), "updated_at": now_iso()}})
    return await _material(org, material_id)


def _alert_state(stock: float, min_qty) -> str:
    if stock <= 0:
        return "empty"
    if min_qty is None or float(min_qty) <= 0:
        return "no_min"
    return "below_min" if stock < float(min_qty) else "ok"


async def alerts(org: str, project_ids: list, only_problem: bool = False) -> dict:
    mats = await db.materials.find({"org_id": org, "project_id": {"$in": project_ids}},
                                   {"_id": 0}).sort("code", 1).to_list(1000)
    names = {p["id"]: p["name"] for p in await db.projects.find(
        {"org_id": org, "id": {"$in": project_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(300)}
    rows = []
    for m in mats:
        stock = await material_book_stock(m["project_id"], m["id"], org)
        state = _alert_state(stock, m.get("min_qty"))
        rows.append({
            "material_id": m["id"], "project_id": m["project_id"],
            "project_name": names.get(m["project_id"]), "code": m.get("code"),
            "name": m.get("name"), "uom": m.get("uom"), "stock": stock,
            "min_qty": m.get("min_qty"), "state": state,
            "shortfall": (round(float(m["min_qty"]) - stock, 2)
                          if state == "below_min" else None),
            "detail": {
                "empty": "Stok habis — pekerjaan bisa berhenti.",
                "below_min": "Stok di bawah batas minimum — ajukan permintaan/PO.",
                "no_min": "Batas minimum belum ditetapkan — sistem tidak bisa memperingatkan.",
                "ok": "Aman.",
            }[state],
        })
    summary = {s: sum(1 for r in rows if r["state"] == s)
               for s in ("ok", "below_min", "empty", "no_min")}
    if only_problem:
        rows = [r for r in rows if r["state"] in ("below_min", "empty")]
    return {"rows": rows, "summary": summary}


async def average_cost(org: str, project_id: str, material_id: str):
    """Harga rata-rata bergerak dari mutasi MASUK yang berharga. None = belum ada data."""
    txns = await db.material_txns.find(
        {"org_id": org, "project_id": project_id, "material_id": material_id, "type": "in"},
        {"_id": 0, "qty": 1, "unit_price": 1}).to_list(2000)
    qty = value = 0.0
    for t in txns:
        up = t.get("unit_price")
        if up in (None, 0):
            continue
        qty += float(t.get("qty", 0) or 0)
        value += float(t.get("qty", 0) or 0) * int(up)
    if qty <= 0:
        return None
    return round(value / qty)


async def valuation(org: str, project_id: str) -> dict:
    mats = await db.materials.find({"org_id": org, "project_id": project_id},
                                   {"_id": 0}).sort("code", 1).to_list(1000)
    rows, total_value, priced, unpriced = [], 0, 0, 0
    for m in mats:
        stock = await material_book_stock(project_id, m["id"], org)
        avg = await average_cost(org, project_id, m["id"])
        value = None if avg is None else int(round(stock * avg))
        if avg is None:
            unpriced += 1
        else:
            priced += 1
            total_value += max(0, value or 0)
        rows.append({
            "material_id": m["id"], "code": m.get("code"), "name": m.get("name"),
            "uom": m.get("uom"), "stock": stock, "avg_cost": avg, "value": value,
            "state": "complete" if avg is not None else "missing_price",
            "detail": (None if avg is not None else
                       "Belum ada mutasi masuk berharga (penerimaan PO/transfer) — nilai "
                       "persediaan tidak dikarang."),
        })
    total = priced + unpriced
    return {
        "rows": rows,
        "summary": {
            "materials": total, "priced": priced, "unpriced": unpriced,
            "total_value": total_value,
            "priced_share_pct": round(priced / total * 100, 1) if total else None,
            "state": "complete" if priced and not unpriced else
                     ("partial" if priced else "missing_data"),
            "detail": ("Nilai persediaan lengkap (semua material punya harga masuk)."
                       if priced and not unpriced else
                       (f"{unpriced} material belum punya harga masuk — nilainya tidak "
                        "dihitung agar tidak mengarang." if priced else
                        "Belum ada material dengan harga masuk — nilai persediaan belum "
                        "bisa dihitung.")),
        },
    }
