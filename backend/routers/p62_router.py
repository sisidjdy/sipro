"""ROUTER FASE 62 — surat peringatan tunggakan & pengiriman dokumen ke pihak luar.

Prefix `/docs` (bukan `/documents`, yang sudah dipakai generator dokumen legal pembeli).

Pemisahan tugas yang dipaksakan di sini:
  * **melihat kandidat & riwayat surat peringatan** = `late_fee:view` (sales ber-scope hanya
    transaksinya sendiri, dipaksa SERVER);
  * **menerbitkan surat peringatan** = `late_fee:create` (Keuangan yang menagih) — surat ini
    MEMPERINGATKAN, tidak membatalkan apa pun;
  * **membagikan dokumen ke pihak luar** = izin atas dokumennya sendiri
    (`doc_share.PERMISSION`), karena mengirim SPK ke subkontraktor sama beratnya dengan
    mengubahnya.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

import doc_share as ds
import docgen_p62 as p62
import warning_letters as wl
from core_utils import serialize_doc
from db import ORG_ID, ORG_NAME, db
from models_p62 import DocShareIn, WarningLetterIn
from rbac import audit_log, can, is_scoped_sales, require_permission
from security import get_current_user

router = APIRouter(prefix="/docs", tags=["docs-p62"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _assert_own_deal(user: dict, deal_id: str) -> None:
    """Sales ber-scope hanya boleh menyentuh transaksinya sendiri (dipaksa server)."""
    if not is_scoped_sales(user):
        return
    inv = await db.ar_invoices.find_one(
        {"org_id": _org(user), "deal_id": deal_id}, {"_id": 0, "assigned_to": 1}) or {}
    if inv.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403,
                            detail="Transaksi ini bukan milik Anda.")


# ======================================================== surat peringatan tunggakan
@router.get("/warning-letters")
async def list_letters(deal_id: str = Query(None),
                       user: dict = Depends(require_permission("late_fee", "view"))):
    if deal_id:
        await _assert_own_deal(user, deal_id)
    return {"data": serialize_doc(await wl.letters(_org(user), deal_id=deal_id))}


@router.get("/warning-letters/state")
async def letter_state(deal_id: str = Query(...),
                       user: dict = Depends(require_permission("late_fee", "view"))):
    """Keadaan tunggakan satu transaksi + tingkat yang boleh diterbitkan berikutnya."""
    await _assert_own_deal(user, deal_id)
    return {"data": serialize_doc(await wl.snapshot(_org(user), deal_id))}


@router.post("/warning-letters")
async def issue_letter(payload: WarningLetterIn,
                       user: dict = Depends(require_permission("late_fee", "create"))):
    await _assert_own_deal(user, payload.deal_id)
    try:
        doc = await wl.issue(_org(user), payload.deal_id, payload.level,
                             user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc.get("duplicate"):
        await audit_log(user, "create", "late_fee", doc["id"],
                        {"warning_letter": doc["number"], "level": doc["level"]})
    return {"data": serialize_doc(doc)}


@router.get("/warning-letters/{lid}/pdf")
async def letter_pdf(lid: str, user: dict = Depends(require_permission("late_fee", "view"))):
    letter = await wl.get(_org(user), lid)
    if not letter:
        raise HTTPException(status_code=404, detail="Surat peringatan tidak ditemukan")
    await _assert_own_deal(user, letter["deal_id"])
    pdf = await p62.sp_pdf(_org(user), letter,
                           {"name": user.get("name"), "role": user.get("role")})
    nama = str(letter.get("number") or "surat-peringatan").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nama}.pdf"'})


# ======================================================== kirim dokumen ke pihak luar
def _base_url(request: Request) -> str:
    """URL publik dokumen — dari permintaan yang masuk, tidak pernah ditanam di kode."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


@router.post("/share")
async def share_doc(payload: DocShareIn, request: Request,
                    user: dict = Depends(get_current_user)):
    """Terbitkan tautan berbatas waktu + pesan WhatsApp siap kirim untuk satu dokumen."""
    need = ds.PERMISSION.get(payload.kind)
    if not need:
        raise HTTPException(status_code=400,
                            detail="Jenis dokumen ini belum bisa dikirim ke pihak luar.")
    if not await can(user.get("role"), need[0], need[1]):
        raise HTTPException(
            status_code=403,
            detail=(f"Mengirim {ds.LABEL[payload.kind]} ke pihak luar butuh hak "
                    f"{need[0]}:{need[1]} — sama beratnya dengan mengubah dokumennya."))
    org = _org(user)
    orgdoc = await db.orgs.find_one({"id": org}, {"_id": 0, "name": 1}) or {}
    try:
        out = await ds.create(org, payload.kind, payload.id, actor=user.get("email"),
                              base_url=_base_url(request),
                              org_name=orgdoc.get("name") or ORG_NAME)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", need[0], payload.id,
                    {"share": payload.kind, "doc_number": out.get("doc_number")})
    return {"data": serialize_doc(out)}


@router.get("/share")
async def share_history(kind: str = Query(None), doc_id: str = Query(None),
                        user: dict = Depends(get_current_user)):
    """Riwayat pengiriman: sudah dikirim ke siapa, kapan, dan sudah dibuka berapa kali."""
    if kind and kind not in ds.PERMISSION:
        raise HTTPException(status_code=400, detail="Jenis dokumen tidak dikenal.")
    need = ds.PERMISSION.get(kind or "spk")
    if not await can(user.get("role"), need[0], "view"):
        raise HTTPException(status_code=403, detail="Anda tidak berhak melihat riwayat ini.")
    return {"data": serialize_doc(await ds.history(_org(user), kind=kind, doc_id=doc_id))}
