"""WhatsApp delivery for in-app notifications.

Every event that creates an in-app notification also queues a WhatsApp template, with the same dedupe
rule: a repeat of an event whose notice is still unread queues nothing new. The notice row's id is the
idempotency key, so a retried request can't send the same message twice.

Accounts with no WhatsApp identity (web-only accounts) get the in-app notice only. Document decisions
are sent by document_service.enqueue_review_decision, which has its own dedupe, so they are excluded here.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.user import User
from app.models.whatsapp import WhatsAppIdentity
from app.services import whatsapp_outbox
from app.services.money import format_amount
from app.services.whatsapp_templates import TemplateError, components_for

logger = logging.getLogger("utender.whatsapp")

Builder = Callable[[dict[str, Any]], list[str]]


def _const(text: str) -> Builder:
    return lambda kwargs: [text]


def _tender(kwargs: dict[str, Any]) -> list[str]:
    return [kwargs["project_title"]]


NOTIFICATION_TEMPLATES: dict[NotificationType, tuple[str, Builder]] = {
    NotificationType.verification_activated: ("verification_status", _const("Your contractor account is verified and approved.")),
    NotificationType.owner_verification_activated: ("verification_status", _const("Your owner account is verified and approved.")),
    NotificationType.verification_rejected: ("verification_status", _const("Your contractor verification needs changes. Open U-Tender to see what to fix.")),
    NotificationType.owner_verification_rejected: ("verification_status", _const("Your owner verification needs changes. Open U-Tender to see what to fix.")),
    NotificationType.contractor_suspended: ("account_status", _const("Your account has been suspended. Contact support.")),
    NotificationType.owner_suspended: ("account_status", _const("Your account has been suspended. Contact support.")),
    NotificationType.contractor_reactivated: ("account_status", _const("Your account has been reactivated.")),
    NotificationType.owner_reactivated: ("account_status", _const("Your account has been reactivated.")),
    NotificationType.payment_activated: ("payment_status", _const("Your subscription is active. Marketplace access is on.")),
    NotificationType.payment_failed: ("payment_status", _const("A subscription payment failed. Update your payment method to keep bidding.")),
    NotificationType.payment_override_granted: ("payment_status", _const("An administrator activated full marketplace access on your account.")),
    NotificationType.payment_override_revoked: ("payment_status", _const("Your administrator-granted marketplace access was revoked.")),
    NotificationType.tender_published: ("new_tender", lambda kw: [kw["project_title"], kw["closing_text"]]),
    NotificationType.bid_submitted: ("offer_received", lambda kw: [kw["project_title"], kw["contractor_name"], kw["amount_label"]]),
    NotificationType.bid_revised: ("offer_revised", lambda kw: [kw["project_title"], kw["contractor_name"], kw["amount_label"]]),
    NotificationType.award_won: ("award_won", _tender),
    NotificationType.award_lost: ("award_lost", _tender),
    NotificationType.tender_amendment: ("tender_amended", lambda kw: [kw["project_title"], kw["summary"]]),
    NotificationType.deadline_approaching: ("deadline_reminder", _tender),
    NotificationType.tender_no_award: ("tender_status", lambda kw: [kw["project_title"], "closed with no award"]),
    NotificationType.tender_cancelled: ("tender_status", lambda kw: [kw["project_title"], "canceled"]),
}


def amount_label(amount: float | None, sealed: bool) -> str:
    """What the owner may see of a bid. A sealed tender hides the amount until it closes."""
    if sealed or amount is None:
        return "hidden until the tender closes"
    return format_amount(Decimal(str(amount)), grouped=True)


def _identity_wa_id(db: Session, user_id: str) -> str | None:
    identity = db.scalar(select(WhatsAppIdentity).where(WhatsAppIdentity.user_id == user_id))
    return identity.wa_id if identity else None


def enqueue_notification(db: Session, user: User, notification: Notification, kwargs: dict[str, Any], *, now: datetime) -> bool:
    """Queue the WhatsApp template for a newly created notification. Returns whether anything was queued."""
    mapping = NOTIFICATION_TEMPLATES.get(notification.type)
    if mapping is None:
        return False
    wa_id = _identity_wa_id(db, user.id)
    if wa_id is None:
        return False

    template_name, build = mapping
    if notification.type == NotificationType.bid_submitted and kwargs.get("is_revision"):
        template_name = "offer_revised"
    language = user.language.value if user.language else "en"
    try:
        values = [str(value) if value not in (None, "") else "-" for value in build(kwargs)]
        components_for(template_name, values)  # validates the count before anything is queued
    except (KeyError, TemplateError) as exc:
        logger.error("WhatsApp notification %s not queued: %s", notification.type.value, type(exc).__name__)
        return False

    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"notif:{notification.id}",
        recipient_wa_id=wa_id,
        kind=whatsapp_outbox.KIND_TEMPLATE,
        now=now,
        template_name=template_name,
        params={"language": language, "components": components_for(template_name, values)},
    )
    db.commit()
    return True


def fan_out_new_tender(db: Session, project, *, now: datetime, notify: Callable[..., Any]) -> int:
    """Tell every contractor who can bid on this tender that it is open.

    Eligibility matches the feed and bidding rules: verified, not suspended, paid (or override), and in the
    tender's trade when the tender names one. Each contractor gets one in-app notice, which carries the
    WhatsApp message. Returns how many contractors were notified.
    """
    from app.models.contractor import ContractorProfile
    from app.services.tender_service import format_local_deadline

    closing = format_local_deadline(project.bid_deadline)
    count = 0
    trade = (project.trade or "").strip().lower()
    for profile in db.scalars(select(ContractorProfile)).all():
        if not profile.is_verified_active:
            continue
        if trade and (profile.primary_trade or "").strip().lower() != trade:
            continue
        user = db.get(User, profile.user_id)
        if user is None:
            continue
        notify(
            db,
            user,
            NotificationType.tender_published,
            link=f"/contractor/projects/{project.id}",
            project_title=project.title,
            closing_text=f"{closing} Kuwait time",
        )
        count += 1
    return count
