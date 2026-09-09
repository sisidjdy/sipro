"""OPNAME BERBUKTI & TERMIN BERBASIS ITEM PEKERJAAN (Fase 33).

MASALAH YANG DITUTUP MODUL INI (uang bocor):
Sebelum Fase 33, nilai termin subkontraktor lahir dari **persen kumulatif yang diketik
bebas** (`progress_claims.progress_pct`), lalu "opname" = mengetik persen lain. Tidak ada
satu pun ikatan ke pekerjaan yang benar-benar sudah diverifikasi (Fase 31/32: foto
watermark + checklist mutu + verifikator ≠ pengaju). Akibatnya:
  * subkon bisa ditagihkan 60% padahal fisik terverifikasi 33%,
  * pekerjaan yang sama bisa dibayar dua kali,
  * bahkan dua subkon bisa dibayar untuk item pekerjaan yang sama.

PRINSIP: **uang hanya mengalir mengikuti bukti**. Termin = Σ nilai item jadwal yang
SUDAH diverifikasi dan BELUM pernah ditagih.

INVARIAN (ditegakkan di sini + index database):
  INV-33-1 klaim ≤ nilai pekerjaan terverifikasi
  INV-33-2 satu item pekerjaan hanya bisa dibayar sekali (ledger `claim_id`)
  INV-33-3 satu item pekerjaan hanya boleh masuk satu SPK (unique index)
  INV-33-4 Σ lingkup ≤ nilai kontrak SPK
  INV-33-5 progres SPK mode item tidak bisa diketik manual (dihitung di sini)
  INV-33-6 opname hanya boleh MENGURANGI baris

Catatan kejujuran data: bila pekerjaan yang sudah ditagih kemudian DIKEMBALIKAN untuk
perbaikan, baris tidak dihapus diam-diam — ditandai `regressed=True` agar terlihat di
UI/laporan (bahan untuk klaim balik atau pemotongan retensi).
"""
import logging

from core_utils import new_id, now_iso
from db import db

logger = logging.getLogger("sipro.opname")

COLLECTION = "spk_scope_items"
OPEN_CLAIM = ("submitted", "verified")
DONE = "done"
SPK_EDITABLE = ("draft", "active")
ITEM_FIELDS = {
    "_id": 0, "id": 1, "status": 1, "verified_at": 1, "verified_by": 1, "submitted_at": 1,
    "name": 1, "step_code": 1, "unit_code": 1, "unit_id": 1, "week": 1, "weight": 1,
    "work_category": 1, "planned_start": 1, "planned_finish": 1, "evidence": 1,
    "schedule_id": 1, "order": 1, "project_id": 1, "override": 1,
}
STATE_LABEL = {
    "billed": "Sudah ditagih",
    "pending": "Dalam pengajuan termin",
    "claimable": "Terverifikasi — siap ditagih",
    "unverified": "Menunggu verifikasi supervisor",
    "open": "Belum selesai dikerjakan",
}


def rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def _i(v) -> int:
    return int(round(float(v or 0)))


# ============================== baca lingkup ==============================
async def scope_rows(org: str, spk_id: str) -> list:
    """Baris lingkup SPK + kondisi NYATA item pekerjaannya (bukan kopi basi)."""
    rows = await db.spk_scope_items.find(
        {"org_id": org, "spk_id": spk_id}, {"_id": 0}).to_list(2000)
    if not rows:
        return []
    items = await db.build_items.find(
        {"org_id": org, "id": {"$in": [r["build_item_id"] for r in rows]}},
        ITEM_FIELDS).to_list(2000)
    imap = {i["id"]: i for i in items}
    out = []
    for r in rows:
        out.append(_enrich(r, imap.get(r["build_item_id"]) or {}))
    out.sort(key=lambda r: (r.get("unit_code") or "", r.get("order") or 0))
    return out


