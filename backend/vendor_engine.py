"""vendor_engine.py — master vendor, daftar harga, uji kewajaran harga, evaluasi berbukti (Fase 48A/48D).

Prinsip yang dijaga:

1. **Vendor adalah DATA, bukan teks bebas.** Sebelum fase ini `purchase_orders.vendor` hanya
   string; satu vendor bisa muncul sebagai tiga nama berbeda dan riwayatnya tidak bisa
   dijumlahkan. PO baru boleh menyebut `vendor_id`; nama tetap disimpan sebagai SNAPSHOT
   supaya dokumen lama tidak berubah isi ketika master di-rename.
2. **Harga PO punya pembanding.** `price_check()` membandingkan harga satuan PO dengan harga
   acuan (daftar harga vendor → harga terbaik lintas vendor → realisasi PO terakhir). Bila
   TIDAK ADA acuan, hasilnya `no_reference` — bukan "wajar" palsu.
3. **Evaluasi dihitung dari BUKTI yang sudah ada di sistem** (ketepatan waktu GRN vs jatuh
   tempo PO, nilai retur vs nilai terima, harga vs acuan). Komponen tanpa bukti masuk
   `missing[]` dan TIDAK diberi angka 0 — skor akhir hanya menimbang komponen yang ada.
   Penilaian manusia (`vendor_assessments`) disajikan berdampingan, tidak dicampur.
"""
from datetime import date, timedelta

from db import db, ORG_ID
from core_utils import new_id, now_iso, today_iso_date
from reference_p48 import EVAL_WEIGHTS, PRICE_WARN_PCT


# ------------------------------------------------------------------ master vendor
async def get_vendor(org: str, vendor_id: str) -> dict | None:
    return await db.vendors.find_one({"id": vendor_id, "org_id": org}, {"_id": 0})


