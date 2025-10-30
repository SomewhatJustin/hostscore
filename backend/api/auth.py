"""Authentication helpers: magic links and signed session cookies."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Protocol

import jwt
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer

from .database import Database, User, utcnow


logger = logging.getLogger(__name__)


class MagicLinkSender(Protocol):
    async def send_magic_link(self, *, email: str, link: str, expires_at: datetime) -> None:  # pragma: no cover - interface
        ...


@dataclass
class MagicLink:
    token: str
    user: User
    expires_at: datetime


class MagicLinkService:
    """Issue and consume JWT-backed magic links."""

    def __init__(
        self,
        *,
        db: Database,
        secret: str,
        ttl_seconds: int = 900,
        issuer: str = "hostscore",
    ) -> None:
        self._db = db
        self._secret = secret
        self._ttl = ttl_seconds
        self._issuer = issuer

    async def issue(self, email: str) -> MagicLink:
        """Create a single-use login token and persist its nonce."""

        if not email or "@" not in email:
            raise ValueError("A valid email address is required.")

        user = await self._db.upsert_user(email)
        expires_at = utcnow() + timedelta(seconds=self._ttl)
        nonce = uuid.uuid4().hex

        payload = {
            "sub": user.id,
            "email": user.email,
            "nonce": nonce,
            "iss": self._issuer,
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self._secret, algorithm="HS256")
        token_hash = hashlib.sha256(nonce.encode()).hexdigest()
        await self._db.create_login_token(user.id, token_hash, expires_at)

        return MagicLink(token=token, user=user, expires_at=expires_at)

    async def consume(self, token: str) -> User:
        """Validate a magic link token, enforcing single-use semantics."""

        if not token:
            raise ValueError("Missing token")

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                options={"require": ["sub", "nonce", "exp"]},
            )
        except jwt.ExpiredSignatureError as exc:  # pragma: no cover - library path
            raise ValueError("Magic link expired.") from exc
        except jwt.PyJWTError as exc:  # pragma: no cover - library path
            raise ValueError("Invalid magic link token.") from exc

        nonce = payload.get("nonce")
        if not isinstance(nonce, str):
            raise ValueError("Invalid nonce in token.")

        token_hash = hashlib.sha256(nonce.encode()).hexdigest()
        user = await self._db.consume_login_token(token_hash)
        if not user:
            raise ValueError("Magic link already used or expired.")

        return user


@dataclass
class SessionData:
    user_id: str
    email: str


class SessionManager:
    """Signed session cookies backed by ItsDangerous."""

    def __init__(
        self,
        *,
        secret: str,
        cookie_name: str = "hostscore_session",
        ttl_seconds: int = 30 * 24 * 3600,
        secure_cookie: bool = True,
        cookie_domain: Optional[str] = None,
        cookie_path: str = "/",
    ) -> None:
        self.cookie_name = cookie_name
        self.ttl_seconds = ttl_seconds
        self._secure_cookie = secure_cookie
        self._cookie_domain = cookie_domain
        self._cookie_path = cookie_path
        self._serializer = URLSafeTimedSerializer(secret_key=secret, salt="hostscore-session")

    def issue(self, user: User) -> tuple[str, datetime]:
        """Return cookie value and expiration timestamp."""

        payload = {"user_id": user.id, "email": user.email}
        token = self._serializer.dumps(payload)
        expires_at = utcnow() + timedelta(seconds=self.ttl_seconds)
        return token, expires_at

    def verify(self, token: str) -> Optional[SessionData]:
        if not token:
            return None
        try:
            payload = self._serializer.loads(token, max_age=self.ttl_seconds)
        except (BadSignature, BadTimeSignature):
            return None

        user_id = payload.get("user_id")
        email = payload.get("email")
        if not isinstance(user_id, str) or not isinstance(email, str):
            return None
        return SessionData(user_id=user_id, email=email)

    def cookie_args(self, value: str) -> dict[str, object]:
        """Return keyword arguments for FastAPI's set_cookie."""

        params: dict[str, object] = {
            "key": self.cookie_name,
            "value": value,
            "httponly": True,
            "secure": self._secure_cookie,
            "samesite": "lax",
            "max_age": self.ttl_seconds,
            "path": self._cookie_path,
        }
        if self._cookie_domain:
            params["domain"] = self._cookie_domain
        return params

    def clearing_args(self) -> dict[str, object]:
        """Arguments to clear the session cookie."""

        params = self.cookie_args("")
        params["value"] = ""
        params["max_age"] = 0
        params["expires"] = 0
        return params

