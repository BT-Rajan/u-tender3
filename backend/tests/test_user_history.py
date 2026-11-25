"""An admin can read every audited action on a user, both those done to them and those they did."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.audit import log_action


def _admin_client(db):
    from app.auth.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    client = TestClient(app)
    client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    return client


def test_history_lists_actions_on_a_user_and_actions_by_them(db):
    from app.models.enums import UserRole
    from app.models.user import User

    admin_client = _admin_client(db)
    admin = db.query(User).filter(User.role == UserRole.admin).one()
    owner = User(email="owner-history@example.com", password_hash=None, role=UserRole.owner, full_name="Layla")
    db.add(owner)
    db.commit()
    log_action(db, actor_id=admin.id, action="owner.suspend", target_type="owner_profile", target_id=owner.id, reason="test")
    log_action(db, actor_id=owner.id, action="tender.publish", target_type="project", target_id="some-project")

    response = admin_client.get(f"/admin/users/{owner.id}/history")

    assert response.status_code == 200
    actions = [row["action"] for row in response.json()]
    assert actions == ["tender.publish", "owner.suspend"]
    assert response.json()[1]["actor_name"] == "Admin"


def test_history_for_an_unknown_user_is_not_found(db):
    admin_client = _admin_client(db)

    assert admin_client.get("/admin/users/does-not-exist/history").status_code == 404
