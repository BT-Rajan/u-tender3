"""Owners download the quotations contractors attached, before and after a tender is sealed."""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.offer_quotation import OfferQuotation
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.services import offer_quotations
from app.services.storage import get_storage

NOW = datetime.utcnow()
PDF = b"%PDF-1.4 the contractor's quotation"


def _signed_up_owner(email):
    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "Owner", "role": "owner"})
    assert r.status_code == 201, r.text
    return client, r.json()["id"]


def _approve(db, owner_id):
    profile = db.get(OwnerProfile, owner_id)
    profile.verification_status = VerificationStatus.approved
    db.commit()
    return db.get(User, owner_id)


def _tender(db, owner_id, *, tender_type=TenderType.owner_visible):
    project = Project(
        owner_id=owner_id,
        title="Warehouse fit-out",
        address="Block 3, Salmiya",
        trade="Civil works",
        bid_deadline=NOW + timedelta(days=10),
        status=ProjectStatus.open,
        tender_type=tender_type,
    )
    db.add(project)
    db.commit()
    return project


def _offer_with_quotation(db, project):
    contractor = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Omar", phone="+96522230001")
    db.add(contractor)
    db.flush()
    db.add(
        ContractorProfile(
            user_id=contractor.id,
            company_name="AA construction",
            primary_trade="Civil works",
            verification_status=VerificationStatus.approved,
            paid_until=NOW + timedelta(days=30),
        )
    )
    db.flush()
    offer = Offer(project_id=project.id, contractor_id=contractor.id, amount=Decimal("100000"), status=OfferStatus.submitted)
    db.add(offer)
    db.flush()
    key = f"{project.id}/{contractor.id}/quote.pdf"
    get_storage().save(offer_quotations.BUCKET, key, PDF, "application/pdf")
    quotation = OfferQuotation(
        offer_id=offer.id,
        project_id=project.id,
        contractor_id=contractor.id,
        file_name="quote.pdf",
        content_type="application/pdf",
        storage_key=key,
    )
    db.add(quotation)
    db.commit()
    return offer, quotation


def test_the_owner_sees_the_quotation_on_each_offer_and_can_download_it(db):
    client, owner_id = _signed_up_owner("quotes-owner@example.com")
    _approve(db, owner_id)
    project = _tender(db, owner_id)
    _offer, quotation = _offer_with_quotation(db, project)

    offers = client.get(f"/owner/projects/{project.id}/offers")
    assert offers.status_code == 200, offers.text
    assert offers.json()[0]["quotation"] == {"id": quotation.id, "file_name": "quote.pdf"}

    download = client.get(f"/owner/projects/{project.id}/quotations/{quotation.id}")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"].startswith("application/pdf")
    assert 'attachment; filename="quote.pdf"' in download.headers["content-disposition"]


def test_the_quotation_can_still_be_downloaded_while_the_tender_is_sealed(db):
    client, owner_id = _signed_up_owner("sealed-quotes-owner@example.com")
    _approve(db, owner_id)
    project = _tender(db, owner_id, tender_type=TenderType.sealed)
    _offer, quotation = _offer_with_quotation(db, project)

    download = client.get(f"/owner/projects/{project.id}/quotations/{quotation.id}")
    assert download.status_code == 200
    assert download.content == PDF


def test_another_owner_cannot_download_the_quotation(db):
    owner_client, owner_id = _signed_up_owner("tender-owner@example.com")
    _approve(db, owner_id)
    project = _tender(db, owner_id)
    _offer, quotation = _offer_with_quotation(db, project)

    stranger, stranger_id = _signed_up_owner("stranger-owner@example.com")
    _approve(db, stranger_id)

    assert stranger.get(f"/owner/projects/{project.id}/quotations/{quotation.id}").status_code == 404


def test_an_offer_without_a_quotation_says_so(db):
    client, owner_id = _signed_up_owner("plain-offer-owner@example.com")
    _approve(db, owner_id)
    project = _tender(db, owner_id)
    contractor = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Plain", phone="+96522230002")
    db.add(contractor)
    db.flush()
    db.add(ContractorProfile(user_id=contractor.id, company_name="Plain Builders", primary_trade="Civil works", verification_status=VerificationStatus.approved, paid_until=NOW + timedelta(days=30)))
    db.flush()
    db.add(Offer(project_id=project.id, contractor_id=contractor.id, amount=Decimal("90000"), status=OfferStatus.submitted))
    db.commit()

    offers = client.get(f"/owner/projects/{project.id}/offers").json()
    assert offers[0]["quotation"] is None
