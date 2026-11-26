"""Contractor sign-up and password reset that use a WhatsApp code or a 24-hour invitation link.

- Sign-up with a code: request a code for a number, then create the account with it.
- Finish a WhatsApp sign-up: open the 24-hour link and add an email and password.
- Forgot password: a code is sent on WhatsApp to the number on the account.

Every response that could reveal whether an account exists is the same for everyone.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.router import _set_auth_cookies
from app.auth.security import hash_password
from app.db import get_db
from app.models.contractor import ContractorProfile
from app.models.enums import UserRole
from app.models.onboarding import OTP_RESET, OTP_SIGNUP
from app.models.user import User
from app.schemas.user import UserOut
from app.services.documents import ensure_document_rows
from app.services.onboarding import (
    OnboardingError,
    check_code,
    create_code,
    normalize_phone,
    send_code,
    use_invite,
)
from app.services.whatsapp_client import WhatsAppSendError
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class CodeRequest(BaseModel):
    phone: str


class SignupWithCode(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=10)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=255)
    company_name: str = Field(min_length=2, max_length=255)


class CompleteInvite(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    new_password: str = Field(min_length=8, max_length=72)


def _email_in_use(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email)) is not None


def _send_or_fail(phone_digits: str, code: str) -> None:
    try:
        send_code(phone_digits, code)
    except OnboardingError as exc:
        raise HTTPException(status_code=503, detail=exc.message)
    except WhatsAppSendError:
        raise HTTPException(status_code=502, detail="Could not send the code on WhatsApp. Try again in a moment.")


@router.post("/contractor/code/request")
def request_signup_code(body: CodeRequest, db: Session = Depends(get_db)):
    try:
        digits = normalize_phone(body.phone)
    except OnboardingError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    if db.scalar(select(User.id).where(User.phone == f"+{digits}")) is not None:
        raise HTTPException(
            status_code=400,
            detail="This WhatsApp number already has an account. Log in, or use the link we sent on WhatsApp.",
        )
    code = create_code(db, digits, OTP_SIGNUP, now=datetime.utcnow())
    db.commit()
    _send_or_fail(digits, code)
    return {"sent": True, "expires_in_minutes": get_settings().otp_ttl_minutes}


@router.post("/contractor/signup", response_model=UserOut, status_code=201)
def signup_with_code(body: SignupWithCode, response: Response, db: Session = Depends(get_db)):
    try:
        digits = normalize_phone(body.phone)
    except OnboardingError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    if not check_code(db, digits, OTP_SIGNUP, body.code, now=datetime.utcnow()):
        raise HTTPException(status_code=400, detail="That code is not right or has expired. Ask for a new code.")
    email = str(body.email).strip().lower()
    if _email_in_use(db, email):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    if db.scalar(select(User.id).where(User.phone == f"+{digits}")) is not None:
        raise HTTPException(status_code=400, detail="This WhatsApp number already has an account.")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=UserRole.contractor,
        full_name=body.full_name.strip(),
        phone=f"+{digits}",
    )
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name=body.company_name.strip()))
    db.flush()
    ensure_document_rows(db, user.id)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, user.id)
    return user


@router.post("/contractor/complete-invite", response_model=UserOut)
def complete_invite(body: CompleteInvite, response: Response, db: Session = Depends(get_db)):
    """A contractor who signed up on WhatsApp adds an email and password here, using the 24-hour link."""
    user_id = use_invite(db, body.token, now=datetime.utcnow())
    if user_id is None:
        raise HTTPException(status_code=400, detail="This link has expired or was already used. Ask for a new link on WhatsApp.")
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.contractor:
        raise HTTPException(status_code=400, detail="This link is not valid.")
    if user.email:
        raise HTTPException(status_code=400, detail="This account already has a login. Log in with your email and password.")
    email = str(body.email).strip().lower()
    if _email_in_use(db, email):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user.email = email
    user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, user.id)
    return user


@router.post("/password-reset/request")
def request_reset_code(body: ResetRequest, db: Session = Depends(get_db)):
    """Always answers the same way, so it cannot be used to find out which emails have accounts."""
    email = str(body.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.phone:
        try:
            digits = normalize_phone(user.phone)
            code = create_code(db, digits, OTP_RESET, now=datetime.utcnow())
            db.commit()
            send_code(digits, code)
        except (OnboardingError, WhatsAppSendError):
            db.rollback()
    return {"sent": True, "message": "If an account uses this email, a code has been sent on WhatsApp."}


@router.post("/password-reset/confirm")
def confirm_reset_code(body: ResetConfirm, db: Session = Depends(get_db)):
    email = str(body.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.phone:
        raise HTTPException(status_code=400, detail="That code is not right or has expired.")
    try:
        digits = normalize_phone(user.phone)
    except OnboardingError:
        raise HTTPException(status_code=400, detail="That code is not right or has expired.")
    if not check_code(db, digits, OTP_RESET, body.code, now=datetime.utcnow()):
        raise HTTPException(status_code=400, detail="That code is not right or has expired.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
