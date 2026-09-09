"""procurement_extra.py — jembatan permintaan→PO, retur barang, dan 3-way match yang MENAHAN (Fase 48B).

Tiga cacat nyata yang ditutup:

1. **Permintaan material yang disetujui tidak punya jalan ke pembelian.** Dulu satu-satunya
   tindakan adalah "keluarkan dari stok"; bila stok kurang, pembelian lahir di layar PO tanpa
   jejak ke permintaan lapangan. Sekarang `shortage()` menghitung KEKURANGAN nyata
   (diminta − sudah dikeluarkan − stok tersedia − sudah dipesan) dan `to_po()` hanya boleh
   memesan sebanyak kekurangan itu — memanggilnya dua kali TIDAK melahirkan PO kembar.
2. **GRN tidak bisa dibalik.** Barang rusak/salah kirim/kelebihan terima dulu tetap tercatat
   sebagai "diterima", sehingga stok dan 3-way match sama-sama berbohong. `create_return()`
   mengembalikan barang: stok keluar, `received_qty`/`received_value` PO turun, status PO
   dihitung ulang, dan alasan wajib — TETAPI ditolak bila retur akan membuat nilai barang
   diterima lebih kecil daripada yang SUDAH ditagih (harus lewat nota koreksi tagihan dulu).
3. **3-way match hanya memberi tanda.** `evaluate_bill()` memberi keadaan `held` — router
   MENOLAK tagihan yang melebihi barang diterima/nilai PO, dan hanya manajer keuangan yang
   boleh menerobos dengan alasan tertulis (jejak `override_by/override_reason`).
"""
import sequences as seq
from db import db
from core_utils import new_id, now_iso
from engine import material_book_stock
from reference_p48 import THREEWAY_TOLERANCE

PO_RECEIVABLE = ("approved", "partially_received", "received")


# ------------------------------------------------------------------ permintaan → PO
async def shortage(org: str, req: dict) -> dict:
    """Kekurangan per item = diminta − dikeluarkan − stok tersedia − sudah dipesan (PO aktif)."""
    rows = []
    for it in req.get("items", []):
        requested = float(it.get("qty_requested", 0) or 0)
        issued = float(it.get("qty_issued", 0) or 0)
        ordered = float(it.get("qty_po", 0) or 0)
        stock = await material_book_stock(req["project_id"], it["material_id"], org)
        outstanding = round(max(0.0, requested - issued), 2)
        short = round(max(0.0, outstanding - max(0.0, stock) - ordered), 2)
        rows.append({
            "material_id": it["material_id"], "code": it.get("code"), "name": it.get("name"),
            "uom": it.get("uom"), "qty_requested": requested, "qty_issued": issued,
            "qty_po": ordered, "stock": stock, "outstanding": outstanding,
            "can_issue_now": round(min(outstanding, max(0.0, stock)), 2), "shortage": short,
        })
    total_short = round(sum(r["shortage"] for r in rows), 2)
    return {
        "rows": rows, "total_shortage_items": sum(1 for r in rows if r["shortage"] > 0),
        "total_shortage_qty": total_short,
        "po_numbers": req.get("po_numbers") or [],
        "detail": ("Seluruh kebutuhan sudah tercukupi stok atau PO yang sudah dibuat."
                   if total_short <= 0 else
                   f"{sum(1 for r in rows if r['shortage'] > 0)} item kurang — bisa dibuatkan PO."),
    }


