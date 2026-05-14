import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

from shared.events import ChangeEvent, SiteEvent
from .config import Settings
from .publisher import RabbitMQPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = Settings()
publisher = RabbitMQPublisher(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    publisher.connect()
    yield
    publisher.close()


app = FastAPI(title="OMD Sync – Webhook Receiver", lifespan=lifespan)


# ------------------------------------------------------------------
# Signature verification
# ------------------------------------------------------------------

def _verify_signature(body: bytes, header_value: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_om_signature: Optional[str] = Header(None, alias="X-OM-Signature"),
) -> dict:
    body = await request.body()

    if settings.webhook_secret:
        if not x_om_signature or not _verify_signature(body, x_om_signature, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    # OMD may send a single event object or a list
    raw_events = payload if isinstance(payload, list) else [payload]

    published = 0
    for raw in raw_events:
        try:
            event = ChangeEvent(**raw)
            site_event = SiteEvent(site_code=settings.site_code, event=event)
            publisher.publish(site_event)
            published += 1
        except Exception as exc:
            logger.error("Failed to process event %s: %s", raw.get("entityFullyQualifiedName"), exc)

    return {"status": "ok", "site_code": settings.site_code, "published": published}


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "site_code": settings.site_code}


if __name__ == "__main__":
    uvicorn.run("webhook_receiver.main:app", host="0.0.0.0", port=settings.port, reload=False)
