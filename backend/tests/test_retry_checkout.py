"""
Regression tests for POST /api/my/registrations/{registration_id}/checkout
(retry Stripe checkout for pending/failed registrations owned by user).
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if False else None
# frontend env
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

API = f"{BASE_URL}/api"


# ---------- Helpers ----------
@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def owner_session():
    """Log in the seeded super admin."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={
        "email": "danieloliveira78@gmail.com",
        "password": "ArenaHub@2026",
    }, timeout=15)
    assert r.status_code == 200, r.text
    return s, r.json()["user"]


@pytest.fixture(scope="module")
def athlete_session():
    """Sign up a fresh athlete user."""
    s = requests.Session()
    email = f"test_retry_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/signup", json={
        "email": email, "password": "Passw0rd!",
        "name": "Retry Test Athlete",
        "phone": "", "organization_name": "",
        "accept_terms": True, "accept_privacy": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    return s, r.json()["user"], email


@pytest.fixture(scope="module")
def other_athlete_session():
    s = requests.Session()
    email = f"test_retry_other_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/signup", json={
        "email": email, "password": "Passw0rd!",
        "name": "Other Athlete",
        "phone": "", "organization_name": "",
        "accept_terms": True, "accept_privacy": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    return s, r.json()["user"], email


# ---------- Seed competitions + registrations directly via Mongo ----------
@pytest.fixture(scope="module")
def seed_paid_comp(db, owner_session):
    _, owner = owner_session
    tenant_id = owner.get("tenant_id")
    assert tenant_id
    comp_id = f"comp_TEST_paid_{uuid.uuid4().hex[:6]}"
    run(db.competitions.insert_one({
        "competition_id": comp_id, "tenant_id": tenant_id,
        "title": "TEST Paid Competition", "type_name": "Beach Tennis",
        "type_id": "test_type", "start_date": "2026-12-01",
        "location": "Test", "prize": "-",
        "fee": 100.0, "mode": "individual",
        "status": "open", "banner": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    yield {"competition_id": comp_id, "tenant_id": tenant_id}
    run(db.competitions.delete_one({"competition_id": comp_id}))


@pytest.fixture(scope="module")
def seed_free_comp(db, owner_session):
    _, owner = owner_session
    tenant_id = owner.get("tenant_id")
    comp_id = f"comp_TEST_free_{uuid.uuid4().hex[:6]}"
    run(db.competitions.insert_one({
        "competition_id": comp_id, "tenant_id": tenant_id,
        "title": "TEST Free Competition", "type_name": "Beach Tennis",
        "type_id": "test_type", "start_date": "2026-12-02",
        "location": "Test", "prize": "-",
        "fee": 0.0, "mode": "individual",
        "status": "open", "banner": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    yield {"competition_id": comp_id, "tenant_id": tenant_id}
    run(db.competitions.delete_one({"competition_id": comp_id}))


def _seed_reg(db, comp, user_id, payment_status):
    reg_id = f"reg_TEST_{uuid.uuid4().hex[:8]}"
    run(db.registrations.insert_one({
        "registration_id": reg_id, "tenant_id": comp["tenant_id"],
        "competition_id": comp["competition_id"], "user_id": user_id,
        "mode": "individual", "payment_status": payment_status,
        "check_in_code": f"chk_{uuid.uuid4().hex[:6]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    return reg_id


# ---------- Tests ----------
def test_unauthenticated_returns_401():
    r = requests.post(f"{API}/my/registrations/nonexistent_reg/checkout",
                      json={"origin_url": "https://example.com"}, timeout=10)
    assert r.status_code == 401, r.text


def test_nonexistent_reg_returns_404(athlete_session):
    s, _, _ = athlete_session
    r = s.post(f"{API}/my/registrations/reg_does_not_exist_xyz/checkout",
               json={"origin_url": "https://example.com"}, timeout=10)
    assert r.status_code == 404
    assert "não encontrada" in r.json().get("detail", "").lower()


def test_someone_elses_reg_returns_403(db, seed_paid_comp, athlete_session, other_athlete_session):
    _, other_user, _ = other_athlete_session
    reg_id = _seed_reg(db, seed_paid_comp, other_user["user_id"], "pending")
    try:
        s, _, _ = athlete_session
        r = s.post(f"{API}/my/registrations/{reg_id}/checkout",
                   json={"origin_url": "https://example.com"}, timeout=10)
        assert r.status_code == 403
        assert "dono" in r.json().get("detail", "").lower()
    finally:
        run(db.registrations.delete_one({"registration_id": reg_id}))


def test_paid_reg_returns_400(db, seed_paid_comp, athlete_session):
    s, me, _ = athlete_session
    reg_id = _seed_reg(db, seed_paid_comp, me["user_id"], "paid")
    try:
        r = s.post(f"{API}/my/registrations/{reg_id}/checkout",
                   json={"origin_url": "https://example.com"}, timeout=10)
        assert r.status_code == 400
        assert "confirmada" in r.json().get("detail", "").lower()
    finally:
        run(db.registrations.delete_one({"registration_id": reg_id}))


def test_free_comp_marks_free(db, seed_free_comp, athlete_session):
    s, me, _ = athlete_session
    reg_id = _seed_reg(db, seed_free_comp, me["user_id"], "pending")
    try:
        r = s.post(f"{API}/my/registrations/{reg_id}/checkout",
                   json={"origin_url": "https://example.com"}, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("checkout_url") is None
        assert data.get("free") is True
        # Verify persistence
        doc = run(db.registrations.find_one({"registration_id": reg_id}))
        assert doc["payment_status"] == "free"
    finally:
        run(db.registrations.delete_one({"registration_id": reg_id}))


def test_pending_paid_reg_generates_stripe_session(db, seed_paid_comp, athlete_session):
    s, me, _ = athlete_session
    reg_id = _seed_reg(db, seed_paid_comp, me["user_id"], "pending")
    try:
        r = s.post(f"{API}/my/registrations/{reg_id}/checkout",
                   json={"origin_url": "https://example.com"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com/"), data
        session_id = data.get("session_id")
        assert session_id and session_id.startswith("cs_")

        # Verify payment_transactions doc created
        tx = run(db.payment_transactions.find_one({"session_id": session_id}))
        assert tx is not None
        assert tx["registration_id"] == reg_id
        assert tx["user_id"] == me["user_id"]
        assert tx["tenant_id"] == seed_paid_comp["tenant_id"]
        assert float(tx["amount"]) == 100.0

        # Verify registration updated with new checkout_session_id
        doc = run(db.registrations.find_one({"registration_id": reg_id}))
        assert doc["checkout_session_id"] == session_id
        assert doc["payment_status"] == "pending"

        # Cleanup tx
        run(db.payment_transactions.delete_one({"session_id": session_id}))
    finally:
        run(db.registrations.delete_one({"registration_id": reg_id}))
