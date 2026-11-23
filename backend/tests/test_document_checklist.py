"""The WhatsApp side of Phase 3: the live checklist, sending upload links, and review notices.

These run through the real Flow endpoint (encrypted requests) and the real
outbox dispatcher. The Cloud API is replaced by RecordingSender.
"""

import json
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.contractor import ContractorProfile
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.document_upload import DocumentUploadLink
from app.models.enums import DocumentStatus, Language, UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppOutbox
from app.routers import whatsapp as whatsapp_router
from app.services.document_service import checklist_for, enqueue_review_decision
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_outbox import dispatch_due
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

WA_ID = "96512345678"
PDF = b"%PDF-1.4\n%%EOF\n"


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


def _owner(db, wa_id: str = WA_ID):
    user = User(email=None, password_hash=None, role=UserRole.owner, full_name="Layla Al-Sabah", phone=f"+{wa_id}")
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id))
    identity = get_or_create_identity(db, wa_id, now=datetime.utcnow())
    identity.user_id = user.id
    identity.role = "owner"
    db.commit()
    return user


def _requirements(db, *names, role=UserRole.owner):
    rows = [DocumentRequirement(name=name, applies_to=role, is_active=True) for name in names]
    db.add_all(rows)
    db.commit()
    return rows


def _dashboard_token(client, monkeypatch, db, user) -> str:
    """Open the owner dashboard exactly as a customer would, and return the token it was sent with."""
    sender = RecordingSender()
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message(f"wamid.OPEN{user.id[:6]}", WA_ID, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[0]["flow_token"]


def _choose(client, public_pem, token, choice):
    return flow_request(client, public_pem, token=token, action="data_exchange", screen="MENU", data={"choice": choice})[0]


def _documents(client, public_pem, token):
    return flow_request(client, public_pem, token=token, action="data_exchange", screen="DOCUMENTS", data={"intent": "send_links"})[0]


# --- checklist -----------------------------------------------------------------


def test_the_checklist_is_built_from_the_active_requirements_for_the_role(db):
    user = _owner(db)
    _requirements(db, "Civil ID", "Land deed")
    db.add(DocumentRequirement(name="Retired form", applies_to=UserRole.owner, is_active=False))
    db.add(DocumentRequirement(name="Trade licence", applies_to=UserRole.contractor, is_active=True))
    db.commit()

    names = [item.name for item in checklist_for(db, user)]

    assert names == ["Civil ID", "Land deed"]


def test_a_requirement_added_later_appears_for_an_existing_account(db):
    user = _owner(db)
    _requirements(db, "Civil ID")
    checklist_for(db, user)
    _requirements(db, "Land deed")

    assert [item.name for item in checklist_for(db, user)] == ["Civil ID", "Land deed"]


def test_the_checklist_reflects_each_documents_current_status(client, monkeypatch, db):
    user = _owner(db)
    civil, land = _requirements(db, "Civil ID", "Land deed")
    checklist_for(db, user)
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.requirement_id == civil.id))
    doc.status = DocumentStatus.approved
    land_doc = db.scalar(select(OwnerDocument).where(OwnerDocument.requirement_id == land.id))
    land_doc.status = DocumentStatus.rejected
    land_doc.admin_note = "Scan is cut off"
    db.commit()

    items = {item.name: item for item in checklist_for(db, user)}

    assert items["Civil ID"].status == DocumentStatus.approved
    assert items["Land deed"].needs_upload is True
    assert items["Land deed"].admin_note == "Scan is cut off"


def test_my_documents_shows_the_checklist_text(client, monkeypatch, db):
    user = _owner(db)
    _requirements(db, "Civil ID")
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)

    reply = _choose(client, public_pem, token, "my_documents")

    assert reply["screen"] == "DOCUMENTS"
    assert reply["data"]["checklist"] == "Civil ID: Upload needed"


def test_my_documents_with_no_requirements_says_so(client, monkeypatch, db):
    user = _owner(db)
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)

    reply = _choose(client, public_pem, token, "my_documents")

    assert reply["data"]["checklist"] == "No documents are required for your account."


# --- sending upload links ----------------------------------------------------


