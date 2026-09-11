"""Tests for account_type feature on /api/auth/signup (athlete vs admin).

Covers:
- Athlete signup: no tenant, no auto-provision
- Admin signup: requires organization_name
- Admin signup: creates tenant with trialing status
- Default account_type (backwards compat) = admin
- GET /me/tenant for athlete: no auto-provisioned tenant doc
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _uniq_email(prefix="athlete"):
    return f"TEST_{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def _base_payload(email, account_type=None, org=None):
    body = {
        "name": "Test User",
        "email": email,
        "phone": "11999999999",
        "password": "TestPass123",
        "accept_terms": True,
        "accept_privacy": True,
    }
    if account_type is not None:
        body["account_type"] = account_type
    if org is not None:
        body["organization_name"] = org
    return body


@pytest.fixture
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestAthleteSignup:
    def test_athlete_signup_success_no_tenant(self, session):
        email = _uniq_email("athlete")
        r = session.post(f"{API}/auth/signup", json=_base_payload(email, account_type="athlete"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tenant"] is None, f"Expected tenant=null, got {data['tenant']}"
        user = data["user"]
        assert user["account_type"] == "athlete"
        assert user["is_admin"] is False
        assert user.get("tenant_id") in (None, "")
        token = data["session_token"]

        # GET /me/tenant should not auto-provision a tenant
        r2 = session.get(f"{API}/me/tenant", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200, r2.text
        me_tenant = r2.json()
        assert me_tenant["tenant"] is None, f"Athlete should have no tenant, got {me_tenant}"
        assert me_tenant["can_write"] is False

        # GET /auth/me — verify tenant_id still null (no auto-provisioning)
        r3 = session.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r3.status_code == 200
        me = r3.json().get("user") or r3.json()
        assert me.get("account_type") == "athlete"
        assert not me.get("tenant_id"), f"athlete auto-got tenant_id: {me.get('tenant_id')}"


class TestAdminSignup:
    def test_admin_signup_missing_org_400(self, session):
        email = _uniq_email("admin_noorg")
        r = session.post(f"{API}/auth/signup", json=_base_payload(email, account_type="admin"))
        assert r.status_code == 400, r.text
        assert "organiza" in r.text.lower()

    def test_admin_signup_with_org_creates_trial_tenant(self, session):
        email = _uniq_email("admin_ok")
        r = session.post(f"{API}/auth/signup",
                         json=_base_payload(email, account_type="admin", org="Clube X"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tenant"] is not None
        assert data["tenant"].get("subscription_status") == "trialing"
        assert data["user"]["is_admin"] is True
        assert data["user"]["account_type"] == "admin"
        assert data["user"].get("tenant_id")

    def test_default_account_type_backwards_compat(self, session):
        # No account_type in body -> defaults to admin; needs org
        email = _uniq_email("default")
        r = session.post(f"{API}/auth/signup",
                         json=_base_payload(email, org="Legacy Org"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["is_admin"] is True
        assert data["user"]["account_type"] == "admin"
        assert data["tenant"] is not None
        assert data["tenant"].get("subscription_status") == "trialing"

    def test_default_no_org_still_400(self, session):
        # Default = admin, org required
        email = _uniq_email("default_noorg")
        r = session.post(f"{API}/auth/signup", json=_base_payload(email))
        assert r.status_code == 400