async def to_po(org: str, req: dict, vendor: dict, items_in: list, *, due_date: str,
                note: str, actor: str, price_checker=None) -> dict:
    """Buat PO dari kekurangan permintaan. Idempoten terhadap kuantitas yang SUDAH dipesan."""
    if req.get("status") not in ("approved", "partially_issued"):
        raise ValueError("Hanya permintaan yang SUDAH DISETUJUI yang boleh dibuatkan PO "
                         f"(status sekarang: {req.get('status')}).")
    sh = await shortage(org, req)
    short_map = {r["material_id"]: r for r in sh["rows"]}
    wanted = items_in or [{"material_id": r["material_id"], "qty": r["shortage"], "unit_price": None}
                          for r in sh["rows"] if r["shortage"] > 0]
    if not wanted:
        raise ValueError("Tidak ada kekurangan yang perlu dibeli — " + sh["detail"] +
                         (f" PO terkait: {', '.join(sh['po_numbers'])}." if sh["po_numbers"] else ""))
    items, checks, subtotal = [], [], 0
    for w in wanted:
        mid = w["material_id"] if isinstance(w, dict) else w.material_id
        qty = float(w["qty"] if isinstance(w, dict) else w.qty)
        price = w.get("unit_price") if isinstance(w, dict) else w.unit_price
        row = short_map.get(mid)
        if not row:
            raise ValueError("Material yang dipesan tidak ada di permintaan ini.")
        if row["shortage"] <= 0:
            raise ValueError(f"{row['name']} tidak kurang — stok/PO sudah mencukupi "
                             "(tidak boleh dipesan dua kali).")
        if qty > row["shortage"] + 1e-9:
            raise ValueError(f"Jumlah PO {row['name']} ({qty:g} {row['uom']}) melebihi "
                             f"kekurangan {row['shortage']:g} {row['uom']}.")
        if not price or int(price) <= 0:
            raise ValueError(f"Harga satuan {row['name']} belum diisi — sistem tidak mengarang "
                             "harga. Ambil dari daftar harga vendor atau isi manual.")
        amount = int(round(qty * int(price)))
        subtotal += amount
        items.append({"description": f"{row['name']} ({row['code']})", "material_id": mid,
                      "boq_item_id": None, "uom": row["uom"], "qty": qty,
                      "unit_price": int(price), "amount": amount, "received_qty": 0.0})
        if price_checker:
            chk = await price_checker(org, mid, int(price), vendor["id"])
            checks.append({"material_id": mid, "name": row["name"], **chk})
    ts = now_iso()
    po = {
        "id": new_id(), "org_id": org,
        "po_number": await seq.next_number("po", org, prefix="PO", context={
            "project_id": req["project_id"], "vendor_code": vendor.get("code")}),
        "project_id": req["project_id"], "project_name": req.get("project_name"),
        "po_type": "material", "vendor": vendor.get("name"), "vendor_id": vendor["id"],
        "subcontractor_id": None, "subcontractor_name": None, "spk_id": None,
        "items": items, "subtotal": int(subtotal), "total": int(subtotal),
        "status": "draft", "received_value": 0, "billed_value": 0,
        "high_value": int(subtotal) > 500_000_000,
        "due_date": due_date, "note": note or f"Dari permintaan {req.get('req_number')}",
        "po_source": "requisition", "requisition_id": req["id"],
        "requisition_number": req.get("req_number"),
        "price_checks": checks, "approved_by": None, "approved_at": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.purchase_orders.insert_one(dict(po))
    # Catat kuantitas terpesan di permintaan supaya panggilan kedua tidak melahirkan PO kembar.
    ritems = req["items"]
    for it in ritems:
        add = next((float(x["qty"] if isinstance(x, dict) else x.qty) for x in wanted
                    if (x["material_id"] if isinstance(x, dict) else x.material_id) == it["material_id"]), 0)
        if add:
            it["qty_po"] = round(float(it.get("qty_po", 0) or 0) + add, 2)
    await db.material_requisitions.update_one({"id": req["id"], "org_id": org}, {"$set": {
        "items": ritems, "updated_at": ts}, "$addToSet": {"po_ids": po["id"],
                                                         "po_numbers": po["po_number"]}})
    po.pop("_id", None)
    return {"po": po, "price_checks": checks}


# ------------------------------------------------------------------ retur barang
async def create_return(org: str, grn: dict, po: dict, kind: str, items_in: list,
                        reason: str, actor: str) -> dict:
    gitems = grn.get("items", [])
    pitems = po.get("items", [])
    lines, returned_value = [], 0
    for w in items_in:
        idx = int(w.grn_item_index if hasattr(w, "grn_item_index") else w["grn_item_index"])
        qty = float(w.qty_returned if hasattr(w, "qty_returned") else w["qty_returned"])
        if idx < 0 or idx >= len(gitems):
            raise ValueError("Baris penerimaan yang diretur tidak ditemukan.")
        gi = gitems[idx]
        already = float(gi.get("returned_qty", 0) or 0)
        avail = round(float(gi.get("qty_received", 0)) - already, 4)
        if qty > avail + 1e-9:
            raise ValueError(f"Retur {qty:g} melebihi sisa yang bisa dikembalikan ({avail:g}) "
                             f"untuk '{gi.get('description')}'.")
        amount = int(round(qty * int(gi.get("unit_price", 0) or 0)))
        returned_value += amount
        lines.append({"grn_item_index": idx, "po_item_index": gi.get("po_item_index"),
                      "description": gi.get("description"), "material_id": gi.get("material_id"),
                      "uom": gi.get("uom"), "qty_returned": qty,
                      "unit_price": int(gi.get("unit_price", 0) or 0), "amount": amount})
        gi["returned_qty"] = round(already + qty, 4)
    if not lines:
        raise ValueError("Tidak ada baris retur yang sah.")
    received_after = int(po.get("received_value", 0)) - int(returned_value)
    billed = int(po.get("billed_value", 0))
    if billed > received_after:
        raise ValueError(
            f"Retur ini membuat nilai barang diterima (Rp {received_after:,}) lebih kecil "
            f"daripada yang SUDAH ditagih (Rp {billed:,}). Terbitkan nota koreksi/kredit atas "
            "tagihan vendor lebih dulu — stok dan tagihan tidak boleh saling berbohong.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "return_number": await seq.next_number("grn_return", org, prefix="RTN", context={
            "project_id": po.get("project_id"), "vendor_id": po.get("vendor_id")}),
        "grn_id": grn["id"], "grn_number": grn.get("grn_number"), "po_id": po["id"],
        "po_number": po.get("po_number"), "project_id": po["project_id"],
        "vendor": po.get("vendor"), "vendor_id": po.get("vendor_id"),
        "kind": kind, "items": lines, "returned_value": int(returned_value),
        "reason": reason, "created_by": actor, "created_at": ts,
    }
    await db.grn_returns.insert_one(dict(doc))
    # Stok keluar (barang benar-benar dikembalikan) + jejak nomor retur.
    for ln in lines:
        if ln.get("material_id"):
            await db.material_txns.insert_one({
                "id": new_id(), "org_id": org, "project_id": po["project_id"],
                "material_id": ln["material_id"], "type": "out", "qty": ln["qty_returned"],
                "unit_price": ln["unit_price"], "amount": ln["amount"],
                "note": f"Retur ke vendor ({kind}): {reason}", "ref": doc["return_number"],
                "return_id": doc["id"], "actor": actor, "created_at": ts})
    # Turunkan penerimaan di PO + hitung ulang status.
    for ln in lines:
        pidx = ln.get("po_item_index")
        if pidx is None or pidx >= len(pitems):
            continue
        pitems[pidx]["received_qty"] = round(
            max(0.0, float(pitems[pidx].get("received_qty", 0)) - ln["qty_returned"]), 4)
    fully = all(float(i.get("received_qty", 0)) >= float(i.get("qty", 0)) - 1e-9 for i in pitems)
    any_recv = any(float(i.get("received_qty", 0)) > 0 for i in pitems)
    status = "received" if fully else ("partially_received" if any_recv else "approved")
    await db.purchase_orders.update_one({"id": po["id"], "org_id": org}, {"$set": {
        "items": pitems, "received_value": max(0, received_after), "status": status,
        "updated_at": ts}})
    await db.grns.update_one({"id": grn["id"], "org_id": org}, {"$set": {
        "items": gitems, "returned_value": int(grn.get("returned_value", 0)) + int(returned_value),
        "updated_at": ts}})
    doc.pop("_id", None)
    return doc


