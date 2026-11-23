from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.contractor import ContractorProfile
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.document_upload import DocumentUploadLink, DocumentVersion
from app.models.enums import DocumentStatus, UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.services.upload_links import (
    CODE_WRONG,
    LINK_INVALID,
    LINK_LOCKED,
    UploadLinkError,
    consume_upload_link,
    issue_upload_link,
    verify_upload_link,
)

NOW = datetime.utcnow()
PDF = b"%PDF-1.4\n%%EOF\n"


@pytest.fixture
def owner_and_requirement(db):
    user = User(email=None, password_hash=None, role=UserRole.owner, full_name="Layla Al-Sabah", phone="+96511112222")
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id))
    requirement = DocumentRequirement(name="Civil ID", applies_to=UserRole.owner, is_active=True)
    db.add(requirement)
    db.flush()
    db.add(OwnerDocument(owner_id=user.id, requirement_id=requirement.id))
    db.commit()
    return user, requirement


def test_the_raw_token_and_code_are_never_stored(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)

    link = db.get(DocumentUploadLink, issued.link_id)
    stored = " ".join(str(getattr(link, c.name)) for c in DocumentUploadLink.__table__.columns)
    assert issued.token not in stored
    assert issued.code not in stored
    assert len(link.token_hash) == 64 and len(link.code_hash) == 64


def test_a_code_is_six_digits(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    for _ in range(20):
        issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
        assert len(issued.code) == 6 and issued.code.isdigit()


def test_the_link_is_bound_to_the_user_and_requirement(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    link = verify_upload_link(db, token=issued.token, code=issued.code, now=NOW)
    assert link.user_id == user.id
    assert link.requirement_id == requirement.id


def test_the_right_code_verifies(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    assert verify_upload_link(db, token=issued.token, code=issued.code, now=NOW).id == issued.link_id


def test_a_code_from_one_link_does_not_open_another(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    first = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    second = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    # Only the newest link is live, so the first token now fails outright.
    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token=first.token, code=first.code, now=NOW)
    assert excinfo.value.code == LINK_INVALID
    assert verify_upload_link(db, token=second.token, code=second.code, now=NOW).id == second.link_id


def test_issuing_a_new_link_revokes_the_old_one_for_the_same_requirement(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    old = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    assert db.get(DocumentUploadLink, old.link_id).revoked_at is not None


def test_a_wrong_code_is_refused_and_counted(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    wrong = "000000" if issued.code != "000000" else "111111"

    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token=issued.token, code=wrong, now=NOW)

    assert excinfo.value.code == CODE_WRONG
    assert db.get(DocumentUploadLink, issued.link_id).wrong_code_count == 1


def test_the_link_locks_after_the_maximum_number_of_wrong_codes(db, owner_and_requirement, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_link_max_wrong_codes", 3)
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    wrong = "000000" if issued.code != "000000" else "111111"

    codes = []
    for _ in range(3):
        with pytest.raises(UploadLinkError) as excinfo:
            verify_upload_link(db, token=issued.token, code=wrong, now=NOW)
        codes.append(excinfo.value.code)

    assert codes == [CODE_WRONG, CODE_WRONG, LINK_LOCKED]
    # Once locked, even the right code is refused.
    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token=issued.token, code=issued.code, now=NOW)
    assert excinfo.value.code == LINK_INVALID


def test_an_expired_link_is_refused(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    later = issued.expires_at + timedelta(seconds=1)
    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token=issued.token, code=issued.code, now=later)
    assert excinfo.value.code == LINK_INVALID


def test_a_link_lives_for_the_configured_minutes(db, owner_and_requirement, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_link_ttl_minutes", 7)
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    assert issued.expires_at == NOW + timedelta(minutes=7)


def test_a_used_link_is_refused_a_second_time(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=NOW)
    link = verify_upload_link(db, token=issued.token, code=issued.code, now=NOW)
    consume_upload_link(db, link, now=NOW)

    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token=issued.token, code=issued.code, now=NOW)
    assert excinfo.value.code == LINK_INVALID


def test_an_unknown_or_empty_token_is_refused_without_saying_why(db):
    with pytest.raises(UploadLinkError) as excinfo:
        verify_upload_link(db, token="never-issued", code="123456", now=NOW)
    assert excinfo.value.code == LINK_INVALID
    with pytest.raises(UploadLinkError):
        verify_upload_link(db, token="", code="", now=NOW)


# --- the upload page ----------------------------------------------------------


def _issue(db, owner_and_requirement):
    user, requirement = owner_and_requirement
    return issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=datetime.utcnow())


def test_get_shows_the_form_for_a_valid_link_with_security_headers(client, db, owner_and_requirement):
    issued = _issue(db, owner_and_requirement)
    response = client.get(f"/upload/{issued.token}")

    assert response.status_code == 200
    assert "Civil ID" in response.text
    assert "name='code'" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in response.headers["x-robots-tag"]


def test_get_for_an_unknown_token_is_a_generic_404(client):
    response = client.get("/upload/not-a-real-token")
    assert response.status_code == 404
    assert "no longer valid" in response.text


def test_get_does_not_burn_the_link(client, db, owner_and_requirement):
    issued = _issue(db, owner_and_requirement)
    client.get(f"/upload/{issued.token}")
    client.get(f"/upload/{issued.token}")
    assert db.get(DocumentUploadLink, issued.link_id).used_at is None


def test_get_refuses_a_suspended_owner(client, db, owner_and_requirement):
    user, _ = owner_and_requirement
    issued = _issue(db, owner_and_requirement)
    profile = db.get(OwnerProfile, user.id)
    profile.is_suspended = True
    db.commit()

    assert client.get(f"/upload/{issued.token}").status_code == 404


def test_a_valid_upload_stores_privately_marks_pending_versions_and_burns_the_link(client, db, owner_and_requirement):
    user, requirement = owner_and_requirement
    issued = _issue(db, owner_and_requirement)

    response = client.post(
        f"/upload/{issued.token}",
        data={"code": issued.code},
        files={"file": ("civil-id.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 200
    assert "Document received" in response.text
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id))
    assert doc.status == DocumentStatus.pending
    assert doc.file_path.startswith(f"{user.id}/{requirement.id}/")
    assert "civil-id" not in doc.file_path
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.user_id == user.id))
    assert version.channel == "whatsapp"
    assert version.mime_type == "application/pdf"
    assert db.get(DocumentUploadLink, issued.link_id).used_at is not None


def test_the_uploaded_file_is_retrievable_only_through_the_storage_layer(client, db, owner_and_requirement):
    from app.services.storage import get_storage

    user, _ = owner_and_requirement
    issued = _issue(db, owner_and_requirement)
    client.post(f"/upload/{issued.token}", data={"code": issued.code}, files={"file": ("a.pdf", PDF, "application/pdf")})

    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id))
    assert get_storage().download("owner-documents", doc.file_path) == PDF


