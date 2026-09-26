"""Password hashing and JWT helpers. No database access here."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

# Password hash format (self-describing, so the cost can be raised later without
# invalidating existing hashes):
#
#     scrypt$<N>$<r>$<p>$<salt hex>$<digest hex>
#
# Verification reads N/r/p and the digest length from the stored string; new
# hashes use the SCRYPT_* values below. Legacy hashes written before this format
# ("<salt hex>$<digest hex>", fixed N=2**14, r=8, p=1) still verify.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
_SCHEME = "scrypt"
_LEGACY_PARAMS = (2**14, 8, 1)
# Upper bounds on parameters read from a stored hash, to bound memory/CPU.
_MAX_N, _MAX_R, _MAX_P = 2**18, 32, 16

ACCESS_TOKEN = "access"
RESET_TOKEN = "reset"


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int = 32) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=256 * n * r
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"{_SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def _parse_hash(password_hash: str) -> tuple[int, int, int, bytes, bytes]:
    """Return (n, r, p, salt, digest); raise ValueError if malformed or out of bounds."""
    parts = password_hash.split("$")
    if len(parts) == 6 and parts[0] == _SCHEME:
        n, r, p = (int(x) for x in parts[1:4])
        salt_hex, digest_hex = parts[4], parts[5]
    elif len(parts) == 2:  # legacy format
        n, r, p = _LEGACY_PARAMS
        salt_hex, digest_hex = parts
    else:
        raise ValueError("unrecognized hash format")
    if not (1 < n <= _MAX_N and n & (n - 1) == 0 and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P):
        raise ValueError("scrypt parameters out of bounds")
    salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    if not salt or not digest:
        raise ValueError("empty salt or digest")
    return n, r, p, salt, digest


def verify_password(password: str, password_hash: str) -> bool:
    """True only for a matching password; any malformed hash returns False."""
    try:
        n, r, p, salt, expected = _parse_hash(password_hash)
        actual = _scrypt(password, salt, n, r, p, dklen=len(expected))
    except (ValueError, TypeError, OverflowError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def _encode(settings: Settings, claims: dict, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "type": token_type, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode(settings: Settings, token: str, token_type: str) -> dict | None:
    """Return the claims, or None if the token is invalid, expired or the wrong type."""
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError:
        return None
    return claims if claims.get("type") == token_type else None


def create_access_token(settings: Settings, user_id: int) -> str:
    return _encode(
        settings,
        {"sub": str(user_id)},
        ACCESS_TOKEN,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def decode_access_token(settings: Settings, token: str) -> int | None:
    claims = _decode(settings, token, ACCESS_TOKEN)
    if claims is None or not claims["sub"].isdigit():
        return None
    return int(claims["sub"])


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_reset_token(settings: Settings, user_id: int, password_hash: str) -> str:
    """Stateless, single-use reset token.

    It embeds a fingerprint of the current password hash, so it stops working as
    soon as the password changes.
    """
    return _encode(
        settings,
        {"sub": str(user_id), "fp": _password_fingerprint(password_hash)},
        RESET_TOKEN,
        timedelta(minutes=settings.password_reset_expire_minutes),
    )


def decode_reset_token(settings: Settings, token: str) -> tuple[int, str] | None:
    """Return (user_id, password fingerprint) for a valid reset token."""
    claims = _decode(settings, token, RESET_TOKEN)
    if claims is None or not claims["sub"].isdigit() or "fp" not in claims:
        return None
    return int(claims["sub"]), claims["fp"]


def reset_token_matches(fingerprint: str, password_hash: str) -> bool:
    return hmac.compare_digest(fingerprint, _password_fingerprint(password_hash))
