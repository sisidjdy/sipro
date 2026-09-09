"""ROUTER FASE 68 — denda keterlambatan terjadwal.

Prefix `/finance`, jalur `/late-fee-auto` (pola p59: tidak menumpang router yang punya
jalur `/{deal_id}` supaya tidak tertelan sebagai id).

Pemisahan tugas: membaca status/pratinjau = `late_fee:view`; MENJALANKAN sekarang =
`late_fee:create` (Keuangan). Tombol manual dan penjadwal memakai fungsi yang SAMA
(`late_fee_auto.run`) — tidak ada mesin kedua.
"""
from fastapi import APIRouter, Depends

import late_fee_auto as lfa
from core_utils import serialize_doc
from db import ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/finance", tags=["finance-p68"])


@router.get("/late-fee-auto")
async def late_fee_auto_status(user: dict = Depends(require_permission("late_fee",
                                                                       "view"))):
    """Aturan aktif, pratinjau yang akan ditagihkan hari ini, dan riwayat putaran."""
    return {"data": serialize_doc(await lfa.status(user.get("org_id", ORG_ID)))}


@router.post("/late-fee-auto/run")
async def late_fee_auto_run(user: dict = Depends(require_permission("late_fee",
                                                                    "create"))):
    """Jalankan sekarang (manual) — idempoten per (termin, bulan), sama seperti penjadwal."""
    out = await lfa.run(user.get("org_id", ORG_ID), actor=user.get("email"), mode="manual")
    await audit_log(user, "run", "late_fee", "auto",
                    {"charged": out.get("charged_count", 0),
                     "total": out.get("charged_total", 0)})
    return {"data": serialize_doc(out), "message": out.get("detail")}
