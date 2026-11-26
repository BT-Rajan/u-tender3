"""Create a fully approved demo dataset on a running U-Tender backend.

Creates 3 owners and 3 contractors, runs each through the app's own
verification flow (documents uploaded, admin approves every document,
admin approves the profile, contractors get a payment override so bidding
works without a subscription), and opens one project per owner so contractors can
bid straight away.

Run by install.sh after the API is up. Can also be run by hand:

    backend/.venv/bin/python backend/scripts/create_demo_accounts.py \
        --api-url http://127.0.0.1:8001 --password 'Demo#2026' \
        --admin-email admin@example.com --admin-password 'AdminPass1'

If the admin account does not exist it is created directly in the database
(admin signup is intentionally not self-serve), using the app's own
password hashing. Run it once against a database without demo data: the
projects have no natural key, so a second run creates them again.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import httpx

# Make `app.*` importable when this file is run directly from backend/.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

FAKE_PDF = b"%PDF-1.4\n%demo document\n"

OWNERS = [
    {"email": "owner1@demo.example.com", "full_name": "Mohammed Al-Sabah"},
    {"email": "owner2@demo.example.com", "full_name": "Fahad Al-Rashidi"},
    {"email": "owner3@demo.example.com", "full_name": "Yousef Al-Azmi"},
]

CONTRACTORS = [
    {"email": "contractor1@demo.example.com", "full_name": "Ahmad Al-Fadhli",
     "company_name": "Al Diyar General Trading & Contracting Co. W.L.L.",
     "primary_trade": "General Contracting", "service_area": "Kuwait City, Hawally, Salmiya"},
    {"email": "contractor2@demo.example.com", "full_name": "Bader Al-Enezi",
     "company_name": "Gulf Coast MEP Contracting Co.",
     "primary_trade": "MEP (Mechanical/Electrical/Plumbing)", "service_area": "Fintas, Mangaf, Ahmadi"},
    {"email": "contractor3@demo.example.com", "full_name": "Nasser Al-Otaibi",
     "company_name": "Al Manara Finishing & Interiors",
     "primary_trade": "Finishing & Interior Fit-Out", "service_area": "Jabriya, Salwa, Rumaithiya"},
]

PROJECTS = [
    ("Villa Renovation - Block 4, Salmiya", "Block 4, Street 12, Salmiya, Kuwait",
     "Full interior renovation of a 2-floor villa: flooring, painting and kitchen remodel.",
     "Finishing & Interior Fit-Out", 12),
    ("New Majlis Construction - Jabriya", "Plot 7, Block 9, Jabriya, Kuwait",
     "Construction of a new majlis extension, approx. 120 sqm, with AC ducting and electrical.",
     "General Contracting", 14),
    ("Mosque AC System Upgrade - Fintas", "Al-Fintas District, near Block 3, Kuwait",
     "Replacement of the central AC system serving the prayer hall.",
     "MEP (Mechanical/Electrical/Plumbing)", 7),
]

CONTRACTOR_REQUIREMENTS = [
    ("Commercial License", "Kuwait Municipality commercial license for the contracting company."),
    ("Chamber of Commerce Certificate", "Kuwait Chamber of Commerce and Industry membership certificate."),
]


def log(msg):
    print(f"  {msg}", flush=True)


def step(msg):
    print(f"\n==> {msg}", flush=True)


def check(r, context):
    if r.status_code >= 400:
        raise RuntimeError(f"{context} failed: {r.status_code} {r.text}")
    return r


class Api:
    def __init__(self, base):
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=30)

    def login(self, email, password):
        check(self.http.post("/auth/login", json={"email": email, "password": password}), "login")

    def signup_or_login(self, email, password, full_name, role, company_name=None):
        payload = {"email": email, "password": password, "full_name": full_name, "role": role}
        if company_name:
            payload["company_name"] = company_name
        r = self.http.post("/auth/signup", json=payload)
        if r.status_code == 201:
            log(f"signed up {email}")
        elif r.status_code == 400 and "already" in r.text.lower():
            self.login(email, password)
            log(f"{email} already exists -- logged in")
        else:
            check(r, f"signup {email}")
        return self.http.get("/auth/me").json()["id"]


def upload_requirements(api, requirements_path, upload_tmpl, submit_path, submit_payload=None):
    for req in check(api.http.get(requirements_path), "list requirements").json():
        check(
            api.http.post(upload_tmpl.format(id=req["id"]), files={"file": ("doc.pdf", FAKE_PDF, "application/pdf")}),
            f"upload {req['name']}",
        )
    check(api.http.post(submit_path, json=submit_payload or {}), f"submit {submit_path}")


def approve_documents(admin, entity_id, detail_path, review_path, id_field):
    body = check(admin.http.get(detail_path), "load documents").json()
    docs = body["documents"] if isinstance(body, dict) else body
    for d in docs:
        check(
            admin.http.post(review_path, json={id_field: entity_id, "requirement_id": d["requirement_id"], "decision": "approved"}),
            "approve document",
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--password", required=True, help="Password given to every demo account.")
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-password", required=True)
    a = p.parse_args()

    # Make sure the admin exists. Admin signup is not public, so create it
    # with the app's own hashing rather than through the API.
    step("Admin account")
    from app.auth.security import hash_password
    from app.db import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == a.admin_email).first():
            db.add(User(email=a.admin_email, password_hash=hash_password(a.admin_password),
                        role=UserRole.admin, full_name="Demo Admin", email_verified=True))
            db.commit()
            log(f"created admin {a.admin_email}")
        else:
            log(f"admin {a.admin_email} already exists")
    finally:
        db.close()

    admin = Api(a.api_url)
    admin.login(a.admin_email, a.admin_password)
    log("logged in as admin")

    step("Contractor document requirements")
    existing = {r["name"] for r in check(admin.http.get("/admin/requirements"), "list admin requirements").json()}
    for name, desc in CONTRACTOR_REQUIREMENTS:
        if name not in existing:
            check(admin.http.post("/admin/requirements",
                                  json={"name": name, "description": desc, "is_required": True, "applies_to": "contractor"}),
                  f"add requirement {name}")
            log(f"added {name}")

    step("Owners (3, all approved)")
    owner_ids = []
    for o in OWNERS:
        api = Api(a.api_url)
        oid = api.signup_or_login(o["email"], a.password, o["full_name"], "owner")
        upload_requirements(api, "/owner/requirements", "/owner/documents/{id}/upload", "/owner/submit-for-review")
        approve_documents(admin, oid, f"/admin/owners/{oid}", "/admin/review/owner-documents", "owner_id")
        check(admin.http.post(f"/admin/review/owners/{oid}/approve"), "approve owner")
        owner_ids.append((oid, api))
        log(f"approved {o['full_name']} <{o['email']}>")

    step("Contractors (3, all approved and active)")
    contractor_apis = []
    for c in CONTRACTORS:
        api = Api(a.api_url)
        cid = api.signup_or_login(c["email"], a.password, c["full_name"], "contractor", c["company_name"])
        upload_requirements(api, "/contractor/requirements", "/contractor/documents/{id}/upload",
                            "/contractor/submit-for-review", {"company_name": c["company_name"]})
        approve_documents(admin, cid, f"/admin/contractors/{cid}", "/admin/review/documents", "contractor_id")
        check(admin.http.post(f"/admin/review/contractors/{cid}/approve"), "approve contractor")
        check(admin.http.post(f"/admin/contractors/{cid}/payment-override",
                              json={"reason": "Demo account: marketplace access without a subscription."}),
              "grant payment override")
        check(admin.http.patch(f"/admin/contractors/{cid}", json={
            "company_name": c["company_name"], "license_number": None,
            "primary_trade": c["primary_trade"], "service_area": c["service_area"],
        }), "update contractor profile")
        contractor_apis.append(api)
        log(f"approved + active {c['company_name']} <{c['email']}>")

    step("Open projects (one per owner)")
    future = (datetime.utcnow() + timedelta(days=14)).isoformat()
    for (oid, api), (title, address, description, trade, days) in zip(owner_ids, PROJECTS):
        check(api.http.post("/projects", data={
            "title": title, "address": address, "description": description, "trade": trade,
            "bid_deadline": (datetime.utcnow() + timedelta(days=days)).isoformat(),
            "tender_type": "owner_visible", "status": "open",
        }), f"create project {title}")
        log(f"open: {title}")

    print("\nDemo accounts are ready. Password for all of them: " + a.password)
    for o in OWNERS:
        print(f"  Owner:      {o['email']}")
    for c in CONTRACTORS:
        print(f"  Contractor: {c['email']}")
    print(f"  Admin:      {a.admin_email}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, httpx.HTTPError) as e:
        sys.exit(f"ERROR: {e}")
