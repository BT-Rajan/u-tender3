from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.enums import NotificationType, ProjectStatus
from app.models.offer import Offer
from app.models.project import Project
from app.models.user import User
from app.services.email import notify_owner_deadline_approaching
from app.services.notify import notify
from app.services.whatsapp_client import WhatsAppCloudClient
from app.services.whatsapp_outbox import dispatch_due

router = APIRouter(tags=["cron"])
settings = get_settings()


def build_whatsapp_sender() -> WhatsAppCloudClient:
    """Indirection so tests can substitute a sender without touching the network."""
    return WhatsAppCloudClient.from_settings(settings)


# Intended to be hit by an external scheduler (plain cron, a GitHub Actions
# scheduled workflow, etc — this doesn't assume one specific host) roughly
# once an hour. Protected by a shared secret rather than a user session,
# since the caller isn't a browser. Ported from
# src/app/api/cron/deadline-reminders/route.ts.
@router.get("/cron/deadline-reminders")
def deadline_reminders(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not settings.cron_secret or authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = datetime.utcnow()
    in_24h = now + timedelta(hours=24)

    projects = (
        db.query(Project)
        .filter(
            Project.status == ProjectStatus.open,
            Project.deadline_reminder_sent.is_(False),
            Project.bid_deadline >= now,
            Project.bid_deadline <= in_24h,
        )
        .all()
    )

    sent = 0
    for p in projects:
        offer_count = db.query(Offer).filter(Offer.project_id == p.id).count()
        owner = db.get(User, p.owner_id)
        if owner:
            notify_owner_deadline_approaching(owner.email, p.title, p.id, offer_count)
            notify(db, owner, NotificationType.deadline_approaching, link=f"/owner/projects/{p.id}", project_title=p.title)
        p.deadline_reminder_sent = True
        sent += 1
    db.commit()

    return {"checked": len(projects), "sent": sent}


# Run every minute by the same external scheduler. Sends due WhatsApp outbox
# rows and retries transient failures with backoff. Does nothing while
# WhatsApp is disabled, so the rows wait until it is switched on.
@router.get("/cron/whatsapp-outbox")
def whatsapp_outbox(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not settings.cron_secret or authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not settings.whatsapp_enabled:
        return {"skipped": True}

    sender = build_whatsapp_sender()
    try:
        stats = dispatch_due(
            db,
            sender,
            now=datetime.utcnow(),
            max_attempts=settings.whatsapp_outbox_max_attempts,
        )
    finally:
        sender.close()
    return {"skipped": False, **stats}
