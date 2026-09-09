"""Target proyek (Fase 45) — `docs/v2/32` §2. Endpoint tipis: semua hitungan di engine.

Keputusan yang tercermin di kode ini:
  1. **Router tidak menghitung apa pun.** Aritmatika target ada di `target_engine` (fungsi
     murni) dan lapisan datanya di `target_store`. Kalau router ikut menghitung, angka di
     layar target bisa berbeda dengan angka penyesuaian otomatis.
  2. **Realisasi tidak bisa diinput.** Tidak ada satu pun endpoint yang menerima `unit_actual`
     — realisasi selalu dibaca dari `deals` (sumber yang sama dengan metrik SLS-01/03).
  3. **Hitung ulang wajib beralasan.** `POST /{id}/recalc` menolak tanpa `reason`, dan
     alasannya masuk `history[]` bersama daftar periode yang berubah.
  4. Urutan rute: path statis (`/methods`, `/preview`) DIDAFTARKAN SEBELUM `/{tid}`
     (pelajaran `verify_api_contract`: kalau tidak, `/methods` terbaca sebagai id target).
"""
import reference as ref
import target_engine as te
import target_store as tstore
from core_utils import now_iso, serialize_doc
from db import ORG_ID, db
from fastapi import APIRouter, Depends, HTTPException
from models_p45 import (TargetCreate, TargetPreview, TargetRecalc, TargetStatusChange,
                        TargetUpdate)
from rbac import (is_scoped_sales, assert_project_access, audit_log, project_query,
                 require_permission)

router = APIRouter(prefix="/targets", tags=["targets"])


def _own_scope(user: dict) -> str:
    """Email pemilik bila peran hanya boleh melihat miliknya sendiri (sales)."""
    return user.get("email") if is_scoped_sales(user) else None


async def _accessible_projects(user: dict) -> dict:
    rows = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}) \
        .to_list(500)
    return {p["id"]: p.get("name") for p in rows}


