"""Admin user management: every account in one list with search and filters, a detail view, and suspend or
reactivate. Contractor and owner suspensions call the same functions as the role pages, so the audit log and
notifications are identical whichever screen the admin used.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models.audit_log import AuditLog
from app.models.contractor import ContractorProfile
from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.routers.admin import OwnerSuspendPatch, SuspendPatch, set_owner_suspended, set_suspended

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

ROLE_VALUES = {role.value for role in UserRole}


def _profile_for(user: User, contractor: ContractorProfile | None, owner: OwnerProfile | None):
    if user.role == UserRole.contractor:
        return contractor
    if user.role == UserRole.owner:
        return owner
    return None


def _status_for(user: User, profile) -> str:
    if user.role == UserRole.admin:
        return "admin"
    if profile is None:
        return "no_profile"
    return profile.marketplace_status


def _row(user: User, contractor: ContractorProfile | None, owner: OwnerProfile | None) -> dict:
    profile = _profile_for(user, contractor, owner)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role.value,
        "company_name": contractor.company_name if user.role == UserRole.contractor and contractor else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "status": _status_for(user, profile),
        "is_suspended": bool(profile.is_suspended) if profile is not None else False,
    }


@router.get("/users")
def list_users(
    role: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Accounts, newest first. `status` is the account's marketplace status (for example suspended or verified_active)."""
    if role and role not in ROLE_VALUES:
        raise HTTPException(status_code=400, detail="Unknown role.")
    query = (
        db.query(User, ContractorProfile, OwnerProfile)
        .outerjoin(ContractorProfile, ContractorProfile.user_id == User.id)
        .outerjoin(OwnerProfile, OwnerProfile.user_id == User.id)
    )
    if role:
        query = query.filter(User.role == UserRole(role))
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(User.email.ilike(term), User.full_name.ilike(term), User.phone.ilike(term), ContractorProfile.company_name.ilike(term))
        )
    rows = query.order_by(User.created_at.desc(), User.id).all()
    items = [_row(user, contractor, owner) for user, contractor, owner in rows]
    if status:
        items = [item for item in items if item["status"] == status]
    return {"items": items[offset : offset + limit], "total": len(items), "limit": limit, "offset": offset}


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    contractor = db.get(ContractorProfile, user_id)
    owner = db.get(OwnerProfile, user_id)
    data = _row(user, contractor, owner)
    data.update({"language": user.language.value, "email_verified": user.email_verified, "can_log_in_with_password": bool(user.password_hash)})

    if user.role == UserRole.contractor and contractor is not None:
        data["contractor"] = {
            "verification_status": contractor.verification_status.value,
            "marketplace_status": contractor.marketplace_status,
            "payment_active": contractor.is_payment_active,
            "paid_until": contractor.paid_until.isoformat() if contractor.paid_until else None,
            "trial_until": contractor.trial_until.isoformat() if contractor.trial_until else None,
            "activation_due_at": contractor.activation_due_at.isoformat() if contractor.activation_due_at else None,
            "payment_override_active": contractor.payment_override_active,
        }
    if user.role == UserRole.owner and owner is not None:
        data["owner"] = {
            "verification_status": owner.verification_status.value,
            "marketplace_status": owner.marketplace_status,
            "project_count": db.query(Project).filter(Project.owner_id == user_id).count(),
        }

    history = db.query(AuditLog).filter(AuditLog.target_id == user_id).order_by(AuditLog.created_at.desc()).limit(20).all()
    data["recent_activity"] = [
        {
            "action": entry.action,
            "previous_value": entry.previous_value,
            "new_value": entry.new_value,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in history
    ]
    return data


class UserSuspendIn(BaseModel):
    suspended: bool


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: str, body: UserSuspendIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot suspend your own account.")
    if user.role == UserRole.contractor:
        set_suspended(contractor_id=user_id, payload=SuspendPatch(suspended=body.suspended), admin=admin, db=db)
    elif user.role == UserRole.owner:
        set_owner_suspended(owner_id=user_id, payload=OwnerSuspendPatch(suspended=body.suspended), admin=admin, db=db)
    else:
        raise HTTPException(status_code=400, detail="Admin accounts cannot be suspended from here.")
    return {"user_id": user_id, "is_suspended": body.suspended}
