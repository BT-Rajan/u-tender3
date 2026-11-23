from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.enums import DocumentStatus, UserRole
from app.models.user import User
from app.models.whatsapp import WhatsAppIdentity
from app.services import whatsapp_outbox
from app.services.document_files import storage_path, validate_document
from app.models.document_upload import DocumentVersion
from app.services.documents import ensure_document_rows, ensure_owner_document_rows
from app.services.storage import get_storage

OwnerKind = Literal["owner", "contractor"]
Channel = Literal["web", "whatsapp"]

# The bucket names are the ones the existing web upload already used, so files
# uploaded before this change stay where the admin review expects them.
BUCKET = {"contractor": "contractor-documents", "owner": "owner-documents"}


@dataclass(frozen=True)
class ChecklistItem:
    requirement_id: str
    name: str
    status: DocumentStatus
    admin_note: str | None

    @property
    def needs_upload(self) -> bool:
        return self.status in (DocumentStatus.not_submitted, DocumentStatus.rejected)


def _document_row(db: Session, kind: OwnerKind, user_id: str, requirement_id: str):
    if kind == "owner":
        return db.scalar(
            select(OwnerDocument).where(OwnerDocument.owner_id == user_id, OwnerDocument.requirement_id == requirement_id)
        )
    return db.scalar(
        select(ContractorDocument).where(
            ContractorDocument.contractor_id == user_id, ContractorDocument.requirement_id == requirement_id
        )
    )


def accept_document(
    db: Session,
    *,
    kind: OwnerKind,
    user_id: str,
    requirement_id: str,
    filename: str | None,
    content: bytes,
    channel: Channel,
    now: datetime,
):
    """Validate, store privately, version, and mark a document pending review. Used by web and WhatsApp uploads alike.

    Raises DocumentValidationError before anything is written, so a refused file
    leaves the existing document and its history untouched.
    """
    validated = validate_document(filename, content)

    doc = _document_row(db, kind, user_id, requirement_id)
    if doc is None:
        raise LookupError("Document requirement not found for this account.")

    path = storage_path(user_id, requirement_id, validated.extension)
    get_storage().save(BUCKET[kind], path, content, validated.mime_type)

    previous_path = doc.file_path
    if previous_path:
        for version in db.scalars(select(DocumentVersion).where(DocumentVersion.file_path == previous_path)).all():
            version.superseded_at = now
    db.add(
        DocumentVersion(
            owner_kind=kind,
            user_id=user_id,
            requirement_id=requirement_id,
            file_path=path,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            channel=channel,
            uploaded_at=now,
        )
    )

    doc.file_path = path
    doc.status = DocumentStatus.pending
    doc.submitted_at = now
    doc.admin_note = None
    doc.expires_on = None
    db.commit()
    db.refresh(doc)
    return doc


def checklist_for(db: Session, user: User) -> list[ChecklistItem]:
    """The documents this user must provide: active requirements for their role, with each one's current status.

    Rows are created on demand so an account that predates a new requirement
    still gets it.
    """
    if user.role == UserRole.owner:
        ensure_owner_document_rows(db, user.id)
        kind: OwnerKind = "owner"
    else:
        ensure_document_rows(db, user.id)
        kind = "contractor"

    requirements = db.scalars(
        select(DocumentRequirement)
        .where(DocumentRequirement.is_active.is_(True), DocumentRequirement.applies_to == user.role)
        .order_by(DocumentRequirement.name)
    ).all()

    items: list[ChecklistItem] = []
    for requirement in requirements:
        doc = _document_row(db, kind, user.id, requirement.id)
        status = doc.status if doc is not None else DocumentStatus.not_submitted
        note = doc.admin_note if doc is not None else None
        items.append(ChecklistItem(requirement.id, requirement.name, status, note))
    return items


def review_recipient_wa_id(db: Session, user_id: str) -> str | None:
    identity = db.scalar(select(WhatsAppIdentity).where(WhatsAppIdentity.user_id == user_id))
    return identity.wa_id if identity else None


def enqueue_review_decision(
    db: Session,
    *,
    user: User,
    document_id: str,
    requirement_name: str,
    decision: DocumentStatus,
    decided_at: datetime,
    now: datetime,
) -> None:
    """Queue the approved or rejected notice for WhatsApp.

    A review can happen days after the upload, outside the 24-hour window, so
    this is sent as an approved template. The dedupe key includes the decision
    time, so the same review queues once even if the admin action is retried.
    Accounts with no WhatsApp identity are skipped, and the in-app notice still
    goes out as before.
    """
    if decision not in (DocumentStatus.approved, DocumentStatus.rejected):
        return
    wa_id = review_recipient_wa_id(db, user.id)
    if wa_id is None:
        return

    settings = get_settings()
    template = (
        settings.whatsapp_template_document_approved
        if decision == DocumentStatus.approved
        else settings.whatsapp_template_document_rejected
    )
    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"doc-review:{document_id}:{decided_at.isoformat()}",
        recipient_wa_id=wa_id,
        kind=whatsapp_outbox.KIND_TEMPLATE,
        now=now,
        template_name=template,
        params={
            "language": user.language.value if user.language else "en",
            "components": [{"type": "body", "parameters": [{"type": "text", "text": requirement_name[:200]}]}],
        },
    )
