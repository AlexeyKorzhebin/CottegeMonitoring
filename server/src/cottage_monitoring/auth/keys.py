"""API key generation and verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, key_prefix). Raw key shown once to the operator."""
    suffix = secrets.token_urlsafe(32)
    raw = f"cm_{suffix}"
    prefix = raw[:12]
    return raw, prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    expected = hash_api_key(raw_key)
    return hmac.compare_digest(expected, key_hash)
