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
import bcrypt
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

# ---------------- SaaS Plan Config ----------------
TRIAL_DAYS = 14
GRACE_DAYS = 7  # extra edit-access days after payment failure before we lock writes

PLAN_LOOKUPS = ["starter_monthly", "starter_yearly"]

PLAN_LIMITS = {
    "starter": {"tournaments": 5, "athletes": 200},
}

# ---------------- Password hashing (bcrypt) ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

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

async def require_super_admin(user=Depends(get_current_user)):
    if user.get("platform_role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user

# ---------------- Tenant helpers ----------------
async def _get_tenant(tenant_id: str) -> Optional[dict]:
    if not tenant_id:
        return None
    return await db.tenants.find_one({"tenant_id": tenant_id}, {"_id": 0})

async def _create_tenant(owner_user_id: str, org_name: str) -> dict:
    tenant_id = f"tn_{uuid.uuid4().hex[:12]}"
    slug_base = re.sub(r"[^a-z0-9]+", "-", (org_name or "org").lower()).strip("-") or "org"
    slug = slug_base
    i = 1
    while await db.tenants.find_one({"slug": slug}, {"_id": 0}):
        i += 1
        slug = f"{slug_base}-{i}"
    trial_end = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    doc = {
        "tenant_id": tenant_id, "slug": slug, "name": org_name,
        "owner_user_id": owner_user_id,
        "subscription_status": "trialing",  # trialing | active | past_due | canceled | inactive
        "plan": "starter",
        "trial_end": trial_end.isoformat(),
        "current_period_end": trial_end.isoformat(),
        "stripe_customer_id": None, "stripe_subscription_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tenants.insert_one(doc)
    doc.pop("_id", None)
    return doc

def _sub_effective_status(tenant: dict) -> str:
    """Compute effective status considering grace period."""
    if not tenant:
        return "inactive"
    status = tenant.get("subscription_status", "inactive")
    if status == "past_due":
        # Grace period
        cpe = tenant.get("current_period_end")
        if cpe:
            try:
                end = datetime.fromisoformat(cpe)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > end + timedelta(days=GRACE_DAYS):
                    return "inactive"
                return "grace_period"
            except Exception:
                return status
    return status

def _can_write(tenant: dict) -> bool:
    st = _sub_effective_status(tenant)
    return st in ("trialing", "active", "grace_period")

async def resolve_principal(user=Depends(get_current_user)):
    """Attach effective tenant + subscription status. Auto-creates tenant if missing."""
    tenant = None
    if user.get("tenant_id"):
        tenant = await _get_tenant(user["tenant_id"])
    if not tenant:
        # Auto-provision default tenant on first authenticated call (Google OAuth path)
        tenant = await _create_tenant(user["user_id"], user.get("name") or user.get("email") or "Meu clube")
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"tenant_id": tenant["tenant_id"], "tenant_role": "admin"}})
        user["tenant_id"] = tenant["tenant_id"]
        user["tenant_role"] = "admin"
    user["_tenant"] = tenant
    user["_effective_status"] = _sub_effective_status(tenant)
    user["_can_write"] = _can_write(tenant)
    return user

async def require_active_subscription(user=Depends(resolve_principal)):
    """For write endpoints — blocks if subscription is fully expired."""
    if user.get("platform_role") == "super_admin":
        return user
    st = user.get("_effective_status")
    if st not in ("trialing", "active", "grace_period"):
        raise HTTPException(402, "Assinatura inativa. Regularize para continuar usando a plataforma.")
    return user

async def require_admin(user=Depends(resolve_principal)):
    if not user.get("is_admin") and user.get("platform_role") != "super_admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def _admin_owns_or_raise(admin: dict, entity: Optional[dict], name: str = "recurso"):
    """Ensure admin can access the entity by tenant. Super admin bypasses."""
    if not entity:
        raise HTTPException(404, f"{name.capitalize()} não encontrado")
    if admin.get("platform_role") == "super_admin":
        return
    if entity.get("tenant_id") and entity["tenant_id"] != admin.get("tenant_id"):
        raise HTTPException(404, f"{name.capitalize()} não encontrado")

def tenant_scope(user: dict, extra: Optional[dict] = None) -> dict:
    """Return mongo filter scoped to the user's tenant. Super admin sees all."""
    q = dict(extra or {})
    if user.get("platform_role") != "super_admin":
        q["tenant_id"] = user.get("tenant_id")
    return q

# ---------------- Models ----------------
class SessionRequest(BaseModel):
    session_id: str

class SignupRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = ""
    password: str
    organization_name: str
    accept_terms: bool = True
    accept_privacy: bool = True

class LoginRequest(BaseModel):
    email: str
    password: str

class SubscribeRequest(BaseModel):
    lookup_key: Literal["starter_monthly", "starter_yearly"]
    origin_url: str

class ImpersonateRequest(BaseModel):
    tenant_id: str

class CompetitionTypeCreate(BaseModel):
    name: str
    icon: str = "trophy"
    format: Literal["individual", "duplas", "times", "duplas_rotativas"] = "duplas"
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

class RetirePlayerRequest(BaseModel):
    registration_id: str
    reason: Literal["contusao", "estafe", "outro"] = "contusao"
    notes: Optional[str] = ""

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
        platform_role = "super_admin" if email == OWNER_EMAIL else None
        # Auto-create tenant for new Google user
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "is_admin": True,  # tenant admin (of their own tenant)
            "tenant_role": "admin",
            "platform_role": platform_role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        tenant = await _create_tenant(user_id, name or "Meu clube")
        await db.users.update_one({"user_id": user_id},
                                  {"$set": {"tenant_id": tenant["tenant_id"]}})

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