def test_a_wrong_code_shows_the_form_again_and_keeps_the_link(client, db, owner_and_requirement):
    issued = _issue(db, owner_and_requirement)
    wrong = "000000" if issued.code != "000000" else "111111"

    response = client.post(
        f"/upload/{issued.token}",
        data={"code": wrong},
        files={"file": ("a.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 400
    assert "not right" in response.text
    assert db.get(DocumentUploadLink, issued.link_id).used_at is None


def test_a_refused_file_does_not_burn_the_link_or_touch_the_document(client, db, owner_and_requirement):
    user, _ = owner_and_requirement
    issued = _issue(db, owner_and_requirement)

    response = client.post(
        f"/upload/{issued.token}",
        data={"code": issued.code},
        files={"file": ("virus.pdf", b"MZ\x90 not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "not a PDF" in response.text
    assert db.get(DocumentUploadLink, issued.link_id).used_at is None
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id))
    assert doc.status == DocumentStatus.not_submitted
    assert doc.file_path is None


def test_a_second_upload_on_the_same_link_is_refused(client, db, owner_and_requirement):
    issued = _issue(db, owner_and_requirement)
    client.post(f"/upload/{issued.token}", data={"code": issued.code}, files={"file": ("a.pdf", PDF, "application/pdf")})

    response = client.post(f"/upload/{issued.token}", data={"code": issued.code}, files={"file": ("b.pdf", PDF, "application/pdf")})
    assert response.status_code == 404


def test_replacing_a_document_supersedes_the_old_version_and_keeps_it(client, db, owner_and_requirement):
    user, _ = owner_and_requirement
    first = _issue(db, owner_and_requirement)
    client.post(f"/upload/{first.token}", data={"code": first.code}, files={"file": ("a.pdf", PDF, "application/pdf")})
    first_path = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id)).file_path

    # A rejection sends the user back to upload again.
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id))
    doc.status = DocumentStatus.rejected
    db.commit()

    second = _issue(db, owner_and_requirement)
    client.post(f"/upload/{second.token}", data={"code": second.code}, files={"file": ("b.pdf", PDF + b"v2", "application/pdf")})

    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.user_id == user.id).order_by(DocumentVersion.uploaded_at)).all()
    assert len(versions) == 2
    old = next(v for v in versions if v.file_path == first_path)
    assert old.superseded_at is not None
    assert db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id)).status == DocumentStatus.pending


def test_a_contractor_upload_goes_to_the_contractor_bucket_and_row(client, db):
    user = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Omar Haddad", phone="+96522223333")
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name="Haddad Builders"))
    requirement = DocumentRequirement(name="Trade licence", applies_to=UserRole.contractor, is_active=True)
    db.add(requirement)
    db.flush()
    db.add(ContractorDocument(contractor_id=user.id, requirement_id=requirement.id))
    db.commit()
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=datetime.utcnow())

    client.post(f"/upload/{issued.token}", data={"code": issued.code}, files={"file": ("licence.pdf", PDF, "application/pdf")})

    doc = db.scalar(select(ContractorDocument).where(ContractorDocument.contractor_id == user.id))
    assert doc.status == DocumentStatus.pending
    from app.services.storage import get_storage

    assert get_storage().download("contractor-documents", doc.file_path) == PDF


def test_an_upload_for_a_requirement_with_no_checklist_row_gets_the_generic_page(client, db):
    # A link whose user never got a row for the requirement must not turn into a 500.
    user = User(email=None, password_hash=None, role=UserRole.owner, full_name="Noor Ali", phone="+96533334444")
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id))
    requirement = DocumentRequirement(name="Land deed", applies_to=UserRole.owner, is_active=True)
    db.add(requirement)
    db.commit()
    issued = issue_upload_link(db, user_id=user.id, requirement_id=requirement.id, now=datetime.utcnow())

    response = client.post(f"/upload/{issued.token}", data={"code": issued.code}, files={"file": ("d.pdf", PDF, "application/pdf")})

    assert response.status_code == 404
    assert "no longer valid" in response.text
