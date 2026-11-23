from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.models.whatsapp import OUTBOX_SENT, WhatsAppOutbox
from app.routers import cron as cron_module
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_outbox import KIND_TEXT, enqueue
from whatsapp_helpers import CRON_SECRET, enable_whatsapp

URL = "/cron/whatsapp-outbox"


def _sender_returning(messages_by_call):
    """A real Cloud API client whose transport answers without any network traffic."""
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json={"messages": [{"id": f"wamid.CRON{counter['n']}"}]})

    return WhatsAppCloudClient(
        access_token="t",
        phone_number_id="1",
        api_version="v21.0",
        api_url="https://graph.facebook.com",
        transport=httpx.MockTransport(handler),
    )


def test_outbox_cron_requires_the_cron_secret(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_outbox_cron_refuses_when_no_cron_secret_is_configured(monkeypatch, client):
    enable_whatsapp(monkeypatch, cron_secret=None)
    assert client.get(URL, headers={"Authorization": "Bearer "}).status_code == 401


def test_outbox_cron_is_a_no_op_while_whatsapp_is_disabled(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_enabled=False)
    enqueue(db, dedupe_key="waiting", recipient_wa_id="96512345678", kind=KIND_TEXT, now=datetime.utcnow(), params={"body": "x"})
    db.commit()

    response = client.get(URL, headers={"Authorization": f"Bearer {CRON_SECRET}"})

    assert response.status_code == 200
    assert response.json() == {"skipped": True}
    assert db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.dedupe_key == "waiting")).status == "pending"


def test_outbox_cron_sends_due_rows_and_reports_the_counts(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    now = datetime.utcnow()
    enqueue(db, dedupe_key="due", recipient_wa_id="96512345678", kind=KIND_TEXT, now=now - timedelta(minutes=1), params={"body": "x"})
    db.commit()

    monkeypatch.setattr(cron_module, "build_whatsapp_sender", lambda: _sender_returning(None))

    response = client.get(URL, headers={"Authorization": f"Bearer {CRON_SECRET}"})

    assert response.status_code == 200
    assert response.json() == {"skipped": False, "sent": 1, "retry": 0, "failed": 0, "dead": 0, "held": 0}
    assert db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.dedupe_key == "due")).status == OUTBOX_SENT


def test_outbox_cron_closes_the_sender_even_when_dispatch_fails(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    closed = {"value": False}

    class ExplodingSender:
        def close(self):
            closed["value"] = True

    def boom(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(cron_module, "build_whatsapp_sender", lambda: ExplodingSender())
    monkeypatch.setattr(cron_module, "dispatch_due", boom)

    try:
        client.get(URL, headers={"Authorization": f"Bearer {CRON_SECRET}"})
    except RuntimeError:
        pass

    assert closed["value"] is True