# ---------------- Email/Password Signup + Login ----------------
@api_router.post("/auth/signup")
async def signup(body: SignupRequest, response: Response):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "E-mail inválido")
    if len(body.password) < 6:
        raise HTTPException(400, "Senha muito curta (mínimo 6 caracteres)")
    if not body.accept_terms or not body.accept_privacy:
        raise HTTPException(400, "É necessário aceitar os termos e a política")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(400, "E-mail já cadastrado")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    platform_role = "super_admin" if email == OWNER_EMAIL else None
    await db.users.insert_one({
        "user_id": user_id, "email": email, "name": body.name.strip(),
        "phone": body.phone or "",
        "password_hash": hash_password(body.password),
        "is_admin": True, "tenant_role": "admin",
        "platform_role": platform_role,
        "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    tenant = await _create_tenant(user_id, body.organization_name or body.name)
    await db.users.update_one({"user_id": user_id},
                              {"$set": {"tenant_id": tenant["tenant_id"]}})

    # Create session
    session_token = f"sess_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(key="session_token", value=session_token, httponly=True,
                        secure=True, samesite="none", path="/", max_age=7*24*3600)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"user": user, "tenant": tenant, "session_token": session_token}

@api_router.post("/auth/login")
async def login(body: LoginRequest, response: Response):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "E-mail ou senha inválidos")
    session_token = f"sess_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user["user_id"],
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(key="session_token", value=session_token, httponly=True,
                        secure=True, samesite="none", path="/", max_age=7*24*3600)
    user.pop("password_hash", None)
    return {"user": user, "session_token": session_token}

class ForgotPasswordRequest(BaseModel):
    email: str
    origin_url: Optional[str] = ""

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@api_router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    """Always returns ok:true (do not leak whether email exists). Sends reset link if user exists."""
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("password_hash"):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user["user_id"], "email": email,
            "expires_at": expires_at.isoformat(),
            "used": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        origin = (body.origin_url or "").rstrip("/") or os.environ.get("APP_URL", "").rstrip("/")
        reset_link = f"{origin}/redefinir-senha?token={token}" if origin else f"https://arenahub.app/redefinir-senha?token={token}"
        html = f"""
        <table role="presentation" width="100%" style="background:#0B0F17;padding:24px">
          <tr><td>
            <table role="presentation" width="100%" style="max-width:520px;margin:0 auto;background:#111827;border-radius:12px;padding:32px;font-family:Arial,sans-serif;color:#F8FAFC">
              <tr><td>
                <h1 style="color:#22C55E;font-size:22px;margin:0 0 16px 0">Redefinir sua senha</h1>
                <p style="color:#94A3B8;margin:0 0 20px 0">Olá {escape(user.get('name') or email)}, recebemos uma solicitação para redefinir a senha da sua conta ArenaHub.</p>
                <p style="color:#94A3B8;margin:0 0 24px 0">Clique no botão abaixo para escolher uma nova senha. Este link expira em 1 hora.</p>
                <table role="presentation" align="center" style="margin:0 auto 24px auto"><tr><td>
                  <a href="{escape(reset_link)}" style="display:inline-block;background:#22C55E;color:#0F172A;text-decoration:none;padding:14px 24px;border-radius:10px;font-weight:bold;font-size:15px">Redefinir minha senha</a>
                </td></tr></table>
                <p style="color:#64748B;font-size:12px;margin:20px 0 0 0">Se você não solicitou, ignore este e-mail. Nunca pedimos senhas ou cartões por resposta de e-mail.</p>
                <p style="color:#64748B;font-size:12px;margin:12px 0 0 0">Enviado por {escape(EMAIL_FROM_NAME)}.</p>
              </td></tr>
            </table>
          </td></tr>
        </table>
        """
        try:
            await send_email(to=email, subject="[ArenaHub] Redefinir sua senha", html=html)
        except Exception as e:
            logger.error(f"forgot-password email send failed for {email}: {e}")
    return {"ok": True}

@api_router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordRequest):
    if len(body.new_password) < 6:
        raise HTTPException(400, "Senha muito curta (mínimo 6 caracteres)")
    rec = await db.password_reset_tokens.find_one({"token": body.token}, {"_id": 0})
    if not rec:
        raise HTTPException(400, "Token inválido ou já usado")
    if rec.get("used"):
        raise HTTPException(400, "Este link já foi utilizado. Solicite outro.")
    exp = rec["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Este link expirou. Solicite outro.")
    await db.users.update_one({"user_id": rec["user_id"]},
                              {"$set": {"password_hash": hash_password(body.new_password)}})
    await db.password_reset_tokens.update_one({"token": body.token},
                                              {"$set": {"used": True,
                                                        "used_at": datetime.now(timezone.utc).isoformat()}})
    # Invalidate all existing sessions for that user (defense-in-depth)
    await db.user_sessions.delete_many({"user_id": rec["user_id"]})
    return {"ok": True}

# ---------------- Plans + Subscriptions ----------------
@api_router.get("/plans")
async def list_plans():
    plans = []
    for lk in PLAN_LOOKUPS:
        try:
            prices = stripe.Price.list(lookup_keys=[lk], active=True, limit=1).data
            if prices:
                p = prices[0]
                plans.append({
                    "lookup_key": lk,
                    "amount": (p.unit_amount or 0) / 100,
                    "currency": p.currency,
                    "interval": (p.recurring or {}).get("interval") if p.recurring else None,
                    "product_name": stripe.Product.retrieve(p.product).name,
                    "limits": PLAN_LIMITS.get("starter"),
                    "trial_days": TRIAL_DAYS,
                })
        except Exception as e:
            logger.error(f"plan lookup {lk}: {e}")
    return plans

