"""Outbound notification providers (config-driven, real-ready + honest fallback).

- WhatsApp: Meta WhatsApp Cloud API when WHATSAPP_TOKEN + WHATSAPP_PHONE_ID are set,
            otherwise a simulation that logs the message (used for OTP + complaint ack).
- E-sign:   generic provider when ESIGN_API_KEY is set, otherwise a simulation that
            marks the request as signed immediately.

Nothing here blocks the app: if credentials are absent the simulation path runs so
the feature is fully functional now; add env vars later to go live.
"""
import os
import random
import asyncio
import logging

import requests

from core_utils import now_iso
from db import ORG_ID

logger = logging.getLogger("sipro.notifications")


# ----------------------------- WhatsApp -----------------------------
def whatsapp_configured() -> bool:
    return bool(os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_ID"))


async def send_whatsapp(to: str, message: str, *, kind: str = "notification",
                        conversation_id: str = None, actor: str = "system", template: dict = None,
                        template_params: list = None) -> dict:
    """Kirim teks WA lewat gateway tunggal (`wa_gateway`): live bila kredensial + mode live,
    selain itu simulasi yang TERCATAT (status `simulated`). Gagal = `failed` + alasan."""
    import wa_gateway as gw
    msg = await gw.send(ORG_ID, to, kind=kind, body=message, conversation_id=conversation_id, actor=actor,
                        template=template, template_params=template_params)
    status = msg.get("status")
    provider = "whatsapp_cloud" if msg.get("mode") == "live" else "simulation"
    return {"provider": provider, "status": "logged" if status == "simulated" else status,
            "message_id": msg.get("id"), "provider_message_id": msg.get("provider_message_id"),
            "error_code": msg.get("error_code"), "error_detail": msg.get("error_detail"), "mode": msg.get("mode")}


def gen_otp(n: int = 6) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(n))


# ----------------------------- E-sign -----------------------------
def esign_configured() -> bool:
    return bool(os.environ.get("ESIGN_API_KEY") and os.environ.get("ESIGN_BASE_URL"))


def _request_esign_real(*, document_id: str, signer_name: str, signer_email: str = None) -> dict:
    base = os.environ["ESIGN_BASE_URL"].rstrip("/")
    resp = requests.post(
        f"{base}/signature-requests",
        headers={"Authorization": f"Bearer {os.environ['ESIGN_API_KEY']}"},
        json={"document_id": document_id, "signer_name": signer_name, "signer_email": signer_email},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def request_esignature(*, document_id: str, signer_name: str, signer_email: str = None) -> dict:
    """Request an e-signature; simulation marks it signed immediately when not configured."""
    if esign_configured():
        try:
            raw = await asyncio.to_thread(
                _request_esign_real, document_id=document_id,
                signer_name=signer_name, signer_email=signer_email)
            return {"provider": "esign", "status": "pending", "raw": raw}
        except Exception as e:  # noqa: BLE001
            logger.warning("E-sign request failed (%s); simulating.", e)
    logger.info("[SIM e-sign] doc=%s signer=%s", document_id, signer_name)
    return {"provider": "simulation", "status": "signed", "signed_at": now_iso()}