async def _get(tid: str, user: dict) -> dict:
    doc = await db.project_targets.find_one({"id": tid, "org_id": user.get("org_id", ORG_ID)},
                                           {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Target tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    scoped = _own_scope(user)
    if scoped and doc.get("owner_email") != scoped:
        raise HTTPException(status_code=403,
                            detail="Akses ditolak: Anda hanya boleh melihat target milik Anda.")
    return doc


# ------------------------------------------------------------------ statis (sebelum /{tid})
@router.get("/methods")
async def methods(user: dict = Depends(require_permission("targets", "view"))):
    """Kamus metode target: nilai, label (SSOT), dan RUMUS yang benar-benar dijalankan.

    Rumus dikirim dari backend supaya penjelasan di layar tidak bisa berbeda dengan mesinnya.
    """
    options = (ref.GROUPS["target_method"]["options"])
    return {"data": [{**o, "formula": te.METHOD_FORMULA.get(o["value"]),
                      "needs": _method_needs(o["value"])} for o in options]}


def _method_needs(method: str) -> list:
    return {
        "linear_remaining": ["total target unit", "horizon bulan"],
        "s_curve": ["bobot per bulan (Σ 100%)"],
        "manual": ["angka rencana tiap bulan"],
        "velocity_forecast": ["riwayat realisasi 3 bulan terakhir", "asumsi pertumbuhan"],
        "revenue_first": ["target pendapatan", "harga rata-rata unit"],
    }.get(method, [])


@router.post("/preview")
async def preview(payload: TargetPreview,
                  user: dict = Depends(require_permission("targets", "view"))):
    """PRATINJAU DAMPAK sebelum menyimpan (DoD #1 `docs/v2/32` §6).

    Mengubah metode target mengubah rencana seluruh bulan berikutnya. Menyimpan dulu lalu
    melihat hasilnya berarti pemakai sudah mengubah rencana resmi sebelum tahu akibatnya.
    """
    org = user.get("org_id", ORG_ID)
    body = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    body.pop("target_id", None)
    if payload.target_id:
        base = await _get(payload.target_id, user)
    else:
        if not payload.project_id:
            raise HTTPException(status_code=400,
                                detail="Sertakan `target_id` (untuk melihat dampak perubahan) "
                                       "atau `project_id` (untuk rancangan target baru).")
        await assert_project_access(payload.project_id, user)
        base = {"project_id": payload.project_id, "method": "linear_remaining",
                "horizon": {}, "unit_target": 0, "revenue_target": 0, "periods": [],
                "recalc_policy": {"mode": "monthly", "keep_total": True, "lock_past": True},
                "assumptions": {}}
    return {"data": serialize_doc(await tstore.preview(org, base, overrides=body))}


@router.get("")
async def list_targets(project_id: str = None, status: str = None,
                       user: dict = Depends(require_permission("targets", "view"))):
    """Daftar target. Tanpa `project_id` = seluruh proyek yang boleh diakses pemakai."""
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_projects(user)
    q = {"org_id": org, "project_id": {"$in": list(pmap.keys())}}
    if project_id:
        if project_id not in pmap:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk proyek ini")
        q["project_id"] = project_id
    if status:
        q["status"] = {"$in": [s.strip() for s in status.split(",") if s.strip()]}
    scoped = _own_scope(user)
    if scoped:
        q["owner_email"] = scoped
    rows = await db.project_targets.find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"))
    return {"data": serialize_doc(rows), "total": len(rows), "scoped_to": scoped}


@router.post("")
async def create_target(payload: TargetCreate,
                        user: dict = Depends(require_permission("targets", "create"))):
    org = user.get("org_id", ORG_ID)
    await assert_project_access(payload.project_id, user)
    body = payload.dict()
    body["horizon"] = dict(body["horizon"])
    if body.get("scope") == "cluster" and not body.get("cluster_id"):
        raise HTTPException(status_code=400,
                            detail="Cakupan cluster wajib menyebut cluster-nya.")
    if body.get("scope") == "sales" and not body.get("owner_email"):
        raise HTTPException(status_code=400,
                            detail="Cakupan sales wajib menyebut email sales-nya.")
    if body.get("cluster_id") or body.get("owner_email"):
        await _assert_child_fits(org, body)
    doc = await tstore.create_target(org, body, actor=user.get("email"))
    await audit_log(user, "create", "project_targets", doc["id"],
                    {"method": doc["method"], "unit_target": doc["unit_target"]})
    return {"data": serialize_doc(doc)}


async def _assert_child_fits(org: str, body: dict, target_id: str = None):
    """Total target anak (cluster/sales) tidak boleh melewati target induk proyek (§2.1)."""
    parent = await db.project_targets.find_one(
        {"org_id": org, "project_id": body["project_id"], "cluster_id": None,
         "owner_email": None, "status": {"$ne": "closed"}}, {"_id": 0, "unit_target": 1})
    if not parent:
        return
    children = await db.project_targets.find(
        {"org_id": org, "project_id": body["project_id"], "status": {"$ne": "closed"},
         "id": {"$ne": target_id},
         "$or": [{"cluster_id": {"$ne": None}}, {"owner_email": {"$ne": None}}]},
        {"_id": 0, "unit_target": 1}).to_list(200)
    problems = te.validate_scope(parent.get("unit_target") or 0,
                                 children + [{"unit_target": body.get("unit_target") or 0}])
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))


# ------------------------------------------------------------------ per target
@router.get("/{tid}")
async def get_target(tid: str, user: dict = Depends(require_permission("targets", "view"))):
    """Detail target + periode + realisasi terkini (dihitung ulang, bukan angka basi)."""
    doc = await _get(tid, user)
    prog = await tstore.progress(user.get("org_id", ORG_ID), doc)
    return {"data": serialize_doc({**doc, "progress": prog})}


@router.get("/{tid}/progress")
async def target_progress(tid: str,
                          user: dict = Depends(require_permission("targets", "view"))):
    """Target vs realisasi per periode + proyeksi selesai terjual."""
    doc = await _get(tid, user)
    return {"data": serialize_doc(await tstore.progress(user.get("org_id", ORG_ID), doc))}