def _enrich(row: dict, item: dict) -> dict:
    verified = item.get("status") == DONE and bool(item.get("verified_by"))
    billed = bool(row.get("claim_id"))
    pending = bool(row.get("pending_claim_id")) and not billed
    state = ("billed" if billed else "pending" if pending else
             "claimable" if verified else
             "unverified" if item.get("status") == "submitted" else "open")
    return {
        **row,
        "item_status": item.get("status"),
        "verified": verified,
        "verified_at": item.get("verified_at"),
        "verified_by": item.get("verified_by"),
        "planned_finish": item.get("planned_finish"),
        "evidence_count": len(item.get("evidence") or []),
        "override": bool(item.get("override")),
        "order": row.get("order") or item.get("order") or 0,
        "state": state, "state_label": STATE_LABEL[state],
        "claimable": bool(verified and not billed and not pending),
        "regressed": bool(billed and item.get("status") != DONE),
    }


def int_pct(part, total) -> int:
    """Persen bulat dari NILAI mentah (hindari pembulatan ganda yang menggeser angka)."""
    t = _i(total)
    return int(round(_i(part) / t * 100)) if t else 0


def summarize(rows: list) -> dict:
    scope = sum(_i(r.get("value")) for r in rows)
    verified = sum(_i(r.get("value")) for r in rows if r.get("verified"))
    billed = sum(_i(r.get("value")) for r in rows if r.get("claim_id"))
    pending = sum(_i(r.get("value")) for r in rows if r.get("state") == "pending")
    claimable = sum(_i(r.get("value")) for r in rows if r.get("claimable"))
    return {
        "items": len(rows), "scope_value": scope, "verified_value": verified,
        "billed_value": billed, "pending_value": pending, "claimable_value": claimable,
        "verified_items": sum(1 for r in rows if r.get("verified")),
        "billed_items": sum(1 for r in rows if r.get("claim_id")),
        "claimable_items": sum(1 for r in rows if r.get("claimable")),
        "regressed_items": sum(1 for r in rows if r.get("regressed")),
        "progress_pct": round(verified / scope * 100, 1) if scope else 0.0,
        "billed_pct": round(billed / scope * 100, 1) if scope else 0.0,
    }


async def sync_spk(org: str, spk_id: str) -> dict:
    """Tulis ulang angka ringkas ke dokumen SPK (SSOT tetap baris lingkup)."""
    rows = await scope_rows(org, spk_id)
    s = summarize(rows)
    setter = {
        "scope_mode": "items" if rows else "lumpsum",
        "scope_items": s["items"], "scope_value": s["scope_value"],
        "scope_verified_value": s["verified_value"],
        "scope_billed_value": s["billed_value"],
        "scope_claimable_value": s["claimable_value"],
        "updated_at": now_iso(),
    }
    if rows:
        setter["progress_pct"] = int_pct(s["verified_value"], s["scope_value"])
        setter["billed_pct"] = int_pct(s["billed_value"], s["scope_value"])
    await db.spk.update_one({"id": spk_id, "org_id": org}, {"$set": setter})
    return s


async def enrich_spk_list(org: str, spks: list) -> list:
    """Segarkan angka lingkup pada DAFTAR SPK tanpa menulis (anti kopi basi).

    Memverifikasi satu pekerjaan mengubah nilai terverifikasi sebuah SPK. Kalau daftar
    hanya membaca angka yang dulu ditulis, direksi bisa melihat progres lama. Karena itu
    daftar dihitung ulang dari baris lingkup + status item pekerjaan (2 query, bukan N).
    """
    ids = [s["id"] for s in spks]
    if not ids:
        return spks
    rows = await db.spk_scope_items.find({"org_id": org, "spk_id": {"$in": ids}},
                                         {"_id": 0}).to_list(8000)
    if not rows:
        return spks
    items = await db.build_items.find(
        {"org_id": org, "id": {"$in": [r["build_item_id"] for r in rows]}},
        ITEM_FIELDS).to_list(8000)
    imap = {i["id"]: i for i in items}
    per = {}
    for r in rows:
        per.setdefault(r["spk_id"], []).append(_enrich(r, imap.get(r["build_item_id"]) or {}))
    for s in spks:
        group = per.get(s["id"])
        if not group:
            continue
        g = summarize(group)
        s.update({
            "scope_mode": "items", "scope_items": g["items"],
            "scope_value": g["scope_value"], "scope_verified_value": g["verified_value"],
            "scope_billed_value": g["billed_value"],
            "scope_claimable_value": g["claimable_value"],
            "progress_pct": int_pct(g["verified_value"], g["scope_value"]),
            "billed_pct": int_pct(g["billed_value"], g["scope_value"]),
        })
    return spks


