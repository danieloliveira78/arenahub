"""Backend tests for retire-player + tied score handling in duplas_rotativas."""
import os
import uuid
import asyncio
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _signup_tenant(prefix="rr"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.com"
    pwd = "Passw0rd!"
    r = requests.post(f"{BASE_URL}/auth/signup", json={
        "email": email, "password": pwd, "name": f"Admin {prefix}",
        "organization_name": f"Clube {prefix}",
        "accept_terms": True, "accept_privacy": True,
    })
    assert r.status_code == 200, r.text
    return {"email": email, "token": r.json()["session_token"],
            "tenant": r.json()["tenant"]}


def _create_type(token, fmt="duplas_rotativas"):
    r = requests.post(f"{BASE_URL}/competition-types",
                      json={"name": f"Type {fmt}", "format": fmt, "icon": "trophy"},
                      headers=_hdr(token))
    assert r.status_code == 200, r.text
    return r.json()["type_id"]


def _create_competition(token, type_id, title="Rot Retire"):
    r = requests.post(f"{BASE_URL}/competitions", json={
        "title": title, "type_id": type_id, "description": "",
        "registration_start": "2026-01-01", "registration_end": "2026-12-31",
        "start_date": "2026-01-15", "end_date": "2026-01-16",
        "prize": "T", "fee": 0.0, "max_slots": 32, "location": "Praia",
    }, headers=_hdr(token))
    assert r.status_code == 200, r.text
    return r.json()["competition_id"]


async def _seed(cid, tenant_id, n=8):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    reg_ids = []
    for i in range(n):
        uid = f"user_{uuid.uuid4().hex[:12]}"
        rid = f"reg_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({
            "user_id": uid, "email": f"p{i}_{uuid.uuid4().hex[:6]}@t.co",
            "name": f"P{i}", "is_admin": False, "tenant_role": "athlete",
        })
        await db.registrations.insert_one({
            "registration_id": rid, "competition_id": cid, "tenant_id": tenant_id,
            "user_id": uid, "user_name": f"P{i}", "user_email": f"p{i}@t.co",
            "mode": "individual", "partner_name": "", "partner_email": "",
            "phone": "", "fee": 0.0, "payment_status": "free",
            "checkout_session_id": None, "check_in_code": f"chk_{uuid.uuid4().hex[:12]}",
            "checked_in": False,
        })
        reg_ids.append(rid)
    client.close()
    return reg_ids


async def _cleanup(cid):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.registrations.delete_many({"competition_id": cid})
    await db.matches.delete_many({"competition_id": cid})
    await db.teams.delete_many({"competition_id": cid})
    await db.groups.delete_many({"competition_id": cid})
    await db.competitions.delete_many({"competition_id": cid})
    client.close()


async def _find_reg(rid):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    r = await db.registrations.find_one({"registration_id": rid}, {"_id": 0})
    client.close()
    return r


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def tenant_a():
    t = _signup_tenant("rrA")
    yield t
    async def _c():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"email": t["email"]})
        await db.tenants.delete_one({"tenant_id": t["tenant"]["tenant_id"]})
        client.close()
    asyncio.get_event_loop().run_until_complete(_c())


@pytest.fixture(scope="module")
def tenant_b():
    t = _signup_tenant("rrB")
    yield t
    async def _c():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"email": t["email"]})
        await db.tenants.delete_one({"tenant_id": t["tenant"]["tenant_id"]})
        client.close()
    asyncio.get_event_loop().run_until_complete(_c())


@pytest.fixture(scope="module")
def seeded_comp(tenant_a):
    tid = _create_type(tenant_a["token"])
    cid = _create_competition(tenant_a["token"], tid)
    asyncio.get_event_loop().run_until_complete(_seed(cid, tenant_a["tenant"]["tenant_id"], n=8))
    # draw groups
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups",
                      headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200, r.text
    yield {"cid": cid, "token": tenant_a["token"], "tenant_id": tenant_a["tenant"]["tenant_id"]}
    asyncio.get_event_loop().run_until_complete(_cleanup(cid))


