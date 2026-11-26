"""The application's time is Kuwait time. Web deadlines are typed in Kuwait time and stored as UTC; the
WhatsApp and report output shows Kuwait time."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.services.tender_service import to_utc_naive


def test_a_web_deadline_without_a_zone_is_kuwait_time():
    # 14:00 in Kuwait is 11:00 UTC (Kuwait is UTC+3 all year).
    assert to_utc_naive("2026-12-01T14:00") == datetime(2026, 12, 1, 11, 0)
    assert to_utc_naive("2026-12-01T14:00:00") == datetime(2026, 12, 1, 11, 0)


def test_a_deadline_with_a_zone_is_converted_to_utc():
    assert to_utc_naive("2026-12-01T11:00:00Z") == datetime(2026, 12, 1, 11, 0)
    assert to_utc_naive("2026-12-01T14:00:00+03:00") == datetime(2026, 12, 1, 11, 0)
    assert to_utc_naive(datetime(2026, 12, 1, 14, 0)) == datetime(2026, 12, 1, 11, 0)


def test_the_summary_report_times_carry_the_kuwait_offset(db):
    db.add(User(email="admin-kuwait@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": "admin-kuwait@example.com", "password": "adminpass123"}).status_code == 200

    body = client.get("/admin/reports/summary").json()

    assert body["generated_at"].endswith("+03:00")