# ============================== harga acuan RAB ==============================
async def rab_reference(org: str, project_id: str) -> dict:
    """Harga acuan per LANGKAH dari item RAB yang dipetakan ke langkah tersebut.

    Alokasi dibagi RATA ke langkah yang dipilih pada item RAB, lalu dibagi jumlah unit
    yang memiliki langkah itu — disebut apa adanya di UI sebagai "harga acuan RAB (bisa
    diubah)", bukan angka final yang seolah-olah presisi.
    """
    boq = await db.boq_items.find(
        {"org_id": org, "project_id": project_id, "step_codes": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "cost_code": 1, "category": 1, "description": 1,
         "amount": 1, "step_codes": 1}).to_list(1000)
    if not boq:
        return {}
    units = await db.build_items.aggregate([
        {"$match": {"org_id": org, "project_id": project_id}},
        {"$group": {"_id": "$step_code", "units": {"$addToSet": "$unit_id"}}},
    ]).to_list(500)
    ucount = {u["_id"]: max(1, len(u["units"])) for u in units}
    acc = {}
    for b in boq:
        codes = [c for c in (b.get("step_codes") or []) if c]
        if not codes:
            continue
        share = _i(b.get("amount")) / len(codes)
        for code in codes:
            cur = acc.setdefault(code, {"total": 0, "boq_item_id": b["id"],
                                        "cost_code": b.get("cost_code"),
                                        "category": b.get("category"),
                                        "description": b.get("description"), "best": 0})
            cur["total"] += share
            if share > cur["best"]:
                cur.update({"best": share, "boq_item_id": b["id"],
                            "cost_code": b.get("cost_code"), "category": b.get("category"),
                            "description": b.get("description")})
    out = {}
    for code, v in acc.items():
        out[code] = {
            "suggested_value": _i(v["total"] / ucount.get(code, 1)),
            "boq_item_id": v["boq_item_id"], "cost_code": v["cost_code"],
            "category": v["category"], "boq_description": v["description"],
        }
    return out


# ============================== kandidat & tulis lingkup ==============================
async def used_item_ids(org: str) -> dict:
    rows = await db.spk_scope_items.find(
        {"org_id": org}, {"_id": 0, "build_item_id": 1, "spk_number": 1}).to_list(5000)
    return {r["build_item_id"]: r.get("spk_number") for r in rows}


async def candidates(org: str, spk: dict, unit_id: str = None) -> dict:
    """Item jadwal proyek ini yang BELUM dipakai SPK mana pun (INV-33-3)."""
    q = {"org_id": org, "project_id": spk["project_id"]}
    if unit_id:
        q["unit_id"] = unit_id
    items = await db.build_items.find(q, ITEM_FIELDS).to_list(4000)
    used = await used_item_ids(org)
    ref = await rab_reference(org, spk["project_id"])
    # Fase 80: RAB tipe unit lebih diutamakan sebagai acuan harga per langkah
    import rab_engine as re_
    type_ref = await re_.type_step_reference(org)
    unit_types = {u["id"]: u.get("unit_type_code") for u in await db.units.find(
        {"org_id": org, "project_id": spk["project_id"]}, {"_id": 0, "id": 1, "unit_type_code": 1}).to_list(2000)}
    groups = {}
    for it in sorted(items, key=lambda i: (i.get("unit_code") or "", i.get("order") or 0)):
        if it["id"] in used:
            continue
        hint = type_ref.get((unit_types.get(it.get("unit_id")), it.get("step_code"))) or ref.get(it.get("step_code")) or {}
        g = groups.setdefault(it.get("unit_id"), {
            "unit_id": it.get("unit_id"), "unit_code": it.get("unit_code"), "items": []})
        g["items"].append({
            "build_item_id": it["id"], "step_code": it.get("step_code"),
            "step_name": it.get("name"), "week": it.get("week"), "weight": it.get("weight"),
            "unit_id": it.get("unit_id"), "unit_code": it.get("unit_code"),
            "work_category": it.get("work_category"), "status": it.get("status"),
            "verified": it.get("status") == DONE and bool(it.get("verified_by")),
            "planned_start": it.get("planned_start"), "planned_finish": it.get("planned_finish"),
            "schedule_id": it.get("schedule_id"), "order": it.get("order"),
            "suggested_value": hint.get("suggested_value") or 0,
            "boq_item_id": hint.get("boq_item_id"), "cost_code": hint.get("cost_code"),
            "boq_description": hint.get("boq_description"),
        })
    rows = await scope_rows(org, spk["id"])
    s = summarize(rows)
    return {
        "units": sorted(groups.values(), key=lambda g: g.get("unit_code") or ""),
        "contract_value": _i(spk.get("contract_value")),
        "allocated": s["scope_value"],
        "unallocated": _i(spk.get("contract_value")) - s["scope_value"],
        "rab_mapped": bool(ref),
    }


