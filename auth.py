import datetime
import os
import uuid
import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from database import GuestSession, User, get_db

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "default_development_secret_key_change_in_production"
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))


# -----------------------------------------------------------------------------
# Password Utilities (Direct Bcrypt)
# -----------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    pwd_bytes = plain_password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


# -----------------------------------------------------------------------------
# JWT Token Generation & Verification
# -----------------------------------------------------------------------------
def create_jwt(user_id: str, role: str, name: str, email: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    expire = now + datetime.timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "role": role,
        "name": name,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Pydantic Schemas for Request / Response
# -----------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password at least 6 characters")
    name: str = Field(..., min_length=2, description="User full name")
    role: str = Field("user", description="Optional role: 'user' or 'admin'")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfileResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse


class IdentityContext(BaseModel):
    id: str
    role: str  # "admin" | "user" | "guest"
    is_authenticated: bool
    email: str | None = None
    name: str | None = None

    @property
    def is_guest(self) -> bool:
        return self.role == "guest"


# -----------------------------------------------------------------------------
# Security Context Dependency
# -----------------------------------------------------------------------------
def get_security_context(
    request: Request,
    db: Session = Depends(get_db),
) -> IdentityContext:
    """
    Extracts tenant identity seamlessly from either:
    1. Authenticated User: `Authorization: Bearer <JWT>`
    2. Ephemeral Guest: `X-Session-ID: gst_<uuid>`
    3. Auto-generated ephemeral guest if neither is provided.
    """
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_jwt(token)
        if payload and "sub" in payload:
            user = db.query(User).filter(User.id == payload["sub"]).first()
            if user:
                return IdentityContext(
                    id=user.id,
                    role=user.role,
                    is_authenticated=True,
                    email=user.email,
                    name=user.name,
                )

    # Fallback to Guest Session
    session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    if not session_id or not session_id.strip():
        session_id = f"gst_{uuid.uuid4().hex[:12]}"

    session_id = session_id.strip()

    # Track / touch guest session in DB
    try:
        guest = db.query(GuestSession).filter(GuestSession.session_id == session_id).first()
        now = datetime.datetime.now(datetime.timezone.utc)
        if not guest:
            guest = GuestSession(session_id=session_id, created_at=now, last_seen=now)
            db.add(guest)
            db.commit()
        else:
            guest.last_seen = now
            db.commit()
    except Exception:
        db.rollback()

    return IdentityContext(
        id=session_id,
        role="guest",
        is_authenticated=False,
        email=None,
        name="Guest",
    )


def require_admin(identity: IdentityContext = Depends(get_security_context)) -> IdentityContext:
    """Enforces strict role-based access control for administrative actions."""
    if identity.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges are required to access Inngest Observability and telemetry.",
        )
    return identity


def require_authenticated(identity: IdentityContext = Depends(get_security_context)) -> IdentityContext:
    """Enforces authenticated user status."""
    if not identity.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Please sign in or register to access this resource.",
        )
    return identity
