"""Async SQLite persistence layer for monetization features."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite


logger = logging.getLogger(__name__)

UTC = timezone.utc


def utcnow() -> datetime:
    """Return aware UTC timestamp."""

    return datetime.now(tz=UTC)


def _serialize_dt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError:
        return None


@dataclass
class User:
    id: str
    email: str
    created_at: datetime
    last_login: Optional[datetime]


@dataclass
class Credit:
    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    reserved_at: Optional[datetime]
    redeemed_at: Optional[datetime]


@dataclass
class UserCreditSummary:
    available: int
    next_expiration: Optional[datetime]


@dataclass
class ReportRecord:
    id: str
    user_id: Optional[str]
    listing_url: str
    type: str
    credit_id: Optional[str]
    created_at: datetime


class Database:
    """Lightweight async wrapper around SQLite for user and credit state."""

    def __init__(self, path: str, *, reservation_ttl_minutes: int = 10) -> None:
        self._path = Path(path)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    async def connect(self) -> None:
        if self._conn is not None:
            return

        if self._path.parent and not self._path.parent.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.commit()
        await self._migrate()
        logger.info("SQLite database ready at %s", self._path)

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def _migrate(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS credits (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                reserved_at TEXT,
                redeemed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS credits_available_idx
                ON credits(user_id, expires_at)
                WHERE redeemed_at IS NULL;

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                listing_url TEXT NOT NULL,
                type TEXT NOT NULL,
                credit_id TEXT REFERENCES credits(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                payload_hash TEXT,
                payload TEXT
            );

            CREATE INDEX IF NOT EXISTS reports_user_idx ON reports(user_id);

            CREATE TABLE IF NOT EXISTS login_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT
            );

            DROP TABLE IF EXISTS transactions;

            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                external_id TEXT UNIQUE NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await self._conn.commit()

    def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected.")
        return self._conn

    async def get_user_by_email(self, email: str) -> Optional[User]:
        conn = self._ensure_conn()
        normalized = email.strip().lower()
        async with conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (normalized,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            email=row["email"],
            created_at=_parse_dt(row["created_at"]) or utcnow(),
            last_login=_parse_dt(row["last_login"]),
        )

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        conn = self._ensure_conn()
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            email=row["email"],
            created_at=_parse_dt(row["created_at"]) or utcnow(),
            last_login=_parse_dt(row["last_login"]),
        )

    async def upsert_user(self, email: str) -> User:
        conn = self._ensure_conn()
        normalized = email.strip().lower()
        async with self._lock:
            async with conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalized,),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                return User(
                    id=row["id"],
                    email=row["email"],
                    created_at=_parse_dt(row["created_at"]) or utcnow(),
                    last_login=_parse_dt(row["last_login"]),
                )

            user_id = uuid.uuid4().hex
            created = _serialize_dt(utcnow())
            await conn.execute(
                "INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)",
                (user_id, normalized, created),
            )
            await conn.commit()
            return User(
                id=user_id,
                email=normalized,
                created_at=_parse_dt(created) or utcnow(),
                last_login=None,
            )

    async def touch_last_login(self, user_id: str) -> None:
        conn = self._ensure_conn()
        await conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (_serialize_dt(utcnow()), user_id),
        )
        await conn.commit()

    async def create_login_token(self, user_id: str, token_hash: str, expires_at: datetime) -> str:
        conn = self._ensure_conn()
        token_id = uuid.uuid4().hex
        now_iso = _serialize_dt(utcnow())
        async with self._lock:
            await conn.execute(
                """
                INSERT INTO login_tokens (id, user_id, token_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_id, user_id, token_hash, now_iso, _serialize_dt(expires_at)),
            )
            await conn.commit()
        return token_id

    async def consume_login_token(self, token_hash: str) -> Optional[User]:
        conn = self._ensure_conn()
        async with self._lock:
            async with conn.execute(
                "SELECT * FROM login_tokens WHERE token_hash = ?",
                (token_hash,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None

            expires_at = _parse_dt(row["expires_at"])
            if not expires_at or expires_at < utcnow():
                return None

            if row["consumed_at"]:
                return None

            await conn.execute(
                "UPDATE login_tokens SET consumed_at = ? WHERE id = ?",
                (_serialize_dt(utcnow()), row["id"]),
            )
            await conn.commit()

        return await self.get_user_by_id(row["user_id"])

    async def create_credit(self, user_id: str, expires_at: datetime) -> Credit:
        conn = self._ensure_conn()
        credit_id = uuid.uuid4().hex
        created = utcnow()
        await conn.execute(
            """
            INSERT INTO credits (id, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (credit_id, user_id, _serialize_dt(created), _serialize_dt(expires_at)),
        )
        await conn.commit()
        return Credit(
            id=credit_id,
            user_id=user_id,
            created_at=created,
            expires_at=expires_at,
            reserved_at=None,
            redeemed_at=None,
        )

    async def reserve_credit(self, user_id: str) -> Optional[Credit]:
        conn = self._ensure_conn()
        now = utcnow()
        stale_cutoff = now - self._reservation_ttl
        async with self._lock:
            async with conn.execute(
                """
                SELECT * FROM credits
                WHERE user_id = ?
                  AND redeemed_at IS NULL
                  AND expires_at > ?
                  AND (reserved_at IS NULL OR reserved_at < ?)
                ORDER BY expires_at ASC
                LIMIT 1
                """,
                (user_id, _serialize_dt(now), _serialize_dt(stale_cutoff)),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            await conn.execute(
                "UPDATE credits SET reserved_at = ? WHERE id = ?",
                (_serialize_dt(now), row["id"]),
            )
            await conn.commit()

        return Credit(
            id=row["id"],
            user_id=row["user_id"],
            created_at=_parse_dt(row["created_at"]) or now,
            expires_at=_parse_dt(row["expires_at"]) or now,
            reserved_at=now,
            redeemed_at=_parse_dt(row["redeemed_at"]),
        )

    async def release_credit(self, credit_id: str) -> None:
        conn = self._ensure_conn()
        await conn.execute(
            "UPDATE credits SET reserved_at = NULL WHERE id = ?",
            (credit_id,),
        )
        await conn.commit()

    async def redeem_credit(self, credit_id: str) -> None:
        conn = self._ensure_conn()
        now_iso = _serialize_dt(utcnow())
        await conn.execute(
            "UPDATE credits SET redeemed_at = ?, reserved_at = ? WHERE id = ?",
            (now_iso, now_iso, credit_id),
        )
        await conn.commit()

    async def get_credit_summary(self, user_id: str) -> UserCreditSummary:
        conn = self._ensure_conn()
        async with conn.execute(
            """
            SELECT COUNT(*) as available,
                   MIN(expires_at) as next_expiration
            FROM credits
            WHERE user_id = ?
              AND redeemed_at IS NULL
              AND expires_at > ?
            """,
            (user_id, _serialize_dt(utcnow())),
        ) as cursor:
            row = await cursor.fetchone()

        available = int(row["available"] if row and row["available"] is not None else 0)
        next_expiration = _parse_dt(row["next_expiration"]) if row else None
        return UserCreditSummary(available=available, next_expiration=next_expiration)

    async def log_report(
        self,
        *,
        user_id: Optional[str],
        listing_url: str,
        report_type: str,
        credit_id: Optional[str],
        payload_hash: Optional[str],
        payload: str,
    ) -> ReportRecord:
        conn = self._ensure_conn()
        report_id = uuid.uuid4().hex
        created = utcnow()
        await conn.execute(
            """
            INSERT INTO reports (id, user_id, listing_url, type, credit_id, created_at, payload_hash, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                user_id,
                listing_url,
                report_type,
                credit_id,
                _serialize_dt(created),
                payload_hash,
                payload,
            ),
        )
        await conn.commit()
        return ReportRecord(
            id=report_id,
            user_id=user_id,
            listing_url=listing_url,
            type=report_type,
            credit_id=credit_id,
            created_at=created,
        )

    async def record_transaction(
        self,
        *,
        user_id: str,
        provider: str,
        external_id: str,
        amount_cents: int,
        currency: str,
    ) -> None:
        conn = self._ensure_conn()
        async with self._lock:
            await conn.execute(
                """
                INSERT OR IGNORE INTO payments
                    (id, user_id, provider, external_id, amount_cents, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hashlib.sha256(f"{provider}:{external_id}".encode()).hexdigest(),
                    user_id,
                    provider,
                    external_id,
                    amount_cents,
                    currency,
                    _serialize_dt(utcnow()),
                ),
            )
            await conn.commit()

    async def transaction_exists(self, external_id: str) -> bool:
        conn = self._ensure_conn()
        async with conn.execute(
            "SELECT 1 FROM payments WHERE external_id = ?",
            (external_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return bool(row)
