from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.contractor import ContractorProfile
from app.models.enums import Language, UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity
from app.services.documents import ensure_document_rows, ensure_owner_document_rows
from app.services.whatsapp_identity import normalise_wa_id

# Trades offered in the contractor Flow. A fixed list, because a Flow dropdown
# can't take free text. Labels are stored as primary_trade, matching how the
# web app already stores the trade.
TRADE_OPTIONS: tuple[str, ...] = (
    "General contracting",
    "Electrical",
    "Plumbing",
    "HVAC",
    "Civil works",
    "Finishing",
    "Fire safety",
    "Landscaping",
    "Other",
)

NAME_MIN = 2
NAME_MAX = 120
ADDRESS_MIN = 5
ADDRESS_MAX = 255
COMPANY_MAX = 255

CODE_INVALID = "invalid"
CODE_ALREADY_REGISTERED = "already_registered"
CODE_PHONE_IN_USE = "phone_in_use"

# Shown to the user when a registration can't be completed. Plain text is kept
# in English here; the Flow screens carry the bilingual copy.
MESSAGE_PHONE_IN_USE = (
    "This number is already linked to a U-Tender account. Please contact support to get access."
)
MESSAGE_ALREADY_REGISTERED = "This number already has an account. Send any message to open your dashboard."


class RegistrationError(Exception):
    """A registration that can't be completed. `code` is stable; `message` is safe to show the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _clean_text(value: object, field: str, minimum: int, maximum: int) -> str:
    text = " ".join(str(value or "").split())
    if not (minimum <= len(text) <= maximum):
        raise RegistrationError(
            CODE_INVALID, f"{field} must be between {minimum} and {maximum} characters."
        )
    return text


def _clean_language(value: object) -> Language:
    try:
        return Language(str(value))
    except ValueError as exc:
        raise RegistrationError(CODE_INVALID, "Choose English or Arabic.") from exc


def _clean_trade(value: object) -> str:
    if value not in TRADE_OPTIONS:
        raise RegistrationError(CODE_INVALID, "Choose a trade from the list.")
    return str(value)


def _phone_taken_by_another_account(db: Session, wa_id: str) -> bool:
    """Whether a web or other account already carries this number.

    Web accounts store the phone as typed, so formatting differs ("+965 1234 5678"
    vs "96512345678"). Candidates are narrowed by the last eight digits, then
    compared on digits only.
    """
    # Narrow by the last four digits, which are the least likely to be split by
    # spaces or dashes. The full comparison below is on digits only.
    candidates = db.scalars(
        select(User).where(User.phone.is_not(None), User.phone.like(f"%{wa_id[-4:]}"))
    ).all()
    for candidate in candidates:
        try:
            if normalise_wa_id(candidate.phone or "") == wa_id:
                return True
        except ValueError:
            continue
    return False


def _create_account(
    db: Session,
    identity: WhatsAppIdentity,
    session: WhatsAppFlowSession,
    *,
    role: UserRole,
    full_name: str,
    language: Language,
    now: datetime,
    address: str,
    contractor: dict[str, str] | None = None,
) -> User:
    """Create the user, its role profile, the document checklist, the identity link and the session completion.

    One transaction. Any failure rolls everything back, so a half-made account
    is never left behind. A second registration from the same number is stopped
    by the unique user_id on the identity, and that IntegrityError is reported
    as already_registered.
    """
    if identity.user_id is not None:
        raise RegistrationError(CODE_ALREADY_REGISTERED, MESSAGE_ALREADY_REGISTERED)
    if _phone_taken_by_another_account(db, identity.wa_id):
        raise RegistrationError(CODE_PHONE_IN_USE, MESSAGE_PHONE_IN_USE)

    try:
        user = User(
            email=None,
            password_hash=None,
            role=role,
            full_name=full_name,
            phone=identity.phone_e164,
            address=address,
            language=language,
            email_verified=False,
        )
        db.add(user)
        db.flush()

        if role == UserRole.owner:
            db.add(OwnerProfile(user_id=user.id))
            db.flush()
            ensure_owner_document_rows(db, user.id, commit=False)
        else:
            assert contractor is not None
            db.add(
                ContractorProfile(
                    user_id=user.id,
                    company_name=contractor["company_name"],
                    primary_trade=contractor["primary_trade"],
                )
            )
            db.flush()
            ensure_document_rows(db, user.id, commit=False)

        identity.user_id = user.id
        identity.role = role.value
        identity.last_seen_at = now
        session.completed_at = now
        session.state_json = None
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RegistrationError(CODE_ALREADY_REGISTERED, MESSAGE_ALREADY_REGISTERED) from exc
    except Exception:
        db.rollback()
        raise
    return user


def register_owner(
    db: Session,
    identity: WhatsAppIdentity,
    session: WhatsAppFlowSession,
    *,
    full_name: object,
    address: object,
    language: object,
    now: datetime,
) -> User:
    name = _clean_text(full_name, "Full name", NAME_MIN, NAME_MAX)
    place = _clean_text(address, "Address", ADDRESS_MIN, ADDRESS_MAX)
    return _create_account(
        db,
        identity,
        session,
        role=UserRole.owner,
        full_name=name,
        language=_clean_language(language),
        now=now,
        address=place,
    )


def register_contractor(
    db: Session,
    identity: WhatsAppIdentity,
    session: WhatsAppFlowSession,
    *,
    contact_name: object,
    company_name: object,
    primary_trade: object,
    address: object,
    language: object,
    now: datetime,
) -> User:
    contact = _clean_text(contact_name, "Contact name", NAME_MIN, NAME_MAX)
    company = _clean_text(company_name, "Company name", NAME_MIN, COMPANY_MAX)
    trade = _clean_trade(primary_trade)
    place = _clean_text(address, "Address", ADDRESS_MIN, ADDRESS_MAX)
    return _create_account(
        db,
        identity,
        session,
        role=UserRole.contractor,
        full_name=contact,
        language=_clean_language(language),
        now=now,
        address=place,
        contractor={"company_name": company, "primary_trade": trade},
    )