@router.put("/{tid}")
async def update_target(tid: str, payload: TargetUpdate,
                        user: dict = Depends(require_permission("targets", "update"))):
    org = user.get("org_id", ORG_ID)
    doc = await _get(tid, user)
    if doc.get("status") == "closed":
        raise HTTPException(status_code=400, detail=(
            "Target yang sudah DITUTUP tidak bisa diubah — laporan historis mengacu padanya. "
            "Buat target baru bila rencananya berubah."))
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    reason = upd.pop("reason", None)
    if "horizon" in upd:
        upd["horizon"] = dict(upd["horizon"])
    if "assumptions" in upd:
        upd["assumptions"] = dict(upd["assumptions"])
    if "recalc_policy" in upd:
        upd["recalc_policy"] = dict(upd["recalc_policy"])
    if not upd:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan yang dikirim.")
    if doc.get("cluster_id") or doc.get("owner_email"):
        await _assert_child_fits(org, {**doc, **upd}, target_id=tid)
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user.get("email")
    await db.project_targets.update_one({"id": tid, "org_id": org}, {"$set": upd})
    out = await tstore.recalc_target(
        org, tid, actor=user.get("email"),
        reason=reason or "Target diubah (" + ", ".join(sorted(upd.keys())) + ")")
    await audit_log(user, "update", "project_targets", tid, {"fields": sorted(upd.keys())})
    return {"data": serialize_doc({**await _get(tid, user), "recalc": out})}


@router.post("/{tid}/recalc")
async def recalc(tid: str, payload: TargetRecalc,
                 user: dict = Depends(require_permission("targets", "update"))):
    """Hitung ulang manual — WAJIB beralasan (jejak tanpa alasan sama dengan tanpa jejak)."""
    org = user.get("org_id", ORG_ID)
    await _get(tid, user)
    out = await tstore.recalc_target(org, tid, reason=payload.reason,
                                     actor=user.get("email"), today=payload.today)
    await audit_log(user, "recalc", "project_targets", tid,
                    {"reason": payload.reason, "changed": len(out.get("changes") or [])})
    return {"data": serialize_doc(out)}


@router.post("/{tid}/activate")
async def activate(tid: str, payload: TargetStatusChange,
                   user: dict = Depends(require_permission("targets", "manage"))):
    """Aktifkan target. Satu proyek hanya boleh punya SATU target induk aktif."""
    org = user.get("org_id", ORG_ID)
    doc = await _get(tid, user)
    if doc.get("missing"):
        raise HTTPException(status_code=400, detail=(
            "Target belum bisa diaktifkan karena rencananya belum bisa dihitung: "
            + "; ".join(doc["missing"])))
    if not doc.get("cluster_id") and not doc.get("owner_email"):
        other = await db.project_targets.find_one(
            {"org_id": org, "project_id": doc["project_id"], "status": "active",
             "cluster_id": None, "owner_email": None, "id": {"$ne": tid}},
            {"_id": 0, "name": 1})
        if other:
            raise HTTPException(status_code=400, detail=(
                f"Proyek ini sudah punya target induk aktif: '{other.get('name')}'. "
                "Tutup target itu dulu supaya tidak ada dua target resmi yang berbeda."))
    await db.project_targets.update_one(
        {"id": tid, "org_id": org},
        {"$set": {"status": "active", "activated_at": now_iso(),
                  "activated_by": user.get("email"), "updated_at": now_iso()},
         "$push": {"history": {"at": now_iso(), "by": user.get("email"),
                               "method": doc.get("method"),
                               "reason": payload.reason or "Target diaktifkan",
                               "changes": [], "changed_periods": 0}}})
    await audit_log(user, "activate", "project_targets", tid, {"reason": payload.reason})
    return {"data": serialize_doc(await _get(tid, user))}


@router.post("/{tid}/close")
async def close(tid: str, payload: TargetStatusChange,
                user: dict = Depends(require_permission("targets", "manage"))):
    org = user.get("org_id", ORG_ID)
    doc = await _get(tid, user)
    await db.project_targets.update_one(
        {"id": tid, "org_id": org},
        {"$set": {"status": "closed", "closed_at": now_iso(),
                  "closed_by": user.get("email"), "updated_at": now_iso()},
         "$push": {"history": {"at": now_iso(), "by": user.get("email"),
                               "method": doc.get("method"),
                               "reason": payload.reason or "Target ditutup",
                               "changes": [], "changed_periods": 0}}})
    await audit_log(user, "close", "project_targets", tid, {"reason": payload.reason})
    return {"data": serialize_doc(await _get(tid, user))}
