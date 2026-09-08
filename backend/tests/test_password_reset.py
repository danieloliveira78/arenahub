"""Backend tests for forgot-password / reset-password flow."""
import os
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://gamify-tournaments.preview.emergentagent.com"
# fall back to frontend .env
if "REACT_APP_BACKEND_URL" not in os.environ:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def fresh_user(db):
    email = f"pwreset_{uuid.uuid4().hex[:8]}@test.com"
    password = "oldpass123"
    r = requests.post(f"{API}/auth/signup", json={"name": "PWReset Test", "email": email, "password": password, "organization_name": f"Org {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200, r.text
    user_id = r.json()["user"]["user_id"]
    yield {"email": email, "password": password, "user_id": user_id}
    # cleanup
    async def _cleanup():
        u = await db.users.find_one({"email": email})
        if u:
            await db.tenants.delete_many({"owner_user_id": u["user_id"]})
        await db.users.delete_many({"email": email})
        await db.password_reset_tokens.delete_many({"email": email})
        await db.user_sessions.delete_many({"user_id": user_id})
    run(_cleanup())


def test_forgot_password_existing_creates_token(db):
    email = "danieloliveira78@gmail.com"
    # snapshot
    before = run(db.password_reset_tokens.count_documents({"email": email}))
    r = requests.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    after = run(db.password_reset_tokens.count_documents({"email": email}))
    assert after == before + 1
    tok = run(db.password_reset_tokens.find_one({"email": email}, sort=[("created_at", -1)]))
    assert tok["used"] is False
    exp = datetime.fromisoformat(tok["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = (exp - datetime.now(timezone.utc)).total_seconds()
    assert 3500 < delta < 3700  # ~1h


def test_forgot_password_nonexistent_no_token(db):
    email = f"ghost_{uuid.uuid4().hex[:8]}@nowhere.test"
    r = requests.post(f"{API}/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    cnt = run(db.password_reset_tokens.count_documents({"email": email}))
    assert cnt == 0


def test_reset_invalid_token():
    r = requests.post(f"{API}/auth/reset-password", json={"token": "invalid_" + uuid.uuid4().hex, "new_password": "newpass1"})
    assert r.status_code == 400
    assert "inválido" in r.json().get("detail", "").lower() or "invalid" in r.json().get("detail", "").lower()


def test_reset_short_password():
    r = requests.post(f"{API}/auth/reset-password", json={"token": "whatever", "new_password": "abc"})
    assert r.status_code == 400
    assert "curta" in r.json().get("detail", "").lower()


def test_full_happy_path(db, fresh_user):
    email = fresh_user["email"]
    user_id = fresh_user["user_id"]
    # create a session (login) to test defense in depth
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": fresh_user["password"]})
    assert r.status_code == 200
    sessions_before = run(db.user_sessions.count_documents({"user_id": user_id}))
    assert sessions_before >= 1

    # forgot
    r = requests.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
    assert r.status_code == 200
    tok_doc = run(db.password_reset_tokens.find_one({"email": email, "used": False}, sort=[("created_at", -1)]))
    assert tok_doc
    token = tok_doc["token"]

    # reset
    new_password = "newpass1"
    r = requests.post(f"{API}/auth/reset-password", json={"token": token, "new_password": new_password})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    # old password no longer works
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": fresh_user["password"]})
    assert r.status_code == 401

    # new password works
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": new_password})
    assert r.status_code == 200

    # token marked used
    tok2 = run(db.password_reset_tokens.find_one({"token": token}))
    assert tok2["used"] is True
    assert "used_at" in tok2

    # sessions previous to reset should be deleted (only new one from login post-reset)
    # can't easily count; just verify the pre-reset session_token cookie is invalid via /auth/me — omitted.

    # Store token for used-token test
    fresh_user["used_token"] = token
    fresh_user["password"] = new_password


def test_reset_used_token(fresh_user):
    used_tok = fresh_user.get("used_token")
    assert used_tok
    r = requests.post(f"{API}/auth/reset-password", json={"token": used_tok, "new_password": "another1"})
    assert r.status_code == 400
    assert "utilizado" in r.json().get("detail", "").lower()


def test_reset_expired_token(db, fresh_user):
    email = fresh_user["email"]
    # create a new token then expire it
    r = requests.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
    assert r.status_code == 200
    tok = run(db.password_reset_tokens.find_one({"email": email, "used": False}, sort=[("created_at", -1)]))
    assert tok
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    run(db.password_reset_tokens.update_one({"token": tok["token"]}, {"$set": {"expires_at": past}}))
    r = requests.post(f"{API}/auth/reset-password", json={"token": tok["token"], "new_password": "newpass2"})
    assert r.status_code == 400
    assert "expirou" in r.json().get("detail", "").lower()
