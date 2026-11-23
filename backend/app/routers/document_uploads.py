import html
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.contractor import ContractorProfile
from app.models.document import DocumentRequirement
from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.services.document_files import DocumentValidationError
from app.services.document_service import accept_document
from app.models.document_upload import DocumentUploadLink
from app.services.upload_links import (
    MESSAGES,
    LINK_INVALID,
    LINK_LOCKED,
    UploadLinkError,
    _sha256,
    consume_upload_link,
    verify_upload_link,
)

router = APIRouter(tags=["document-uploads"])

UPLOAD_LINK_INVALID_MESSAGE = MESSAGES[LINK_INVALID]

# Headers that keep the one-time token out of caches and out of outbound Referer
# headers, and keep the page out of search engines and frames.
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; img-src 'none'",
}

_STYLE = """
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f5f6f8;color:#14213d;}
main{max-width:460px;margin:0 auto;padding:24px 16px;}
h1{font-size:20px;margin:0 0 8px;}
p{line-height:1.5;margin:8px 0;}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08);}
label{display:block;font-weight:600;margin-top:16px;}
input{width:100%;box-sizing:border-box;font-size:18px;padding:12px;margin-top:6px;border:1px solid #c5ccd6;border-radius:8px;}
button{width:100%;margin-top:20px;font-size:17px;padding:14px;border:0;border-radius:10px;background:#14213d;color:#fff;}
.error{background:#fdecea;color:#8a1c12;padding:12px;border-radius:8px;}
.ok{background:#e8f6ee;color:#1d5c34;padding:12px;border-radius:8px;}
.muted{color:#5b6572;font-size:14px;}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex,nofollow'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main><div class='card'>{body}</div></main></body></html>"
    )


def _invalid_page(status: int, message: str = UPLOAD_LINK_INVALID_MESSAGE) -> HTMLResponse:
    body = f"<h1>Link not available</h1><p class='error'>{html.escape(message)}</p>"
    return HTMLResponse(_page("U-Tender upload", body), status_code=status, headers=_SECURITY_HEADERS)


def _active_user_for(db: Session, link: DocumentUploadLink) -> User | None:
    """The account behind the link, if it may still upload: not suspended and of a role that has a checklist."""
    user = db.get(User, link.user_id)
    if user is None:
        return None
    if user.role == UserRole.owner:
        profile = db.get(OwnerProfile, user.id)
        return user if profile is not None and not profile.is_suspended else None
    if user.role == UserRole.contractor:
        profile = db.get(ContractorProfile, user.id)
        return user if profile is not None and not profile.is_suspended else None
    return None


def _form(token: str, requirement_name: str, first_name: str, error: str | None = None) -> str:
    notice = f"<p class='error'>{html.escape(error)}</p>" if error else ""
    return (
        f"<h1>Upload {html.escape(requirement_name)}</h1>"
        f"<p>Hello {html.escape(first_name)}. Enter the 6-digit code from the WhatsApp message "
        "that sent you this link, then choose your file.</p>"
        f"{notice}"
        f"<form method='post' action='/upload/{html.escape(token)}' enctype='multipart/form-data'>"
        "<label for='code'>Code</label>"
        "<input id='code' name='code' inputmode='numeric' autocomplete='one-time-code' maxlength='6' required>"
        "<label for='file'>File (PDF, PNG or JPEG, up to 10 MB)</label>"
        "<input id='file' name='file' type='file' accept='application/pdf,image/png,image/jpeg' required>"
        "<button type='submit'>Upload</button>"
        "</form>"
        "<p class='muted'>This link works once and expires after 20 minutes.</p>"
    )


@router.get("/upload/{token}", response_class=HTMLResponse)
def upload_form(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Show the upload form for a valid link. The code is checked on submit, not here."""
    now = datetime.utcnow()
    link = _find_usable_link(db, token, now)
    if link is None:
        return _invalid_page(404)
    user = _active_user_for(db, link)
    requirement = db.get(DocumentRequirement, link.requirement_id)
    if user is None or requirement is None:
        return _invalid_page(404)
    first_name = (user.full_name or "").split(" ")[0] or "there"
    return HTMLResponse(
        _page("Upload document", _form(token, requirement.name, first_name)),
        headers=_SECURITY_HEADERS,
    )


@router.post("/upload/{token}", response_class=HTMLResponse)
async def upload_submit(
    token: str,
    code: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    now = datetime.utcnow()
    try:
        link = verify_upload_link(db, token=token, code=code, now=now)
    except UploadLinkError as error:
        if error.code == LINK_INVALID:
            return _invalid_page(404)
        if error.code == LINK_LOCKED:
            return _invalid_page(423, error.message)
        return _retry_form(token, db, error.message)

    user = _active_user_for(db, link)
    requirement = db.get(DocumentRequirement, link.requirement_id)
    if user is None or requirement is None:
        return _invalid_page(404)

    content = await file.read()
    kind = "owner" if user.role == UserRole.owner else "contractor"
    try:
        accept_document(
            db,
            kind=kind,
            user_id=user.id,
            requirement_id=requirement.id,
            filename=file.filename,
            content=content,
            channel="whatsapp",
            now=now,
        )
    except DocumentValidationError as error:
        # The link is not used up by a bad file, so the user can try again with a corrected one.
        return _retry_form(token, db, str(error), user=user, requirement=requirement)
    except LookupError:
        # The account has no checklist row for this requirement, so there is nothing to upload into.
        return _invalid_page(404)

    consume_upload_link(db, link, now=now)
    body = (
        "<h1>Document received</h1>"
        f"<p class='ok'>{html.escape(requirement.name)} was uploaded and is with the review team.</p>"
        "<p class='muted'>You will get a WhatsApp message when it has been reviewed. You can close this page.</p>"
    )
    return HTMLResponse(_page("Upload received", body), headers=_SECURITY_HEADERS)


def _find_usable_link(db: Session, token: str, now: datetime) -> DocumentUploadLink | None:
    if not token:
        return None
    link = db.query(DocumentUploadLink).filter(DocumentUploadLink.token_hash == _sha256(token)).first()
    if link is None or link.used_at is not None or link.revoked_at is not None or link.expires_at <= now:
        return None
    return link


def _retry_form(
    token: str,
    db: Session,
    error: str,
    *,
    user: User | None = None,
    requirement: DocumentRequirement | None = None,
) -> HTMLResponse:
    """Show the form again with the error. The link is still valid, so the user keeps their place."""
    now = datetime.utcnow()
    link = _find_usable_link(db, token, now)
    if link is None:
        return _invalid_page(404)
    user = user or _active_user_for(db, link)
    requirement = requirement or db.get(DocumentRequirement, link.requirement_id)
    if user is None or requirement is None:
        return _invalid_page(404)
    first_name = (user.full_name or "").split(" ")[0] or "there"
    return HTMLResponse(
        _page("Upload document", _form(token, requirement.name, first_name, error=error)),
        status_code=400,
        headers=_SECURITY_HEADERS,
    )