# ---------- Tests ----------
def test_tied_score_no_winner_stays_null(seeded_comp):
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    m = [x for x in r.json() if x["phase"] == "group"][0]
    resp = requests.put(f"{BASE_URL}/matches/{m['match_id']}",
                        json={"score_a": 6, "score_b": 6},
                        headers=_hdr(seeded_comp["token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["score_a"] == 6 and body["score_b"] == 6
    assert body["winner"] in (None, "")


def test_tied_score_with_override_winner_A(seeded_comp):
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    m = [x for x in r.json() if x["phase"] == "group"][1]
    resp = requests.put(f"{BASE_URL}/matches/{m['match_id']}",
                        json={"score_a": 6, "score_b": 6, "winner": "A"},
                        headers=_hdr(seeded_comp["token"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["winner"] == "A"


def test_retire_player_success(seeded_comp):
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    m = [x for x in r.json() if x["phase"] == "group"][2]
    # Find registration ids for team_a in this match
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    async def _get_team():
        return await db.teams.find_one({"team_id": m["team_a_id"]}, {"_id": 0})
    team = asyncio.get_event_loop().run_until_complete(_get_team())
    client.close()
    src_regs = team["source_registration_ids"]
    player_rid = src_regs[0]
    partner_rid = src_regs[1]

    resp = requests.post(
        f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches/{m['match_id']}/retire-player",
        json={"registration_id": player_rid, "reason": "contusao"},
        headers=_hdr(seeded_comp["token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert set(body["retired"]) == {player_rid, partner_rid}

    # Verify DB flags
    r1 = asyncio.get_event_loop().run_until_complete(_find_reg(player_rid))
    r2 = asyncio.get_event_loop().run_until_complete(_find_reg(partner_rid))
    assert r1["retired"] is True and r1["retired_reason"] == "contusao"
    assert r2["retired"] is True and r2.get("retired_by_partner") is True
    assert r2.get("retired_partner_reg_id") == player_rid

    # Save context for leaderboard test
    seeded_comp["retired_reg_ids"] = [player_rid, partner_rid]


def test_retire_player_not_in_match(seeded_comp):
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    matches = [x for x in r.json() if x["phase"] == "group"]
    m0 = matches[3]  # different match
    # Use a reg that belongs to a different match's team (retire flow rejects)
    # Easiest: bogus reg id
    resp = requests.post(
        f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches/{m0['match_id']}/retire-player",
        json={"registration_id": "reg_doesnotexist_xxx", "reason": "contusao"},
        headers=_hdr(seeded_comp["token"]))
    assert resp.status_code == 400
    assert "não faz parte" in resp.json()["detail"]


def test_retire_cross_tenant_isolation(seeded_comp, tenant_b):
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    m = [x for x in r.json() if x["phase"] == "group"][4]
    resp = requests.post(
        f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches/{m['match_id']}/retire-player",
        json={"registration_id": "reg_whatever", "reason": "contusao"},
        headers=_hdr(tenant_b["token"]))
    assert resp.status_code == 404


def test_leaderboard_retired_flag_and_sort(seeded_comp):
    # Score all group matches to give varied points before leaderboard check
    r = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches")
    grp = [x for x in r.json() if x["phase"] == "group"]
    for m in grp:
        # Some may already be scored (tied 6-6). Give team A a win of 6x3 to ensure points.
        payload = {"score_a": 6, "score_b": 3, "winner": "A"}
        requests.put(f"{BASE_URL}/matches/{m['match_id']}", json=payload,
                     headers=_hdr(seeded_comp["token"]))
    lb = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/rotating/leaderboard")
    assert lb.status_code == 200
    board = lb.json()
    assert len(board) == 8
    # retired players should be at bottom
    retired_ids = set(seeded_comp.get("retired_reg_ids", []))
    if retired_ids:
        # Last N rows should include the retired players
        last_rows = board[-len(retired_ids):]
        assert all(row["retired"] for row in last_rows)
        assert set(row["registration_id"] for row in last_rows) == retired_ids
        # Non-retired rows all have retired=False
        for row in board[:-len(retired_ids)]:
            assert row["retired"] is False


def test_next_ko_skips_retired_players(seeded_comp):
    # After scoring, retired players in one group leave 2 active players in that group.
    # rotating_next_round should filter them out of qualifiers.
    resp = requests.post(
        f"{BASE_URL}/competitions/{seeded_comp['cid']}/rotating/next-knockout-round",
        headers=_hdr(seeded_comp["token"]))
    # With 2 retired + 6 active, qualifiers may not be multiple of 4 → could error.
    # Accept either: (a) 200 with fewer qualifiers, or (b) 400 with 'múltiplo' message.
    if resp.status_code == 200:
        body = resp.json()
        # Retired ids must not be among qualifiers (check match teams)
        matches = requests.get(f"{BASE_URL}/competitions/{seeded_comp['cid']}/matches").json()
        ko = [m for m in matches if m["phase"] == "knockout"]
        # Get team source regs
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        async def _get_regs():
            team_ids = []
            for m in ko:
                team_ids += [m["team_a_id"], m["team_b_id"]]
            teams = await db.teams.find({"team_id": {"$in": team_ids}}, {"_id": 0}).to_list(50)
            regs = set()
            for t in teams:
                regs.update(t.get("source_registration_ids") or [])
            return regs
        ko_regs = asyncio.get_event_loop().run_until_complete(_get_regs())
        client.close()
        retired_ids = set(seeded_comp.get("retired_reg_ids", []))
        assert retired_ids.isdisjoint(ko_regs), f"Retired players found in KO: {retired_ids & ko_regs}"
    else:
        assert resp.status_code == 400
        # Should mention multiple-of-4 constraint
        assert "múltiplo" in resp.json()["detail"].lower() or "4" in resp.json()["detail"]
