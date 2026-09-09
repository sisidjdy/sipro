"""Finance reports + PDF export (EPIC M5) — worksheet-level.

Routes: /finance/reports/revenue (JSON), /finance/reports/{kind}/pdf (PDF).
kind ∈ {ar-aging, ap-aging, revenue, commissions, collections, cashflow}.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from db import ORG_ID
from core_utils import serialize_doc
from rbac import require_permission
import finance_reports as fr
from pdf_utils import build_table_pdf

router = APIRouter(prefix="/finance/reports", tags=["finance"])


@router.get("/revenue")
async def revenue(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": serialize_doc(await fr.revenue_report(user.get("org_id", ORG_ID)))}


@router.get("/{kind}/pdf")
async def report_pdf(kind: str, user: dict = Depends(require_permission("finance", "view"))):
    try:
        ds = await fr.report_dataset(kind, user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    import doc_layout as dl
    org = user.get("org_id", ORG_ID)
    layout = await dl.get_layout(org, "LAPORAN")
    pdf = build_table_pdf(title=ds["title"], subtitle=ds.get("subtitle", ""),
                          columns=ds["columns"], rows=ds["rows"], total_row=ds.get("total_row"),
                          layout=layout, images=await dl.images(org, layout))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="laporan-{kind}.pdf"'})
