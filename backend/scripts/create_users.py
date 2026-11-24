"""Create the admin, owner and contractor accounts for a deployment.

Owners and contractors are created with an approved profile so they can log in and
reach their dashboards. Contractors still need a payment override or an active
subscription before they can bid. Existing emails are skipped, so re-running is safe.

Passwords are read from the environment, so they are never stored in the repo:

    ADMIN_PASSWORD='...' USER_PASSWORD='...' .venv/bin/python scripts/create_users.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.auth.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.contractor import ContractorProfile  # noqa: E402
from app.models.enums import Language, UserRole, VerificationStatus  # noqa: E402
from app.models.owner import OwnerProfile  # noqa: E402
from app.models.user import User  # noqa: E402

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "")
if not ADMIN_PASSWORD or not USER_PASSWORD:
    sys.exit("Set ADMIN_PASSWORD and USER_PASSWORD in the environment before running this script.")

ADMIN = {"email": "admin@example.com", "password": ADMIN_PASSWORD, "full_name": "Site Admin", "role": UserRole.admin}
OWNERS = [
    {"email": f"owner{n}@example.com", "full_name": f"Owner {n}", "role": UserRole.owner} for n in (1, 2, 3)
]
CONTRACTORS = [
    {
        "email": f"contractor{n}@example.com",
        "full_name": f"Contractor {n}",
        "role": UserRole.contractor,
        "company_name": f"Contractor {n} Company",
        "primary_trade": "Other",
    }
    for n in (1, 2, 3)
]


def main() -> None:
    db = SessionLocal()
    created: list[str] = []
    skipped: list[str] = []
    try:
        for account in [ADMIN, *OWNERS, *CONTRACTORS]:
            if db.query(User).filter(User.email == account["email"]).first():
                skipped.append(account["email"])
                continue
            password = account.get("password", USER_PASSWORD)
            user = User(
                email=account["email"],
                password_hash=hash_password(password),
                role=account["role"],
                full_name=account["full_name"],
                language=Language.en,
                email_verified=True,
            )
            db.add(user)
            db.flush()
            if account["role"] == UserRole.owner:
                db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved))
            elif account["role"] == UserRole.contractor:
                db.add(
                    ContractorProfile(
                        user_id=user.id,
                        company_name=account["company_name"],
                        primary_trade=account["primary_trade"],
                        verification_status=VerificationStatus.approved,
                    )
                )
            created.append(account["email"])
        db.commit()
    finally:
        db.close()

    print("Created:", ", ".join(created) or "none")
    print("Already existed:", ", ".join(skipped) or "none")


if __name__ == "__main__":
    main()
