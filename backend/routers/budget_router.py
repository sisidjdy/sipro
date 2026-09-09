"""Master anggaran & realisasi RAB (Fase 45) — `docs/v2/32` §3–§5. Endpoint tipis.

Tiga lapis tampilan yang diminta owner ada di tiga endpoint yang berbeda, sengaja:
  * `GET /budget/summary`             lapis 1 — angka umum proyek + status + peringatan
  * `GET /budget/by-category`         lapis 2 — kategori × (rencana/komitmen/realisasi/%)
  * `GET /budget/items/{id}/realization` lapis 3 — DAFTAR DOKUMEN penyusun angkanya

Aturan yang ditegakkan di sini (bukan hanya dijanjikan di dokumen):
  * rencana item kategori `konstruksi` dengan aturan `by_boq_item` bersifat **read-only** —
    ia dihitung dari Σ item RAB yang ditaut. Mengirim `planned_amount` untuk item seperti itu
    DITOLAK dengan penjelasan, supaya tidak pernah ada dua angka anggaran konstruksi.
  * revisi anggaran WAJIB beralasan dan butuh izin `approve` (pemisahan tugas: yang menyusun
    anggaran bukan yang menyetujui perubahannya).
  * `budget.enforce_cost_ref` bawaannya MATI. Saat dinyalakan, dokumen biaya baru wajib
    menyebut item anggaran — dan daftar "biaya belum terpetakan" adalah alat merapikannya.
"""
import budget_engine as be
import budget_reports as br
import settings_store as cfg
from core_utils import new_id, now_iso, serialize_doc
from db import ORG_ID, db
from fastapi import APIRouter, Depends, HTTPException
from models_p45 import (BudgetItemCreate, BudgetItemUpdate, BudgetManualEntry, BudgetRevise)
from rbac import assert_project_access, audit_log, project_query, require_permission

router = APIRouter(prefix="/budget", tags=["budget"])
READONLY_MSG = ("Rencana item anggaran KONSTRUKSI dihitung dari total item RAB yang ditaut "
                "(read-only). Ubah nilainya di RAB/BoQ atau ubah daftar item RAB yang ditaut "
                "— supaya tidak ada dua angka anggaran konstruksi yang berbeda.")


async def _projects(user: dict) -> dict:
    rows = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}) \
        .to_list(500)
    return {p["id"]: p.get("name") for p in rows}


async def _resolve(user: dict, project_id: str = None) -> list:
    """Daftar proyek yang dipakai jawaban. Tanpa `project_id` = semua yang boleh diakses."""
    pmap = await _projects(user)
    if project_id:
        if project_id not in pmap:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk proyek ini")
        return [project_id]
    return list(pmap.keys())


async def _alert_pct(org: str, project_id: str) -> float:
    return float(await cfg.get("budget.alert_pct", org_id=org, project_id=project_id) or 90)