async def list_returns(org: str, *, po_id: str = None, project_id: str = None) -> list:
    q = {"org_id": org}
    if po_id:
        q["po_id"] = po_id
    if project_id:
        q["project_id"] = project_id
    return await db.grn_returns.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


# ------------------------------------------------------------------ 3-way match MENAHAN
def evaluate_bill(po: dict, claimed: int, grn_received_value: int = 0) -> dict:
    """Bandingkan DIPESAN (PO) vs DITERIMA (kumulatif) vs DITAGIH (sebelumnya + ini).

    Beda dengan Fase 12: hasilnya bukan cuma label. `state="held"` berarti tagihan TIDAK
    BOLEH dibuat — kecuali diterobos manajer keuangan dengan alasan tertulis.
    """
    po_total = int(po.get("total", 0))
    received = int(po.get("received_value", 0))
    billed_before = int(po.get("billed_value", 0))
    billed_after = billed_before + int(claimed)
    over_received = billed_after - received
    over_po = billed_after - po_total
    tol_recv = round(received * THREEWAY_TOLERANCE) + 1
    tol_po = round(po_total * THREEWAY_TOLERANCE) + 1
    reasons = []
    if over_received > tol_recv:
        reasons.append(f"Tagihan kumulatif Rp {billed_after:,} melebihi nilai barang yang "
                       f"BENAR-BENAR diterima Rp {received:,} (selisih Rp {over_received:,}).")
    if over_po > tol_po:
        reasons.append(f"Tagihan kumulatif Rp {billed_after:,} melebihi nilai PO "
                       f"Rp {po_total:,} (selisih Rp {over_po:,}).")
    held = bool(reasons)
    return {
        "po_total": po_total, "received_value": received, "grn_received_value": int(grn_received_value),
        "billed_before": billed_before, "billed_after": billed_after,
        "variance_vs_received": over_received, "variance_vs_po": over_po,
        "state": "held" if held else "matched",
        "status": "flagged" if held else "matched",   # kompatibel dengan layar/laporan Fase 12
        "reasons": reasons,
        "detail": ("; ".join(reasons) if held else
                   "Cocok: tagihan tidak melebihi barang diterima maupun nilai PO."),
    }
