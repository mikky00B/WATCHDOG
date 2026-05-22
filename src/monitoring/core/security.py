from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from monitoring.config import get_settings


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2_sha256$120000${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = password_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return hmac.compare_digest(digest.hex(), expected)


def hash_email_verification_code(email: str, code: str) -> str:
    settings = get_settings()
    message = f"{email.lower()}:{code}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def verify_email_verification_code(email: str, code: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    actual_hash = hash_email_verification_code(email, code)
    return hmac.compare_digest(actual_hash, expected_hash)


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    settings = get_settings()
    return hmac.new(settings.jwt_secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def hash_password_reset_code(email: str, code: str) -> str:
    settings = get_settings()
    message = f"password-reset:{email.lower()}:{code}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def verify_password_reset_code(email: str, code: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    actual_hash = hash_password_reset_code(email, code)
    return hmac.compare_digest(actual_hash, expected_hash)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
        "typ": "access",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded_payload = _b64encode(payload_bytes)
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        settings.jwt_secret_key.encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()

    try:
        actual_signature = _b64decode(encoded_signature)
    except ValueError:
        return None

    if not hmac.compare_digest(actual_signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(UTC).timestamp()):
        return None

    if payload.get("typ") != "access":
        return None

    return payload
