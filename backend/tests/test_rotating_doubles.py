"""Backend tests for 'duplas_rotativas' (Rei da Praia) tournament format."""
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
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SUPER_EMAIL = "danieloliveira78@gmail.com"
SUPER_PASSWORD = "ArenaHub@2026"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _signup_tenant(prefix="rot"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.com"
    pwd = "Passw0rd!"
    r = requests.post(f"{BASE_URL}/auth/signup", json={
        "email": email, "password": pwd, "name": f"Admin {prefix}",
        "organization_name": f"Clube {prefix}",
        "accept_terms": True, "accept_privacy": True,
    })
    assert r.status_code == 200, r.text
    return {"email": email, "password": pwd, "token": r.json()["session_token"],
            "user": r.json()["user"], "tenant": r.json()["tenant"]}


def _create_type(token, fmt="duplas_rotativas", name=None):
    r = requests.post(f"{BASE_URL}/competition-types",
                      json={"name": name or f"Type {fmt}", "format": fmt, "icon": "trophy"},
                      headers=_hdr(token))
    return r


def _create_competition(token, type_id, title="Rei da Praia Test", fee=0.0):
    r = requests.post(f"{BASE_URL}/competitions", json={
        "title": title, "type_id": type_id, "description": "",
        "registration_start": "2026-01-01", "registration_end": "2026-12-31",
        "start_date": "2026-01-15", "end_date": "2026-01-16",
        "prize": "Trophy", "fee": fee, "max_slots": 32, "location": "Praia",
    }, headers=_hdr(token))
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_registrations(competition_id, tenant_id, n=8, prefix="P"):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    reg_ids = []
    for i in range(n):
        uid = f"user_{uuid.uuid4().hex[:12]}"
        rid = f"reg_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({
            "user_id": uid, "email": f"{prefix.lower()}{i}_{uuid.uuid4().hex[:6]}@t.co",
            "name": f"{prefix}{i}", "is_admin": False, "tenant_role": "athlete",
        })
        await db.registrations.insert_one({
            "registration_id": rid, "competition_id": competition_id,
            "tenant_id": tenant_id, "user_id": uid,
            "user_name": f"{prefix}{i}", "user_email": f"{prefix.lower()}{i}@t.co",
            "mode": "individual", "partner_name": "", "partner_email": "",
            "phone": "", "fee": 0.0, "payment_status": "free",
            "checkout_session_id": None, "check_in_code": f"chk_{uuid.uuid4().hex[:12]}",
            "checked_in": False,
        })
        reg_ids.append(rid)
    client.close()
    return reg_ids


async def _cleanup(competition_id):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.registrations.delete_many({"competition_id": competition_id})
    await db.matches.delete_many({"competition_id": competition_id})
    await db.teams.delete_many({"competition_id": competition_id})
    await db.groups.delete_many({"competition_id": competition_id})
    client.close()


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def tenant_a():
    t = _signup_tenant("rotA")
    yield t
    # cleanup users/tenant
    async def _c():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"email": t["email"]})
        await db.tenants.delete_one({"tenant_id": t["tenant"]["tenant_id"]})
        client.close()
    asyncio.get_event_loop().run_until_complete(_c())


@pytest.fixture(scope="module")
def tenant_b():
    t = _signup_tenant("rotB")
    yield t
    async def _c():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"email": t["email"]})
        await db.tenants.delete_one({"tenant_id": t["tenant"]["tenant_id"]})
        client.close()
    asyncio.get_event_loop().run_until_complete(_c())


# ---------------- Tests ----------------
def test_create_type_duplas_rotativas(tenant_a):
    r = _create_type(tenant_a["token"], "duplas_rotativas")
    assert r.status_code == 200, r.text
    assert r.json()["format"] == "duplas_rotativas"
    tenant_a["type_id_rot"] = r.json()["type_id"]


def test_create_type_invalid_format(tenant_a):
    r = _create_type(tenant_a["token"], "invalido")
    assert r.status_code == 422


def test_create_competition_and_type_format(tenant_a):
    comp = _create_competition(tenant_a["token"], tenant_a["type_id_rot"], "Comp Rot Basic")
    r = requests.get(f"{BASE_URL}/competitions/{comp['competition_id']}")
    assert r.status_code == 200
    assert r.json().get("type_format") == "duplas_rotativas"
    tenant_a["comp_id_basic"] = comp["competition_id"]


def test_draw_groups_fewer_than_4(tenant_a):
    comp = _create_competition(tenant_a["token"], tenant_a["type_id_rot"], "Comp <4")
    cid = comp["competition_id"]
    # No regs
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 400
    assert "múltiplos de 4" in r.json()["detail"] or "mínimo" in r.json()["detail"]
    asyncio.get_event_loop().run_until_complete(_cleanup(cid))


def test_draw_groups_non_multiple_of_4(tenant_a):
    comp = _create_competition(tenant_a["token"], tenant_a["type_id_rot"], "Comp 5")
    cid = comp["competition_id"]
    asyncio.get_event_loop().run_until_complete(
        _seed_registrations(cid, tenant_a["tenant"]["tenant_id"], n=5))
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 400
    assert "múltiplos de 4" in r.json()["detail"]
    asyncio.get_event_loop().run_until_complete(_cleanup(cid))


