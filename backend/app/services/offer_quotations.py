"""A contractor's quotation for a tender. The contractor uploads it on the WhatsApp offer form. It is held until
the offer is submitted, then linked to that offer."""

import uuid

from sqlalchemy.orm import Session

from app.models.offer import Offer
from app.models.offer_quotation import OfferQuotation
from app.models.project import Project
from app.models.user import User
from app.services import flow_media
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, sanitize_path_segment
from app.services.flow_documents import CONTENT_TYPES, _extension
from app.services.storage import Storage, get_storage

BUCKET = "offer-quotations"


def store_pending_quotation(
    db: Session, user: User, project: Project, documents, *, storage: Storage | None = None
) -> OfferQuotation:
    """Decrypt the one file the contractor attached and hold it for this tender. Replaces an earlier pending one."""
    if not isinstance(documents, list) or len(documents) != 1:
        raise flow_media.FlowMediaError("Upload one quotation file.")
    document = documents[0]
    if not isinstance(document, dict):
        raise flow_media.FlowMediaError("The upload is not a file.")

    name = str(document.get("file_name") or "quotation")
    extension = _extension(name)
    if extension not in ALLOWED_DRAWING_EXTENSIONS or extension not in CONTENT_TYPES:
        raise flow_media.FlowMediaError("This file type is not accepted. Use PDF, JPG, PNG or ZIP.")

    try:
        encrypted = flow_media.download_cdn_file(str(document.get("cdn_url", "")))
    except OSError as error:
        raise flow_media.FlowMediaError("The quotation could not be downloaded. Try again.") from error
    content = flow_media.decrypt_flow_media(encrypted, document.get("encryption_metadata") or {})
    if len(content) > flow_media.MAX_FILE_BYTES:
        raise flow_media.FlowMediaError("This file is larger than 25 MB.")

    content_type = CONTENT_TYPES[extension]
    key = f"{project.id}/{user.id}/{uuid.uuid4().hex}-{sanitize_path_segment(name)}"
    try:
        (storage or get_storage()).save(BUCKET, key, content, content_type)
    except OSError as error:
        raise flow_media.FlowMediaError("The quotation could not be saved. Try again.") from error

    _pending(db, user, project).delete(synchronize_session=False)
    row = OfferQuotation(
        project_id=project.id,
        contractor_id=user.id,
        file_name=name,
        content_type=content_type,
        storage_key=key,
    )
    db.add(row)
    db.commit()
    return row


def pending_quotation(db: Session, user: User, project: Project) -> OfferQuotation | None:
    """The quotation held for this tender and contractor, not yet linked to an offer."""
    return _pending(db, user, project).order_by(OfferQuotation.created_at.desc()).first()


def link_pending_quotation(db: Session, offer: Offer, user: User, project: Project) -> None:
    """Attach the held quotation to the offer that was just submitted."""
    _pending(db, user, project).update({"offer_id": offer.id}, synchronize_session=False)
    db.commit()


def _pending(db: Session, user: User, project: Project):
    return db.query(OfferQuotation).filter(
        OfferQuotation.project_id == project.id,
        OfferQuotation.contractor_id == user.id,
        OfferQuotation.offer_id.is_(None),
    )