async def add_lines(org: str, spk: dict, lines: list, actor: str) -> dict:
    """Masukkan item pekerjaan ke lingkup SPK. Semua penolakan berpesan manusiawi."""
    if spk.get("status") not in SPK_EDITABLE:
        raise ValueError("Lingkup hanya bisa diubah saat SPK berstatus draf atau aktif.")
    if not lines:
        raise ValueError("Pilih minimal satu item pekerjaan.")
    used = await used_item_ids(org)
    existing = await scope_rows(org, spk["id"])
    total = summarize(existing)["scope_value"]
    contract = _i(spk.get("contract_value"))
    ref = await rab_reference(org, spk["project_id"])
    docs, ts = [], now_iso()
    for ln in lines:
        bid = ln.build_item_id if hasattr(ln, "build_item_id") else ln["build_item_id"]
        value = _i(ln.value if hasattr(ln, "value") else ln.get("value"))
        boq_id = (ln.boq_item_id if hasattr(ln, "boq_item_id") else ln.get("boq_item_id"))
        item = await db.build_items.find_one({"org_id": org, "id": bid}, ITEM_FIELDS)
        if not item:
            raise ValueError("Item pekerjaan tidak ditemukan.")
        if item.get("project_id") != spk["project_id"]:
            raise ValueError(f"Item {item.get('step_code')} bukan milik proyek SPK ini.")
        if bid in used:
            raise ValueError(f"Pekerjaan {item.get('unit_code')} · {item.get('step_code')} sudah "
                             f"masuk lingkup {used[bid]} — satu pekerjaan tidak boleh dibayar "
                             "lewat dua SPK.")
        if value <= 0:
            raise ValueError(f"Nilai borongan {item.get('step_code')} harus lebih dari 0 — "
                             "pekerjaan tanpa nilai tidak bisa ditagih.")
        hint = ref.get(item.get("step_code")) or {}
        boq = None
        if boq_id:
            boq = await db.boq_items.find_one({"org_id": org, "id": boq_id},
                                              {"_id": 0, "cost_code": 1, "category": 1})
        total += value
        docs.append({
            "id": new_id(), "org_id": org, "spk_id": spk["id"],
            "spk_number": spk.get("spk_number"), "project_id": spk["project_id"],
            "subcontractor_id": spk.get("subcontractor_id"),
            "subcontractor_name": spk.get("subcontractor_name"),
            "unit_id": item.get("unit_id"), "unit_code": item.get("unit_code"),
            "schedule_id": item.get("schedule_id"), "build_item_id": bid,
            "step_code": item.get("step_code"), "step_name": item.get("name"),
            "week": item.get("week"), "weight": item.get("weight"),
            "order": item.get("order"), "value": value,
            "boq_item_id": boq_id or hint.get("boq_item_id"),
            "cost_code": (boq or {}).get("cost_code") or hint.get("cost_code"),
            "category": ((boq or {}).get("category") or hint.get("category")
                         or item.get("work_category") or "lainnya"),
            "pending_claim_id": None, "claim_id": None, "claim_number": None,
            "claimed_at": None, "exclude_reason": None,
            "created_by": actor, "created_at": ts, "updated_at": ts,
        })
        used[bid] = spk.get("spk_number")
    if contract and total > contract:
        raise ValueError(f"Total lingkup {rp(total)} melebihi nilai kontrak SPK {rp(contract)}. "
                         "Tambah nilai kontrak lewat Change Order, atau kurangi item.")
    await db.spk_scope_items.insert_many([dict(d) for d in docs])
    s = await sync_spk(org, spk["id"])
    return {"added": len(docs), "summary": s}


