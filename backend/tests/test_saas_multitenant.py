"""ArenaHub SaaS multi-tenant backend tests.

Covers:
- Auth signup/login/me (email/password)
- Tenant creation with trialing, /me/tenant response
- Plans listing (starter monthly/yearly, R$49 / R$490, BRL, limits, trial 14d)
- Stripe subscription checkout url
- CROSS-TENANT ISOLATION (competition_types, competitions, admin/*)
- Super admin platform stats/tenants + 403 for non-super-admin
- Plan limit enforcement (5 competitions -> 402)
- Public marketplace unauth still returns competitions
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or
            open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()).rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "danieloliveira78@gmail.com"
OWNER_PASSWORD = "ArenaHub@2026"


def _rand_email(prefix="tenant"):
    return f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _signup(name, email, password="Passw0rd!", org=None):
    r = requests.post(f"{API}/auth/signup", json={
        "name": name, "email": email, "password": password,
        "organization_name": org or f"Org_{name}",
        "accept_terms": True, "accept_privacy": True,
    })
    return r


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------- Signup / Login / me -------------------
class TestAuthSignup:
    def test_signup_creates_user_and_trialing_tenant(self):
        email = _rand_email("signup")
        r = _signup("Alice", email)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_token" in data and data["session_token"]
        assert data["user"]["email"].lower() == email.lower()
        assert data["tenant"]["subscription_status"] == "trialing"
        assert data["tenant"]["trial_end"]
        # 14 days ahead (approx)
        te = datetime.fromisoformat(data["tenant"]["trial_end"])
        if te.tzinfo is None:
            te = te.replace(tzinfo=timezone.utc)
        delta = te - datetime.now(timezone.utc)
        assert 13 <= delta.days <= 14

        # /auth/me returns the user
        me = requests.get(f"{API}/auth/me", headers=_auth(data["session_token"]))
        assert me.status_code == 200
        assert me.json()["email"].lower() == email.lower()

        # /me/tenant response shape
        mt = requests.get(f"{API}/me/tenant", headers=_auth(data["session_token"]))
        assert mt.status_code == 200
        body = mt.json()
        assert body["effective_status"] == "trialing"
        assert body["can_write"] is True
        assert body["limits"]["tournaments"] == 5
        assert body["limits"]["athletes"] == 200

    def test_signup_duplicate_email_400(self):
        email = _rand_email("dup")
        r1 = _signup("Bob", email)
        assert r1.status_code == 200
        r2 = _signup("Bob2", email)
        assert r2.status_code == 400

    def test_me_unauth_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


class TestAuthLogin:
    def test_owner_login_ok(self):
        r = requests.post(f"{API}/auth/login", json={
            "email": OWNER_EMAIL, "password": OWNER_PASSWORD,
        })
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == OWNER_EMAIL
        assert r.json().get("session_token")

    def test_wrong_password_401(self):
        r = requests.post(f"{API}/auth/login", json={
            "email": OWNER_EMAIL, "password": "wrong-nope",
        })
        assert r.status_code == 401


# ------------------- Plans -------------------
class TestPlans:
    def test_plans_lists_both(self):
        r = requests.get(f"{API}/plans")
        assert r.status_code == 200, r.text
        plans = r.json()
        keys = {p["lookup_key"]: p for p in plans}
        assert "starter_monthly" in keys and "starter_yearly" in keys
        m = keys["starter_monthly"]; y = keys["starter_yearly"]
        assert m["amount"] == 49.0
        assert m["currency"].lower() == "brl"
        assert m["interval"] == "month"
        assert m["trial_days"] == 14
        assert m["limits"]["tournaments"] == 5
        assert m["limits"]["athletes"] == 200
        assert y["amount"] == 490.0
        assert y["currency"].lower() == "brl"
        assert y["interval"] == "year"


# ------------------- Subscription checkout -------------------
class TestSubscriptionCheckout:
    def test_checkout_returns_url(self):
        email = _rand_email("chk")
        r = _signup("Chk", email)
        token = r.json()["session_token"]
        rr = requests.post(f"{API}/subscriptions/checkout",
                           headers=_auth(token),
                           json={"lookup_key": "starter_monthly",
                                 "origin_url": "https://example.com"})
        assert rr.status_code == 200, rr.text
        data = rr.json()
        assert data.get("checkout_url", "").startswith("https://")
        assert "stripe.com" in data["checkout_url"] or "checkout" in data["checkout_url"]


# ------------------- CROSS-TENANT ISOLATION -------------------
@pytest.fixture(scope="module")
def two_tenants():
    """Create tenant A + tenant B. A creates a competition_type + competition."""
    email_a = _rand_email("A")
    email_b = _rand_email("B")
    ra = _signup("Alice A", email_a, org="Tenant A")
    rb = _signup("Bob B", email_b, org="Tenant B")
    assert ra.status_code == 200 and rb.status_code == 200
    tok_a = ra.json()["session_token"]
    tok_b = rb.json()["session_token"]

    # A creates a competition type
    ct_resp = requests.post(f"{API}/competition-types", headers=_auth(tok_a),
                            json={"name": f"TypeA_{uuid.uuid4().hex[:5]}",
                                  "format": "duplas"})
    assert ct_resp.status_code == 200, ct_resp.text
    type_a = ct_resp.json()

    # A creates a competition
    c_resp = requests.post(f"{API}/competitions", headers=_auth(tok_a), json={
        "title": f"TEST_A_Comp_{uuid.uuid4().hex[:5]}",
        "type_id": type_a["type_id"],
        "registration_start": "2025-01-01", "registration_end": "2026-12-31",
        "start_date": "2027-01-01", "end_date": "2027-01-02",
        "prize": "-", "fee": 0,
    })
    assert c_resp.status_code == 200, c_resp.text
    comp_a = c_resp.json()

    yield {"tok_a": tok_a, "tok_b": tok_b, "type_a": type_a, "comp_a": comp_a,
           "email_a": email_a, "email_b": email_b}


class TestTenantIsolation:
    def test_types_scoped_to_tenant(self, two_tenants):
        # B's list must not include A's type
        r = requests.get(f"{API}/competition-types", headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 200
        ids = [t["type_id"] for t in r.json()]
        assert two_tenants["type_a"]["type_id"] not in ids

    def test_authenticated_competitions_scoped(self, two_tenants):
        # B authenticated: should NOT see A's competition
        r = requests.get(f"{API}/competitions", headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 200
        ids = [c["competition_id"] for c in r.json()]
        assert two_tenants["comp_a"]["competition_id"] not in ids

    def test_public_marketplace_unauth_shows_all(self, two_tenants):
        # Public (no auth) should include A's competition
        r = requests.get(f"{API}/competitions")
        assert r.status_code == 200
        ids = [c["competition_id"] for c in r.json()]
        assert two_tenants["comp_a"]["competition_id"] in ids

    def test_put_other_tenant_comp_404(self, two_tenants):
        r = requests.put(f"{API}/competitions/{two_tenants['comp_a']['competition_id']}",
                         headers=_auth(two_tenants["tok_b"]), json={"title": "hacked"})
        assert r.status_code == 404

    def test_delete_other_tenant_comp_404(self, two_tenants):
        r = requests.delete(f"{API}/competitions/{two_tenants['comp_a']['competition_id']}",
                            headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 404

    def test_draw_other_tenant_comp_404(self, two_tenants):
        r = requests.post(f"{API}/competitions/{two_tenants['comp_a']['competition_id']}/draw",
                          headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 404

    def test_bracket_other_tenant_comp_404(self, two_tenants):
        r = requests.post(f"{API}/competitions/{two_tenants['comp_a']['competition_id']}/bracket",
                          headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 404

    def test_admin_finance_scoped(self, two_tenants):
        r = requests.get(f"{API}/admin/finance", headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 200
        # No tx from A should leak (we haven't created any, but ensure structure)
        assert "rows" in r.json()

    def test_admin_users_scoped(self, two_tenants):
        r = requests.get(f"{API}/admin/users", headers=_auth(two_tenants["tok_b"]))
        assert r.status_code == 200
        emails = [u["email"].lower() for u in r.json()]
        assert two_tenants["email_a"].lower() not in emails
        assert two_tenants["email_b"].lower() in emails


# ------------------- Super admin -------------------
class TestSuperAdmin:
    @pytest.fixture(scope="class")
    def owner_token(self):
        r = requests.post(f"{API}/auth/login", json={
            "email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200, r.text
        return r.json()["session_token"]

    def test_platform_tenants_as_super_admin(self, owner_token):
        r = requests.get(f"{API}/platform/tenants", headers=_auth(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_platform_stats_as_super_admin(self, owner_token):
        r = requests.get(f"{API}/platform/stats", headers=_auth(owner_token))
        assert r.status_code == 200
        body = r.json()
        assert "mrr" in body
        assert "totals" in body
        for k in ("tenants", "active", "past_due", "canceled"):
            assert k in body["totals"]

    def test_platform_forbidden_for_regular(self):
        email = _rand_email("regular")
        r = _signup("Reg", email)
        tok = r.json()["session_token"]
        r1 = requests.get(f"{API}/platform/tenants", headers=_auth(tok))
        r2 = requests.get(f"{API}/platform/stats", headers=_auth(tok))
        assert r1.status_code == 403
        assert r2.status_code == 403


# ------------------- Plan limit enforcement -------------------
class TestPlanLimits:
    def test_sixth_competition_returns_402(self):
        email = _rand_email("limit")
        r = _signup("Lim", email)
        tok = r.json()["session_token"]

        # Create a type
        ct = requests.post(f"{API}/competition-types", headers=_auth(tok),
                           json={"name": "T", "format": "individual"}).json()

        # Create 5 competitions successfully
        for i in range(5):
            rr = requests.post(f"{API}/competitions", headers=_auth(tok), json={
                "title": f"TEST_Lim_{i}_{uuid.uuid4().hex[:4]}",
                "type_id": ct["type_id"],
                "registration_start": "2025-01-01", "registration_end": "2026-12-31",
                "start_date": "2027-01-01", "end_date": "2027-01-02",
                "prize": "-", "fee": 0,
            })
            assert rr.status_code == 200, f"i={i} {rr.status_code} {rr.text}"

        # 6th must return 402
        rr = requests.post(f"{API}/competitions", headers=_auth(tok), json={
            "title": "TEST_Lim_6",
            "type_id": ct["type_id"],
            "registration_start": "2025-01-01", "registration_end": "2026-12-31",
            "start_date": "2027-01-01", "end_date": "2027-01-02",
            "prize": "-", "fee": 0,
        })
        assert rr.status_code == 402, rr.text


# ------------------- Public rankings still works -------------------
class TestPublic:
    def test_rankings(self):
        r = requests.get(f"{API}/rankings")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
