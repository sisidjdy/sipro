"""Progress Claim (Termin) & Change Order (EPIC 2.3) — subcon.

Alur JUJUR & ber-SoD:
- **Progress Claim / Termin**: field (site/PM) MENGAJUKAN klaim progres kumulatif ->
  PM OPNAME (verifikasi %) -> finance/owner MENYETUJUI. Saat disetujui otomatis
  membuat & meng-approve tagihan AP subcon (retensi ditahan sesuai SPK) sehingga
  posting ke Buku Besar lewat engine AP yang sudah ada; progres SPK ikut diperbarui.
- **Change Order (Addendum)**: PM membuat CO (delta nilai/waktu) -> finance/owner
  MENYETUJUI -> nilai kontrak SPK di-update (tidak boleh < nilai yang sudah ditagih).

Semua uang IDR integer; read org-scoped + project-scoped untuk PM/site.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import docgen_p62 as p62
import opname as op
import sequences as seq
import subcon_finance as sf
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc
from rbac import has_role, require_permission, assert_project_access
from engine import add_activity, emit, dispatch_pending
import finance_engine as fe
from models import ProgressClaimCreate, StatusNote, ChangeOrderCreate
from models_p33 import ClaimOpnameIn

router = APIRouter(prefix="/subcon", tags=["subcon-claims"])

CLAIM_OPEN = ("submitted", "verified")
PROJECT_SCOPED = ("project_manager", "site_engineer")


SCOPE_BY_PREFIX = {"TRM": "claim", "CO": "change_order"}


async def _next_number(prefix: str, coll, org_id: str = None, context: dict = None) -> str:
    """Nomor atomik per org+tahun (lihat sequences.py)."""
    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),
                                 org_id or ORG_ID, prefix=prefix, context=context)


async def _get_spk(org: str, spk_id: str, user: dict) -> dict:
    spk = await db.spk.find_one({"id": spk_id, "org_id": org}, {"_id": 0})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan")
    await assert_project_access(spk["project_id"], user)
    return spk


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


# =============================== PROGRESS CLAIMS ===============================
@router.get("/claims")
async def list_claims(spk_id: str = None, status: str = None, project_id: str = None,
                      user: dict = Depends(require_permission("progress_claims", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if has_role(user, *PROJECT_SCOPED):
        from rbac import project_query
        projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
        q["project_id"] = {"$in": [p["id"] for p in projs]}
    if spk_id:
        q["spk_id"] = spk_id
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    rows = await db.progress_claims.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    summary = {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") in CLAIM_OPEN),
        "approved": sum(1 for r in rows if r.get("status") == "approved"),
        "approved_value": sum(int(r.get("gross", 0)) for r in rows if r.get("status") == "approved"),
        "retention_held": sum(int(r.get("retention_held", 0)) for r in rows if r.get("status") == "approved"),
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.post("/claims")
async def create_claim(payload: ProgressClaimCreate,
                       user: dict = Depends(require_permission("progress_claims", "create"))):
    org = user.get("org_id", ORG_ID)
    spk = await _get_spk(org, payload.spk_id, user)
    if spk.get("status") not in ("active", "draft"):
        raise HTTPException(status_code=400, detail="SPK harus berstatus draft/aktif untuk pengajuan termin.")
    if await db.progress_claims.count_documents({"org_id": org, "spk_id": spk["id"], "status": {"$in": list(CLAIM_OPEN)}}):
        raise HTTPException(status_code=400, detail="Masih ada termin yang belum diselesaikan untuk SPK ini.")
    if await db.spk_scope_items.count_documents({"org_id": org, "spk_id": spk["id"]}):
        return await _create_item_claim(org, spk, payload, user)
    if payload.progress_pct is None:
        raise HTTPException(status_code=400, detail=(
            "SPK ini belum punya lingkup item pekerjaan. Isi lingkup dulu (tab Lingkup & "
            "Opname) agar nilai termin lahir dari pekerjaan terverifikasi, atau kirim "
            "persen kumulatif untuk SPK borongan lump-sum."))
    prev = int(spk.get("progress_pct", 0) or 0)
    claimed = int(payload.progress_pct)
    if claimed <= prev or claimed > 100:
        raise HTTPException(status_code=400, detail=f"Progres kumulatif harus di antara {prev + 1}%–100%.")
    if spk.get("spk_kind") == "fasum":  # Fase 81: termin fasum mengikuti progres fase konstruksi
        import rab_engine as re_
        try:
            re_.assert_fasum_claim_within_phase(await re_.fasum_phase_cap(org, spk), claimed)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    cv = int(spk.get("contract_value", 0) or 0)
    gross_est = round((claimed - prev) / 100 * cv)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "claim_number": await _next_number(
            "TRM", db.progress_claims, org, {"project_id": spk.get("project_id"), "subcon_id": spk.get("subcontractor_id")}),
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "subcontractor_id": spk.get("subcontractor_id"), "subcontractor_name": spk.get("subcontractor_name"),
        "project_id": spk["project_id"], "project_name": spk.get("project_name"),
        "period": payload.period or f"Termin s/d {claimed}%",
        "basis": "lumpsum", "lines": [], "scope_value": 0,
        "prev_pct": prev, "claimed_pct": claimed, "verified_pct": None,
        "effective_pct": None, "contract_value_at_submit": cv,
        "gross_est": int(gross_est), "gross": 0, "retention_pct": float(spk.get("retention_pct", 0) or 0),
        "retention_held": 0, "net": 0, "ap_bill_id": None, "due_date": payload.due_date,
        "status": "submitted", "note": payload.note,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.progress_claims.insert_one(dict(doc))
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=f"Termin {doc['claim_number']} SPK {spk.get('spk_number')} diajukan "
                            f"({prev}%→{claimed}%, est {_rp(gross_est)}).",
                       actor=user.get("email"), org_id=org)
    await emit("progress_claim.submitted", "progress_claim", doc["id"],
               {"label": f"{doc['claim_number']} · {spk.get('spk_number')}"}, org_id=org)
    await dispatch_pending()
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _create_item_claim(org: str, spk: dict, payload: ProgressClaimCreate,
                             user: dict) -> dict:
    """Termin BERBASIS BUKTI: nilai dihitung sistem dari pekerjaan terverifikasi.

    Tidak ada kolom persen yang bisa diketik: baris termin = item jadwal yang sudah
    diverifikasi supervisor (foto + checklist) dan belum pernah ditagih (INV-33-1/2).
    """
    view = await op.opname_preview(org, spk)
    lines = op.claim_lines(view["lines"])
    if not lines:
        why = "; ".join(f"{b['items']} pekerjaan {str(b['label']).lower()} ({op.rp(b['value'])})"
                        for b in view["blockers"]) or "lingkup SPK masih kosong"
        raise HTTPException(status_code=400, detail=(
            "Belum ada pekerjaan terverifikasi yang bisa ditagih pada SPK ini — " + why +
            ". Pekerjaan harus diajukan pelaksana lalu DIVERIFIKASI supervisor dulu."))
    s = view["summary"]
    gross = sum(int(ln["value"]) for ln in lines)
    cv = int(spk.get("contract_value", 0) or 0)
    if cv and s["billed_value"] + gross > cv:
        raise HTTPException(status_code=400, detail=(
            f"Total tagihan {_rp(s['billed_value'] + gross)} melebihi nilai kontrak "
            f"{_rp(cv)}. Sahkan tambahan pekerjaan lewat Change Order dulu."))
    scope_value = s["scope_value"] or 1
    prev_pct = int(round(s["billed_value"] / scope_value * 100))
    claimed_pct = int(round((s["billed_value"] + gross) / scope_value * 100))
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "claim_number": await _next_number("TRM", db.progress_claims, org),
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "subcontractor_id": spk.get("subcontractor_id"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "project_id": spk["project_id"], "project_name": spk.get("project_name"),
        "period": payload.period or f"Termin {len(lines)} pekerjaan terverifikasi",
        "basis": "items", "lines": lines, "scope_value": s["scope_value"],
        "prev_pct": prev_pct, "claimed_pct": claimed_pct, "verified_pct": None,
        "effective_pct": None, "contract_value_at_submit": cv,
        "gross_est": gross, "gross": 0,
        "retention_pct": float(spk.get("retention_pct", 0) or 0),
        "retention_held": 0, "net": 0, "ap_bill_id": None, "due_date": payload.due_date,
        "status": "submitted", "note": payload.note,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.progress_claims.insert_one(dict(doc))
    await op.hold_lines(org, doc["id"], lines)
    await op.sync_spk(org, spk["id"])
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=(f"Termin {doc['claim_number']} SPK {spk.get('spk_number')} diajukan "
                             f"atas {len(lines)} pekerjaan TERVERIFIKASI ({_rp(gross)}). "
                             "Nilai dihitung dari item jadwal, bukan persen manual."),
                       actor=user.get("email"), org_id=org)
    await emit("progress_claim.submitted", "progress_claim", doc["id"],
               {"label": f"{doc['claim_number']} · {spk.get('spk_number')}"}, org_id=org)
    await dispatch_pending()
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _get_claim(org: str, cid: str, user: dict) -> dict:
    claim = await db.progress_claims.find_one({"id": cid, "org_id": org}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Termin tidak ditemukan")
    await assert_project_access(claim["project_id"], user)
    return claim


@router.get("/claims/{cid}")
async def get_claim(cid: str, user: dict = Depends(require_permission("progress_claims", "view"))):
    return {"data": serialize_doc(await _get_claim(user.get("org_id", ORG_ID), cid, user))}


@router.get("/claims/{cid}/pdf")
async def claim_pdf(cid: str,
                    user: dict = Depends(require_permission("progress_claims", "view"))):
    """Cetak BERITA ACARA OPNAME berkop (Fase 62) — ditandatangani di lapangan."""
    org = user.get("org_id", ORG_ID)
    claim = await _get_claim(org, cid, user)
    spk = await db.spk.find_one({"id": claim["spk_id"], "org_id": org}, {"_id": 0}) or {}
    pdf = await p62.ba_pdf(org, claim, spk,
                           {"name": user.get("name"), "role": user.get("role")})
    nama = str(claim.get("claim_number") or "berita-acara-opname").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nama}.pdf"'})


@router.post("/claims/{cid}/verify")
async def verify_claim(cid: str, payload: ClaimOpnameIn,
                       user: dict = Depends(require_permission("progress_claims", "update"))):
    org = user.get("org_id", ORG_ID)
    claim = await _get_claim(org, cid, user)
    if claim.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Hanya termin berstatus 'diajukan' yang bisa di-opname.")
    # INV-33-7 pemisahan tugas: pengaju tidak boleh meng-opname pengajuannya sendiri.
    if claim.get("created_by") == user.get("email") and not has_role(user, "owner", "super_admin"):
        raise HTTPException(status_code=403, detail=(
            "Termin ini Anda sendiri yang mengajukan. Opname harus dilakukan orang lain "
            "(Manajer Proyek) agar pemeriksaan tetap independen."))
    if claim.get("basis") == "items":
        return await _opname_item_claim(org, claim, payload, user)
    if payload.verified_pct is None:
        raise HTTPException(status_code=400, detail="Isi hasil opname (persen kumulatif).")
    vp = int(payload.verified_pct)
    prev = int(claim.get("prev_pct", 0))
    if vp <= prev or vp > int(claim.get("claimed_pct", 100)):
        raise HTTPException(status_code=400,
                            detail=f"Hasil opname harus di antara {prev + 1}%–{claim.get('claimed_pct')}%.")
    cv = int(claim.get("contract_value_at_submit", 0))
    gross_est = round((vp - prev) / 100 * cv)
    ts = now_iso()
    setter = {"verified_pct": vp, "gross_est": int(gross_est), "status": "verified", "updated_at": ts,
              "verified_by": user.get("email"), "verified_at": ts}
    if payload.note:
        setter["note"] = ((claim.get("note") or "") + f"\n[opname {ts[:10]}] {payload.note}").strip()
    await db.progress_claims.update_one({"id": cid, "org_id": org}, {"$set": setter})
    return {"data": serialize_doc(await db.progress_claims.find_one({"id": cid}, {"_id": 0}))}


async def _opname_item_claim(org: str, claim: dict, payload: ClaimOpnameIn,
                             user: dict) -> dict:
    """Opname per baris: hanya boleh MENGURANGI (INV-33-6) dan wajib beralasan."""
    lines = claim.get("lines") or []
    known = {ln["scope_item_id"] for ln in lines}
    drop = [x for x in (payload.exclude or [])]
    unknown = [x for x in drop if x not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=(
            "Opname hanya boleh MENGURANGI baris yang diajukan — tidak bisa menambah "
            "pekerjaan baru ke termin yang sudah masuk. Ajukan termin berikutnya untuk "
            "pekerjaan lain yang sudah terverifikasi."))
    reason = (payload.reason or "").strip()
    if drop and len(reason) < 5:
        raise HTTPException(status_code=400, detail=(
            "Sebutkan alasan pengurangan (mis. \"volume plester kurang 4 m2\") supaya "
            "subkontraktor tahu apa yang harus diperbaiki."))
    dropset = set(drop)
    new_lines = [{**ln, "included": ln["scope_item_id"] not in dropset,
                  "exclude_reason": reason if ln["scope_item_id"] in dropset else None}
                 for ln in lines]
    gross = sum(int(ln["value"]) for ln in new_lines if ln["included"])
    if gross <= 0:
        raise HTTPException(status_code=400, detail=(
            "Semua baris dikeluarkan sehingga nilai termin menjadi nol — TOLAK termin ini "
            "agar riwayatnya jujur, jangan disetujui dengan nilai nol."))
    scope_value = int(claim.get("scope_value") or 0) or 1
    billed = int(round(int(claim.get("prev_pct", 0)) / 100 * scope_value))
    ts = now_iso()
    setter = {
        "lines": new_lines, "gross_est": gross, "status": "verified",
        "verified_pct": int(round((billed + gross) / scope_value * 100)),
        "excluded_items": len(dropset), "excluded_value": sum(
            int(ln["value"]) for ln in new_lines if not ln["included"]),
        "opname_reason": reason or None,
        "verified_by": user.get("email"), "verified_at": ts, "updated_at": ts,
    }
    if payload.note or reason:
        setter["note"] = ((claim.get("note") or "") +
                          f"\n[opname {ts[:10]}] {payload.note or reason}").strip()
    await db.progress_claims.update_one({"id": claim["id"], "org_id": org}, {"$set": setter})
    if dropset:
        await add_activity(entity_type="project", entity_id=claim["project_id"], type="system",
                           body=(f"Opname termin {claim.get('claim_number')}: {len(dropset)} "
                                 f"pekerjaan dikeluarkan ({_rp(setter['excluded_value'])}) — "
                                 f"alasan: {reason}"),
                           actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.progress_claims.find_one({"id": claim["id"]}, {"_id": 0}))}


@router.post("/claims/{cid}/approve")
async def approve_claim(cid: str,
                        user: dict = Depends(require_permission("progress_claims", "approve"))):
    org = user.get("org_id", ORG_ID)
    claim = await _get_claim(org, cid, user)
    if claim.get("status") not in CLAIM_OPEN:
        raise HTTPException(status_code=400, detail="Termin ini tidak dalam status yang bisa disetujui.")
    spk = await db.spk.find_one({"id": claim["spk_id"], "org_id": org}, {"_id": 0})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan")
    if claim.get("basis") == "items":
        return await _approve_item_claim(org, claim, spk, user)
    prev = int(spk.get("progress_pct", 0) or 0)
    eff = int(claim.get("verified_pct") or claim.get("claimed_pct"))
    if eff <= prev:
        raise HTTPException(status_code=400,
                            detail=f"Progres SPK sudah {prev}%; termin ini tidak menambah progres.")
    cv = int(spk.get("contract_value", 0) or 0)
    gross = round((eff - prev) / 100 * cv)
    note = f"Termin {claim.get('claim_number')} SPK {spk.get('spk_number')} ({prev}%→{eff}%)"
    bill = await fe.create_ap_bill(spk.get("subcontractor_name"), spk["project_id"], int(gross),
                                   spk.get("retention_pct", 0), claim.get("due_date"), note,
                                   user.get("email"), org)
    # Fase 48C: potongan (angsuran uang muka, denda, bon material) ditempelkan SEBELUM
    # persetujuan supaya jurnal seimbang & pembayaran tidak pernah minus.
    try:
        bill = await sf.attach_deductions(org, bill, spk, claim, user.get("email"))
    except ValueError as e:
        await db.ap_invoices.delete_one({"id": bill["id"], "org_id": org})
        raise HTTPException(status_code=400, detail=str(e))
    bill = await fe.approve_ap_bill(bill["id"], user.get("email"), org)  # post ke GL
    await sf.register_retention(org, spk, {**claim, "approved_at": now_iso()}, bill,
                                user.get("email"))
    ts = now_iso()
    await db.progress_claims.update_one({"id": cid, "org_id": org}, {"$set": {
        "status": "approved", "effective_pct": eff, "gross": int(gross),
        "retention_held": int(bill.get("retention_held", 0)), "net": int(bill.get("net", 0)),
        "deduction_total": int(bill.get("deduction_total", 0)),
        "deductions": bill.get("deductions") or [],
        "ap_bill_id": bill["id"], "approved_by": user.get("email"), "approved_at": ts, "updated_at": ts,
    }})
    await db.spk.update_one({"id": spk["id"], "org_id": org}, {"$set": {"progress_pct": eff, "updated_at": ts}})
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=f"Termin {claim.get('claim_number')} disetujui: tagihan AP {_rp(gross)} "
                            f"(retensi {_rp(bill.get('retention_held', 0))}). Progres SPK → {eff}%.",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.progress_claims.find_one({"id": cid}, {"_id": 0}))}


async def _approve_item_claim(org: str, claim: dict, spk: dict, user: dict) -> dict:
    """Persetujuan uang: baris divalidasi ULANG sebelum tagihan AP dibuat."""
    problems = await op.revalidate(org, claim)
    if problems:
        raise HTTPException(status_code=400, detail=(
            "Termin tidak bisa disetujui karena kondisi pekerjaan berubah setelah diajukan:\n- "
            + "\n- ".join(problems)))
    included = [ln for ln in (claim.get("lines") or []) if ln.get("included")]
    gross = sum(int(ln["value"]) for ln in included)
    if gross <= 0:
        raise HTTPException(status_code=400, detail="Tidak ada baris yang lolos opname.")
    s = op.summarize(await op.scope_rows(org, spk["id"]))
    cv = int(spk.get("contract_value", 0) or 0)
    if cv and s["billed_value"] + gross > cv:
        raise HTTPException(status_code=400, detail=(
            f"Total tagihan {_rp(s['billed_value'] + gross)} melebihi nilai kontrak {_rp(cv)}."))
    note = (f"Termin {claim.get('claim_number')} SPK {spk.get('spk_number')} — "
            f"{len(included)} pekerjaan terverifikasi")
    bill = await fe.create_ap_bill(spk.get("subcontractor_name"), spk["project_id"], int(gross),
                                   spk.get("retention_pct", 0), claim.get("due_date"), note,
                                   user.get("email"), org)
    try:
        bill = await sf.attach_deductions(org, bill, spk, claim, user.get("email"))
    except ValueError as e:
        await db.ap_invoices.delete_one({"id": bill["id"], "org_id": org})
        raise HTTPException(status_code=400, detail=str(e))
    bill = await fe.approve_ap_bill(bill["id"], user.get("email"), org)  # post ke GL
    await sf.register_retention(org, spk, {**claim, "approved_at": now_iso()}, bill,
                                user.get("email"))
    scope_value = int(claim.get("scope_value") or 0) or 1
    eff = int(round((s["billed_value"] + gross) / scope_value * 100))
    ts = now_iso()
    await db.progress_claims.update_one({"id": claim["id"], "org_id": org}, {"$set": {
        "status": "approved", "effective_pct": eff, "gross": int(gross),
        "retention_held": int(bill.get("retention_held", 0)), "net": int(bill.get("net", 0)),
        "deduction_total": int(bill.get("deduction_total", 0)),
        "deductions": bill.get("deductions") or [],
        "ap_bill_id": bill["id"], "approved_by": user.get("email"), "approved_at": ts,
        "updated_at": ts,
    }})
    fresh = await db.progress_claims.find_one({"id": claim["id"], "org_id": org}, {"_id": 0})
    await op.settle_lines(org, fresh)   # ledger anti bayar ganda + progres SPK dihitung ulang
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=(f"Termin {claim.get('claim_number')} disetujui: tagihan AP "
                             f"{_rp(gross)} (retensi {_rp(bill.get('retention_held', 0))}) atas "
                             f"{len(included)} pekerjaan terverifikasi. Pekerjaan itu ditandai "
                             "SUDAH DIBAYAR sehingga tidak bisa ditagih dua kali."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.progress_claims.find_one({"id": claim["id"]}, {"_id": 0}))}


@router.post("/claims/{cid}/reject")
async def reject_claim(cid: str, payload: StatusNote,
                       user: dict = Depends(require_permission("progress_claims", "approve"))):
    org = user.get("org_id", ORG_ID)
    claim = await _get_claim(org, cid, user)
    if claim.get("status") not in CLAIM_OPEN:
        raise HTTPException(status_code=400, detail="Termin ini tidak dalam status yang bisa ditolak.")
    ts = now_iso()
    setter = {"status": "rejected", "rejected_by": user.get("email"), "rejected_at": ts, "updated_at": ts}
    if payload.note:
        setter["note"] = ((claim.get("note") or "") + f"\n[tolak {ts[:10]}] {payload.note}").strip()
    await db.progress_claims.update_one({"id": cid, "org_id": org}, {"$set": setter})
    if claim.get("basis") == "items":
        # Pekerjaan kembali ke daftar "siap ditagih" — tidak hangus karena termin ditolak.
        await op.release_lines(org, claim)
    return {"data": serialize_doc(await db.progress_claims.find_one({"id": cid}, {"_id": 0}))}


# =============================== CHANGE ORDERS ===============================
@router.get("/change-orders")
async def list_change_orders(spk_id: str = None, status: str = None,
                             user: dict = Depends(require_permission("change_orders", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if spk_id:
        q["spk_id"] = spk_id
    if status:
        q["status"] = status
    rows = await db.change_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/change-orders")
async def create_change_order(payload: ChangeOrderCreate,
                              user: dict = Depends(require_permission("change_orders", "create"))):
    org = user.get("org_id", ORG_ID)
    spk = await _get_spk(org, payload.spk_id, user)
    if int(payload.value_delta) == 0 and not int(payload.time_extension_days or 0):
        raise HTTPException(status_code=400, detail="Change Order harus mengubah nilai atau menambah waktu.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "co_number": await _next_number(
            "CO", db.change_orders, org, {"project_id": spk.get("project_id"), "subcon_id": spk.get("subcontractor_id")}),
        "spk_id": spk["id"], "spk_number": spk.get("spk_number"),
        "subcontractor_name": spk.get("subcontractor_name"),
        "project_id": spk["project_id"], "project_name": spk.get("project_name"),
        "title": payload.title, "description": payload.description,
        "value_delta": int(payload.value_delta), "time_extension_days": int(payload.time_extension_days or 0),
        "reason": payload.reason, "original_value": int(spk.get("contract_value", 0) or 0),
        "new_value": None, "status": "draft",
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.change_orders.insert_one(dict(doc))
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=f"Change Order {doc['co_number']} SPK {spk.get('spk_number')} dibuat "
                            f"(Δ {_rp(payload.value_delta)}).",
                       actor=user.get("email"), org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _get_co(org: str, coid: str, user: dict) -> dict:
    co = await db.change_orders.find_one({"id": coid, "org_id": org}, {"_id": 0})
    if not co:
        raise HTTPException(status_code=404, detail="Change Order tidak ditemukan")
    await assert_project_access(co["project_id"], user)
    return co


@router.post("/change-orders/{coid}/approve")
async def approve_change_order(coid: str,
                               user: dict = Depends(require_permission("change_orders", "approve"))):
    org = user.get("org_id", ORG_ID)
    co = await _get_co(org, coid, user)
    if co.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Hanya Change Order draft yang bisa disetujui.")
    spk = await db.spk.find_one({"id": co["spk_id"], "org_id": org}, {"_id": 0})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan")
    old = int(spk.get("contract_value", 0) or 0)
    new = old + int(co.get("value_delta", 0))
    if new <= 0:
        raise HTTPException(status_code=400, detail="Nilai kontrak baru harus lebih dari 0.")
    billed = round(int(spk.get("progress_pct", 0) or 0) / 100 * old)
    if new < billed:
        raise HTTPException(status_code=400,
                            detail=f"Nilai kontrak baru ({_rp(new)}) tidak boleh di bawah nilai tertagih ({_rp(billed)}).")
    ts = now_iso()
    spk_set = {"contract_value": new, "updated_at": ts}
    ext = int(co.get("time_extension_days", 0) or 0)
    await db.change_orders.update_one({"id": coid, "org_id": org}, {"$set": {
        "status": "approved", "original_value": old, "new_value": new,
        "approved_by": user.get("email"), "approved_at": ts, "updated_at": ts,
    }})
    await db.spk.update_one({"id": spk["id"], "org_id": org}, {"$set": spk_set})
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=f"Change Order {co.get('co_number')} disetujui: nilai kontrak {_rp(old)} → {_rp(new)}"
                            + (f" (+{ext} hari)." if ext else "."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.change_orders.find_one({"id": coid}, {"_id": 0}))}


@router.post("/change-orders/{coid}/reject")
async def reject_change_order(coid: str, payload: StatusNote,
                              user: dict = Depends(require_permission("change_orders", "approve"))):
    org = user.get("org_id", ORG_ID)
    co = await _get_co(org, coid, user)
    if co.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Hanya Change Order draft yang bisa ditolak.")
    ts = now_iso()
    setter = {"status": "rejected", "rejected_by": user.get("email"), "rejected_at": ts, "updated_at": ts}
    if payload.note:
        setter["reason"] = ((co.get("reason") or "") + f"\n[tolak {ts[:10]}] {payload.note}").strip()
    await db.change_orders.update_one({"id": coid, "org_id": org}, {"$set": setter})
    return {"data": serialize_doc(await db.change_orders.find_one({"id": coid}, {"_id": 0}))}
