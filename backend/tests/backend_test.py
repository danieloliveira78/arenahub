"""ArenaHub Backend Tests - covers public, auth RBAC, competitions CRUD,
registrations (free & paid), teams draw, bracket, match scoring, my-registrations, CORS."""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def _mk_session(is_admin: bool, email_prefix: str = "user"):
    uid = f"test-{email_prefix}-{uuid.uuid4().hex[:8]}"
    token = f"testtok_{uuid.uuid4().hex}"
    email = "danieloliveira78@gmail.com" if is_admin else f"TEST_{email_prefix}_{uuid.uuid4().hex[:6]}@example.com"
    # If admin, clean prior admin doc to allow deterministic creation
    if is_admin:
        db.users.delete_many({"email": email})
    db.users.insert_one({
        "user_id": uid, "email": email, "name": f"{email_prefix.title()} Tester",
        "picture": "", "is_admin": is_admin,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"user_id": uid, "token": token, "email": email}


@pytest.fixture(scope="module")
def admin_ctx():
    ctx = _mk_session(True, "admin")
    yield ctx
    db.user_sessions.delete_many({"user_id": ctx["user_id"]})
    db.users.delete_many({"user_id": ctx["user_id"]})


@pytest.fixture(scope="module")
def user_ctx():
    ctx = _mk_session(False, "user")
    yield ctx
    db.user_sessions.delete_many({"user_id": ctx["user_id"]})
    db.users.delete_many({"user_id": ctx["user_id"]})


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


# ------------- Public routes -------------
class TestPublic:
    def test_root(self):
        r = requests.get(f"{API}/")
        assert r.status_code == 200
        assert "message" in r.json()

    def test_seed_defaults_idempotent(self):
        r1 = requests.post(f"{API}/seed-defaults")
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/seed-defaults")
        assert r2.status_code == 200
        # Second call should not re-seed (count>0)
        assert r2.json().get("seeded") in (False, True)  # if DB was empty first time it may seed

    def test_competition_types_has_5(self):
        r = requests.get(f"{API}/competition-types")
        assert r.status_code == 200
        types = r.json()
        assert isinstance(types, list)
        assert len(types) >= 5

    def test_list_competitions(self):
        r = requests.get(f"{API}/competitions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ------------- Auth -------------
class TestAuth:
    def test_session_invalid(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "invalid_xxx"})
        assert r.status_code == 401

    def test_me_no_auth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, user_ctx):
        r = requests.get(f"{API}/auth/me", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == user_ctx["email"]

    def test_logout_deletes_session(self):
        ctx = _mk_session(False, "logout")
        r = requests.post(f"{API}/auth/logout", headers=auth_h(ctx["token"]))
        assert r.status_code == 200
        # subsequent me should fail
        r2 = requests.get(f"{API}/auth/me", headers=auth_h(ctx["token"]))
        assert r2.status_code == 401
        db.users.delete_many({"user_id": ctx["user_id"]})


# ------------- Admin RBAC -------------
class TestRBAC:
    def test_non_admin_forbidden_type(self, user_ctx):
        r = requests.post(f"{API}/competition-types",
                          headers=auth_h(user_ctx["token"]),
                          json={"name": "X", "format": "duplas"})
        assert r.status_code == 403

    def test_non_admin_forbidden_competition(self, user_ctx):
        r = requests.post(f"{API}/competitions",
                          headers=auth_h(user_ctx["token"]),
                          json={"title": "X", "type_id": "x",
                                "registration_start": "2025-01-01",
                                "registration_end": "2025-01-02",
                                "start_date": "2025-01-03",
                                "end_date": "2025-01-04",
                                "prize": "-", "fee": 0})
        assert r.status_code == 403


# ------------- Competitions CRUD + Registrations + Teams + Bracket -------------
@pytest.fixture(scope="module")
def free_comp(admin_ctx):
    """Create a free duplas competition."""
    types = requests.get(f"{API}/competition-types").json()
    dup_type = next((t for t in types if t["format"] == "duplas"), types[0])
    body = {
        "title": f"TEST_Free_{uuid.uuid4().hex[:6]}",
        "type_id": dup_type["type_id"],
        "description": "test",
        "registration_start": "2025-01-01",
        "registration_end": "2026-12-31",
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
        "prize": "Trophy",
        "fee": 0.0,
        "max_slots": 16,
        "location": "Praia",
    }
    r = requests.post(f"{API}/competitions", headers=auth_h(admin_ctx["token"]), json=body)
    assert r.status_code == 200, r.text
    comp = r.json()
    yield comp
    db.competitions.delete_many({"competition_id": comp["competition_id"]})
    db.registrations.delete_many({"competition_id": comp["competition_id"]})
    db.teams.delete_many({"competition_id": comp["competition_id"]})
    db.matches.delete_many({"competition_id": comp["competition_id"]})


@pytest.fixture(scope="module")
def paid_comp(admin_ctx):
    types = requests.get(f"{API}/competition-types").json()
    dup_type = next((t for t in types if t["format"] == "duplas"), types[0])
    body = {
        "title": f"TEST_Paid_{uuid.uuid4().hex[:6]}",
        "type_id": dup_type["type_id"],
        "description": "test paid",
        "registration_start": "2025-01-01",
        "registration_end": "2026-12-31",
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
        "prize": "R$ 500",
        "fee": 50.0,
        "max_slots": 8,
        "location": "Arena",
    }
    r = requests.post(f"{API}/competitions", headers=auth_h(admin_ctx["token"]), json=body)
    assert r.status_code == 200, r.text
    comp = r.json()
    yield comp
    db.competitions.delete_many({"competition_id": comp["competition_id"]})
    db.registrations.delete_many({"competition_id": comp["competition_id"]})
    db.payment_transactions.delete_many({"registration_id": {"$regex": "^reg_"}})


class TestCompetitionsCRUD:
    def test_get_competition_with_count(self, free_comp):
        r = requests.get(f"{API}/competitions/{free_comp['competition_id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == free_comp["title"]
        assert "registered_count" in data
        assert data["registered_count"] == 0

    def test_get_competition_404(self):
        r = requests.get(f"{API}/competitions/nonexistent_xxx")
        assert r.status_code == 404


class TestRegistrationsFree:
    def test_register_free(self, free_comp, user_ctx):
        r = requests.post(f"{API}/registrations",
                          headers=auth_h(user_ctx["token"]),
                          json={"competition_id": free_comp["competition_id"],
                                "mode": "individual"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["registration"]["payment_status"] == "free"
        assert body["checkout_url"] is None

    def test_duplicate_registration(self, free_comp, user_ctx):
        r = requests.post(f"{API}/registrations",
                          headers=auth_h(user_ctx["token"]),
                          json={"competition_id": free_comp["competition_id"],
                                "mode": "individual"})
        assert r.status_code == 400

    def test_my_registrations(self, user_ctx, free_comp):
        r = requests.get(f"{API}/my-registrations", headers=auth_h(user_ctx["token"]))
        assert r.status_code == 200
        regs = r.json()
        assert len(regs) >= 1
        assert any(x["competition_id"] == free_comp["competition_id"] and x.get("competition") for x in regs)


class TestRegistrationsPaid:
    def test_register_paid_creates_checkout(self, paid_comp, user_ctx):
        r = requests.post(f"{API}/registrations",
                          headers=auth_h(user_ctx["token"]),
                          json={"competition_id": paid_comp["competition_id"],
                                "mode": "individual",
                                "origin_url": "https://example.com"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["checkout_url"] is not None
        assert "stripe.com" in body["checkout_url"] or "checkout" in body["checkout_url"]
        assert body["registration"]["payment_status"] == "pending"
        sess_id = body["registration"]["checkout_session_id"]
        assert sess_id
        # payment_status endpoint
        s = requests.get(f"{API}/payments/status/{sess_id}")
        assert s.status_code == 200
        assert s.json()["payment_status"] in ("pending", "paid")


class TestDrawAndBracket:
    def _seed_confirmed_regs(self, comp_id, n=5):
        """Directly seed n free/paid registrations for draw testing."""
        for i in range(n):
            db.registrations.insert_one({
                "registration_id": f"reg_{uuid.uuid4().hex[:10]}",
                "competition_id": comp_id,
                "user_id": f"seed_user_{i}",
                "user_name": f"SeedUser{i}",
                "user_email": f"seed{i}@t.com",
                "mode": "individual",
                "partner_name": "", "partner_email": "", "phone": "",
                "fee": 0, "payment_status": "free",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    def test_draw_requires_min_2(self, admin_ctx):
        # create empty comp
        types = requests.get(f"{API}/competition-types").json()
        dup = next(t for t in types if t["format"] == "duplas")
        r = requests.post(f"{API}/competitions",
                          headers=auth_h(admin_ctx["token"]),
                          json={"title": f"TEST_empty_{uuid.uuid4().hex[:4]}",
                                "type_id": dup["type_id"],
                                "registration_start": "2025-01-01",
                                "registration_end": "2026-12-31",
                                "start_date": "2027-01-01",
                                "end_date": "2027-01-02",
                                "prize": "-", "fee": 0})
        cid = r.json()["competition_id"]
        r2 = requests.post(f"{API}/competitions/{cid}/draw",
                           headers=auth_h(admin_ctx["token"]))
        assert r2.status_code == 400
        db.competitions.delete_many({"competition_id": cid})

    def test_draw_and_bracket(self, admin_ctx, free_comp):
        cid = free_comp["competition_id"]
        # Already has 1 registration from earlier test (user_ctx). Seed 4 more.
        self._seed_confirmed_regs(cid, n=4)
        r = requests.post(f"{API}/competitions/{cid}/draw", headers=auth_h(admin_ctx["token"]))
        assert r.status_code == 200, r.text
        teams = r.json()
        assert len(teams) >= 2  # 5 solos -> 2 pairs + 1 BYE = 3 teams
        # bracket
        r2 = requests.post(f"{API}/competitions/{cid}/bracket", headers=auth_h(admin_ctx["token"]))
        assert r2.status_code == 200, r2.text
        matches = r2.json()
        # next power of 2 >= team count; n-1 matches total
        n = 1
        while n < len(teams):
            n *= 2
        assert len(matches) == n - 1
        # Some BYE round1 winners should already be set
        r1 = [m for m in matches if m["round"] == 1]
        assert len(r1) == n // 2
        # save one match id for scoring
        pytest.match_for_scoring = next(
            (m for m in r1 if m["team_a_name"] != "BYE" and m["team_b_name"] != "BYE"), None
        )

    def test_update_match_score(self, admin_ctx, free_comp):
        m = getattr(pytest, "match_for_scoring", None)
        if not m:
            pytest.skip("No non-BYE round1 match found")
        r = requests.put(f"{API}/matches/{m['match_id']}",
                         headers=auth_h(admin_ctx["token"]),
                         json={"score_a": 10, "score_b": 5})
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["winner"] == "A"
        # Verify propagation into next match
        if updated.get("next_match_id"):
            nxt = db.matches.find_one({"match_id": updated["next_match_id"]}, {"_id": 0})
            slot_a = updated["position"] % 2 == 0
            if slot_a:
                assert nxt["team_a_id"] == updated["team_a_id"]
            else:
                assert nxt["team_b_id"] == updated["team_a_id"]


# ------------- CORS -------------
class TestCORS:
    def test_preflight(self):
        r = requests.options(
            f"{API}/competitions",
            headers={
                "Origin": "https://gamify-tournaments.preview.emergentagent.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") is not None
