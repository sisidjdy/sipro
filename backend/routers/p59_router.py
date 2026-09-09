"""ROUTER FASE 59 — laporan keringanan denda, kandidat tunggakan, utang refund.

Prefix `/finance`. Jalur sengaja TIDAK diletakkan di bawah `/finance/late-fees/...` maupun
`/cancellations/...`: kedua router itu punya jalur bercorak `/{deal_id}` dan `/{cid}`, jadi
menambahkan sub-jalur baru di sana akan tertelan sebagai "id" tergantung urutan pendaftaran
router — cacat yang mahal dicari.

Pemisahan tugas yang dipaksakan di sini:
  * **membaca laporan keringanan** = `late_fee:view` (sales hanya transaksinya sendiri);
  * **membaca kandidat tunggakan** = `cancellation:view`;
  * **menitipkan tugas peninjauan tunggakan** = `cancellation:approve` (Manajer Keuangan) —
    dan mesin tetap TIDAK boleh membatalkan apa pun;
  * **membaca utang refund** = `finance:view`.
"""
from fastapi import APIRouter, Depends, Query, Response

import arrears_engine as arr
import doc_layout as dl
import late_fee_report as lfr
import refund_debt as rd
from core_utils import serialize_doc
from db import ORG_ID
from pdf_utils import build_table_pdf
from rbac import audit_log, is_scoped_sales, require_permission

router = APIRouter(prefix="/finance", tags=["finance-p59"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _own(user: dict):
    """Lingkup baris: sales ber-scope hanya membaca transaksi miliknya (dipaksa SERVER)."""
    return user.get("email") if is_scoped_sales(user) else None


@router.get("/late-fee-waivers")
async def waiver_report(date_from: str = Query(None), date_to: str = Query(None),
                        deal_id: str = Query(None),
                        user: dict = Depends(require_permission("late_fee", "view"))):
    """Siapa meringankan denda apa, berapa, kapan, dan dengan alasan apa."""
    out = await lfr.waivers(_org(user), date_from=date_from, date_to=date_to,
                            deal_id=deal_id, own_email=_own(user))
    return {"data": serialize_doc(out)}


@router.get("/late-fee-waivers/pdf")
async def waiver_report_pdf(date_from: str = Query(None), date_to: str = Query(None),
                            deal_id: str = Query(None),
                            user: dict = Depends(require_permission("late_fee", "view"))):
    ds = await lfr.dataset(_org(user), date_from=date_from, date_to=date_to,
                           deal_id=deal_id, own_email=_own(user))
    layout = await dl.get_layout(_org(user), "LAPORAN")
    pdf = build_table_pdf(title=ds["title"], subtitle=ds["subtitle"], columns=ds["columns"],
                          rows=ds["rows"], total_row=ds["total_row"], layout=layout,
                          images=await dl.images(_org(user), layout))
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="laporan-keringanan-denda.pdf"'})


@router.get("/arrears/candidates")
async def arrears_candidates(user: dict = Depends(require_permission("cancellation",
                                                                    "view"))):
    """Pesanan yang tunggakannya sudah (hampir) melewati batas kontrak — USULAN, bukan aksi."""
    out = await arr.candidates(_org(user), own_email=_own(user))
    return {"data": serialize_doc(out)}


@router.post("/arrears/sweep")
async def arrears_sweep(user: dict = Depends(require_permission("cancellation", "approve"))):
    """Titipkan tugas peninjauan kepada Manajer Keuangan (idempoten per kontrak per bulan)."""
    out = await arr.sweep(_org(user), user.get("email"))
    if out["created"]:
        await audit_log(user, "create", "cancellation", None,
                        {"arrears_tasks": len(out["created"])})
    return {"data": serialize_doc(out)}


@router.get("/refund-debt")
async def refund_debt(horizon: int = Query(6),
                      user: dict = Depends(require_permission("finance", "view"))):
    """Utang refund 2-1460: jatuh tempo, umur, proyeksi kas, dan uji cocok dengan buku besar."""
    return {"data": serialize_doc(await rd.report(_org(user), horizon=horizon))}


@router.get("/refund-debt/pdf")
async def refund_debt_pdf(horizon: int = Query(6),
                          user: dict = Depends(require_permission("finance", "view"))):
    ds = await rd.dataset(_org(user), horizon=horizon)
    layout = await dl.get_layout(_org(user), "LAPORAN")
    pdf = build_table_pdf(title=ds["title"], subtitle=ds["subtitle"], columns=ds["columns"],
                          rows=ds["rows"], total_row=ds["total_row"], layout=layout,
                          images=await dl.images(_org(user), layout))
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="laporan-utang-refund.pdf"'})
