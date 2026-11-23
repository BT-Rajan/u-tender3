from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.whatsapp import OUTBOX_DEAD, OUTBOX_FAILED, OUTBOX_PENDING, OUTBOX_SENT, WhatsAppOutbox
from app.services.whatsapp_client import WhatsAppSendError
from app.services.whatsapp_outbox import (
    BASE_BACKOFF_SECONDS,
    KIND_TEMPLATE,
    KIND_TEXT,
    MAX_BACKOFF_SECONDS,
    backoff_seconds,
    dispatch_due,
    enqueue,
)

NOW = datetime(2026, 11, 23, 12, 0, 0)
RECIPIENT = "96512345678"


class FakeSender:
    """Records every send. `script` is consumed one call at a time: an exception is raised, anything else is the message id."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[tuple] = []

    def _next(self, *args):
        self.calls.append(args)
        if self.script:
            outcome = self.script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return f"wamid.{len(self.calls)}"

    def send_text(self, to_wa_id, body):
        return self._next("text", to_wa_id, body)

    def send_template(self, to_wa_id, template_name, language_code, components=None):
        return self._next("template", to_wa_id, template_name, language_code, components)


def _transient():
    return WhatsAppSendError("temporary", transient=True, status_code=503)


def _permanent():
    return WhatsAppSendError("rejected", transient=False, status_code=400, error_code="132000")


def _row(db, dedupe_key="evt:1") -> WhatsAppOutbox:
    return db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.dedupe_key == dedupe_key))


def test_enqueue_stores_a_pending_row_with_only_the_params_it_was_given(db):
    row = enqueue(
        db,
        dedupe_key="doc:approved:1",
        recipient_wa_id=RECIPIENT,
        kind=KIND_TEMPLATE,
        now=NOW,
        template_name="document_approved",
        params={"language": "en", "components": []},
    )
    db.commit()

    stored = _row(db, "doc:approved:1")
    assert stored.id == row.id
    assert stored.status == OUTBOX_PENDING
    assert stored.attempts == 0
    assert stored.next_attempt_at == NOW
    assert stored.params_json == {"language": "en", "components": []}


def test_enqueue_with_the_same_dedupe_key_returns_the_existing_row(db):
    first = enqueue(db, dedupe_key="k", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "a"})
    db.commit()
    second = enqueue(db, dedupe_key="k", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "b"})
    db.commit()

    assert second.id == first.id
    assert db.query(WhatsAppOutbox).count() == 1


def test_enqueue_rejects_an_unknown_kind(db):
    with pytest.raises(ValueError):
        enqueue(db, dedupe_key="k", recipient_wa_id=RECIPIENT, kind="carrier-pigeon", now=NOW)


def test_a_template_without_a_name_is_rejected(db):
    with pytest.raises(ValueError):
        enqueue(db, dedupe_key="k", recipient_wa_id=RECIPIENT, kind=KIND_TEMPLATE, now=NOW)


def test_a_rolled_back_enqueue_never_reaches_the_sender(db):
    enqueue(db, dedupe_key="rolled-back", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "x"})
    db.rollback()

    sender = FakeSender()
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3)

    assert sender.calls == []
    assert stats == {"sent": 0, "retry": 0, "failed": 0, "dead": 0}


def test_dispatch_sends_a_due_row_and_records_the_message_id(db):
    enqueue(db, dedupe_key="evt:1", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "hi"})
    db.commit()

    sender = FakeSender(["wamid.SENT"])
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3)

    row = _row(db)
    assert stats["sent"] == 1
    assert row.status == OUTBOX_SENT
    assert row.provider_message_id == "wamid.SENT"
    assert row.attempts == 1
    assert row.sent_at == NOW
    assert sender.calls == [("text", RECIPIENT, "hi")]


def test_dispatch_routes_templates_with_their_language_and_components(db):
    components = [{"type": "body", "parameters": [{"type": "text", "text": "Tower A"}]}]
    enqueue(
        db,
        dedupe_key="tpl",
        recipient_wa_id=RECIPIENT,
        kind=KIND_TEMPLATE,
        now=NOW,
        template_name="offer_submitted",
        params={"language": "ar", "components": components},
    )
    db.commit()

    sender = FakeSender()
    dispatch_due(db, sender, now=NOW, max_attempts=3)

    assert sender.calls == [("template", RECIPIENT, "offer_submitted", "ar", components)]


def test_a_row_not_yet_due_is_left_alone(db):
    enqueue(db, dedupe_key="later", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW + timedelta(minutes=5), params={"body": "x"})
    db.commit()

    sender = FakeSender()
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3)

    assert sender.calls == []
    assert stats["sent"] == 0
    assert _row(db, "later").status == OUTBOX_PENDING


def test_a_transient_failure_schedules_a_retry_with_backoff(db):
    enqueue(db, dedupe_key="retry", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "x"})
    db.commit()

    sender = FakeSender([_transient()])
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3)

    row = _row(db, "retry")
    assert stats["retry"] == 1
    assert row.status == OUTBOX_PENDING
    assert row.attempts == 1
    assert row.next_attempt_at == NOW + timedelta(seconds=BASE_BACKOFF_SECONDS)
    assert row.last_error_code == "503"


def test_a_retried_row_is_not_sent_again_before_its_backoff_has_passed(db):
    enqueue(db, dedupe_key="retry", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "x"})
    db.commit()
    dispatch_due(db, FakeSender([_transient()]), now=NOW, max_attempts=3)

    sender = FakeSender()
    dispatch_due(db, sender, now=NOW + timedelta(seconds=10), max_attempts=3)
    assert sender.calls == []

    dispatch_due(db, sender, now=NOW + timedelta(seconds=BASE_BACKOFF_SECONDS), max_attempts=3)
    assert len(sender.calls) == 1
    assert _row(db, "retry").status == OUTBOX_SENT


def test_repeated_transient_failures_end_in_dead_after_max_attempts(db):
    enqueue(db, dedupe_key="dead", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "x"})
    db.commit()

    max_attempts = 3
    sender = FakeSender([_transient(), _transient(), _transient()])
    now = NOW
    for _ in range(max_attempts):
        dispatch_due(db, sender, now=now, max_attempts=max_attempts)
        now = now + timedelta(seconds=MAX_BACKOFF_SECONDS)

    row = _row(db, "dead")
    assert row.status == OUTBOX_DEAD
    assert row.attempts == max_attempts
    assert len(sender.calls) == max_attempts


def test_a_permanent_failure_is_not_retried(db):
    enqueue(db, dedupe_key="perm", recipient_wa_id=RECIPIENT, kind=KIND_TEMPLATE, now=NOW, template_name="bad", params={"language": "en"})
    db.commit()

    sender = FakeSender([_permanent()])
    stats = dispatch_due(db, sender, now=NOW, max_attempts=8)

    row = _row(db, "perm")
    assert stats["failed"] == 1
    assert row.status == OUTBOX_FAILED
    assert row.attempts == 1
    assert row.last_error_code == "132000"

    dispatch_due(db, sender, now=NOW + timedelta(days=1), max_attempts=8)
    assert len(sender.calls) == 1


def test_one_failing_row_does_not_stop_the_others(db):
    for key in ("a", "b", "c"):
        enqueue(db, dedupe_key=key, recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": key})
    db.commit()

    sender = FakeSender([_permanent(), "wamid.B", "wamid.C"])
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3)

    assert stats == {"sent": 2, "retry": 0, "failed": 1, "dead": 0}
    assert _row(db, "b").status == OUTBOX_SENT
    assert _row(db, "c").status == OUTBOX_SENT


def test_batch_size_limits_how_many_rows_one_run_sends(db):
    for index in range(5):
        enqueue(db, dedupe_key=f"batch-{index}", recipient_wa_id=RECIPIENT, kind=KIND_TEXT, now=NOW, params={"body": "x"})
    db.commit()

    sender = FakeSender()
    stats = dispatch_due(db, sender, now=NOW, max_attempts=3, batch_size=2)

    assert stats["sent"] == 2
    assert len(sender.calls) == 2


@pytest.mark.parametrize(
    "attempts, expected",
    [(1, 30), (2, 60), (3, 120), (4, 240), (20, MAX_BACKOFF_SECONDS)],
)
def test_backoff_doubles_and_is_capped(attempts, expected):
    assert backoff_seconds(attempts) == expected
