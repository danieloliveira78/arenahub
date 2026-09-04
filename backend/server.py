from fastapi import FastAPI, APIRouter, HTTPException, Request, Cookie, Depends, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import ipaddress
import logging
import random
import secrets
import httpx
import stripe
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="ArenaHub API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------- Stripe ----------------
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ---------------- Email ----------------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "ArenaHub")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "danieloliveira78@gmail.com")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)

def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)

def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)

class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []
    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []

def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan(); scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")

async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY not set - skipping email send")
        return None
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return None

# ---------------- Auth Dependencies ----------------
async def get_current_user(request: Request, session_token: Optional[str] = Cookie(None)):
    token = session_token
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def require_admin(user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ---------------- Models ----------------
class SessionRequest(BaseModel):
    session_id: str

class CompetitionTypeCreate(BaseModel):
    name: str
    icon: str = "trophy"
    format: Literal["individual", "duplas", "times"] = "duplas"
    description: Optional[str] = ""

class CompetitionCreate(BaseModel):
    title: str
    type_id: str
    description: Optional[str] = ""
    registration_start: str
    registration_end: str
    start_date: str
    end_date: str
    prize: str
    fee: float = 0.0  # BRL
    max_slots: int = 16
    location: Optional[str] = ""
    allow_individual: bool = True  # if duplas format, allow solo signups for sorteio

class CompetitionUpdate(BaseModel):
    title: Optional[str] = None
    type_id: Optional[str] = None
    description: Optional[str] = None
    registration_start: Optional[str] = None
    registration_end: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    prize: Optional[str] = None
    fee: Optional[float] = None
    max_slots: Optional[int] = None
    location: Optional[str] = None
    allow_individual: Optional[bool] = None

class ProfileUpdate(BaseModel):
    bio: Optional[str] = None
    avatar: Optional[str] = None  # data URL, ~<= 500KB

class RegistrationAdminUpdate(BaseModel):
    mode: Optional[Literal["individual", "dupla"]] = None
    partner_name: Optional[str] = None
    partner_email: Optional[str] = None
    phone: Optional[str] = None
    payment_status: Optional[Literal["paid", "free", "pending", "failed", "refunded"]] = None
    checked_in: Optional[bool] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None

class UserAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    is_admin: Optional[bool] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None

class RegistrationCreate(BaseModel):
    competition_id: str
    mode: Literal["individual", "dupla"] = "individual"
    partner_name: Optional[str] = ""
    partner_email: Optional[str] = ""
    phone: Optional[str] = ""
    origin_url: Optional[str] = ""

class MatchScoreUpdate(BaseModel):
    score_a: int
    score_b: int
    winner: Optional[Literal["A", "B"]] = None

# ---------------- Auth Routes ----------------
@api_router.post("/auth/session")
async def create_session(body: SessionRequest, response: Response):
    """Exchange session_id from Emergent auth for a session_token cookie."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": body.session_id},
            )
        if r.status_code != 200:
            raise HTTPException(401, "Invalid session_id")
        data = r.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session exchange error: {e}")
        raise HTTPException(500, "Auth service error")

    email = data.get("email")
    name = data.get("name")
    picture = data.get("picture")
    session_token = data.get("session_token")

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": name, "picture": picture}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        is_admin = (email == OWNER_EMAIL)
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "is_admin": is_admin, "created_at": datetime.now(timezone.utc).isoformat(),
        })

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        key="session_token", value=session_token, httponly=True, secure=True,
        samesite="none", path="/", max_age=7 * 24 * 3600,
    )
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user, "session_token": session_token}

@api_router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response, session_token: Optional[str] = Cookie(None)):
    token = session_token or (request.headers.get("Authorization", "").replace("Bearer ", "") or None)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"ok": True}

# ---------------- Competition Types (Admin) ----------------
@api_router.get("/competition-types")
async def list_types():
    docs = await db.competition_types.find({}, {"_id": 0}).to_list(500)
    return docs

@api_router.post("/competition-types")
async def create_type(body: CompetitionTypeCreate, admin=Depends(require_admin)):
    doc = {"type_id": f"ct_{uuid.uuid4().hex[:10]}", **body.model_dump(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.competition_types.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/competition-types/{type_id}")
async def delete_type(type_id: str, admin=Depends(require_admin)):
    await db.competition_types.delete_one({"type_id": type_id})
    return {"ok": True}

# ---------------- Competitions ----------------
@api_router.get("/competitions")
async def list_competitions():
    docs = await db.competitions.find({}, {"_id": 0}).sort("start_date", 1).to_list(500)
    # attach counts
    for d in docs:
        d["registered_count"] = await db.registrations.count_documents(
            {"competition_id": d["competition_id"], "payment_status": {"$in": ["paid", "free"]}}
        )
    return docs

@api_router.get("/competitions/{competition_id}")
async def get_competition(competition_id: str):
    doc = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Competition not found")
    doc["registered_count"] = await db.registrations.count_documents(
        {"competition_id": competition_id, "payment_status": {"$in": ["paid", "free"]}}
    )
    return doc

@api_router.post("/competitions")
async def create_competition(body: CompetitionCreate, admin=Depends(require_admin)):
    ct = await db.competition_types.find_one({"type_id": body.type_id}, {"_id": 0})
    if not ct:
        raise HTTPException(404, "Competition type not found")
    doc = {"competition_id": f"comp_{uuid.uuid4().hex[:10]}", **body.model_dump(),
           "type_name": ct["name"], "type_icon": ct.get("icon", "trophy"),
           "type_format": ct["format"], "status": "draft",
           "created_by": admin["user_id"],
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.competitions.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/competitions/{competition_id}")
async def delete_competition(competition_id: str, admin=Depends(require_admin)):
    await db.competitions.delete_one({"competition_id": competition_id})
    await db.registrations.delete_many({"competition_id": competition_id})
    await db.teams.delete_many({"competition_id": competition_id})
    await db.matches.delete_many({"competition_id": competition_id})
    return {"ok": True}

@api_router.put("/competitions/{competition_id}")
async def update_competition(competition_id: str, body: CompetitionUpdate, admin=Depends(require_admin)):
    existing = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Competition not found")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "type_id" in patch:
        ct = await db.competition_types.find_one({"type_id": patch["type_id"]}, {"_id": 0})
        if not ct:
            raise HTTPException(404, "Competition type not found")
        patch["type_name"] = ct["name"]
        patch["type_icon"] = ct.get("icon", "trophy")
        patch["type_format"] = ct["format"]
    if patch:
        await db.competitions.update_one({"competition_id": competition_id}, {"$set": patch})
    fresh = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    fresh["registered_count"] = await db.registrations.count_documents(
        {"competition_id": competition_id, "payment_status": {"$in": ["paid", "free"]}}
    )
    return fresh

# ---------------- User profile ----------------
@api_router.put("/me/profile")
async def update_my_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": patch})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return fresh

# ---------------- Athlete profile (public) ----------------
@api_router.get("/athletes/{player_name}")
async def athlete_profile(player_name: str):
    """Public profile aggregated by player display name from teams + matches."""
    from urllib.parse import unquote
    name = unquote(player_name).strip()
    if not name:
        raise HTTPException(404, "Not found")

    teams = await db.teams.find({"players": name}, {"_id": 0}).to_list(1000)
    if not teams:
        # Also try registrations by user_name (in case they never joined a team)
        regs = await db.registrations.find({"user_name": name}, {"_id": 0}).to_list(500)
        history = []
        for r in regs:
            comp = await db.competitions.find_one({"competition_id": r["competition_id"]}, {"_id": 0})
            if comp:
                history.append({"competition": comp, "team": None, "champion": False, "wins": 0})
        # Try find user for bio
        user = await db.users.find_one({"name": name}, {"_id": 0}) or {}
        return {"player": name, "bio": user.get("bio", ""), "picture": user.get("avatar") or user.get("picture", ""),
                "wins": 0, "championships": 0, "tournaments": len(history),
                "history": history, "partners": []}

    team_ids = [t["team_id"] for t in teams]
    comp_ids = list({t["competition_id"] for t in teams})

    # Get all matches for those competitions
    matches = await db.matches.find({"competition_id": {"$in": comp_ids}}, {"_id": 0}).to_list(5000)
    max_round = {}
    for m in matches:
        c = m["competition_id"]
        if c not in max_round or m["round"] > max_round[c]:
            max_round[c] = m["round"]

    wins = 0
    championships = 0
    per_comp_won_final = {}
    for m in matches:
        winner_id = m["team_a_id"] if m["winner"] == "A" else (m["team_b_id"] if m["winner"] == "B" else None)
        if winner_id and winner_id in team_ids:
            wins += 1
            if m["round"] == max_round.get(m["competition_id"]):
                per_comp_won_final[m["competition_id"]] = True
                championships += 1

    # Partners: co-players in the same teams
    partners = {}
    for t in teams:
        for p in (t.get("players") or []):
            if p and p != name:
                partners[p] = partners.get(p, 0) + 1
    partners_list = [{"name": k, "count": v} for k, v in sorted(partners.items(), key=lambda x: -x[1])]

    # History
    history = []
    for c_id in comp_ids:
        comp = await db.competitions.find_one({"competition_id": c_id}, {"_id": 0})
        team = next((t for t in teams if t["competition_id"] == c_id), None)
        comp_wins = sum(
            1 for m in matches
            if m["competition_id"] == c_id
            and (m["team_a_id"] if m["winner"] == "A" else m["team_b_id"] if m["winner"] == "B" else None) in team_ids
        )
        history.append({
            "competition": comp,
            "team": team,
            "champion": per_comp_won_final.get(c_id, False),
            "wins": comp_wins,
        })
    history.sort(key=lambda x: (not x["champion"], -(x["wins"] or 0)))

    user = await db.users.find_one({"name": name}, {"_id": 0}) or {}

    return {
        "player": name,
        "bio": user.get("bio", ""),
        "picture": user.get("avatar") or user.get("picture", ""),
        "wins": wins,
        "championships": championships,
        "tournaments": len(comp_ids),
        "history": history,
        "partners": partners_list,
    }

async def _avatars_by_email_or_name(emails: list, names: list) -> dict:
    """Return {email: avatar_url, name: avatar_url} lookup."""
    users = await db.users.find(
        {"$or": [{"email": {"$in": emails}}, {"name": {"$in": names}}]},
        {"_id": 0, "email": 1, "name": 1, "avatar": 1, "picture": 1}
    ).to_list(2000)
    by_email = {u.get("email"): (u.get("avatar") or u.get("picture") or "") for u in users if u.get("email")}
    by_name = {u.get("name"): (u.get("avatar") or u.get("picture") or "") for u in users if u.get("name")}
    return {"by_email": by_email, "by_name": by_name}

# ---------------- Registrations ----------------
@api_router.get("/my-registrations")
async def my_registrations(user=Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(200)
    emails = [r.get("partner_email") for r in regs if r.get("partner_email")]
    names = [r.get("partner_name") for r in regs if r.get("partner_name")]
    lookup = await _avatars_by_email_or_name(emails, names)
    for r in regs:
        c = await db.competitions.find_one({"competition_id": r["competition_id"]}, {"_id": 0})
        r["competition"] = c
        r["partner_avatar"] = (
            lookup["by_email"].get(r.get("partner_email") or "")
            or lookup["by_name"].get(r.get("partner_name") or "")
            or ""
        )
    return regs

@api_router.get("/competitions/{competition_id}/registrations")
async def competition_registrations(competition_id: str, admin=Depends(require_admin)):
    return await db.registrations.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)

@api_router.put("/admin/registrations/{registration_id}")
async def admin_update_registration(registration_id: str, body: RegistrationAdminUpdate, admin=Depends(require_admin)):
    existing = await db.registrations.find_one({"registration_id": registration_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Registration not found")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.registrations.update_one({"registration_id": registration_id}, {"$set": patch})
    fresh = await db.registrations.find_one({"registration_id": registration_id}, {"_id": 0})
    return fresh

@api_router.delete("/admin/registrations/{registration_id}")
async def admin_delete_registration(registration_id: str, admin=Depends(require_admin)):
    await db.registrations.delete_one({"registration_id": registration_id})
    return {"ok": True}

@api_router.get("/admin/users")
async def admin_list_users(admin=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "avatar": 0}).sort("created_at", -1).to_list(2000)
    for u in users:
        u["registrations_count"] = await db.registrations.count_documents({"user_id": u["user_id"]})
    return users

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: UserAdminUpdate, admin=Depends(require_admin)):
    existing = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "User not found")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.users.update_one({"user_id": user_id}, {"$set": patch})
    fresh = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return fresh

@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["user_id"]:
        raise HTTPException(400, "Você não pode excluir a si mesmo")
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.registrations.delete_many({"user_id": user_id})
    return {"ok": True}

@api_router.post("/admin/refund/{session_id}")
async def admin_refund(session_id: str, admin=Depends(require_admin)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transação não encontrada")
    if tx.get("payment_status") != "paid":
        raise HTTPException(400, "Transação não está paga (não é possível reembolsar)")
    payment_intent = tx.get("stripe_payment_intent_id")
    if not payment_intent:
        # Try to fetch from session
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            payment_intent = s.payment_intent
        except stripe.error.StripeError as e:
            raise HTTPException(500, f"Erro Stripe: {e}")
    if not payment_intent:
        raise HTTPException(400, "PaymentIntent não localizado")
    try:
        refund = stripe.Refund.create(payment_intent=payment_intent)
    except stripe.error.StripeError as e:
        raise HTTPException(500, f"Erro ao reembolsar: {e}")

    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": "refunded", "refund_id": refund.id,
                  "refunded_at": datetime.now(timezone.utc).isoformat()}}
    )
    reg_id = tx.get("registration_id")
    if reg_id:
        await db.registrations.update_one({"registration_id": reg_id},
                                          {"$set": {"payment_status": "refunded"}})
    return {"ok": True, "refund_id": refund.id, "status": refund.status}

@api_router.post("/registrations")
async def create_registration(body: RegistrationCreate, user=Depends(get_current_user)):
    comp = await db.competitions.find_one({"competition_id": body.competition_id}, {"_id": 0})
    if not comp:
        raise HTTPException(404, "Competition not found")
    existing = await db.registrations.find_one(
        {"competition_id": body.competition_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if existing:
        raise HTTPException(400, "Você já está inscrito nesta competição")

    fee = float(comp.get("fee", 0.0))
    is_free = fee <= 0

    reg_id = f"reg_{uuid.uuid4().hex[:10]}"
    check_in_code = f"chk_{uuid.uuid4().hex[:16]}"
    reg = {
        "registration_id": reg_id,
        "competition_id": body.competition_id,
        "user_id": user["user_id"],
        "user_name": user["name"],
        "user_email": user["email"],
        "mode": body.mode,
        "partner_name": body.partner_name or "",
        "partner_email": body.partner_email or "",
        "phone": body.phone or "",
        "fee": fee,
        "payment_status": "free" if is_free else "pending",
        "checkout_session_id": None,
        "check_in_code": check_in_code,
        "checked_in": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.registrations.insert_one(reg)
    reg.pop("_id", None)

    checkout_url = None
    session_id = None

    if not is_free and body.origin_url:
        try:
            amount_cents = int(round(fee * 100))
            product_name = f"Inscrição: {comp['title']}"
            base_args = dict(
                line_items=[{
                    "price_data": {
                        "currency": "brl",
                        "product_data": {"name": product_name},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=f"{body.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{body.origin_url}/payment/cancel?reg_id={reg_id}",
                metadata={"registration_id": reg_id, "user_id": user["user_id"],
                          "competition_id": body.competition_id},
            )
            # Try card + PIX first (requires BR-activated Stripe account); fallback to card only.
            try:
                session = stripe.checkout.Session.create(
                    **base_args, payment_method_types=["card", "pix"]
                )
            except stripe.error.InvalidRequestError:
                session = stripe.checkout.Session.create(**base_args)
            session_id = session.id
            checkout_url = session.url
            await db.payment_transactions.insert_one({
                "session_id": session_id, "registration_id": reg_id,
                "user_id": user["user_id"], "amount": fee, "currency": "brl",
                "status": "initiated", "payment_status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            await db.registrations.update_one({"registration_id": reg_id},
                                              {"$set": {"checkout_session_id": session_id}})
        except Exception as e:
            logger.error(f"Stripe checkout error: {e}")
            raise HTTPException(500, f"Erro ao criar checkout: {e}")

    if is_free:
        await _send_confirmation_email(user["email"], user["name"], comp, reg, paid=False)

    reg["checkout_session_id"] = session_id
    return {"registration": reg, "checkout_url": checkout_url}

async def _send_confirmation_email(email: str, name: str, comp: dict, reg: dict, paid: bool):
    status_line = ("Pagamento confirmado" if paid else
                   ("Inscrição gratuita confirmada" if reg.get("payment_status") == "free"
                    else "Pagamento pendente"))
    check_in_code = reg.get("check_in_code", "")
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data={check_in_code}"
    html = f"""
    <table role="presentation" width="100%" style="background:#0B0F17;padding:24px">
      <tr><td>
        <table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#111827;border-radius:12px;padding:32px;font-family:Arial,sans-serif;color:#F8FAFC">
          <tr><td>
            <h1 style="color:#22C55E;font-size:24px;margin:0 0 16px 0">Inscrição Confirmada</h1>
            <p style="color:#94A3B8;margin:0 0 24px 0">Olá, {escape(name)}! Sua inscrição em {escape(comp['title'])} foi registrada com sucesso.</p>
            <div style="background:#1E293B;border-radius:8px;padding:20px;margin-bottom:20px">
              <p style="margin:0 0 8px 0"><strong>Torneio:</strong> {escape(comp['title'])}</p>
              <p style="margin:0 0 8px 0"><strong>Modalidade:</strong> {escape(reg['mode'].capitalize())}</p>
              <p style="margin:0 0 8px 0"><strong>Início:</strong> {escape(comp['start_date'])}</p>
              <p style="margin:0 0 8px 0"><strong>Local:</strong> {escape(comp.get('location') or 'A definir')}</p>
              <p style="margin:0 0 8px 0"><strong>Premiação:</strong> {escape(comp.get('prize') or '-')}</p>
              <p style="margin:0"><strong>Status:</strong> {escape(status_line)}</p>
            </div>
            <div style="background:#1E293B;border-radius:8px;padding:20px;margin-bottom:20px;text-align:center">
              <p style="margin:0 0 12px 0;color:#22C55E;font-weight:bold">QR Code de Check-in</p>
              <img src="{qr_url}" alt="QR Check-in" width="220" height="220" style="border-radius:8px;background:#FFF" />
              <p style="margin:12px 0 0 0;font-family:monospace;color:#94A3B8;font-size:12px">{escape(check_in_code)}</p>
              <p style="margin:8px 0 0 0;color:#64748B;font-size:12px">Apresente este código na entrada do torneio.</p>
            </div>
            <p style="color:#64748B;font-size:12px;margin:24px 0 0 0">Enviado por {escape(EMAIL_FROM_NAME)}. Nunca solicitamos senhas ou dados de cartão por e-mail.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """
    await send_email(to=email, subject=f"[ArenaHub] Inscrição em {comp['title']}", html=html)

# ---------------- Payments ----------------
@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not record:
        raise HTTPException(404, "Transaction not found")
    if record.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await _mark_paid(session_id, s.payment_intent)
                record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        except stripe.error.StripeError:
            pass
    return {"session_id": record["session_id"],
            "status": record["status"], "payment_status": record["payment_status"]}

async def _mark_paid(session_id: str, payment_intent: Optional[str] = None):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx or tx.get("payment_status") == "paid":
        return
    await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": "paid",
                  "stripe_payment_intent_id": payment_intent,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    reg_id = tx.get("registration_id")
    if reg_id:
        await db.registrations.update_one({"registration_id": reg_id},
                                          {"$set": {"payment_status": "paid"}})
        reg = await db.registrations.find_one({"registration_id": reg_id}, {"_id": 0})
        if reg:
            comp = await db.competitions.find_one({"competition_id": reg["competition_id"]}, {"_id": 0})
            if comp:
                await _send_confirmation_email(reg["user_email"], reg["user_name"], comp, reg, paid=True)

@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        await _mark_paid(obj["id"], obj.get("payment_intent"))
    elif t == "checkout.session.async_payment_succeeded":
        await _mark_paid(obj["id"], obj.get("payment_intent"))
    elif t in ("checkout.session.async_payment_failed", "checkout.session.expired"):
        await db.payment_transactions.update_one(
            {"session_id": obj["id"]},
            {"$set": {"status": "failed", "payment_status": "failed",
                      "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "ok"}

# ---------------- Teams / Draw ----------------
@api_router.get("/competitions/{competition_id}/teams")
async def list_teams(competition_id: str):
    teams = await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(200)
    names = []
    for t in teams:
        names.extend(t.get("players") or [])
    lookup = await _avatars_by_email_or_name([], names)
    by_name = lookup["by_name"]
    for t in teams:
        t["players_avatars"] = [by_name.get(p, "") for p in (t.get("players") or [])]
    return teams

@api_router.post("/competitions/{competition_id}/draw")
async def draw_teams(competition_id: str, admin=Depends(require_admin)):
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    if not comp:
        raise HTTPException(404, "Competition not found")
    regs = await db.registrations.find(
        {"competition_id": competition_id, "payment_status": {"$in": ["paid", "free"]}},
        {"_id": 0}
    ).to_list(500)
    if len(regs) < 2:
        raise HTTPException(400, "Inscrições confirmadas insuficientes")

    await db.teams.delete_many({"competition_id": competition_id})
    await db.matches.delete_many({"competition_id": competition_id})

    teams = []
    fmt = comp.get("type_format", "duplas")
    if fmt == "duplas":
        # Split into confirmed pairs and solos
        pairs = [r for r in regs if r["mode"] == "dupla" and (r.get("partner_name") or "").strip()]
        solos = [r for r in regs if r["mode"] == "individual" or not (r.get("partner_name") or "").strip()]
        for p in pairs:
            teams.append({
                "team_id": f"team_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "name": f"{p['user_name']} & {p['partner_name']}",
                "players": [p['user_name'], p['partner_name']],
                "source_registration_ids": [p['registration_id']],
            })
        random.shuffle(solos)
        while len(solos) >= 2:
            a = solos.pop(); b = solos.pop()
            teams.append({
                "team_id": f"team_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "name": f"{a['user_name']} & {b['user_name']}",
                "players": [a['user_name'], b['user_name']],
                "source_registration_ids": [a['registration_id'], b['registration_id']],
            })
        if solos:  # odd one out
            leftover = solos.pop()
            teams.append({
                "team_id": f"team_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "name": f"{leftover['user_name']} (BYE)",
                "players": [leftover['user_name']],
                "source_registration_ids": [leftover['registration_id']],
            })
    else:
        # Individual / times: one team per registration
        for r in regs:
            teams.append({
                "team_id": f"team_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "name": r["user_name"],
                "players": [r["user_name"]],
                "source_registration_ids": [r["registration_id"]],
            })

    if teams:
        await db.teams.insert_many([{**t} for t in teams])
    fresh = await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)

    # Notify each registered athlete about their team pairing (fire-and-forget)
    try:
        await _notify_draw(comp, fresh)
    except Exception as e:
        logger.error(f"draw notify failed: {e}")
    return fresh

async def _notify_draw(comp: dict, teams: list):
    """Send email to each paid/free registration announcing their team pairing."""
    # Build source_reg -> team map
    reg_ids = []
    for t in teams:
        reg_ids.extend(t.get("source_registration_ids") or [])
    if not reg_ids:
        return
    regs = await db.registrations.find(
        {"registration_id": {"$in": reg_ids}}, {"_id": 0}
    ).to_list(1000)
    reg_by_id = {r["registration_id"]: r for r in regs}
    # user names for photo lookup
    names_involved = set()
    for t in teams:
        for p in (t.get("players") or []):
            names_involved.add(p)
    users_docs = await db.users.find(
        {"name": {"$in": list(names_involved)}}, {"_id": 0, "name": 1, "avatar": 1, "picture": 1}
    ).to_list(1000)
    photo_by_name = {u["name"]: (u.get("avatar") or u.get("picture") or "") for u in users_docs}

    for t in teams:
        players = t.get("players") or []
        for src_reg_id in (t.get("source_registration_ids") or []):
            r = reg_by_id.get(src_reg_id)
            if not r:
                continue
            partner = next((p for p in players if p != r["user_name"]), "")
            partner_photo = photo_by_name.get(partner, "") if partner else ""
            html = _draw_email_html(r["user_name"], comp, t, partner, partner_photo)
            try:
                await send_email(
                    to=r["user_email"],
                    subject=f"[ArenaHub] Sua dupla em {comp['title']} está definida",
                    html=html,
                )
            except Exception as e:
                logger.error(f"send draw email to {r['user_email']}: {e}")

def _draw_email_html(name: str, comp: dict, team: dict, partner: str, partner_photo: str) -> str:
    # Only include partner photo if it's an absolute https URL (data URLs won't pass gate)
    photo_block = ""
    if partner_photo and partner_photo.startswith("https://"):
        photo_block = (
            f'<img src="{escape(partner_photo)}" alt="{escape(partner)}" width="80" height="80" '
            f'style="border-radius:50%;object-fit:cover;background:#1E293B" />'
        )
    partner_line = (
        f'<div style="margin-top:12px;font-size:18px;color:#F8FAFC"><strong>{escape(partner)}</strong></div>'
        if partner else
        '<div style="margin-top:12px;color:#94A3B8">Você jogará individualmente nesta chave.</div>'
    )
    return f"""
    <table role="presentation" width="100%" style="background:#0B0F17;padding:24px">
      <tr><td>
        <table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#111827;border-radius:12px;padding:32px;font-family:Arial,sans-serif;color:#F8FAFC">
          <tr><td>
            <h1 style="color:#22C55E;font-size:22px;margin:0 0 12px 0">Sorteio realizado!</h1>
            <p style="color:#94A3B8;margin:0 0 20px 0">Olá {escape(name)}, sua dupla em <strong>{escape(comp['title'])}</strong> foi definida.</p>
            <div style="background:#1E293B;border-radius:10px;padding:20px;text-align:center">
              <div style="color:#94A3B8;font-size:12px;text-transform:uppercase;letter-spacing:2px">Seu parceiro(a)</div>
              {photo_block}
              {partner_line}
              <div style="margin-top:16px;color:#94A3B8;font-size:14px">Time: <strong style="color:#22C55E">{escape(team.get('name',''))}</strong></div>
            </div>
            <p style="color:#64748B;font-size:12px;margin:24px 0 0 0">Enviado por {escape(EMAIL_FROM_NAME)}. Boa sorte na disputa!</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """

@api_router.post("/competitions/{competition_id}/bracket")
async def generate_bracket(competition_id: str, admin=Depends(require_admin)):
    teams = await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)
    if len(teams) < 2:
        raise HTTPException(400, "Times insuficientes para chaveamento")

    await db.matches.delete_many({"competition_id": competition_id})

    # Bracket size = next power of 2
    n = 1
    while n < len(teams):
        n *= 2
    shuffled = teams[:]
    random.shuffle(shuffled)
    # Pad with BYEs
    slots = shuffled + [None] * (n - len(shuffled))

    total_rounds = 0
    x = n
    while x > 1:
        total_rounds += 1
        x //= 2

    matches = []
    round_num = 1
    # Round 1
    r1_matches = []
    for i in range(0, n, 2):
        team_a = slots[i]
        team_b = slots[i + 1]
        winner = None
        if team_a and not team_b:
            winner = "A"
        elif team_b and not team_a:
            winner = "B"
        m = {
            "match_id": f"m_{uuid.uuid4().hex[:10]}",
            "competition_id": competition_id,
            "round": round_num,
            "position": i // 2,
            "team_a_id": team_a["team_id"] if team_a else None,
            "team_a_name": team_a["name"] if team_a else "BYE",
            "team_b_id": team_b["team_id"] if team_b else None,
            "team_b_name": team_b["name"] if team_b else "BYE",
            "score_a": 0, "score_b": 0,
            "winner": winner,
            "next_match_id": None,
        }
        matches.append(m); r1_matches.append(m)

    # Subsequent rounds
    prev_round = r1_matches
    for r in range(2, total_rounds + 1):
        curr = []
        for i in range(0, len(prev_round), 2):
            m = {
                "match_id": f"m_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "round": r,
                "position": i // 2,
                "team_a_id": None, "team_a_name": "TBD",
                "team_b_id": None, "team_b_name": "TBD",
                "score_a": 0, "score_b": 0,
                "winner": None,
                "next_match_id": None,
            }
            prev_round[i]["next_match_id"] = m["match_id"]
            prev_round[i + 1]["next_match_id"] = m["match_id"]
            matches.append(m); curr.append(m)
        prev_round = curr

    # Auto-advance BYE winners
    for m in matches:
        if m["winner"] and m["next_match_id"]:
            _propagate_winner(matches, m)

    if matches:
        await db.matches.insert_many([{**m} for m in matches])
    fresh = await db.matches.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)
    return fresh

def _propagate_winner(all_matches: list, m: dict):
    if not m.get("next_match_id"):
        return
    winner_team_id = m["team_a_id"] if m["winner"] == "A" else m["team_b_id"]
    winner_team_name = m["team_a_name"] if m["winner"] == "A" else m["team_b_name"]
    nxt = next((x for x in all_matches if x["match_id"] == m["next_match_id"]), None)
    if not nxt:
        return
    # Even position => slot A; odd => slot B
    slot = "A" if m["position"] % 2 == 0 else "B"
    if slot == "A":
        nxt["team_a_id"] = winner_team_id
        nxt["team_a_name"] = winner_team_name
    else:
        nxt["team_b_id"] = winner_team_id
        nxt["team_b_name"] = winner_team_name

@api_router.get("/competitions/{competition_id}/matches")
async def list_matches(competition_id: str):
    return await db.matches.find({"competition_id": competition_id}, {"_id": 0}).sort([("round", 1), ("position", 1)]).to_list(500)

@api_router.put("/matches/{match_id}")
async def update_match(match_id: str, body: MatchScoreUpdate, admin=Depends(require_admin)):
    m = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Match not found")
    winner = body.winner
    if winner is None:
        if body.score_a > body.score_b:
            winner = "A"
        elif body.score_b > body.score_a:
            winner = "B"
    await db.matches.update_one({"match_id": match_id},
                                {"$set": {"score_a": body.score_a, "score_b": body.score_b,
                                          "winner": winner}})
    if winner and m.get("next_match_id"):
        # Refresh and propagate
        updated = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
        winner_team_id = updated["team_a_id"] if winner == "A" else updated["team_b_id"]
        winner_team_name = updated["team_a_name"] if winner == "A" else updated["team_b_name"]
        slot = "A" if updated["position"] % 2 == 0 else "B"
        if slot == "A":
            await db.matches.update_one({"match_id": updated["next_match_id"]},
                                        {"$set": {"team_a_id": winner_team_id,
                                                  "team_a_name": winner_team_name}})
        else:
            await db.matches.update_one({"match_id": updated["next_match_id"]},
                                        {"$set": {"team_b_id": winner_team_id,
                                                  "team_b_name": winner_team_name}})
    fresh = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
    return fresh

# ---------------- Check-in ----------------
class CheckInRequest(BaseModel):
    code: str

@api_router.get("/checkin/{code}")
async def get_checkin(code: str, admin=Depends(require_admin)):
    reg = await db.registrations.find_one({"check_in_code": code}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Código inválido")
    comp = await db.competitions.find_one({"competition_id": reg["competition_id"]}, {"_id": 0})
    return {"registration": reg, "competition": comp}

@api_router.post("/checkin/{code}")
async def do_checkin(code: str, admin=Depends(require_admin)):
    reg = await db.registrations.find_one({"check_in_code": code}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Código inválido")
    if reg["payment_status"] not in ("paid", "free"):
        raise HTTPException(400, "Inscrição sem pagamento confirmado")
    if reg.get("checked_in"):
        return {"already": True, "registration": reg}
    await db.registrations.update_one({"check_in_code": code},
        {"$set": {"checked_in": True, "checked_in_at": datetime.now(timezone.utc).isoformat()}})
    fresh = await db.registrations.find_one({"check_in_code": code}, {"_id": 0})
    return {"already": False, "registration": fresh}

# ---------------- Rankings ----------------
@api_router.get("/rankings")
async def rankings():
    """Global rankings aggregated from finished matches and championship winners."""
    matches = await db.matches.find(
        {"winner": {"$in": ["A", "B"]}}, {"_id": 0}
    ).to_list(5000)

    wins = {}  # player_name -> win count
    finals_won = {}  # player_name -> championship count

    # Precompute team -> players lookup
    team_ids = set()
    for m in matches:
        if m.get("team_a_id"): team_ids.add(m["team_a_id"])
        if m.get("team_b_id"): team_ids.add(m["team_b_id"])
    if team_ids:
        teams_docs = await db.teams.find({"team_id": {"$in": list(team_ids)}}, {"_id": 0}).to_list(5000)
    else:
        teams_docs = []
    team_players = {t["team_id"]: t.get("players") or [] for t in teams_docs}

    # Determine max round per competition (=final)
    max_round_per_comp = {}
    for m in matches:
        c = m["competition_id"]
        if c not in max_round_per_comp or m["round"] > max_round_per_comp[c]:
            max_round_per_comp[c] = m["round"]

    for m in matches:
        winner_team_id = m["team_a_id"] if m["winner"] == "A" else m["team_b_id"]
        players = team_players.get(winner_team_id, [])
        for p in players:
            wins[p] = wins.get(p, 0) + 1
        if m["round"] == max_round_per_comp.get(m["competition_id"]):
            for p in players:
                finals_won[p] = finals_won.get(p, 0) + 1

    all_players = list(set(wins.keys()) | set(finals_won.keys()))
    # Look up user avatars/pictures for players
    users_docs = await db.users.find({"name": {"$in": all_players}}, {"_id": 0, "name": 1, "avatar": 1, "picture": 1}).to_list(1000)
    user_by_name = {u["name"]: u for u in users_docs}
    ranking_list = []
    for p in all_players:
        u = user_by_name.get(p, {})
        ranking_list.append({
            "player": p,
            "wins": wins.get(p, 0),
            "championships": finals_won.get(p, 0),
            "avatar": u.get("avatar") or u.get("picture") or "",
        })
    ranking_list.sort(key=lambda x: (-x["championships"], -x["wins"], x["player"]))
    return ranking_list

# ---------------- Finance (admin) ----------------
@api_router.get("/admin/finance")
async def admin_finance(competition_id: Optional[str] = None, status: Optional[str] = None,
                        admin=Depends(require_admin)):
    q = {}
    if competition_id:
        # Filter payment_transactions by registration_id belonging to this competition
        regs = await db.registrations.find(
            {"competition_id": competition_id}, {"_id": 0, "registration_id": 1}
        ).to_list(5000)
        q["registration_id"] = {"$in": [r["registration_id"] for r in regs]}
    if status:
        q["payment_status"] = status
    txs = await db.payment_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    # Attach competition + registration info
    reg_ids = [t["registration_id"] for t in txs if t.get("registration_id")]
    regs = await db.registrations.find({"registration_id": {"$in": reg_ids}}, {"_id": 0}).to_list(5000) if reg_ids else []
    reg_by_id = {r["registration_id"]: r for r in regs}
    comp_ids = list({r["competition_id"] for r in regs})
    comps = await db.competitions.find({"competition_id": {"$in": comp_ids}}, {"_id": 0}).to_list(500) if comp_ids else []
    comp_by_id = {c["competition_id"]: c for c in comps}

    rows = []
    total_paid = 0.0
    total_pending = 0.0
    total_failed = 0.0
    per_comp = {}
    for t in txs:
        r = reg_by_id.get(t.get("registration_id"), {})
        c = comp_by_id.get(r.get("competition_id"), {})
        amount = float(t.get("amount") or 0)
        row = {
            "session_id": t.get("session_id"),
            "created_at": t.get("created_at"),
            "amount": amount,
            "currency": t.get("currency", "brl"),
            "payment_status": t.get("payment_status"),
            "user_name": r.get("user_name", ""),
            "user_email": r.get("user_email", ""),
            "competition_id": r.get("competition_id"),
            "competition_title": c.get("title", ""),
        }
        rows.append(row)
        if t.get("payment_status") == "paid":
            total_paid += amount
            comp_key = r.get("competition_id") or "other"
            per_comp[comp_key] = per_comp.get(comp_key, {"title": c.get("title", "Outros"), "total": 0.0, "count": 0})
            per_comp[comp_key]["total"] += amount
            per_comp[comp_key]["count"] += 1
        elif t.get("payment_status") == "pending":
            total_pending += amount
        else:
            total_failed += amount

    return {
        "rows": rows,
        "totals": {"paid": total_paid, "pending": total_pending, "failed": total_failed, "count": len(rows)},
        "per_competition": [
            {"competition_id": k, "title": v["title"], "total": v["total"], "count": v["count"]}
            for k, v in sorted(per_comp.items(), key=lambda x: -x[1]["total"])
        ],
    }

@api_router.get("/admin/finance/export")
async def admin_finance_csv(competition_id: Optional[str] = None, status: Optional[str] = None,
                             admin=Depends(require_admin)):
    from fastapi.responses import Response
    data = await admin_finance(competition_id=competition_id, status=status, admin=admin)
    lines = ["data,torneio,atleta,email,valor,moeda,status,session_id"]
    for r in data["rows"]:
        row = [
            r["created_at"] or "",
            (r["competition_title"] or "").replace(",", " "),
            (r["user_name"] or "").replace(",", " "),
            r["user_email"] or "",
            f"{r['amount']:.2f}",
            r["currency"] or "",
            r["payment_status"] or "",
            r["session_id"] or "",
        ]
        lines.append(",".join(str(x) for x in row))
    csv_content = "\n".join(lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="finance.csv"'},
    )

# ---------------- Seed default data ----------------
@api_router.post("/seed-defaults")
async def seed_defaults():
    """Seed a few competition types if none exist (public bootstrap)."""
    existing = await db.competition_types.count_documents({})
    if existing > 0:
        return {"seeded": False, "count": existing}
    defaults = [
        {"name": "Futevôlei", "icon": "volleyball", "format": "duplas", "description": "Torneios de dupla na areia"},
        {"name": "Beach Tennis", "icon": "tennis", "format": "duplas", "description": "Beach Tennis em duplas"},
        {"name": "Padel", "icon": "tennis", "format": "duplas", "description": "Padel em duplas"},
        {"name": "Vôlei de Praia", "icon": "volleyball", "format": "duplas", "description": "Vôlei de praia 2x2"},
        {"name": "Futebol Society", "icon": "trophy", "format": "times", "description": "Futebol society por times"},
    ]
    for d in defaults:
        await db.competition_types.insert_one({
            "type_id": f"ct_{uuid.uuid4().hex[:10]}", **d,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return {"seeded": True, "count": len(defaults)}

@api_router.get("/")
async def root():
    return {"message": "ArenaHub API"}

# Include router
app.include_router(api_router)

# CORS
origins_env = os.environ.get('CORS_ORIGINS', '*')
if origins_env.strip() == '*':
    origins_config = ["*"]
else:
    origins_config = [o.strip() for o in origins_env.split(',') if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