async def create_vendor(org: str, data: dict, actor: str) -> dict:
    code = str(data.get("code") or "").strip().upper()
    if not code:
        import numbering as nb
        code = await nb.generate_unique("master:vendor", org, "vendors", {"org_id": org},
                                        context={"category": data.get("category")})
    if await db.vendors.find_one({"org_id": org, "code": code}, {"_id": 0, "id": 1}):
        raise ValueError(f"Kode vendor '{code}' sudah dipakai — pakai kode lain "
                         "atau buka vendor yang sudah ada.")
    ts = now_iso()
    doc = {**data, "id": new_id(), "org_id": org, "code": code,
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.vendors.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_vendor(org: str, vendor_id: str, patch: dict) -> dict:
    if patch:
        await db.vendors.update_one({"id": vendor_id, "org_id": org},
                                    {"$set": {**patch, "updated_at": now_iso()}})
    return await get_vendor(org, vendor_id)


async def vendor_usage(org: str, vendor: dict) -> dict:
    """Riwayat pemakaian vendor — dasar tombol/lencana di layar (bukan angka karangan)."""
    q = _vendor_po_query(org, vendor)
    pos = await db.purchase_orders.find(q, {"_id": 0, "id": 1, "total": 1, "status": 1}).to_list(1000)
    active = [p for p in pos if p.get("status") not in ("cancelled",)]
    bills = await db.ap_invoices.find(
        {"org_id": org, "vendor": vendor.get("name")},
        {"_id": 0, "net": 1, "paid": 1, "status": 1}).to_list(1000)
    return {
        "po_count": len(active),
        "po_value": sum(int(p.get("total", 0)) for p in active),
        "bill_count": len(bills),
        "bill_outstanding": sum(int(b.get("net", 0)) - int(b.get("paid", 0))
                                for b in bills if b.get("status") in ("approved", "partial",
                                                                     "pending_approval")),
    }


def _vendor_po_query(org: str, vendor: dict) -> dict:
    """PO milik vendor: lewat `vendor_id` (baru) ATAU nama (dokumen lama, teks bebas)."""
    return {"org_id": org, "$or": [{"vendor_id": vendor["id"]},
                                   {"vendor": vendor.get("name")}]}


# ------------------------------------------------------------------ daftar harga
async def add_price(org: str, data: dict, actor: str) -> dict:
    mat = None
    if data.get("material_id"):
        mat = await db.materials.find_one({"id": data["material_id"], "org_id": org}, {"_id": 0})
        if not mat:
            raise ValueError("Material tidak ditemukan.")
    vendor = await get_vendor(org, data["vendor_id"])
    if not vendor:
        raise ValueError("Vendor tidak ditemukan.")
    key = {"org_id": org, "vendor_id": data["vendor_id"],
           "material_id": data.get("material_id"),
           "item_key": _item_key(data, mat), "valid_from": data["valid_from"]}
    ts = now_iso()
    doc = {**data, **key, "id": new_id(),
           "vendor_name": vendor.get("name"),
           "item_name": data.get("item_name") or (mat or {}).get("name"),
           "uom": data.get("uom") or (mat or {}).get("uom"),
           "is_active": True, "created_by": actor, "created_at": ts, "updated_at": ts}
    existing = await db.vendor_prices.find_one(key, {"_id": 0, "id": 1})
    if existing:
        # Harga untuk kunci alami yang sama = KOREKSI (berjejak), bukan baris kembar.
        doc["id"] = existing["id"]
        await db.vendor_prices.update_one({"id": existing["id"]}, {"$set": {
            **{k: v for k, v in doc.items() if k not in ("id", "created_at", "created_by")},
            "history_appended_at": ts}})
        await db.vendor_prices.update_one({"id": existing["id"]}, {"$push": {"history": {
            "at": ts, "by": actor, "unit_price": int(data["unit_price"])}}})
    else:
        doc["history"] = []
        await db.vendor_prices.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def _item_key(data: dict, mat: dict | None) -> str:
    if data.get("material_id"):
        return f"mat:{data['material_id']}"
    name = (data.get("item_name") or (mat or {}).get("name") or "").strip().lower()
    return f"name:{name}"


def _active(row: dict, on: str) -> bool:
    if not row.get("is_active", True):
        return False
    if row.get("valid_from") and str(row["valid_from"]) > on:
        return False
    if row.get("valid_until") and str(row["valid_until"]) < on:
        return False
    return True


async def list_prices(org: str, *, vendor_id: str = None, material_id: str = None,
                      only_active: bool = False) -> list:
    q = {"org_id": org}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if material_id:
        q["material_id"] = material_id
    rows = await db.vendor_prices.find(q, {"_id": 0}).sort("valid_from", -1).to_list(1000)
    if only_active:
        on = today_iso_date()
        rows = [r for r in rows if _active(r, on)]
    return rows


async def compare_prices(org: str, *, material_id: str = None, item_name: str = None,
                         qty: float = 1) -> dict:
    """Pembanding harga lintas vendor. Kosong = `belum ada data` (bukan Rp 0)."""
    rows = await list_prices(org, material_id=material_id, only_active=True)
    if item_name and not material_id:
        needle = item_name.strip().lower()
        rows = [r for r in await list_prices(org, only_active=True)
                if needle in str(r.get("item_name", "")).lower()]
    if not rows:
        return {"state": "missing_data", "rows": [], "best": None,
                "detail": "Belum ada daftar harga untuk barang ini — catat harga vendor "
                          "dulu agar harga PO punya pembanding."}
    rows.sort(key=lambda r: int(r.get("unit_price", 0)))
    best = rows[0]
    out = []
    for r in rows:
        delta = int(r["unit_price"]) - int(best["unit_price"])
        out.append({
            "price_id": r["id"], "vendor_id": r["vendor_id"], "vendor_name": r.get("vendor_name"),
            "unit_price": int(r["unit_price"]), "uom": r.get("uom"),
            "source": r.get("source"), "valid_from": r.get("valid_from"),
            "valid_until": r.get("valid_until"),
            "delta_vs_best": delta,
            "delta_pct": round(delta / int(best["unit_price"]) * 100, 2) if best.get("unit_price") else None,
            "is_best": r["id"] == best["id"],
            "total_for_qty": int(round(float(qty or 1) * int(r["unit_price"]))),
        })
    return {"state": "complete", "rows": out, "best": out[0],
            "detail": f"{len(out)} penawaran harga aktif; termurah {best.get('vendor_name')}."}


async def reference_price(org: str, material_id: str, vendor_id: str = None) -> dict:
    """Harga acuan: daftar harga vendor → harga terbaik lintas vendor → realisasi PO terakhir."""
    on = today_iso_date()
    if vendor_id:
        rows = [r for r in await list_prices(org, vendor_id=vendor_id, material_id=material_id)
                if _active(r, on)]
        if rows:
            r = min(rows, key=lambda x: int(x["unit_price"]))
            return {"unit_price": int(r["unit_price"]), "basis": "daftar harga vendor ini",
                    "price_id": r["id"]}
    rows = [r for r in await list_prices(org, material_id=material_id) if _active(r, on)]
    if rows:
        r = min(rows, key=lambda x: int(x["unit_price"]))
        return {"unit_price": int(r["unit_price"]),
                "basis": f"harga terbaik lintas vendor ({r.get('vendor_name')})",
                "price_id": r["id"]}
    # Realisasi PO terakhir yang memuat material ini.
    pos = await db.purchase_orders.find(
        {"org_id": org, "items.material_id": material_id, "status": {"$ne": "cancelled"}},
        {"_id": 0, "items": 1, "po_number": 1, "created_at": 1}).sort("created_at", -1).to_list(20)
    for p in pos:
        for it in p.get("items", []):
            if it.get("material_id") == material_id and int(it.get("unit_price", 0)) > 0:
                return {"unit_price": int(it["unit_price"]),
                        "basis": f"realisasi PO {p.get('po_number')}", "price_id": None}
    return {"unit_price": None, "basis": None, "price_id": None}


async def price_check(org: str, material_id: str, unit_price: int, vendor_id: str = None) -> dict:
    """Uji satu harga satuan terhadap acuan. Tidak pernah MENAHAN — hanya memberi alasan."""
    if not material_id:
        return {"state": "no_reference", "detail": "Item tanpa material master — tidak ada acuan harga.",
                "reference_price": None, "variance_pct": None}
    ref_row = await reference_price(org, material_id, vendor_id)
    base = ref_row.get("unit_price")
    if not base:
        return {"state": "no_reference",
                "detail": "Belum ada harga acuan untuk material ini — catat daftar harga vendor "
                          "agar harga PO bisa diuji.",
                "reference_price": None, "variance_pct": None}
    var_pct = round((int(unit_price) - base) / base * 100, 2)
    if var_pct > PRICE_WARN_PCT:
        state, detail = "di_atas_acuan", (
            f"Harga Rp {int(unit_price):,} lebih tinggi {var_pct}% dari acuan Rp {base:,} "
            f"({ref_row['basis']}) — lampirkan alasan sebelum PO disetujui.")
    elif var_pct < 0:
        state, detail = "lebih_murah", (
            f"Harga Rp {int(unit_price):,} lebih murah {abs(var_pct)}% dari acuan Rp {base:,} "
            f"({ref_row['basis']}).")
    else:
        state, detail = "wajar", (
            f"Harga Rp {int(unit_price):,} masih di dalam ambang {PRICE_WARN_PCT}% "
            f"dari acuan Rp {base:,} ({ref_row['basis']}).")
    return {"state": state, "detail": detail, "reference_price": base,
            "reference_basis": ref_row["basis"], "variance_pct": var_pct}


# ------------------------------------------------------------------ evaluasi berbukti
def _grade(score) -> str:
    if score is None:
        return "missing_data"
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _combine(components: dict) -> tuple:
    """Rata-rata BERBOBOT hanya atas komponen yang punya bukti (honest-null)."""
    got = {k: v for k, v in components.items() if v.get("score") is not None}
    if not got:
        return None, [k for k in components]
    wsum = sum(EVAL_WEIGHTS.get(k, 10) for k in got)
    score = sum(v["score"] * EVAL_WEIGHTS.get(k, 10) for k, v in got.items()) / wsum
    missing = [k for k, v in components.items() if v.get("score") is None]
    return round(score, 1), missing


async def evaluate_vendor(org: str, vendor: dict) -> dict:
    pos = await db.purchase_orders.find(_vendor_po_query(org, vendor), {"_id": 0}).to_list(500)
    po_ids = [p["id"] for p in pos]
    grns = await db.grns.find({"org_id": org, "po_id": {"$in": po_ids}}, {"_id": 0}).to_list(1000)
    returns = await db.grn_returns.find({"org_id": org, "po_id": {"$in": po_ids}},
                                       {"_id": 0}).to_list(1000)
    comp = {"timeliness": await _c_timeliness(pos, grns),
            "quality": _c_quality(grns, returns),
            "price": await _c_price(org, pos, vendor),
            "service": {"score": None, "detail": "Belum ada sumber data pelayanan di sistem — "
                                                  "pakai penilaian manusia di bawah."}}
    score, missing = _combine(comp)
    return {
        "vendor_id": vendor["id"], "vendor_name": vendor.get("name"),
        "state": "complete" if score is not None else "missing_data",
        "score": score, "grade": _grade(score), "components": comp, "missing": missing,
        "evidence": {"po_count": len(pos), "grn_count": len(grns), "return_count": len(returns)},
        "detail": ("Skor dihitung dari bukti transaksi di sistem." if score is not None else
                   "Belum ada data — vendor ini belum punya PO/penerimaan yang bisa dinilai."),
    }


async def _c_timeliness(pos: list, grns: list) -> dict:
    by_po = {}
    for g in grns:
        cur = by_po.get(g["po_id"])
        gd = str(g.get("created_at", ""))[:10]
        if not cur or gd > cur:
            by_po[g["po_id"]] = gd
    judged = [(p, by_po[p["id"]]) for p in pos if p.get("due_date") and by_po.get(p["id"])]
    if not judged:
        return {"score": None, "detail": "Belum ada PO berjatuh tempo yang sudah diterima — "
                                        "ketepatan waktu belum bisa dinilai."}
    on_time = sum(1 for p, d in judged if d <= str(p["due_date"])[:10])
    late = [f"{p.get('po_number')} (terima {d}, jatuh tempo {str(p['due_date'])[:10]})"
            for p, d in judged if d > str(p["due_date"])[:10]]
    pct = round(on_time / len(judged) * 100, 1)
    return {"score": pct, "detail": f"{on_time} dari {len(judged)} PO diterima tepat waktu "
                                   f"({pct}%).", "late": late[:5]}


def _c_quality(grns: list, returns: list) -> dict:
    received = sum(int(g.get("received_value", 0)) for g in grns)
    if received <= 0:
        return {"score": None, "detail": "Belum ada penerimaan barang — mutu belum bisa dinilai."}
    returned = sum(int(r.get("returned_value", 0)) for r in returns)
    rate = returned / received * 100
    score = max(0.0, round(100 - rate * 2, 1))   # 1% retur menurunkan 2 poin
    return {"score": score,
            "detail": (f"Nilai retur Rp {returned:,} dari Rp {received:,} barang diterima "
                       f"({round(rate, 2)}%).")}


async def _c_price(org: str, pos: list, vendor: dict) -> dict:
    diffs = []
    for p in pos:
        if p.get("status") == "cancelled":
            continue
        for it in p.get("items", []):
            if not it.get("material_id"):
                continue
            row = await reference_price(org, it["material_id"])
            base = row.get("unit_price")
            if base and int(it.get("unit_price", 0)) > 0:
                diffs.append((int(it["unit_price"]) - base) / base * 100)
    if not diffs:
        return {"score": None, "detail": "Belum ada harga acuan untuk item PO vendor ini — "
                                        "kewajaran harga belum bisa dinilai."}
    avg = sum(diffs) / len(diffs)
    score = max(0.0, min(100.0, round(100 - max(0.0, avg) * 3, 1)))
    return {"score": score,
            "detail": (f"Rata-rata harga {round(avg, 2)}% dibanding acuan atas {len(diffs)} "
                       "baris PO bermaterial.")}


async def evaluate_subcon(org: str, sub: dict) -> dict:
    spks = await db.spk.find({"org_id": org, "subcontractor_id": sub["id"]}, {"_id": 0}).to_list(200)
    spk_ids = [s["id"] for s in spks]
    claims = await db.progress_claims.find({"org_id": org, "spk_id": {"$in": spk_ids}},
                                           {"_id": 0}).to_list(500)
    penalties = await db.subcon_deductions.find(
        {"org_id": org, "spk_id": {"$in": spk_ids}, "kind": "penalty",
         "state": {"$ne": "cancelled"}}, {"_id": 0}).to_list(500)
    comp = {"timeliness": _s_timeliness(spks, penalties),
            "quality": _s_quality(claims),
            "price": {"score": None, "detail": "Nilai kontrak subkon tidak punya acuan harga "
                                               "pasar di sistem — tidak dinilai."},
            "service": {"score": None, "detail": "Belum ada sumber data pelayanan — pakai "
                                                 "penilaian manusia."}}
    score, missing = _combine(comp)
    return {
        "subcontractor_id": sub["id"], "vendor_name": sub.get("name"),
        "state": "complete" if score is not None else "missing_data",
        "score": score, "grade": _grade(score), "components": comp, "missing": missing,
        "evidence": {"spk_count": len(spks), "claim_count": len(claims),
                     "penalty_count": len(penalties)},
        "detail": ("Skor dihitung dari SPK, termin, dan denda nyata." if score is not None else
                   "Belum ada data — subkontraktor ini belum punya SPK/termin yang bisa dinilai."),
    }


def _s_timeliness(spks: list, penalties: list) -> dict:
    judged = [s for s in spks if s.get("start_date") and s.get("end_date")]
    if not judged:
        return {"score": None, "detail": "SPK belum punya tanggal mulai/selesai — ketepatan "
                                        "waktu belum bisa dinilai."}
    today = date.fromisoformat(today_iso_date())
    scores, notes = [], []
    for s in judged:
        start = date.fromisoformat(str(s["start_date"])[:10])
        end = date.fromisoformat(str(s["end_date"])[:10])
        span = max((end - start).days, 1)
        elapsed = max((min(today, end + timedelta(days=365)) - start).days, 0)
        expected = min(100.0, elapsed / span * 100)
        got = float(s.get("progress_pct", 0) or 0)
        if s.get("status") == "completed":
            got = 100.0
        scores.append(100.0 if got >= expected else max(0.0, 100 - (expected - got)))
        notes.append(f"{s.get('spk_number')}: progres {got:g}% vs rencana {round(expected)}%")
    penalty_value = sum(int(p.get("amount", 0)) for p in penalties)
    base = sum(scores) / len(scores)
    if penalty_value:
        base = max(0.0, base - min(30.0, len(penalties) * 5))
        notes.append(f"denda tercatat {len(penalties)} kali (Rp {penalty_value:,})")
    return {"score": round(base, 1), "detail": "; ".join(notes[:4])}


def _s_quality(claims: list) -> dict:
    judged = [c for c in claims if c.get("lines")]
    if not judged:
        return {"score": None, "detail": "Belum ada termin berbasis item (opname) — mutu "
                                        "pekerjaan belum bisa dinilai dari data."}
    asked = cut = 0
    for c in judged:
        for ln in c.get("lines", []):
            val = int(ln.get("value", 0) or 0)
            asked += val
            if not ln.get("included"):
                cut += val
    if asked <= 0:
        return {"score": None, "detail": "Nilai baris opname belum terisi — belum bisa dinilai."}
    rate = cut / asked * 100
    return {"score": max(0.0, round(100 - rate * 2, 1)),
            "detail": (f"Rp {cut:,} dari Rp {asked:,} nilai yang diajukan dipotong saat opname "
                       f"({round(rate, 2)}%).")}


async def save_assessment(org: str, target: dict, data: dict, actor: str) -> dict:
    """Penilaian manusia per periode. Satu penilai, satu periode, satu baris (koreksi = update)."""
    key = {"org_id": org, "target_type": target["type"], "target_id": target["id"],
           "period": data["period"], "assessor": actor}
    avg = round(sum(data["scores"].values()) / len(data["scores"]), 2)
    ts = now_iso()
    doc = {**key, **data, "average": avg, "target_name": target.get("name"), "updated_at": ts}
    old = await db.vendor_assessments.find_one(key, {"_id": 0, "id": 1, "created_at": 1})
    if old:
        doc["id"] = old["id"]
        await db.vendor_assessments.update_one({"id": old["id"]}, {"$set": doc})
    else:
        doc.update({"id": new_id(), "created_at": ts})
        await db.vendor_assessments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def list_assessments(org: str, target_type: str, target_id: str) -> list:
    return await db.vendor_assessments.find(
        {"org_id": org, "target_type": target_type, "target_id": target_id},
        {"_id": 0}).sort("period", -1).to_list(100)