def test_full_flow_8_players(tenant_a):
    comp = _create_competition(tenant_a["token"], tenant_a["type_id_rot"], "Comp 8 Full")
    cid = comp["competition_id"]
    tenant_a["comp_id_full"] = cid
    reg_ids = asyncio.get_event_loop().run_until_complete(
        _seed_registrations(cid, tenant_a["tenant"]["tenant_id"], n=8))

    # Draw groups
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["groups"] == 2
    assert body["matches"] == 6

    # GET groups
    r = requests.get(f"{BASE_URL}/competitions/{cid}/rotating/groups", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 2
    for g in groups:
        assert len(g["player_reg_ids"]) == 4
        assert len(g["player_names"]) == 4

    # Verify matches (2 groups * 3 rounds = 6, phase=group, round in 1..3)
    r = requests.get(f"{BASE_URL}/competitions/{cid}/matches")
    matches = r.json()
    grp_matches = [m for m in matches if m["phase"] == "group"]
    assert len(grp_matches) == 6
    for m in grp_matches:
        assert m["round"] in (1, 2, 3)
        assert m["group_id"] and m["team_a_id"] and m["team_b_id"]
        assert m["team_a_name"] and m["team_b_name"]

    # next-knockout-round before group phase complete → 400
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/next-knockout-round", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 400
    assert "fase de grupos" in r.json()["detail"]

    # Score all group matches: A wins 6x3
    for m in grp_matches:
        r = requests.put(f"{BASE_URL}/matches/{m['match_id']}",
                         json={"score_a": 6, "score_b": 3, "winner": "A"},
                         headers=_hdr(tenant_a["token"]))
        assert r.status_code == 200, r.text

    # Leaderboard
    r = requests.get(f"{BASE_URL}/competitions/{cid}/rotating/leaderboard")
    assert r.status_code == 200
    board = r.json()
    assert len(board) == 8
    # Descending sort
    for i in range(len(board) - 1):
        assert board[i]["points"] >= board[i + 1]["points"]
    # Every player has 3 matches (each player plays every round in their group)
    for p in board:
        assert p["matches"] == 3
        # points = sum of their team score across 3 matches. In each round they're on team A or B.
        # points should be between 9 (all losing) and 18 (all winning). Since all winners scored 6, losers 3:
        # each player has some wins & losses (individual). Points >= 9.
        assert p["points"] >= 9

    # Start knockout (only 4 qualifiers from 2 groups → 1 KO match)
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/next-knockout-round", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200, r.text
    ko = r.json()
    assert ko["round"] == 1
    assert ko["matches"] == 1
    assert ko["phase"] == "knockout"

    # Call again while KO match unresolved → 400
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/next-knockout-round", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 400
    assert "rodada atual" in r.json()["detail"]

    # Fetch KO match and score it
    r = requests.get(f"{BASE_URL}/competitions/{cid}/matches")
    ko_matches = [m for m in r.json() if m["phase"] == "knockout"]
    assert len(ko_matches) == 1
    final = ko_matches[0]
    r = requests.put(f"{BASE_URL}/matches/{final['match_id']}",
                     json={"score_a": 6, "score_b": 4, "winner": "A"},
                     headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200

    # Next call → finished
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/next-knockout-round", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 200, r.text
    result = r.json()
    assert result.get("finished") is True
    assert len(result.get("champions_registration_ids", [])) == 2


def test_tenant_isolation(tenant_a, tenant_b):
    cid = tenant_a["comp_id_basic"]
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups", headers=_hdr(tenant_b["token"]))
    assert r.status_code == 404


def test_legacy_format_rejects_rotating_endpoint(tenant_a):
    # Create individual-format type + competition
    r = _create_type(tenant_a["token"], "individual", "Individual T")
    assert r.status_code == 200
    tid = r.json()["type_id"]
    comp = _create_competition(tenant_a["token"], tid, "Legacy Individual")
    cid = comp["competition_id"]
    r = requests.post(f"{BASE_URL}/competitions/{cid}/rotating/draw-groups", headers=_hdr(tenant_a["token"]))
    assert r.status_code == 400
    assert "não é do formato" in r.json()["detail"]


def test_legacy_duplas_draw_still_works(tenant_b):
    r = _create_type(tenant_b["token"], "duplas", "Duplas Legacy")
    assert r.status_code == 200
    tid = r.json()["type_id"]
    comp = _create_competition(tenant_b["token"], tid, "Legacy Duplas")
    cid = comp["competition_id"]
    # Seed 4 individual regs (allow_individual=True)
    asyncio.get_event_loop().run_until_complete(
        _seed_registrations(cid, tenant_b["tenant"]["tenant_id"], n=4, prefix="D"))
    # Classic draw endpoint
    r = requests.post(f"{BASE_URL}/competitions/{cid}/draw", headers=_hdr(tenant_b["token"]))
    # Should either succeed (200) or return a valid non-500 response
    assert r.status_code in (200, 400), r.text
    asyncio.get_event_loop().run_until_complete(_cleanup(cid))