async def remove_line(org: str, spk_id: str, scope_id: str) -> dict:
    row = await db.spk_scope_items.find_one({"org_id": org, "id": scope_id, "spk_id": spk_id},
                                            {"_id": 0})
    if not row:
        raise ValueError("Baris lingkup tidak ditemukan.")
    if row.get("claim_id"):
        raise ValueError(f"Pekerjaan ini sudah ditagih pada termin {row.get('claim_number')} — "
                         "tidak bisa dikeluarkan dari lingkup.")
    if row.get("pending_claim_id"):
        raise ValueError("Pekerjaan ini sedang dalam pengajuan termin — selesaikan atau tolak "
                         "termin tersebut dulu.")
    await db.spk_scope_items.delete_one({"org_id": org, "id": scope_id})
    s = await sync_spk(org, spk_id)
    return {"deleted": True, "summary": s}


# ============================== opname & termin ==============================
def _blockers(rows: list) -> list:
    """Kenapa sebuah pekerjaan belum bisa ditagih — dijelaskan, bukan disembunyikan."""
    reasons = {}
    for r in rows:
        if r.get("claimable") or r.get("claim_id"):
            continue
        key = r.get("state")
        reasons.setdefault(key, {"state": key, "label": r.get("state_label"),
                                 "items": 0, "value": 0})
        reasons[key]["items"] += 1
        reasons[key]["value"] += _i(r.get("value"))
    return list(reasons.values())


async def opname_preview(org: str, spk: dict) -> dict:
    rows = await scope_rows(org, spk["id"])
    s = summarize(rows)
    claimable = [r for r in rows if r.get("claimable")]
    ret_pct = float(spk.get("retention_pct") or 0)
    gross = sum(_i(r.get("value")) for r in claimable)
    retention = round(gross * ret_pct / 100)
    return {
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "contract_value": _i(spk.get("contract_value")),
        "retention_pct": ret_pct, "lines": claimable, "gross": gross,
        "retention_est": retention, "net_est": gross - retention,
        "summary": s, "blockers": _blockers(rows),
        "open_claim": await db.progress_claims.find_one(
            {"org_id": org, "spk_id": spk["id"], "status": {"$in": list(OPEN_CLAIM)}},
            {"_id": 0, "id": 1, "claim_number": 1, "status": 1}),
    }


def claim_lines(rows: list) -> list:
    """Snapshot baris termin (nilai dibekukan saat pengajuan agar jejak audit jelas)."""
    return [{
        "scope_item_id": r["id"], "build_item_id": r["build_item_id"],
        "unit_code": r.get("unit_code"), "step_code": r.get("step_code"),
        "step_name": r.get("step_name"), "value": _i(r.get("value")),
        "category": r.get("category"), "cost_code": r.get("cost_code"),
        "verified_at": r.get("verified_at"), "verified_by": r.get("verified_by"),
        "included": True, "exclude_reason": None,
    } for r in rows]


async def hold_lines(org: str, claim_id: str, lines: list) -> None:
    ids = [ln["scope_item_id"] for ln in lines]
    await db.spk_scope_items.update_many(
        {"org_id": org, "id": {"$in": ids}},
        {"$set": {"pending_claim_id": claim_id, "updated_at": now_iso()}})


async def release_lines(org: str, claim: dict) -> None:
    ids = [ln["scope_item_id"] for ln in (claim.get("lines") or [])]
    if ids:
        await db.spk_scope_items.update_many(
            {"org_id": org, "id": {"$in": ids}, "claim_id": None},
            {"$set": {"pending_claim_id": None, "updated_at": now_iso()}})
    await sync_spk(org, claim["spk_id"])


