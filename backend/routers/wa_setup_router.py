"""wa_setup_router — `/api/wa/setup/*` (Fase 100): wizard koneksi WhatsApp Cloud API dari antarmuka."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import wa_setup as ws
from db import ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/wa/setup", tags=["wa-setup"])


class PinIn(BaseModel):
    pin: str


class CodeMethodIn(BaseModel):
    method: str = "SMS"


class CodeIn(BaseModel):
    code: str


class PublicBaseIn(BaseModel):
    public_base: str


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _guard(coro):
    try:
        return {"data": await coro}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/diagnose")
async def diagnose(user: dict = Depends(require_permission("settings", "manage"))):
    return await _guard(ws.diagnose(_org(user)))


@router.post("/register")
async def register(p: PinIn, user: dict = Depends(require_permission("settings", "manage"))):
    out = await _guard(ws.register_phone(_org(user), p.pin.strip()))
    await audit_log(user, "update", "wa_config", "register_phone", {"ok": out["data"]["ok"], "error_code": out["data"].get("error_code")})
    return out


@router.post("/request-code")
async def request_code(p: CodeMethodIn, user: dict = Depends(require_permission("settings", "manage"))):
    return await _guard(ws.request_code(_org(user), p.method))


@router.post("/verify-code")
async def verify_code(p: CodeIn, user: dict = Depends(require_permission("settings", "manage"))):
    return await _guard(ws.verify_code(_org(user), p.code.strip()))


@router.post("/subscribe")
async def subscribe(user: dict = Depends(require_permission("settings", "manage"))):
    out = await _guard(ws.subscribe_app(_org(user)))
    await audit_log(user, "update", "wa_config", "subscribe_app", {"ok": out["data"]["ok"]})
    return out


@router.get("/webhook-guide")
async def webhook_guide(public_base: Optional[str] = "", user: dict = Depends(require_permission("settings", "manage"))):
    return await _guard(ws.webhook_guide(_org(user), public_base))


@router.post("/handshake")
async def handshake(p: PublicBaseIn, user: dict = Depends(require_permission("settings", "manage"))):
    return await _guard(ws.handshake_check(_org(user), p.public_base))