def test_send_links_queues_one_link_and_one_separate_code_per_outstanding_requirement(client, monkeypatch, db):
    user = _owner(db)
    _requirements(db, "Civil ID", "Land deed")
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")

    reply = _documents(client, public_pem, token)

    assert reply["screen"] == "LINKS_SENT"
    rows = db.scalars(select(WhatsAppOutbox).where(WhatsAppOutbox.kind.in_(["cta_url", "text"]))).all()
    links = [row for row in rows if row.kind == "cta_url"]
    codes = [row for row in rows if row.kind == "text" and row.params_json.get("sensitive")]
    assert len(links) == 2
    assert len(codes) == 2
    # Each link and its code are different messages.
    assert all(link.params_json["url"] for link in links)


def test_send_links_actually_reaches_the_sender_and_each_link_works_once(client, monkeypatch, db):
    user = _owner(db)
    _requirements(db, "Civil ID")
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")
    _documents(client, public_pem, token)
    dispatch_due(db, sender, now=datetime.utcnow(), max_attempts=3)

    link_message = sender.links()[0]
    code_message = next(m for m in sender.texts() if "code for" in m["body"])
    url_token = link_message["url"].rsplit("/upload/", 1)[1]
    code = code_message["body"].split("code for Civil ID is ")[1].split(".")[0]

    page = client.post(f"/upload/{url_token}", data={"code": code}, files={"file": ("civil.pdf", PDF, "application/pdf")})
    assert page.status_code == 200
    again = client.post(f"/upload/{url_token}", data={"code": code}, files={"file": ("civil.pdf", PDF, "application/pdf")})
    assert again.status_code == 404


def test_send_links_skips_approved_documents(client, monkeypatch, db):
    user = _owner(db)
    civil, land = _requirements(db, "Civil ID", "Land deed")
    checklist_for(db, user)
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.requirement_id == civil.id))
    doc.status = DocumentStatus.approved
    db.commit()
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")

    _documents(client, public_pem, token)

    links = db.scalars(select(WhatsAppOutbox).where(WhatsAppOutbox.kind == "cta_url")).all()
    assert len(links) == 1
    assert "Land deed" in links[0].params_json["body"]


def test_send_links_says_nothing_is_needed_when_everything_is_approved(client, monkeypatch, db):
    user = _owner(db)
    (civil,) = _requirements(db, "Civil ID")
    checklist_for(db, user)
    db.scalar(select(OwnerDocument).where(OwnerDocument.requirement_id == civil.id)).status = DocumentStatus.approved
    db.commit()
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")

    reply = _documents(client, public_pem, token)

    assert "Nothing needs uploading" in reply["data"]["message"]
    assert db.query(DocumentUploadLink).count() == 0


def test_send_links_caps_how_many_links_one_tap_can_create(client, monkeypatch, db):
    from app.services.whatsapp_flows import MAX_LINKS_PER_REQUEST

    user = _owner(db)
    _requirements(db, *[f"Document {n}" for n in range(MAX_LINKS_PER_REQUEST + 3)])
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")

    _documents(client, public_pem, token)

    assert db.query(DocumentUploadLink).count() == MAX_LINKS_PER_REQUEST


def test_sent_codes_and_links_are_redacted_from_the_outbox(client, monkeypatch, db):
    user = _owner(db)
    _requirements(db, "Civil ID")
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")
    _documents(client, public_pem, token)
    dispatch_due(db, sender, now=datetime.utcnow(), max_attempts=3)

    rows = db.scalars(select(WhatsAppOutbox).where(WhatsAppOutbox.kind.in_(["cta_url", "text"]))).all()
    assert rows and all(row.status == "sent" for row in rows)
    for row in rows:
        assert "url" not in (row.params_json or {})
        if row.params_json.get("sensitive"):
            assert row.params_json["body"] == "[redacted]"


def test_a_documents_link_for_a_user_is_bound_to_that_user(client, monkeypatch, db):
    user = _owner(db)
    _requirements(db, "Civil ID")
    _, public_pem = enable_whatsapp(monkeypatch)
    token = _dashboard_token(client, monkeypatch, db, user)
    _choose(client, public_pem, token, "my_documents")
    _documents(client, public_pem, token)

    link = db.scalars(select(DocumentUploadLink)).one()
    assert link.user_id == user.id


