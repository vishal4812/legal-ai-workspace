from __future__ import annotations

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    """Hash a password using pwdlib's recommended Argon2id parameters."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without exposing malformed-hash errors."""

    try:
        return _password_hash.verify(password, password_hash)
    except (TypeError, ValueError):
        return False


def consume_password_verification_time(password: str) -> None:
    """Reduce the login timing difference when no user record exists."""

    verify_password(password, _dummy_hash)