async def _get_item(iid: str, user: dict) -> dict:
    doc = await db.budget_items.find_one({"id": iid, "org_id": user.get("org_id", ORG_ID)},
                                        {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item anggaran tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


def _is_readonly(item: dict) -> bool:
    return (item.get("category") == be.CONSTRUCTION
            and item.get("match_rule") == "by_boq_item")


# ================================================================= master item anggaran
@router.get("/items")
async def list_items(project_id: str = None, category: str = None, active: bool = None,
                     user: dict = Depends(require_permission("budget", "view"))):
    """Master item anggaran (bisa ditambah user — keputusan D6)."""
    org = user.get("org_id", ORG_ID)
    pmap = await _projects(user)
    pids = await _resolve(user, project_id)
    q = {"org_id": org, "project_id": {"$in": pids}}
    if category:
        q["category"] = category
    if active is not None:
        q["active"] = active
    rows = await db.budget_items.find(q, {"_id": 0}).sort([("order", 1), ("code", 1)]) \
        .to_list(2000)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"))
        r["planned_readonly"] = _is_readonly(r)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/items")
async def create_item(payload: BudgetItemCreate,
                      user: dict = Depends(require_permission("budget", "create"))):
    org = user.get("org_id", ORG_ID)
    proj = await assert_project_access(payload.project_id, user)
    body = payload.dict()
    if _is_readonly(body):
        if body.get("planned_amount"):
            raise HTTPException(status_code=400, detail=READONLY_MSG)
        if not body.get("boq_item_ids"):
            raise HTTPException(status_code=400, detail=(
                "Item anggaran konstruksi harus menaut minimal satu item RAB — tanpa itu "
                "rencananya tidak bisa dihitung dari RAB."))
    if body.get("match_rule") == "by_gl_account" and not body.get("gl_account"):
        raise HTTPException(status_code=400, detail=(
            "Aturan 'dari akun buku besar' membutuhkan akun GL — tanpa itu realisasinya "
            "tidak bisa dicocokkan ke apa pun."))
    if body.get("boq_item_ids"):
        found = await db.boq_items.count_documents(
            {"org_id": org, "project_id": payload.project_id,
             "id": {"$in": body["boq_item_ids"]}})
        if found != len(set(body["boq_item_ids"])):
            raise HTTPException(status_code=400, detail=(
                "Ada item RAB yang tidak ditemukan pada proyek ini. Pilih dari daftar RAB "
                "proyek yang benar."))
    dup = await db.budget_items.find_one({"org_id": org, "project_id": payload.project_id,
                                         "code": body["code"]}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(status_code=400,
                            detail=f"Kode anggaran '{body['code']}' sudah dipakai di proyek ini.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "project_name": proj.get("name"), **body,
           "revision": [], "alerts": [], "alert_level": "aman", "active": True,
           "created_by": user.get("email"), "created_at": ts, "updated_at": ts}
    await db.budget_items.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit_log(user, "create", "budget_items", doc["id"],
                    {"code": doc["code"], "category": doc["category"]})
    return {"data": serialize_doc({**doc, "planned_readonly": _is_readonly(doc)})}


@router.put("/items/{iid}")
async def update_item(iid: str, payload: BudgetItemUpdate,
                      user: dict = Depends(require_permission("budget", "update"))):
    org = user.get("org_id", ORG_ID)
    item = await _get_item(iid, user)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan yang dikirim.")
    merged = {**item, **upd}
    if _is_readonly(merged) and not merged.get("boq_item_ids"):
        raise HTTPException(status_code=400, detail=(
            "Item anggaran konstruksi harus tetap menaut minimal satu item RAB."))
    if merged.get("match_rule") == "by_gl_account" and not merged.get("gl_account"):
        raise HTTPException(status_code=400,
                            detail="Aturan 'dari akun buku besar' membutuhkan akun GL.")
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user.get("email")
    await db.budget_items.update_one({"id": iid, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", "budget_items", iid, {"fields": sorted(upd.keys())})
    doc = await db.budget_items.find_one({"id": iid}, {"_id": 0})
    return {"data": serialize_doc({**doc, "planned_readonly": _is_readonly(doc)})}


@router.delete("/items/{iid}")
async def delete_item(iid: str, user: dict = Depends(require_permission("budget", "delete"))):
    item = await _get_item(iid, user)
    ctx = await be.build_context(item["org_id"], item["project_id"],
                                 alert_pct=await _alert_pct(item["org_id"], item["project_id"]))
    fig = be.item_figures(item, ctx)
    if fig["realized"] or fig["committed"]:
        raise HTTPException(status_code=400, detail=(
            f"Item ini sudah punya realisasi/komitmen (Rp {fig['exposure']:,}) dari "
            f"{fig['document_count']} dokumen. Nonaktifkan saja (active=false) supaya jejak "
            "biayanya tidak hilang dari laporan.".replace(",", ".")))
    await db.budget_items.delete_one({"id": iid, "org_id": item["org_id"]})
    await audit_log(user, "delete", "budget_items", iid, {"code": item.get("code")})
    return {"data": {"deleted": True}}


@router.post("/items/{iid}/revise")
async def revise_item(iid: str, payload: BudgetRevise,
                      user: dict = Depends(require_permission("budget", "approve"))):
    """Revisi rencana anggaran — alasan wajib, jejak permanen, dan konstruksi ditolak."""
    item = await _get_item(iid, user)
    if _is_readonly(item):
        raise HTTPException(status_code=400, detail=READONLY_MSG)
    entry = await br.revise_item(item["org_id"], iid, planned_amount=payload.planned_amount,
                                reason=payload.reason, actor=user.get("email"))
    await audit_log(user, "revise", "budget_items", iid, entry)
    doc = await db.budget_items.find_one({"id": iid}, {"_id": 0})
    return {"data": serialize_doc(doc), "entry": serialize_doc(entry)}


@router.post("/items/{iid}/manual-entry")
async def manual_entry(iid: str, payload: BudgetManualEntry,
                       user: dict = Depends(require_permission("budget", "update"))):
    """Catat realisasi manual (untuk item ber-aturan `manual`) — selalu ber-jejak & beralasan."""
    item = await _get_item(iid, user)
    if item.get("match_rule") != "manual":
        raise HTTPException(status_code=400, detail=(
            f"Item ini dicocokkan otomatis ({item.get('match_rule')}), jadi realisasinya tidak "
            "boleh diketik manual — itu akan membuat angkanya terhitung dua kali. Ubah aturan "
            "pencocokan ke 'Dicatat manual' bila memang biayanya di luar sistem."))
    doc = await br.add_manual_entry(item["org_id"], iid, amount=payload.amount,
                                    note=payload.note, actor=user.get("email"),
                                    kind=payload.kind, ref_no=payload.ref_no)
    await audit_log(user, "manual_entry", "budget_items", iid,
                    {"amount": payload.amount, "kind": payload.kind})
    return {"data": serialize_doc(doc)}


@router.get("/items/{iid}/realization")
async def item_realization(iid: str,
                           user: dict = Depends(require_permission("budget", "view"))):
    """LAPIS 3: daftar dokumen sumber penyusun angka item ini (audit trail lengkap).

    Σ dokumen berjenis `realisasi` == realisasi item; Σ `komitmen` == komitmen item. Kalau
    tidak sama, itu cacat — gate `verify_budget_target.py` memeriksanya.
    """
    item = await _get_item(iid, user)
    org = item["org_id"]
    ctx = await be.build_context(org, item["project_id"],
                                 alert_pct=await _alert_pct(org, item["project_id"]))
    fig = be.item_figures(item, ctx)
    by_source = {}
    for d in fig["documents"]:
        row = by_source.setdefault(d["source"], {"source": d["source"], "amount": 0,
                                                 "count": 0})
        row["amount"] += d["amount"]
        row["count"] += 1
    checks = {
        "documents_realisasi": sum(d["amount"] for d in fig["documents"]
                                   if d["kind"] == "realisasi"),
        "documents_komitmen": sum(d["amount"] for d in fig["documents"]
                                  if d["kind"] == "komitmen"),
    }
    checks["tie_out_ok"] = (checks["documents_realisasi"] == fig["realized"]
                            and checks["documents_komitmen"] == fig["committed"])
    material = (await be.material_usage(org, item["project_id"])
                if item.get("category") == be.CONSTRUCTION else None)
    return {"data": serialize_doc({
        **fig, "project_id": item["project_id"], "project_name": item.get("project_name"),
        "by_source": sorted(by_source.values(), key=lambda r: -r["amount"]),
        "checks": checks, "material_usage": material,
        "revision": item.get("revision") or [], "alerts": (item.get("alerts") or [])[-5:],
    })}


# ================================================================= lapis 1 & 2
@router.get("/summary")
async def summary(project_id: str = None,
                  user: dict = Depends(require_permission("budget", "view"))):
    """LAPIS 1: rencana/komitmen/realisasi/sisa/% + status per proyek.

    Tanpa `project_id`, ringkasan dibuat untuk SEMUA proyek yang boleh diakses (dipakai kartu
    portofolio). Proyek tanpa item anggaran mengaku `kosong` — bukan "Rp 0, aman".
    """
    org = user.get("org_id", ORG_ID)
    pids = await _resolve(user, project_id)
    out = []
    for pid in pids:
        out.append(await be.compute_project(org, pid, alert_pct=await _alert_pct(org, pid)))
    if project_id:
        return {"data": serialize_doc(out[0] if out else None)}
    return {"data": serialize_doc(out), "total": len(out)}


@router.get("/by-category")
async def by_category(project_id: str = None,
                      user: dict = Depends(require_permission("budget", "view"))):
    """LAPIS 2: tabel kategori × (rencana, komitmen, realisasi, selisih, %, status)."""
    org = user.get("org_id", ORG_ID)
    pids = await _resolve(user, project_id)
    rows = []
    for pid in pids:
        res = await be.compute_project(org, pid, alert_pct=await _alert_pct(org, pid))
        for c in res["categories"]:
            rows.append({**c, "project_id": pid, "project_name": res.get("project_name")})
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("/rab-vs-actual")
async def rab_vs_actual(project_id: str = None, group_by: str = "item",
                        user: dict = Depends(require_permission("budget", "view"))):
    """RAB vs realisasi per item / langkah / unit / kategori (+ bukti tie-out)."""
    if group_by not in ("item", "step", "unit", "category"):
        raise HTTPException(status_code=400, detail=(
            "group_by harus salah satu dari: item, step, unit, category."))
    org = user.get("org_id", ORG_ID)
    pids = await _resolve(user, project_id)
    if not pids:
        return {"data": [], "total": 0}
    if project_id:
        return {"data": serialize_doc(await br.rab_vs_actual(org, project_id, group_by))}
    out = [await br.rab_vs_actual(org, pid, group_by) for pid in pids]
    return {"data": serialize_doc(out), "total": len(out)}


@router.get("/margin")
async def margin(project_id: str = None,
                 user: dict = Depends(require_permission("budget", "view"))):
    """Margin proyek + margin proyeksi. Kas masuk ditampilkan TERPISAH dari pendapatan."""
    org = user.get("org_id", ORG_ID)
    pids = await _resolve(user, project_id)
    if project_id:
        return {"data": serialize_doc(await br.margin(org, project_id))}
    return {"data": serialize_doc([await br.margin(org, pid) for pid in pids]),
            "total": len(pids)}


@router.get("/unmapped")
async def unmapped(project_id: str = None,
                   user: dict = Depends(require_permission("budget", "view"))):
    """Laporan 'biaya belum terpetakan' — alat merapikan sebelum enforce dinyalakan."""
    org = user.get("org_id", ORG_ID)
    pids = await _resolve(user, project_id)
    if project_id:
        return {"data": serialize_doc(await br.unmapped_costs(org, project_id))}
    if not pids:
        return {"data": serialize_doc(await br.unmapped_costs(org, None))}
    return {"data": serialize_doc(await br.unmapped_costs(org, None))}


@router.get("/health")
async def health(user: dict = Depends(require_permission("budget", "view"))):
    """Status kebijakan anggaran yang berlaku (untuk banner & tombol di layar).

    Hanya menyebut MENYALA/MATI dan angka ambang — tidak pernah membocorkan isi env.
    """
    org = user.get("org_id", ORG_ID)
    return {"data": {
        "enforce_cost_ref": bool(await cfg.get("budget.enforce_cost_ref", org_id=org)),
        "alert_pct": await cfg.get("budget.alert_pct", org_id=org),
        "default_target_method": await cfg.get("target.default_method", org_id=org),
        "config_link": "/config?group=anggaran",
    }}


@router.post("/alerts/scan")
async def scan_alerts(project_id: str = None, force: bool = False,
                      user: dict = Depends(require_permission("budget", "manage"))):
    """Jalankan pemeriksaan ambang anggaran sekarang (biasanya dijalankan penjadwal harian)."""
    org = user.get("org_id", ORG_ID)
    if project_id:
        await _resolve(user, project_id)
    out = await br.alert_scan(org, project_id=project_id, actor=user.get("email"), force=force)
    await audit_log(user, "scan", "budget_items", project_id, {"created": out["created"]})
    return {"data": serialize_doc(out)}
