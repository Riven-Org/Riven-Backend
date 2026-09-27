"""Service accounts and API keys (S03.4.1).

A key looks like `rvn_<prefix>_<secret>`. The prefix is stored in clear for lookup; the secret
only as an Argon2 hash, so it is shown exactly once, at creation. Revocation, expiry and
disabled accounts are checked against the database on every request (a revoked key is
rejected on its next use). Successful Argon2 verifications are cached briefly in memory
because hashing on every request would dominate latency; the cache never skips those checks.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from riven_db.models import ApiKey, ServiceAccount

KEY_PREFIX = "rvn_"
TOUCH_EVERY = timedelta(minutes=1)
VERIFIED_TTL_SECONDS = 60.0

_hasher = PasswordHasher()
_verified: dict[tuple[str, str], float] = {}


class InvalidKey(Exception):
    pass


@dataclass(frozen=True)
class IssuedKey:
    key: ApiKey
    secret: str  # the full `rvn_...` value; return it once and never store it


@dataclass(frozen=True)
class AuthenticatedKey:
    key: ApiKey
    account: ServiceAccount


def looks_like_api_key(token: str) -> bool:
    return token.startswith(KEY_PREFIX)


def _split(token: str) -> tuple[str, str]:
    try:
        _, prefix, secret = token.split("_", 2)
    except ValueError as exc:
        raise InvalidKey("malformed key") from exc
    if not prefix or not secret:
        raise InvalidKey("malformed key")
    return prefix, secret


async def issue(
    session: AsyncSession,
    account: ServiceAccount,
    *,
    scopes: list[str],
    expires_at: datetime | None,
    created_by: UUID,
) -> IssuedKey:
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    key = ApiKey(
        org_id=account.org_id,
        service_account_id=account.id,
        prefix=prefix,
        secret_hash=_hasher.hash(secret),
        scopes=sorted(set(scopes)),
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(key)
    await session.flush()
    return IssuedKey(key=key, secret=f"{KEY_PREFIX}{prefix}_{secret}")


def _verify(key: ApiKey, secret: str) -> bool:
    fingerprint = (key.prefix, hashlib.sha256(secret.encode()).hexdigest())
    if _verified.get(fingerprint, 0.0) > time.monotonic():
        return True
    try:
        _hasher.verify(key.secret_hash, secret)
    except (VerificationError, InvalidHashError):
        return False
    _verified[fingerprint] = time.monotonic() + VERIFIED_TTL_SECONDS
    return True


async def authenticate(session: AsyncSession, token: str) -> AuthenticatedKey:
    prefix, secret = _split(token)
    row = (
        await session.execute(
            select(ApiKey, ServiceAccount)
            .join(ServiceAccount, ServiceAccount.id == ApiKey.service_account_id)
            .where(ApiKey.prefix == prefix)
        )
    ).first()
    if row is None:
        raise InvalidKey("unknown key")
    key, account = row
    now = datetime.now(UTC)
    if not _verify(key, secret):
        raise InvalidKey("unknown key")
    if key.revoked_at is not None:
        raise InvalidKey("key revoked")
    if key.expires_at is not None and key.expires_at <= now:
        raise InvalidKey("key expired")
    if account.disabled_at is not None:
        raise InvalidKey("service account disabled")
    if key.last_used_at is None or now - key.last_used_at > TOUCH_EVERY:
        await session.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=now))
        await session.commit()
    return AuthenticatedKey(key=key, account=account)


async def accounts_with_keys(
    session: AsyncSession, org_id: str
) -> list[tuple[ServiceAccount, list[ApiKey]]]:
    accounts = list(
        await session.scalars(
            select(ServiceAccount)
            .where(ServiceAccount.org_id == org_id, ServiceAccount.disabled_at.is_(None))
            .order_by(ServiceAccount.name)
        )
    )
    keys = list(
        await session.scalars(
            select(ApiKey)
            .where(ApiKey.org_id == org_id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at)
        )
    )
    return [(a, [k for k in keys if k.service_account_id == a.id]) for a in accounts]


async def get_account(session: AsyncSession, org_id: str, account_id: UUID) -> ServiceAccount:
    account = await session.scalar(
        select(ServiceAccount).where(
            ServiceAccount.org_id == org_id,
            ServiceAccount.id == account_id,
            ServiceAccount.disabled_at.is_(None),
        )
    )
    if account is None:
        raise LookupError("service_account_not_found")
    return account


async def get_key(session: AsyncSession, org_id: str, key_id: UUID) -> ApiKey:
    key = await session.scalar(
        select(ApiKey).where(
            ApiKey.org_id == org_id, ApiKey.id == key_id, ApiKey.revoked_at.is_(None)
        )
    )
    if key is None:
        raise LookupError("api_key_not_found")
    return key


async def revoke(session: AsyncSession, key: ApiKey) -> None:
    key.revoked_at = datetime.now(UTC)
    await session.flush()


async def disable_account(session: AsyncSession, account: ServiceAccount) -> None:
    now = datetime.now(UTC)
    account.disabled_at = now
    await session.execute(
        update(ApiKey)
        .where(ApiKey.service_account_id == account.id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.flush()