async def settle_lines(org: str, claim: dict) -> None:
    """Tandai baris yang lolos opname sebagai SUDAH DIBAYAR (INV-33-2); sisanya dilepas."""
    ts = now_iso()
    paid = [ln for ln in (claim.get("lines") or []) if ln.get("included")]
    dropped = [ln for ln in (claim.get("lines") or []) if not ln.get("included")]
    if paid:
        await db.spk_scope_items.update_many(
            {"org_id": org, "id": {"$in": [ln["scope_item_id"] for ln in paid]}},
            {"$set": {"claim_id": claim["id"], "claim_number": claim.get("claim_number"),
                      "claimed_at": ts, "pending_claim_id": None, "updated_at": ts}})
    for ln in dropped:
        await db.spk_scope_items.update_one(
            {"org_id": org, "id": ln["scope_item_id"]},
            {"$set": {"pending_claim_id": None, "exclude_reason": ln.get("exclude_reason"),
                      "updated_at": ts}})
    await sync_spk(org, claim["spk_id"])


async def revalidate(org: str, claim: dict) -> list:
    """Sebelum PERSETUJUAN: pastikan baris masih sah (belum ditagih & masih terverifikasi)."""
    problems = []
    for ln in (claim.get("lines") or []):
        if not ln.get("included"):
            continue
        row = await db.spk_scope_items.find_one(
            {"org_id": org, "id": ln["scope_item_id"]}, {"_id": 0})
        item = await db.build_items.find_one(
            {"org_id": org, "id": ln["build_item_id"]}, ITEM_FIELDS) or {}
        label = f"{ln.get('unit_code')} · {ln.get('step_code')}"
        if not row:
            problems.append(f"{label}: baris lingkup sudah dihapus.")
        elif row.get("claim_id") and row["claim_id"] != claim["id"]:
            problems.append(f"{label}: sudah ditagih pada termin {row.get('claim_number')}.")
        elif item.get("status") != DONE or not item.get("verified_by"):
            problems.append(f"{label}: dikembalikan untuk perbaikan setelah termin diajukan — "
                            "lakukan opname ulang.")
    return problems


# ============================== kendali biaya RAB ==============================
async def cost_control(org: str, project_id: str, project_name: str = None) -> dict:
    """Anggaran (RAB) vs dikontrakkan (lingkup SPK) vs terverifikasi vs ditagih."""
    boq = await db.boq_items.find({"org_id": org, "project_id": project_id}, {"_id": 0}).to_list(2000)
    scope = await db.spk_scope_items.find({"org_id": org, "project_id": project_id},
                                          {"_id": 0}).to_list(4000)
    items = await db.build_items.find(
        {"org_id": org, "id": {"$in": [s["build_item_id"] for s in scope]}},
        ITEM_FIELDS).to_list(4000) if scope else []
    imap = {i["id"]: i for i in items}
    cats, codes = {}, {}

    def bucket(store, key, label=None):
        return store.setdefault(key, {"key": key, "label": label or key, "budget": 0,
                                      "contracted": 0, "verified": 0, "billed": 0,
                                      "steps": [], "mapped": False})
    for b in boq:
        cat = b.get("category") or "lainnya"
        bucket(cats, cat)["budget"] += _i(b.get("amount"))
        c = bucket(codes, b.get("cost_code") or "(tanpa kode)", b.get("description"))
        c["budget"] += _i(b.get("amount"))
        c["category"] = cat
        c["steps"] = sorted(set((c.get("steps") or []) + list(b.get("step_codes") or [])))
        c["mapped"] = bool(c["steps"])
        c["boq_item_id"] = b.get("id")
    for s in scope:
        row = _enrich(s, imap.get(s["build_item_id"]) or {})
        val = _i(row.get("value"))
        cat = bucket(cats, row.get("category") or "lainnya")
        code = bucket(codes, row.get("cost_code") or "(tanpa kode)")
        for store in (cat, code):
            store["contracted"] += val
            store["verified"] += val if row.get("verified") else 0
            store["billed"] += val if row.get("claim_id") else 0
    rows = []
    for store in (cats, codes):
        for v in store.values():
            v["variance"] = v["budget"] - v["contracted"]
            v["over_commit"] = bool(v["budget"] and v["contracted"] > v["budget"])
            v["unbilled_verified"] = v["verified"] - v["billed"]
    rows = sorted(cats.values(), key=lambda r: -r["budget"])
    code_rows = sorted(codes.values(), key=lambda r: -r["budget"])
    totals = {k: sum(r[k] for r in rows) for k in ("budget", "contracted", "verified", "billed")}
    totals["variance"] = totals["budget"] - totals["contracted"]
    totals["unbilled_verified"] = totals["verified"] - totals["billed"]
    unmapped = sum(r["budget"] for r in code_rows if not r.get("mapped"))
    warnings = [f"{r['label'] or r['key']}: nilai dikontrakkan {rp(r['contracted'])} melebihi "
                f"anggaran RAB {rp(r['budget'])} — sahkan lewat Change Order/revisi RAB."
                for r in rows if r["over_commit"]]
    if unmapped:
        warnings.append(f"{rp(unmapped)} anggaran RAB belum dipetakan ke langkah jadwal — "
                        "harga acuan borongan belum bisa dihitung untuk pekerjaan itu.")
    return {
        "project_id": project_id, "project_name": project_name,
        "totals": totals, "categories": rows, "cost_codes": code_rows,
        "unmapped_budget": unmapped, "warnings": warnings,
        "scope_lines": len(scope),
    }


