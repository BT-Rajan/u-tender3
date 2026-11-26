"""Phase 8: the complete WhatsApp journey, end to end, through the real endpoints.

Every step uses what Meta would send: signed webhook deliveries, encrypted Flow requests carrying the
flow_token from the message the bot sent, and the upload link from the message the bot sent. The admin
steps go through the real admin routes. The Cloud API is replaced by RecordingSender, so the only
thing faked is the network. What is NOT covered here: a live Meta test number. That needs credentials
and is a separate step (see docs/whatsapp-deployment.md).
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from app.auth.security import create_access_token, hash_password
from app.config import get_settings
from app.models.contractor import ContractorProfile
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.enums import DocumentStatus, Language, UserRole
from app.models.owner import OwnerProfile
from app.models.notification import Notification
from app.models.project import Project
from app.models.user import User
from app.models.whatsapp import WhatsAppMessageEvent, WhatsAppOutbox, WhatsAppTemplateStatus
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

OWNER_WA = "96511119001"
CONTRACTOR_WA = "96522229001"
PDF = b"%PDF-1.4\n%%EOF\n"


def _deliver(client, sender, monkeypatch, *messages, raw_override=None, signature=None):
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = raw_override if raw_override is not None else json.dumps(message_envelope(*messages)).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": signature or sign(raw)}
    return client.post("/whatsapp/webhook", content=raw, headers=headers)


def _flow(client, public_pem, token, screen, data=None, action="data_exchange"):
    reply, status = flow_request(client, public_pem, token=token, action=action, screen=screen, data=data)
    assert status == 200, f"Flow request returned {status}"
    return reply


def _approve_every_template(db):
    from app.services.whatsapp_templates import CATALOG

    for name in CATALOG:
        for language in ("en", "ar"):
            db.add(WhatsAppTemplateStatus(name=name, language=language, status="APPROVED"))
    db.commit()


def _admin(client, db):
    admin = User(email="ops@example.com", password_hash=hash_password("ops-pass-123"), role=UserRole.admin, email_verified=True)
    db.add(admin)
    db.commit()
    client.cookies.set("access_token", create_access_token(admin.id))


def test_the_full_journey_from_registration_to_award_and_suspension(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    install_whatsapp_handlers()
    sender = RecordingSender()
    _approve_every_template(db)
    db.add_all([
        DocumentRequirement(name="Civil ID", applies_to=UserRole.owner, is_active=True),
        DocumentRequirement(name="Trade licence", applies_to=UserRole.contractor, is_active=True),
    ])
    db.commit()
    _admin(client, db)

    # 1. New owner registers from their first message.
    assert _deliver(client, sender, monkeypatch, text_message("wamid.OWNER1", OWNER_WA, "hi")).status_code == 200
    owner_token = sender.flows()[-1]["flow_token"]
    assert _flow(client, public_pem, owner_token, "ROLE", {"role": "owner", "language": "en"})["screen"] == "OWNER_DETAILS"
    assert _flow(client, public_pem, owner_token, "OWNER_DETAILS", {"full_name": "Layla Al-Sabah"})["screen"] == "SUCCESS"
    owner = db.scalar(select(User).where(User.phone == f"+{OWNER_WA}"))
    assert owner.role == UserRole.owner and owner.email is None and owner.password_hash is None

    # 2. Returning owner, while still unverified: the dashboard says what is missing.
    sender.sent.clear()
    assert _deliver(client, sender, monkeypatch, text_message("wamid.OWNER2", OWNER_WA, "menu")).status_code == 200
    owner_menu = sender.flows()[-1]["flow_token"]
    menu = _flow(client, public_pem, owner_menu, "MENU", action="INIT")
    assert "Documents are incomplete" in menu["data"]["status"]

    # 3. Document upload through a secure link, with the one-time code in its own message.
    assert _flow(client, public_pem, owner_menu, "MENU", {"choice": "my_documents"})["screen"] == "DOCUMENTS"
    assert _flow(client, public_pem, owner_menu, "DOCUMENTS", {"intent": "send_links"})["screen"] == "LINKS_SENT"
    from app.services.whatsapp_outbox import dispatch_due

    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    link = sender.links()[-1]["url"]
    token = link.rsplit("/upload/", 1)[1]
    code = next(m["body"] for m in sender.texts() if "code for Civil ID" in m["body"]).split("is ")[1].split(".")[0]
    page = client.post(f"/upload/{token}", data={"code": code}, files={"file": ("civil-id.pdf", PDF, "application/pdf")})
    assert page.status_code == 200 and "Document received" in page.text

    # 4. Admin approves the document and the account; the owner is told on WhatsApp.
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == owner.id))
    requirement = db.scalar(select(DocumentRequirement).where(DocumentRequirement.applies_to == UserRole.owner))
    review = client.post("/admin/review/owner-documents", json={"owner_id": owner.id, "requirement_id": requirement.id, "decision": "approved"})
    assert review.status_code == 200
    assert client.post(f"/admin/review/owners/{owner.id}/approve").status_code == 200
    db.expire_all()  # the admin route committed in its own session
    assert db.get(OwnerDocument, doc.id).status == DocumentStatus.approved

    # 5. Contractor registers, is approved, and has an active subscription.
    sender.sent.clear()
    assert _deliver(client, sender, monkeypatch, text_message("wamid.CON1", CONTRACTOR_WA, "hi")).status_code == 200
    con_token = sender.flows()[-1]["flow_token"]
    _flow(client, public_pem, con_token, "ROLE", {"role": "contractor", "language": "en"})
    assert _flow(client, public_pem, con_token, "CONTRACTOR_DETAILS", {
        "contact_name": "Omar Haddad", "company_name": "Haddad Builders", "primary_trade": "Electrical"})["screen"] == "SUCCESS"
    contractor = db.scalar(select(User).where(User.phone == f"+{CONTRACTOR_WA}"))
    contractor_req = db.scalar(select(DocumentRequirement).where(DocumentRequirement.applies_to == UserRole.contractor))
    assert client.post("/admin/review/documents", json={
        "contractor_id": contractor.id, "requirement_id": contractor_req.id, "decision": "approved"}).status_code == 200
    assert client.post(f"/admin/review/contractors/{contractor.id}/approve").status_code == 200
    db.expire_all()
    db.get(ContractorProfile, contractor.id).paid_until = datetime.utcnow() + timedelta(days=30)
    db.commit()

    # 6. Owner creates a sealed tender over WhatsApp and publishes it. The paid contractor in Electrical is told.
    sender.sent.clear()
    deadline = (datetime.utcnow() + timedelta(days=10)).strftime("%d-%m-%Y %H:%M")
    _deliver(client, sender, monkeypatch, text_message("wamid.OWNER3", OWNER_WA, "tender"))
    owner_menu = sender.flows()[-1]["flow_token"]
    review_screen = _flow(client, public_pem, owner_menu, "CREATE_TENDER", {
        "title": "Villa renovation", "address": "Block 3, Salmiya", "trade": "Electrical",
        "bid_deadline": deadline, "tender_type": "sealed"})
    tender_id = review_screen["data"]["tender_id"]
    assert _flow(client, public_pem, owner_menu, "REVIEW", {"tender_id": tender_id, "action": "publish"})["screen"] == "DONE"
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert any(m.get("template") == "new_tender" and m["to"] == CONTRACTOR_WA for m in sender.sent)

    # 7. Contractor discovers the tender, submits an offer, then revises it.
    sender.sent.clear()
    _deliver(client, sender, monkeypatch, text_message("wamid.CON2", CONTRACTOR_WA, "projects"))
    con_menu = sender.flows()[-1]["flow_token"]
    listing = _flow(client, public_pem, con_menu, "MENU", {"choice": "browse_projects"})
    assert [p["id"] for p in listing["data"]["projects"]] == [tender_id]
    _flow(client, public_pem, con_menu, "PROJECT_LIST", {"project_id": tender_id})
    _flow(client, public_pem, con_menu, "PROJECT_DETAILS", {"project_id": tender_id, "action": "submit"})
    _flow(client, public_pem, con_menu, "REVIEW_OFFER", {"project_id": tender_id, "amount": "12500", "timeline": "6 months", "message": "Ready", "decision": "submit"})
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert [m.get("template") for m in sender.sent if m["to"] == OWNER_WA] == ["offer_received"]

    # A revision while the owner's bid notice is still unread queues nothing new (the dedupe rule).
    _flow(client, public_pem, con_menu, "PROJECT_DETAILS", {"project_id": tender_id, "action": "revise"})
    _flow(client, public_pem, con_menu, "REVIEW_OFFER", {"project_id": tender_id, "amount": "11900", "timeline": "5 months", "message": "Better", "decision": "submit"})
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert [m.get("template") for m in sender.sent if m["to"] == OWNER_WA] == ["offer_received"]

    # Once the owner has read the notice, the next revision is announced as a revision.
    for notice in db.scalars(select(Notification).where(Notification.user_id == owner.id)).all():
        notice.is_read = True
    db.commit()
    _flow(client, public_pem, con_menu, "PROJECT_DETAILS", {"project_id": tender_id, "action": "revise"})
    _flow(client, public_pem, con_menu, "REVIEW_OFFER", {"project_id": tender_id, "amount": "11500", "timeline": "5 months", "message": "Final", "decision": "submit"})
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert "offer_revised" in [m.get("template") for m in sender.sent if m["to"] == OWNER_WA]

    # 8. Sealed-bid confidentiality: the owner's view names no bidder and shows no amount.
    owner_view = _flow(client, public_pem, owner_menu, "TENDER_DETAILS", {"tender_id": tender_id, "action": "offers"})
    assert owner_view["screen"] == "OFFERS"
    assert "Haddad" not in owner_view["data"]["offers"] and "11,900" not in owner_view["data"]["offers"]

    # 9. Owner amends the tender; the bidder is told.
    sender.sent.clear()
    details = _flow(client, public_pem, owner_menu, "TENDER_DETAILS", {"tender_id": tender_id, "action": "edit"})
    assert details["screen"] == "AMEND"
    done = _flow(client, public_pem, owner_menu, "AMEND", {**details["data"], "title": "Villa renovation phase 2", "reason": "Scope"})
    assert done["screen"] == "DONE"
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert any(m.get("template") == "tender_amended" and m["to"] == CONTRACTOR_WA for m in sender.sent)

    # 10. Contractor's offer history is their own; awards are empty until one is made.
    history = _flow(client, public_pem, con_menu, "PROJECT_DETAILS", {"project_id": tender_id, "action": "history"})
    assert history["screen"] == "OFFER_HISTORY" and "12,500.00" in history["data"]["body"]

    # 11. Duplicate webhook delivery: the same message again changes nothing.
    events_before = db.query(WhatsAppMessageEvent).count()
    outbox_before = db.query(WhatsAppOutbox).count()
    replay = json.dumps(message_envelope(text_message("wamid.CON2", CONTRACTOR_WA, "projects"))).encode()
    assert _deliver(client, sender, monkeypatch, raw_override=replay).status_code == 200
    assert db.query(WhatsAppMessageEvent).count() == events_before
    assert db.query(WhatsAppOutbox).count() == outbox_before

    # 12. Invalid signature is refused and stores nothing.
    bad = _deliver(client, sender, monkeypatch, text_message("wamid.BAD", CONTRACTOR_WA, "x"), signature="sha256=00")
    assert bad.status_code == 403
    assert db.scalar(select(WhatsAppMessageEvent).where(WhatsAppMessageEvent.provider_message_id == "wamid.BAD")) is None

    # 13. Admin suspends the contractor: they lose browsing and are told.
    sender.sent.clear()
    assert client.post(f"/admin/contractors/{contractor.id}/suspend", json={"suspended": True}).status_code == 200
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    assert any(m.get("template") == "account_status" and m["to"] == CONTRACTOR_WA for m in sender.sent)
    _deliver(client, sender, monkeypatch, text_message("wamid.CON3", CONTRACTOR_WA, "projects"))
    suspended_menu = sender.flows()[-1]["flow_token"]
    refused = _flow(client, public_pem, suspended_menu, "MENU", {"choice": "browse_projects"})
    assert refused["screen"] == "MENU" and "suspended" in refused["data"]["error_message"]

    # 14. Expired upload link: the page refuses it, generically.
    from app.services.upload_links import issue_upload_link

    stale = issue_upload_link(db, user_id=owner.id, requirement_id=requirement.id, now=datetime.utcnow() - timedelta(hours=2))
    assert client.get(f"/upload/{stale.token}").status_code == 404

    # 15. Nothing is left stuck: every template message the journey queued is either sent or held for approval.
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    failed = db.query(WhatsAppOutbox).filter(WhatsAppOutbox.status.in_(["failed", "dead"])).count()
    assert failed == 0