def test_a_contractor_only_sees_contractor_requirements(client, monkeypatch, db):
    user = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Omar Haddad", phone=f"+{WA_ID}")
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name="Haddad Builders"))
    identity = get_or_create_identity(db, WA_ID, now=datetime.utcnow())
    identity.user_id = user.id
    identity.role = "contractor"
    db.commit()
    _requirements(db, "Civil ID", role=UserRole.owner)
    _requirements(db, "Trade licence", role=UserRole.contractor)
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message("wamid.CONCHK", WA_ID, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    token = sender.flows()[0]["flow_token"]

    reply = _choose(client, public_pem, token, "my_documents")

    assert reply["data"]["checklist"] == "Trade licence: Upload needed"


# --- review notices ----------------------------------------------------------


def test_an_approval_queues_an_approved_template_in_the_users_language(db):
    user = _owner(db)
    user.language = Language.ar
    db.commit()
    decided = datetime.utcnow()

    enqueue_review_decision(
        db,
        user=user,
        document_id="doc-1",
        requirement_name="Civil ID",
        decision=DocumentStatus.approved,
        decided_at=decided,
        now=datetime.utcnow(),
    )
    db.commit()

    row = db.scalar(select(WhatsAppOutbox))
    assert row.kind == "template"
    assert row.template_name == "document_approved"
    assert row.params_json["language"] == "ar"
    assert row.params_json["components"][0]["parameters"][0]["text"] == "Civil ID"


def test_a_rejection_queues_the_rejected_template(db):
    user = _owner(db)
    enqueue_review_decision(
        db,
        user=user,
        document_id="doc-2",
        requirement_name="Civil ID",
        decision=DocumentStatus.rejected,
        decided_at=datetime.utcnow(),
        now=datetime.utcnow(),
    )
    db.commit()
    assert db.scalar(select(WhatsAppOutbox)).template_name == "document_rejected"


def test_a_review_that_is_retried_queues_only_once(db):
    user = _owner(db)
    decided = datetime(2026, 11, 23, 9, 0, 0)
    for _ in range(3):
        enqueue_review_decision(
            db, user=user, document_id="doc-3", requirement_name="Civil ID", decision=DocumentStatus.approved, decided_at=decided, now=datetime.utcnow()
        )
        db.commit()
    assert db.query(WhatsAppOutbox).count() == 1


def test_a_pending_decision_queues_nothing(db):
    user = _owner(db)
    enqueue_review_decision(
        db, user=user, document_id="doc-4", requirement_name="Civil ID", decision=DocumentStatus.pending, decided_at=datetime.utcnow(), now=datetime.utcnow()
    )
    db.commit()
    assert db.query(WhatsAppOutbox).count() == 0


def test_an_account_with_no_whatsapp_identity_is_skipped(db):
    user = User(email="web@example.com", password_hash="x", role=UserRole.owner)
    db.add(user)
    db.commit()
    enqueue_review_decision(
        db, user=user, document_id="doc-5", requirement_name="Civil ID", decision=DocumentStatus.approved, decided_at=datetime.utcnow(), now=datetime.utcnow()
    )
    db.commit()
    assert db.query(WhatsAppOutbox).count() == 0


def test_an_admin_approval_over_the_web_queues_the_whatsapp_notice(client, db):
    from app.auth.security import create_access_token, hash_password

    owner = _owner(db)
    (civil,) = _requirements(db, "Civil ID")
    checklist_for(db, owner)
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == owner.id))
    doc.status = DocumentStatus.pending
    doc.file_path = f"{owner.id}/{civil.id}/x.pdf"
    admin = User(email="admin@example.com", password_hash=hash_password("admin-pass-1"), role=UserRole.admin, email_verified=True)
    db.add(admin)
    db.commit()
    client.cookies.set("access_token", create_access_token(admin.id))

    response = client.post(
        "/admin/review/owner-documents",
        json={"owner_id": owner.id, "requirement_id": civil.id, "decision": "approved"},
    )

    assert response.status_code == 200
    row = db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.template_name == "document_approved"))
    assert row is not None
    assert row.recipient_wa_id == WA_ID
