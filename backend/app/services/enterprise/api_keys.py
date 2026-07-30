"""API-key generation, hashing, and verification (Phase 19).

Pure crypto helpers for the enterprise API-key scheme. A raw key is a
high-entropy random token (`pik_` + 24 random bytes, url-safe) — because
that's ~192 bits of entropy, a plain SHA-256 hash is a sound at-rest
representation (unlike a low-entropy password, which would need a slow
salted KDF). Only the hash and a short non-secret `prefix` are ever
stored; verification recomputes the hash from a presented key and
compares it against the stored one in constant time (`hmac.compare_digest`,
so a match doesn't leak timing).
"""

import hashlib
import hmac
import secrets

_KEY_BYTES = 24
_PREFIX_LENGTH = 12


def generate_raw_key() -> str:
    """Return a fresh high-entropy raw API key (shown to the caller exactly once)."""
    return "pik_" + secrets.token_urlsafe(_KEY_BYTES)


def key_prefix(raw_key: str) -> str:
    """Return the short, non-secret leading segment used to index the key."""
    return raw_key[:_PREFIX_LENGTH]


def hash_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest stored for `raw_key`."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_key(raw_key: str, key_hash: str) -> bool:
    """Return whether `raw_key` hashes to `key_hash`, compared in constant time."""
    return hmac.compare_digest(hash_key(raw_key), key_hash)
