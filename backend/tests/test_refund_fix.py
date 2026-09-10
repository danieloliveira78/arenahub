"""Regression test for admin_refund NameError fix (payment_intent scope).

Bug: payment_intent assignment was nested inside `if payment_status != 'paid'`
so downstream `if not payment_intent` raised NameError on every legitimate refund.

Test seeds a payment_transactions doc via motor and calls POST /api/admin/refund/{session_id}
as super admin. Expected: NO NameError. For 'paid' doc with fake intent -> 500
'Erro ao reembolsar' from Stripe. For 'pending' doc -> 400 'não está paga'.
Also smoke: /auth/login, /auth/me, /plans, /me/tenant still return 200.
"""
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or
            open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()).rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "danieloliveira78@gmail.com"
OWNER_PASSWORD = "ArenaHub@2026"

MONGO_URL = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip('"')
DB_NAME = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip('"')


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def owner_user(owner_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 200
    return r.json()


def _seed_tx(session_id: str, tenant_id: str, payment_status: str, payment_intent: str = "pi_test_nonexistent"):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.payment_transactions.insert_one({
            "session_id": session_id,
            "stripe_payment_intent_id": payment_intent,
            "payment_status": payment_status,
            "tenant_id": tenant_id,
            "amount": 5000,
            "currency": "brl",
            "registration_id": None,
        })
        client.close()
    asyncio.run(_do())


def _cleanup_tx(session_id: str):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.payment_transactions.delete_many({"session_id": session_id})
        client.close()
    asyncio.run(_do())


# ------- Regression smoke -------
class TestRegressionSmoke:
    def test_login_owner_200(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200
        assert "session_token" in r.json()

    def test_auth_me_200(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {owner_token}"})
        assert r.status_code == 200
        assert r.json().get("email", "").lower() == OWNER_EMAIL.lower()

    def test_plans_200(self):
        r = requests.get(f"{API}/plans")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1

    def test_me_tenant_200(self, owner_token):
        r = requests.get(f"{API}/me/tenant", headers={"Authorization": f"Bearer {owner_token}"})
        assert r.status_code == 200


# ------- Refund NameError regression -------
class TestAdminRefundFix:
    def test_refund_paid_no_nameerror_returns_stripe_error(self, owner_token, owner_user):
        session_id = f"cs_test_TEST_{uuid.uuid4().hex[:12]}"
        tenant_id = owner_user.get("tenant_id") or "platform"
        _seed_tx(session_id, tenant_id, payment_status="paid", payment_intent="pi_test_nonexistent_TEST")
        try:
            r = requests.post(f"{API}/admin/refund/{session_id}",
                              headers={"Authorization": f"Bearer {owner_token}"})
            # Must NOT be a NameError crash. Should be 500 'Erro ao reembolsar'
            # (Stripe rejects fake intent) — status 500 with detail mentioning
            # Stripe error, not a python-level NameError.
            assert r.status_code == 500, f"Expected 500 Stripe error, got {r.status_code}: {r.text}"
            detail = r.json().get("detail", "")
            assert "NameError" not in detail, f"NameError leaked: {detail}"
            assert "reembolsar" in detail.lower() or "stripe" in detail.lower() or "no such" in detail.lower(), \
                f"Unexpected detail: {detail}"
        finally:
            _cleanup_tx(session_id)

    def test_refund_pending_returns_400_clean(self, owner_token, owner_user):
        session_id = f"cs_test_TEST_{uuid.uuid4().hex[:12]}"
        tenant_id = owner_user.get("tenant_id") or "platform"
        _seed_tx(session_id, tenant_id, payment_status="pending")
        try:
            r = requests.post(f"{API}/admin/refund/{session_id}",
                              headers={"Authorization": f"Bearer {owner_token}"})
            assert r.status_code == 400, r.text
            detail = r.json().get("detail", "")
            assert "não está paga" in detail.lower() or "nao esta paga" in detail.lower() \
                or "paga" in detail.lower(), f"Unexpected detail: {detail}"
        finally:
            _cleanup_tx(session_id)

    def test_refund_missing_tx_returns_404(self, owner_token):
        session_id = f"cs_test_TEST_missing_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/admin/refund/{session_id}",
                          headers={"Authorization": f"Bearer {owner_token}"})
        assert r.status_code == 404