@api_router.get("/me/tenant")
async def get_my_tenant(user=Depends(resolve_principal)):
    return {
        "tenant": user.get("_tenant"),
        "effective_status": user.get("_effective_status"),
        "can_write": user.get("_can_write"),
        "limits": PLAN_LIMITS.get(user.get("_tenant", {}).get("plan", "starter"), {}),
    }

@api_router.post("/subscriptions/checkout")
async def subscription_checkout(body: SubscribeRequest, user=Depends(resolve_principal)):
    tenant = user["_tenant"]
    prices = stripe.Price.list(lookup_keys=[body.lookup_key], active=True, limit=1).data
    if not prices:
        raise HTTPException(500, "Preço não encontrado")
    price = prices[0]

    # Ensure Stripe customer
    customer_id = tenant.get("stripe_customer_id")
    if not customer_id:
        cust = stripe.Customer.create(
            email=user["email"], name=tenant.get("name") or user.get("name"),
            metadata={"tenant_id": tenant["tenant_id"], "user_id": user["user_id"]},
        )
        customer_id = cust.id
        await db.tenants.update_one({"tenant_id": tenant["tenant_id"]},
                                    {"$set": {"stripe_customer_id": customer_id}})

    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription",
        success_url=f"{body.origin_url}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/subscription/cancel",
        metadata={"tenant_id": tenant["tenant_id"], "lookup_key": body.lookup_key,
                  "purpose": "saas_subscription"},
        subscription_data={
            "metadata": {"tenant_id": tenant["tenant_id"], "lookup_key": body.lookup_key},
        },
    )
    return {"checkout_url": session.url, "session_id": session.id}

