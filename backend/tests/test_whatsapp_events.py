from datetime import datetime

from sqlalchemy import select

from app.models.whatsapp import EVENT_STATUS_FAILED, EVENT_STATUS_PROCESSED, WhatsAppMessageEvent
from app.services.whatsapp_events import (
    parse_webhook,
    record_events,
    register_inbound_handler,
)
from whatsapp_helpers import message_envelope, status_update, text_message

NOW = datetime(2026, 11, 23, 12, 0, 0)
SECRET_TEXT = "Tower A budget is 90000 KWD, do not leak"


def _events(db):
    return db.scalars(select(WhatsAppMessageEvent).order_by(WhatsAppMessageEvent.event_key)).all()


def test_parse_flattens_messages_and_statuses_into_one_event_each():
    body = message_envelope(
        text_message("wamid.IN1", "96512345678", SECRET_TEXT),
        statuses=[status_update("wamid.OUT1", "96512345678", "delivered")],
    )
    parsed = parse_webhook(body)

    assert [event.event_key for event in parsed] == ["inbound:wamid.IN1", "status:wamid.OUT1:delivered"]
    assert parsed[0].direction == "inbound"
    assert parsed[0].event_type == "text"
    assert parsed[1].direction == "status"
    assert parsed[1].event_type == "status_delivered"


def test_parse_skips_entries_without_ids():
    body = message_envelope({"from": "96512345678", "type": "text"}, statuses=[{"status": "sent"}])
    assert parse_webhook(body) == []


def test_parse_handles_a_body_with_no_entries():
    assert parse_webhook({}) == []


def test_recording_a_new_message_stores_an_event_row(db):
    result = record_events(db, message_envelope(text_message("wamid.IN1", "96512345678", "hi")), now=NOW)

    assert result.duplicates == 0
    assert len(result.new) == 1
    rows = _events(db)
    assert len(rows) == 1
    assert rows[0].provider_message_id == "wamid.IN1"
    assert rows[0].wa_id == "96512345678"
    assert rows[0].status == EVENT_STATUS_PROCESSED
    assert rows[0].received_at == NOW


def test_a_duplicate_delivery_adds_no_rows_and_runs_no_handler_twice(db):
    calls = []
    register_inbound_handler(lambda session, event, message: calls.append(message["id"]))
    body = message_envelope(text_message("wamid.DUP", "96512345678", "hi"))

    first = record_events(db, body, now=NOW)
    second = record_events(db, body, now=NOW)

    assert len(first.new) == 1
    assert second.new == []
    assert second.duplicates == 1
    assert calls == ["wamid.DUP"]
    assert db.query(WhatsAppMessageEvent).count() == 1


def test_a_status_redelivered_is_a_duplicate_but_a_new_status_is_not(db):
    first = message_envelope(statuses=[status_update("wamid.OUT", "96512345678", "sent")])
    later = message_envelope(statuses=[status_update("wamid.OUT", "96512345678", "read")])

    record_events(db, first, now=NOW)
    assert record_events(db, first, now=NOW).duplicates == 1
    assert record_events(db, later, now=NOW).duplicates == 0
    assert db.query(WhatsAppMessageEvent).count() == 2


def test_only_the_digest_of_the_message_is_stored_never_its_text(db):
    record_events(db, message_envelope(text_message("wamid.PII", "96512345678", SECRET_TEXT)), now=NOW)

    row = _events(db)[0]
    assert len(row.payload_sha256) == 64
    stored = " ".join(str(getattr(row, column.name)) for column in WhatsAppMessageEvent.__table__.columns)
    assert SECRET_TEXT not in stored
    assert "Tower A" not in stored


def test_the_digest_changes_when_the_same_id_carries_different_content(db):
    record_events(db, message_envelope(text_message("wamid.X", "96512345678", "one")), now=NOW)
    record_events(db, message_envelope(text_message("wamid.X", "96512345678", "two")), now=NOW)

    # Same id, so the second is recognised as a duplicate and not stored again.
    rows = _events(db)
    assert len(rows) == 1
    assert rows[0].payload_sha256 == parse_webhook(message_envelope(text_message("wamid.X", "96512345678", "one")))[0].payload_sha256


def test_a_handler_failure_is_recorded_without_raising_and_without_its_message(db, caplog):
    def broken(session, event, message):
        raise RuntimeError(f"boom with {SECRET_TEXT}")

    register_inbound_handler(broken)
    result = record_events(db, message_envelope(text_message("wamid.FAIL", "96512345678", "hi")), now=NOW)

    assert result.failed_handlers == 1
    row = _events(db)[0]
    assert row.status == EVENT_STATUS_FAILED
    assert row.last_error_code == "RuntimeError"
    assert SECRET_TEXT not in caplog.text
    assert SECRET_TEXT not in str(row.last_error_code)


def test_a_failed_handler_does_not_stop_later_messages_in_the_same_delivery(db):
    seen = []

    def flaky(session, event, message):
        if message["id"] == "wamid.1":
            raise ValueError("first one breaks")
        seen.append(message["id"])

    register_inbound_handler(flaky)
    body = message_envelope(
        text_message("wamid.1", "96512345678", "a"),
        text_message("wamid.2", "96512345678", "b"),
    )
    result = record_events(db, body, now=NOW)

    assert seen == ["wamid.2"]
    assert result.failed_handlers == 1
    statuses = {row.provider_message_id: row.status for row in _events(db)}
    assert statuses == {"wamid.1": EVENT_STATUS_FAILED, "wamid.2": EVENT_STATUS_PROCESSED}


def test_status_events_do_not_invoke_inbound_handlers(db):
    calls = []
    register_inbound_handler(lambda session, event, message: calls.append(message))

    record_events(db, message_envelope(statuses=[status_update("wamid.S", "96512345678", "delivered")]), now=NOW)

    assert calls == []
    assert _events(db)[0].status == EVENT_STATUS_PROCESSED
