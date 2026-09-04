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

# ---------------- Registrations ----------------
@api_router.get("/my-registrations")
async def my_registrations(user=Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(200)
    for r in regs:
        c = await db.competitions.find_one({"competition_id": r["competition_id"]}, {"_id": 0})
        r["competition"] = c
    return regs

@api_router.get("/competitions/{competition_id}/registrations")
async def competition_registrations(competition_id: str, admin=Depends(require_admin)):
    return await db.registrations.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)

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
            session = stripe.checkout.Session.create(
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
    return await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(200)

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
    # Return without ObjectIds
    fresh = await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)
    return fresh

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