@api_router.post("/subscriptions/portal")
async def subscription_portal(user=Depends(resolve_principal)):
    tenant = user["_tenant"]
    customer_id = tenant.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(400, "Nenhuma assinatura ativa")
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{os.environ.get('APP_URL','')}/minha-assinatura" or "https://arenahub.com",
        )
        return {"portal_url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(500, f"Erro: {e}")

@api_router.post("/subscriptions/cancel")
async def cancel_subscription(user=Depends(resolve_principal)):
    tenant = user["_tenant"]
    sub_id = tenant.get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(400, "Nenhuma assinatura ativa")
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        await db.tenants.update_one({"tenant_id": tenant["tenant_id"]},
                                    {"$set": {"cancel_at_period_end": True}})
        return {"ok": True}
    except stripe.error.StripeError as e:
        raise HTTPException(500, f"Erro: {e}")

# ---------------- Competition Types (Admin) ----------------
@api_router.get("/competition-types")
async def list_types(request: Request):
    """Public list: optionally filter by tenant slug. Authenticated admins get their tenant."""
    tenant_slug = request.query_params.get("tenant")
    q = {}
    if tenant_slug:
        t = await db.tenants.find_one({"slug": tenant_slug}, {"_id": 0})
        if t:
            q["tenant_id"] = t["tenant_id"]
        else:
            return []
    else:
        # If authenticated, scope to user's tenant
        token = request.cookies.get("session_token") or (request.headers.get("Authorization","").replace("Bearer ","") or None)
        if token:
            sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            if sess:
                u = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
                if u and u.get("tenant_id") and u.get("platform_role") != "super_admin":
                    q["tenant_id"] = u["tenant_id"]
    docs = await db.competition_types.find(q, {"_id": 0}).to_list(500)
    return docs

@api_router.post("/competition-types")
async def create_type(body: CompetitionTypeCreate, admin=Depends(require_active_subscription)):
    doc = {"type_id": f"ct_{uuid.uuid4().hex[:10]}", **body.model_dump(),
           "tenant_id": admin["tenant_id"], "created_by": admin["user_id"],
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.competition_types.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/competition-types/{type_id}")
async def delete_type(type_id: str, admin=Depends(require_admin)):
    existing = await db.competition_types.find_one({"type_id": type_id}, {"_id": 0})
    _admin_owns_or_raise(admin, existing, "tipo de competição")
    await db.competition_types.delete_one({"type_id": type_id})
    return {"ok": True}

# ---------------- Competitions ----------------
@api_router.get("/competitions")
async def list_competitions(request: Request):
    tenant_slug = request.query_params.get("tenant")
    q = {}
    if tenant_slug:
        t = await db.tenants.find_one({"slug": tenant_slug}, {"_id": 0})
        if not t:
            return []
        q["tenant_id"] = t["tenant_id"]
    else:
        # If authenticated non-super_admin: scope to tenant. Else: public marketplace (all).
        token = request.cookies.get("session_token") or (request.headers.get("Authorization","").replace("Bearer ","") or None)
        if token:
            sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            if sess:
                u = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
                if u and u.get("tenant_id") and u.get("platform_role") != "super_admin":
                    q["tenant_id"] = u["tenant_id"]
    docs = await db.competitions.find(q, {"_id": 0}).sort("start_date", 1).to_list(500)
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
async def create_competition(body: CompetitionCreate, admin=Depends(require_active_subscription)):
    # Plan limit enforcement
    active_count = await db.competitions.count_documents({"tenant_id": admin["tenant_id"]})
    limit = PLAN_LIMITS.get("starter", {}).get("tournaments", 5)
    if admin.get("platform_role") != "super_admin" and active_count >= limit:
        raise HTTPException(402, f"Limite do plano atingido ({limit} torneios). Faça upgrade para adicionar mais.")
    ct = await db.competition_types.find_one(
        {"type_id": body.type_id, "tenant_id": admin["tenant_id"]}, {"_id": 0}
    ) or await db.competition_types.find_one({"type_id": body.type_id}, {"_id": 0})
    if not ct:
        raise HTTPException(404, "Competition type not found")
    doc = {"competition_id": f"comp_{uuid.uuid4().hex[:10]}", **body.model_dump(),
           "type_name": ct["name"], "type_icon": ct.get("icon", "trophy"),
           "type_format": ct["format"], "status": "draft",
           "tenant_id": admin["tenant_id"],
           "created_by": admin["user_id"],
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.competitions.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/competitions/{competition_id}")
async def delete_competition(competition_id: str, admin=Depends(require_admin)):
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    await db.competitions.delete_one({"competition_id": competition_id})
    await db.registrations.delete_many({"competition_id": competition_id})
    await db.teams.delete_many({"competition_id": competition_id})
    await db.matches.delete_many({"competition_id": competition_id})
    return {"ok": True}

@api_router.put("/competitions/{competition_id}")
async def update_competition(competition_id: str, body: CompetitionUpdate, admin=Depends(require_admin)):
    existing = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, existing, "torneio")
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
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    return await db.registrations.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)

@api_router.put("/admin/registrations/{registration_id}")
async def admin_update_registration(registration_id: str, body: RegistrationAdminUpdate, admin=Depends(require_admin)):
    existing = await db.registrations.find_one({"registration_id": registration_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Registration not found")
    comp = await db.competitions.find_one({"competition_id": existing["competition_id"]}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.registrations.update_one({"registration_id": registration_id}, {"$set": patch})
    fresh = await db.registrations.find_one({"registration_id": registration_id}, {"_id": 0})
    return fresh

@api_router.delete("/admin/registrations/{registration_id}")
async def admin_delete_registration(registration_id: str, admin=Depends(require_admin)):
    existing = await db.registrations.find_one({"registration_id": registration_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Registration not found")
    comp = await db.competitions.find_one({"competition_id": existing["competition_id"]}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    await db.registrations.delete_one({"registration_id": registration_id})
    return {"ok": True}

@api_router.get("/admin/users")
async def admin_list_users(admin=Depends(require_admin)):
    q = tenant_scope(admin)
    users = await db.users.find(q, {"_id": 0, "avatar": 0}).sort("created_at", -1).to_list(2000)
    for u in users:
        u["registrations_count"] = await db.registrations.count_documents({"user_id": u["user_id"]})
    return users

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: UserAdminUpdate, admin=Depends(require_admin)):
    existing = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "User not found")
    _admin_owns_or_raise(admin, existing, "usuário")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.users.update_one({"user_id": user_id}, {"$set": patch})
    fresh = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return fresh

@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["user_id"]:
        raise HTTPException(400, "Você não pode excluir a si mesmo")
    existing = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "User not found")
    _admin_owns_or_raise(admin, existing, "usuário")
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.registrations.delete_many({"user_id": user_id})
    return {"ok": True}

@api_router.post("/admin/refund/{session_id}")
async def admin_refund(session_id: str, admin=Depends(require_admin)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transação não encontrada")
    _admin_owns_or_raise(admin, tx, "transação")
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

    # Enforce tenant athletes plan limit
    tenant_id = comp.get("tenant_id")
    if tenant_id:
        tenant = await _get_tenant(tenant_id)
        plan = (tenant or {}).get("plan", "starter")
        athletes_limit = PLAN_LIMITS.get(plan, {}).get("athletes", 200)
        current_athletes = await db.registrations.count_documents({"tenant_id": tenant_id})
        if current_athletes >= athletes_limit:
            raise HTTPException(402, f"Este clube atingiu o limite de {athletes_limit} inscrições do plano.")

    fee = float(comp.get("fee", 0.0))
    is_free = fee <= 0

    reg_id = f"reg_{uuid.uuid4().hex[:10]}"
    check_in_code = f"chk_{uuid.uuid4().hex[:16]}"
    reg = {
        "registration_id": reg_id,
        "competition_id": body.competition_id,
        "tenant_id": tenant_id,
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
                "tenant_id": tenant_id,
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

    # Subscription events (SaaS billing)
    if t in ("customer.subscription.created", "customer.subscription.updated"):
        tenant_id = (obj.get("metadata") or {}).get("tenant_id")
        if not tenant_id:
            # try customer metadata
            try:
                cust = stripe.Customer.retrieve(obj["customer"])
                tenant_id = (cust.metadata or {}).get("tenant_id")
            except Exception:
                pass
        if tenant_id:
            status_map = {"trialing":"trialing","active":"active","past_due":"past_due",
                          "canceled":"canceled","incomplete":"past_due","incomplete_expired":"canceled",
                          "unpaid":"past_due", "paused":"past_due"}
            new_status = status_map.get(obj.get("status"), "inactive")
            update = {
                "subscription_status": new_status,
                "stripe_subscription_id": obj["id"],
                "cancel_at_period_end": obj.get("cancel_at_period_end", False),
            }
            cpe = obj.get("current_period_end")
            if cpe:
                update["current_period_end"] = datetime.fromtimestamp(cpe, tz=timezone.utc).isoformat()
            lk = (obj.get("metadata") or {}).get("lookup_key")
            if lk:
                update["plan_lookup_key"] = lk
            await db.tenants.update_one({"tenant_id": tenant_id}, {"$set": update})
        return {"status": "ok"}
    if t == "customer.subscription.deleted":
        tenant_id = (obj.get("metadata") or {}).get("tenant_id")
        if tenant_id:
            await db.tenants.update_one({"tenant_id": tenant_id},
                {"$set": {"subscription_status": "canceled",
                          "cancel_at_period_end": False}})
        return {"status": "ok"}
    if t == "invoice.payment_failed":
        try:
            sub_id = obj.get("subscription")
            if sub_id:
                sub = stripe.Subscription.retrieve(sub_id)
                tenant_id = (sub.metadata or {}).get("tenant_id")
                if tenant_id:
                    await db.tenants.update_one({"tenant_id": tenant_id},
                        {"$set": {"subscription_status": "past_due"}})
        except Exception as e:
            logger.error(f"invoice.payment_failed: {e}")
        return {"status": "ok"}

    # One-time tournament fee events (kept from prior implementation)
    if t == "checkout.session.completed":
        purpose = (obj.get("metadata") or {}).get("purpose")
        if purpose == "saas_subscription":
            return {"status": "ok"}
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
    _admin_owns_or_raise(admin, comp, "torneio")
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
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
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

# ---------------- Rotating Doubles (formato "Rei da Praia") ----------------
# Individual signup, doubles pairs randomly drawn every round, individual scoring.
# Group phase: 4 players/group × 3 rounds (all pairings). Top-2 individual per group
# advance to knockout, where pairs are re-drawn each round.
GROUP_COMBOS_OF_4 = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]

async def _rotating_leaderboard_data(competition_id: str) -> list:
    matches = await db.matches.find({"competition_id": competition_id}, {"_id": 0}).to_list(2000)
    teams = await db.teams.find({"competition_id": competition_id}, {"_id": 0}).to_list(2000)
    regs = await db.registrations.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)
    reg_by_id = {r["registration_id"]: r for r in regs}
    team_by_id = {t["team_id"]: t for t in teams}
    scores = {}  # reg_id -> {name, points, wins, matches}
    for m in matches:
        for side, key_id in (("A", "team_a_id"), ("B", "team_b_id")):
            team = team_by_id.get(m.get(key_id))
            if not team:
                continue
            src_regs = team.get("source_registration_ids", []) or []
            names = team.get("players", []) or []
            score = m.get(f"score_{side.lower()}", 0) or 0
            for reg_id, name in zip(src_regs, names):
                s = scores.setdefault(reg_id, {"name": name, "points": 0, "wins": 0, "matches": 0})
                s["points"] += score
                s["matches"] += 1
                if m.get("winner") == side:
                    s["wins"] += 1
    board = []
    for k, v in scores.items():
        r = reg_by_id.get(k) or {}
        board.append({
            "registration_id": k, **v,
            "retired": bool(r.get("retired")),
            "retired_reason": r.get("retired_reason"),
            "retired_by_partner": bool(r.get("retired_by_partner")),
        })
    board.sort(key=lambda x: (x["retired"], -x["points"], -x["wins"], x["name"]))
    return board

def _make_team(competition_id: str, tenant_id: str, players: list) -> dict:
    return {
        "team_id": f"team_{uuid.uuid4().hex[:10]}",
        "competition_id": competition_id,
        "tenant_id": tenant_id,
        "name": " & ".join(p["user_name"] for p in players),
        "players": [p["user_name"] for p in players],
        "source_registration_ids": [p["registration_id"] for p in players],
    }

@api_router.post("/competitions/{competition_id}/rotating/draw-groups")
async def rotating_draw_groups(competition_id: str, admin=Depends(require_admin)):
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    if comp.get("type_format") != "duplas_rotativas":
        raise HTTPException(400, "Este torneio não é do formato duplas rotativas")

    regs = await db.registrations.find(
        {"competition_id": competition_id, "payment_status": {"$in": ["paid", "free"]}},
        {"_id": 0}
    ).to_list(500)
    n = len(regs)
    if n < 4 or n % 4 != 0:
        raise HTTPException(400, f"Precisa múltiplos de 4 jogadores confirmados (temos {n}, mínimo 4)")

    await db.matches.delete_many({"competition_id": competition_id})
    await db.teams.delete_many({"competition_id": competition_id})
    await db.groups.delete_many({"competition_id": competition_id})

    random.shuffle(regs)
    groups_docs, teams_docs, matches_docs = [], [], []
    tenant_id = comp.get("tenant_id")
    for gi in range(0, n, 4):
        g_players = regs[gi:gi + 4]
        group_id = f"grp_{uuid.uuid4().hex[:10]}"
        group_letter = chr(65 + gi // 4)
        groups_docs.append({
            "group_id": group_id,
            "competition_id": competition_id,
            "tenant_id": tenant_id,
            "name": f"Grupo {group_letter}",
            "player_reg_ids": [p["registration_id"] for p in g_players],
            "player_names": [p["user_name"] for p in g_players],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        for ri, ((a1, a2), (b1, b2)) in enumerate(GROUP_COMBOS_OF_4, start=1):
            ta = _make_team(competition_id, tenant_id, [g_players[a1], g_players[a2]])
            tb = _make_team(competition_id, tenant_id, [g_players[b1], g_players[b2]])
            teams_docs.extend([ta, tb])
            matches_docs.append({
                "match_id": f"m_{uuid.uuid4().hex[:10]}",
                "competition_id": competition_id,
                "tenant_id": tenant_id,
                "phase": "group",
                "group_id": group_id,
                "group_name": f"Grupo {group_letter}",
                "round": ri,
                "position": gi // 4,
                "team_a_id": ta["team_id"], "team_a_name": ta["name"],
                "team_b_id": tb["team_id"], "team_b_name": tb["name"],
                "score_a": 0, "score_b": 0, "winner": None, "next_match_id": None,
            })

    if groups_docs: await db.groups.insert_many([{**g} for g in groups_docs])
    if teams_docs: await db.teams.insert_many([{**t} for t in teams_docs])
    if matches_docs: await db.matches.insert_many([{**m} for m in matches_docs])
    return {"groups": len(groups_docs), "matches": len(matches_docs)}

@api_router.get("/competitions/{competition_id}/rotating/leaderboard")
async def rotating_leaderboard(competition_id: str):
    return await _rotating_leaderboard_data(competition_id)

@api_router.get("/competitions/{competition_id}/rotating/groups")
async def rotating_groups(competition_id: str):
    return await db.groups.find({"competition_id": competition_id}, {"_id": 0}).to_list(100)

@api_router.post("/competitions/{competition_id}/rotating/next-knockout-round")
async def rotating_next_round(competition_id: str, admin=Depends(require_admin)):
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    if comp.get("type_format") != "duplas_rotativas":
        raise HTTPException(400, "Este torneio não é do formato duplas rotativas")

    tenant_id = comp.get("tenant_id")
    # Verify group phase complete
    group_matches = await db.matches.find(
        {"competition_id": competition_id, "phase": "group"}, {"_id": 0}
    ).to_list(500)
    if not group_matches:
        raise HTTPException(400, "Sorteie os grupos antes de iniciar a eliminatória")
    if any(m.get("winner") not in ("A", "B") for m in group_matches):
        raise HTTPException(400, "Todos os placares da fase de grupos precisam estar lançados")

    knockout_matches = await db.matches.find(
        {"competition_id": competition_id, "phase": "knockout"}, {"_id": 0}
    ).sort([("round", -1), ("position", 1)]).to_list(500)

    regs_by_id = {r["registration_id"]: r for r in
                  await db.registrations.find({"competition_id": competition_id}, {"_id": 0}).to_list(500)}

    if not knockout_matches:
        # First knockout round: top-2 per group by individual leaderboard, skipping retired players
        board = await _rotating_leaderboard_data(competition_id)
        board_by_reg = {p["registration_id"]: p for p in board}
        groups = await db.groups.find({"competition_id": competition_id}, {"_id": 0}).sort("name", 1).to_list(100)
        qualifiers = []
        for g in groups:
            active = [rid for rid in g.get("player_reg_ids", [])
                      if not board_by_reg.get(rid, {}).get("retired")]
            ranked = sorted(
                active,
                key=lambda rid: (-board_by_reg.get(rid, {}).get("points", 0),
                                 -board_by_reg.get(rid, {}).get("wins", 0)),
            )
            qualifiers.extend(ranked[:2])
        round_num = 1
    else:
        current_round = knockout_matches[0]["round"]
        current_round_matches = [m for m in knockout_matches if m["round"] == current_round]
        if any(m.get("winner") not in ("A", "B") for m in current_round_matches):
            raise HTTPException(400, "Lance todos os placares da rodada atual antes de sortear a próxima")
        winners_teams = await db.teams.find(
            {"team_id": {"$in": [(m["team_a_id"] if m["winner"] == "A" else m["team_b_id"]) for m in current_round_matches]}},
            {"_id": 0}
        ).to_list(500)
        qualifiers = []
        for t in winners_teams:
            qualifiers.extend(t.get("source_registration_ids", []) or [])
        # Filter out retired players (may have retired during the KO round)
        retired_map = await db.registrations.find(
            {"registration_id": {"$in": qualifiers}, "retired": True}, {"_id": 0, "registration_id": 1}
        ).to_list(500)
        retired_ids = {r["registration_id"] for r in retired_map}
        qualifiers = [q for q in qualifiers if q not in retired_ids]
        round_num = current_round + 1

    if len(qualifiers) < 4:
        return {"finished": True, "champions_registration_ids": qualifiers}
    if len(qualifiers) % 4 != 0:
        raise HTTPException(400, f"Total de classificados precisa ser múltiplo de 4 (temos {len(qualifiers)})")

    random.shuffle(qualifiers)
    teams_docs, matches_docs = [], []
    for i in range(0, len(qualifiers), 4):
        quartet = [regs_by_id[qualifiers[i + k]] for k in range(4)]
        # Random pairing within the quartet
        random.shuffle(quartet)
        ta = _make_team(competition_id, tenant_id, [quartet[0], quartet[1]])
        tb = _make_team(competition_id, tenant_id, [quartet[2], quartet[3]])
        teams_docs.extend([ta, tb])
        matches_docs.append({
            "match_id": f"m_{uuid.uuid4().hex[:10]}",
            "competition_id": competition_id,
            "tenant_id": tenant_id,
            "phase": "knockout",
            "group_id": None,
            "group_name": None,
            "round": round_num,
            "position": i // 4,
            "team_a_id": ta["team_id"], "team_a_name": ta["name"],
            "team_b_id": tb["team_id"], "team_b_name": tb["name"],
            "score_a": 0, "score_b": 0, "winner": None, "next_match_id": None,
        })

    await db.teams.insert_many([{**t} for t in teams_docs])
    await db.matches.insert_many([{**m} for m in matches_docs])
    return {"round": round_num, "matches": len(matches_docs), "phase": "knockout"}

@api_router.post("/competitions/{competition_id}/matches/{match_id}/retire-player")
async def retire_player(competition_id: str, match_id: str, body: RetirePlayerRequest,
                        admin=Depends(require_admin)):
    """Mark a player as retired (contusão/estafe/outro) — the partner in this match
    is also disqualified. Retired regs are excluded from future knockout rounds."""
    comp = await db.competitions.find_one({"competition_id": competition_id}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
    m = await db.matches.find_one({"match_id": match_id, "competition_id": competition_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Partida não encontrada")

    # Find the team the player belongs to in this match
    teams = await db.teams.find(
        {"team_id": {"$in": [m.get("team_a_id"), m.get("team_b_id")]}}, {"_id": 0}
    ).to_list(4)
    partner_reg_id = None
    for t in teams:
        regs = t.get("source_registration_ids") or []
        if body.registration_id in regs:
            for r in regs:
                if r != body.registration_id:
                    partner_reg_id = r
                    break
            break
    if partner_reg_id is None and not any(body.registration_id in (t.get("source_registration_ids") or []) for t in teams):
        raise HTTPException(400, "Jogador não faz parte desta partida")

    now_iso = datetime.now(timezone.utc).isoformat()
    reg_ids = [body.registration_id] + ([partner_reg_id] if partner_reg_id else [])
    await db.registrations.update_many(
        {"registration_id": {"$in": reg_ids}},
        {"$set": {
            "retired": True,
            "retired_at": now_iso,
            "retired_reason": body.reason,
            "retired_notes": body.notes or "",
            "retired_via_match_id": match_id,
        }},
    )
    # Also flag which one was the partner "levado junto"
    if partner_reg_id:
        await db.registrations.update_one(
            {"registration_id": partner_reg_id},
            {"$set": {"retired_by_partner": True, "retired_partner_reg_id": body.registration_id}},
        )
    return {"ok": True, "retired": reg_ids}

@api_router.get("/competitions/{competition_id}/matches")
async def list_matches(competition_id: str):
    return await db.matches.find({"competition_id": competition_id}, {"_id": 0}).sort([("round", 1), ("position", 1)]).to_list(500)

@api_router.put("/matches/{match_id}")
async def update_match(match_id: str, body: MatchScoreUpdate, admin=Depends(require_admin)):
    m = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Match not found")
    comp = await db.competitions.find_one({"competition_id": m["competition_id"]}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
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
    _admin_owns_or_raise(admin, comp, "torneio")
    return {"registration": reg, "competition": comp}

@api_router.post("/checkin/{code}")
async def do_checkin(code: str, admin=Depends(require_admin)):
    reg = await db.registrations.find_one({"check_in_code": code}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Código inválido")
    comp = await db.competitions.find_one({"competition_id": reg["competition_id"]}, {"_id": 0})
    _admin_owns_or_raise(admin, comp, "torneio")
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
    q = tenant_scope(admin)
    if competition_id:
        # Filter payment_transactions by registration_id belonging to this competition
        reg_q = {"competition_id": competition_id}
        if admin.get("platform_role") != "super_admin":
            reg_q["tenant_id"] = admin.get("tenant_id")
        regs = await db.registrations.find(
            reg_q, {"_id": 0, "registration_id": 1}
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
@api_router.post("/platform/migrate")
async def migrate_legacy(super_admin=Depends(require_super_admin)):
    """Backfill tenant_id on all legacy documents. Assigns owner's tenant."""
    owner = await db.users.find_one({"email": OWNER_EMAIL}, {"_id": 0})
    if not owner:
        raise HTTPException(400, "Owner user not found")
    tenant_id = owner.get("tenant_id")
    if not tenant_id:
        tenant = await _create_tenant(owner["user_id"], "ArenaHub Legacy")
        tenant_id = tenant["tenant_id"]
        await db.users.update_one({"user_id": owner["user_id"]},
                                  {"$set": {"tenant_id": tenant_id, "platform_role": "super_admin"}})
    collections = ["competition_types", "competitions", "registrations", "teams", "matches", "payment_transactions"]
    counts = {}
    for col in collections:
        res = await db[col].update_many(
            {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]},
            {"$set": {"tenant_id": tenant_id}},
        )
        counts[col] = res.modified_count
    # Also make sure all users have a tenant
    orphan_users = await db.users.find(
        {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]}, {"_id": 0}
    ).to_list(2000)
    for u in orphan_users:
        t = await _create_tenant(u["user_id"], u.get("name") or u.get("email") or "Meu clube")
        await db.users.update_one({"user_id": u["user_id"]},
                                  {"$set": {"tenant_id": t["tenant_id"], "tenant_role": "admin"}})
    counts["users_backfilled"] = len(orphan_users)
    return {"ok": True, "counts": counts, "legacy_tenant_id": tenant_id}

# ---------------- Super admin (platform) ----------------
@api_router.get("/platform/stats")
async def platform_stats(admin=Depends(require_super_admin)):
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(5000)
    active = [t for t in tenants if t.get("subscription_status") in ("active", "trialing")]
    past_due = [t for t in tenants if t.get("subscription_status") == "past_due"]
    canceled = [t for t in tenants if t.get("subscription_status") == "canceled"]

    # MRR: sum of prices per active subscription (best effort)
    mrr = 0.0
    for t in active:
        lk = t.get("plan_lookup_key")
        if lk == "starter_monthly":
            mrr += 49.0
        elif lk == "starter_yearly":
            mrr += 490.0 / 12.0

    txs = await db.payment_transactions.find(
        {"payment_status": "paid"}, {"_id": 0}
    ).to_list(10000)
    total_paid = sum(float(t.get("amount") or 0) for t in txs)

    return {
        "totals": {
            "tenants": len(tenants),
            "active": len(active),
            "past_due": len(past_due),
            "canceled": len(canceled),
        },
        "mrr": round(mrr, 2),
        "total_tournament_revenue": round(total_paid, 2),
    }

@api_router.get("/platform/tenants")
async def platform_tenants(admin=Depends(require_super_admin)):
    tenants = await db.tenants.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    for t in tenants:
        owner = await db.users.find_one({"user_id": t.get("owner_user_id")},
                                        {"_id": 0, "name": 1, "email": 1})
        t["owner"] = owner
        t["competitions_count"] = await db.competitions.count_documents({"tenant_id": t["tenant_id"]})
        t["users_count"] = await db.users.count_documents({"tenant_id": t["tenant_id"]})
    return tenants

# ---------------- Seed default data (per tenant) ----------------
@api_router.post("/seed-defaults")
async def seed_defaults(request: Request):
    """Seed a few competition types for the current authenticated tenant (or public global if none)."""
    # Determine tenant to seed
    tenant_id = None
    token = request.cookies.get("session_token") or (request.headers.get("Authorization","").replace("Bearer ","") or None)
    if token:
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            u = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
            if u:
                tenant_id = u.get("tenant_id")
    filter_ = {"tenant_id": tenant_id} if tenant_id else {}
    existing = await db.competition_types.count_documents(filter_)
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
        doc = {"type_id": f"ct_{uuid.uuid4().hex[:10]}", **d,
               "created_at": datetime.now(timezone.utc).isoformat()}
        if tenant_id:
            doc["tenant_id"] = tenant_id
        await db.competition_types.insert_one(doc)
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

@app.on_event("startup")
async def startup_migrations():
    """Ensure OWNER_EMAIL user is super_admin with a legacy tenant, and backfill tenant_id.
    Also (re)sets password_hash from ADMIN_PASSWORD env so the owner can log in via email/password
    (in addition to Google OAuth)."""
    try:
        owner = await db.users.find_one({"email": OWNER_EMAIL}, {"_id": 0})
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if not owner:
            # Seed the owner account so email/password login works out of the box
            if admin_password:
                user_id = f"user_{uuid.uuid4().hex[:12]}"
                await db.users.insert_one({
                    "user_id": user_id, "email": OWNER_EMAIL, "name": "Daniel Oliveira",
                    "phone": "", "password_hash": hash_password(admin_password),
                    "is_admin": True, "tenant_role": "admin",
                    "platform_role": "super_admin", "picture": "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                t = await _create_tenant(user_id, "ArenaHub HQ")
                await db.users.update_one({"user_id": user_id},
                                          {"$set": {"tenant_id": t["tenant_id"]}})
                logger.info(f"[startup] Seeded owner account {OWNER_EMAIL} as super_admin")
                owner = await db.users.find_one({"email": OWNER_EMAIL}, {"_id": 0})
            else:
                logger.info(f"[startup] Owner user {OWNER_EMAIL} not found — skipping legacy migration")
                return
        # Promote to super_admin if not already
        if owner.get("platform_role") != "super_admin":
            await db.users.update_one({"user_id": owner["user_id"]},
                                      {"$set": {"platform_role": "super_admin"}})
        # Sync owner password from ADMIN_PASSWORD if provided
        if admin_password:
            if not owner.get("password_hash") or not verify_password(admin_password, owner["password_hash"]):
                await db.users.update_one({"user_id": owner["user_id"]},
                                          {"$set": {"password_hash": hash_password(admin_password)}})
                logger.info(f"[startup] Synced password for owner {OWNER_EMAIL}")
        tenant_id = owner.get("tenant_id")
        if not tenant_id:
            t = await _create_tenant(owner["user_id"], owner.get("name") or "ArenaHub HQ")
            tenant_id = t["tenant_id"]
            await db.users.update_one({"user_id": owner["user_id"]},
                                      {"$set": {"tenant_id": tenant_id, "tenant_role": "admin"}})
        # Backfill tenant_id on legacy collections (only untagged docs)
        collections = ["competition_types", "competitions", "registrations", "teams",
                       "matches", "payment_transactions"]
        for col in collections:
            res = await db[col].update_many(
                {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]},
                {"$set": {"tenant_id": tenant_id}},
            )
            if res.modified_count:
                logger.info(f"[startup] Backfilled {res.modified_count} docs in '{col}' -> tenant {tenant_id}")
        # Ensure every non-owner user has a tenant
        orphan_users = await db.users.find(
            {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]}, {"_id": 0}
        ).to_list(2000)
        for u in orphan_users:
            t = await _create_tenant(u["user_id"], u.get("name") or u.get("email") or "Meu clube")
            await db.users.update_one({"user_id": u["user_id"]},
                                      {"$set": {"tenant_id": t["tenant_id"], "tenant_role": "admin"}})
        if orphan_users:
            logger.info(f"[startup] Provisioned tenants for {len(orphan_users)} legacy user(s)")
    except Exception as e:
        logger.error(f"[startup] migration error: {e}")