async def project_steps(org: str, project_id=None) -> list:
    """Langkah jadwal NYATA (untuk pemetaan RAB → langkah).

    `project_id` boleh berupa satu id, daftar id, atau None (semua proyek yang boleh
    diakses) supaya dialog pemetaan maupun ringkasan lintas proyek memakai satu jalur.
    """
    match = {"org_id": org}
    if isinstance(project_id, (list, tuple, set)):
        match["project_id"] = {"$in": list(project_id)}
    elif project_id:
        match["project_id"] = project_id
    rows = await db.build_items.aggregate([
        {"$match": match},
        {"$group": {"_id": {"code": "$step_code", "name": "$name"},
                    "week": {"$min": "$week"}, "category": {"$first": "$work_category"},
                    "units": {"$addToSet": "$unit_id"}, "weight": {"$first": "$weight"}}},
    ]).to_list(500)
    out = [{"step_code": r["_id"]["code"], "step_name": r["_id"]["name"],
            "week": r.get("week"), "category": r.get("category"),
            "weight": r.get("weight"), "units": len(r.get("units") or [])}
           for r in rows if r["_id"].get("code")]
    return sorted(out, key=lambda r: (r.get("week") or 0, r["step_code"]))


async def ensure_indexes() -> None:
    """INV-33-3 dijaga DATABASE: satu item pekerjaan hanya boleh ada di satu lingkup.

    Index-nya PARTIAL (`build_item_id` bertipe string saja). Sebelum ini index unik biasa
    dipakai, sehingga aturannya melebar tanpa sengaja: karena `null == null` di MongoDB,
    HANYA SATU baris lingkup tanpa item pekerjaan yang boleh ada **di seluruh organisasi**.
    Lingkup borongan/manual (yang memang tidak menunjuk item jadwal) jadi ditolak database
    dengan galat mentah 500 pada baris KEDUA — padahal aturan yang ingin dijaga hanya
    "satu item pekerjaan tidak boleh diklaim dua SPK".
    """
    spec = [("org_id", 1), ("build_item_id", 1)]
    nama = "org_id_1_build_item_id_1"
    info = await db.spk_scope_items.index_information()
    if nama in info and not info[nama].get("partialFilterExpression"):
        # Index lama harus dibuang dulu: MongoDB menolak `create_index` dengan opsi berbeda
        # untuk nama/kunci yang sama.
        await db.spk_scope_items.drop_index(nama)
    await db.spk_scope_items.create_index(
        spec, unique=True,
        partialFilterExpression={"build_item_id": {"$type": "string"}})
    await db.spk_scope_items.create_index([("org_id", 1), ("spk_id", 1)])
    await db.spk_scope_items.create_index([("org_id", 1), ("project_id", 1)])
    await db.spk_scope_items.create_index([("org_id", 1), ("claim_id", 1)])
