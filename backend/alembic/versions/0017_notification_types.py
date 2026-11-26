"""Add the notification types the code sends but the notifications.type column did not allow.

Without these values MySQL rejects the insert ("Data truncated for column 'type'"). That made the owner's
publish return an error after the tender was already saved.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

OLD_TYPES = [
    "document_rejected", "document_approved", "verification_activated", "payment_activated", "payment_failed",
    "payment_override_granted", "payment_override_revoked", "contractor_suspended", "contractor_reactivated",
    "document_expiring", "tender_amendment", "drawing_revised", "clarification_asked", "clarification_answered",
    "bid_submitted", "bid_revised", "bid_withdrawn", "deadline_approaching", "tender_closed", "evaluation_ready",
    "award_won", "award_lost", "tender_cancelled", "tender_no_award", "owner_verification_activated",
    "owner_document_rejected", "owner_document_approved", "owner_suspended", "owner_reactivated",
    "project_suspended", "project_reactivated", "offer_suspended", "offer_reactivated",
]

# Values the code uses (app/models/enums.py NotificationType) that the column did not have.
NEW_TYPES = ["verification_rejected", "owner_verification_rejected", "tender_published"]


def _enum(values):
    return "ENUM(" + ", ".join("'" + v + "'" for v in values) + ")"


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute("ALTER TABLE notifications MODIFY type " + _enum(OLD_TYPES + NEW_TYPES) + " NOT NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute("ALTER TABLE notifications MODIFY type " + _enum(OLD_TYPES) + " NOT NULL")
