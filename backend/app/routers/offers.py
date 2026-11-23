from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_contractor_profile, require_approved_contractor, require_marketplace_active_contractor
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from app.models.user import User
from app.schemas.offer import OfferCreate, OfferOut, OfferRevisionOut
from app.services import offer_service
from app.services.tender_service import TenderError

router = APIRouter(prefix="/projects/{project_id}/offers", tags=["offers"])


@router.get("/mine", response_model=OfferOut | None)
def my_offer(project_id: str, user: User = Depends(require_approved_contractor), db: Session = Depends(get_db)):
    return db.query(Offer).filter(Offer.project_id == project_id, Offer.contractor_id == user.id).first()


@router.get("/mine/history", response_model=list[OfferRevisionOut])
def my_offer_history(project_id: str, user: User = Depends(require_approved_contractor), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.project_id == project_id, Offer.contractor_id == user.id).first()
    if not offer:
        return []
    return (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_number.asc())
        .all()
    )


@router.post("", response_model=OfferOut)
def submit_offer(
    project_id: str,
    payload: OfferCreate,
    user: User = Depends(require_marketplace_active_contractor),
    db: Session = Depends(get_db),
):
    try:
        return offer_service.submit_offer(
            db,
            user,
            project_id,
            amount=payload.amount,
            timeline_estimate=payload.timeline_estimate,
            message=payload.message,
            now=datetime.utcnow(),
        )
    except TenderError as error:
        raise _offer_http_error(error)


def _offer_http_error(error: TenderError) -> HTTPException:
    if error.code in ("not_found",):
        return HTTPException(status_code=404, detail=error.message)
    return HTTPException(status_code=400, detail=error.message)


@router.post("/withdraw", response_model=OfferOut)
def withdraw_offer(project_id: str, user: User = Depends(require_approved_contractor), db: Session = Depends(get_db)):
    try:
        return offer_service.withdraw_offer(db, user, project_id, now=datetime.utcnow())
    except TenderError as error:
        raise _offer_http_error(error)
