"""
ManyChat-specific plumbing: webhook authentication, the request/response
shapes its External Request action sends and reads, and the Public API
client used to push an answer that missed the 10-second External Request
window (see orchestrator.py's deadline handling).

Nothing here talks to an LLM or to server.py's data tools; this module only
knows about ManyChat's own wire format. docs/SETUP_MANYCHAT_LLM.md section 5
is the operator-facing description of the flow this code implements.
"""
from __future__ import annotations

import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

from .config import settings

log = logging.getLogger("agriflow.manychat")


# =============================================================================
# Webhook authentication
# =============================================================================

async def require_manychat_key(
    request: Request,
    x_agriflow_key: Optional[str] = Header(default=None, alias="X-AgriFlow-Key"),
) -> None:
    """
    A static shared secret in the header, never the URL (ManyChat logs
    request URLs in its flow history, so a secret there would leak into
    ManyChat's own UI). Constant-time comparison so response timing cannot
    be used to guess the secret byte by byte.

    Empty MANYCHAT_WEBHOOK_SECRET refuses every request rather than
    accepting an unauthenticated one; the equivalent production-posture
    check in security.py raises this from a warning to a boot-time refusal
    when APP_ENV=production, matching how MOCK_MODE and the other demo
    defaults are handled.
    """
    secret = settings.manychat_webhook_secret
    if not secret or not x_agriflow_key or not hmac.compare_digest(x_agriflow_key, secret):
        log.warning("manychat.auth_rejected path=%s", request.url.path)
        raise HTTPException(status_code=401, detail="invalid or missing X-AgriFlow-Key")


# =============================================================================
# Request / response shapes
# =============================================================================

class ManyChatWebhookRequest(BaseModel):
    """What the Default Reply's External Request action sends, per
    docs/SETUP_MANYCHAT_LLM.md section 5. `phone` is the WhatsApp number in
    whatever format ManyChat's getCustomFields exposes it; hash_phone()
    normalises it the same way the Twilio path already does."""
    subscriber_id: str = Field(..., max_length=64)
    phone: str = Field("", max_length=32)
    first_name: str = Field("", max_length=128)
    last_input_text: str = Field(..., max_length=4096)
    last_interaction: Optional[str] = Field(None, max_length=64)


class ManyChatWebhookResponse(BaseModel):
    """Field names match the MANYCHAT_FIELD_* custom fields the setup doc
    has the founder create and map in the flow builder. `agriflow_status`
    is "ok" (agriflow_reply is the full answer) or "pending" (agriflow_reply
    is a short holding line; the real answer follows via the Public API
    push within the 24-hour window)."""
    agriflow_reply: str
    agriflow_status: str = "ok"
    agriflow_lang: str = "id"
    agriflow_intent: str = ""
    agriflow_token: str = ""


HOLDING_MESSAGE_ID = "Sebentar ya, saya sedang mengambil datanya."
HOLDING_MESSAGE_JV = "Sekedhap nggih, kula pados data rumiyin."


# =============================================================================
# Public API push (the async path when the 7.5s deadline is missed)
# =============================================================================

class ManyChatPushError(Exception):
    """The Public API call itself failed. Caught and logged by the caller;
    there is no user-facing retry path for a push that could not be sent."""


def send_content(subscriber_id: str, text: str) -> None:
    """
    POST /fb/sending/sendContent, the ManyChat Public API call that delivers
    a message outside the External Request's own response, used when the
    orchestrator's tool-calling answer did not finish inside the deadline.
    Requires the 24-hour customer-service window still be open, exactly like
    any other WhatsApp business-initiated message; ManyChat itself enforces
    that, not this code.
    """
    if not settings.manychat_api_token:
        log.warning("manychat.push_skipped reason=no_api_token subscriber=%s", subscriber_id)
        return
    import httpx

    url = f"{settings.manychat_api_base.rstrip('/')}/fb/sending/sendContent"
    body = {
        "subscriber_id": subscriber_id,
        "data": {"version": "v2", "content": {"type": "whatsapp", "messages": [{"type": "text", "text": text}]}},
    }
    headers = {"Authorization": f"Bearer {settings.manychat_api_token}", "Content-Type": "application/json"}
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10.0)
        if resp.status_code >= 400:
            raise ManyChatPushError(f"{resp.status_code}: {resp.text[:300]}")
    except httpx.HTTPError as exc:
        raise ManyChatPushError(str(exc)) from exc
