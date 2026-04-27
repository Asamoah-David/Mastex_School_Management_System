"""
TOTP-based Two-Factor Authentication service (Fix #31).

Uses pyotp (RFC 6238 TOTP) — compatible with Google Authenticator,
Authy, 1Password, and any TOTP app.

Flow:
  1. Staff member enables 2FA → generate_secret() → show QR code.
  2. User scans with authenticator app, enters 6-digit code.
  3. verify_setup(user, code) → activates 2FA + generates backup codes.
  4. On every login: if totp_enabled, prompt for code → verify_token().
  5. Backup codes available as one-time fallback.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import string

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False


ISSUER = "Mastex SchoolOS"
TOKEN_WINDOW = 1          # ±30 s drift tolerance (1 = ±1 window = ±60 s)
BACKUP_CODE_COUNT = 8
BACKUP_CODE_LENGTH = 10


def _require_pyotp():
    if not PYOTP_AVAILABLE:
        raise RuntimeError("pyotp is not installed. Add 'pyotp>=2.9,<3.0' to requirements.txt and reinstall.")


def generate_secret() -> str:
    """Generate a new random Base32 TOTP secret (not yet saved to user)."""
    _require_pyotp()
    return pyotp.random_base32()


def get_totp_uri(user, secret: str) -> str:
    """Return the otpauth:// URI for embedding in a QR code."""
    _require_pyotp()
    label = f"{ISSUER}:{user.email or user.username}"
    return pyotp.totp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER)


def verify_token(user, token: str) -> bool:
    """Verify a 6-digit TOTP token for a user who has 2FA enabled."""
    _require_pyotp()
    if not user.totp_enabled or not user.totp_secret:
        return False
    totp = pyotp.TOTP(user.totp_secret)
    return totp.verify(token.strip(), valid_window=TOKEN_WINDOW)


def verify_setup(user, token: str, secret: str) -> tuple[bool, list[str]]:
    """Confirm the user scanned the QR code correctly, then activate 2FA.

    Returns (success, plain_backup_codes).
    The backup codes are returned ONCE; hashed versions are stored on the user.
    """
    _require_pyotp()
    totp = pyotp.TOTP(secret)
    if not totp.verify(token.strip(), valid_window=TOKEN_WINDOW):
        return False, []

    plain_codes = _generate_backup_codes()
    hashed_codes = [_hash_backup_code(c) for c in plain_codes]

    user.totp_secret = secret
    user.totp_enabled = True
    user.totp_backup_codes = "\n".join(hashed_codes)
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_backup_codes"])
    return True, plain_codes


def disable_2fa(user) -> None:
    """Wipe 2FA from a user account (admin or self-service after re-auth)."""
    user.totp_secret = ""
    user.totp_enabled = False
    user.totp_backup_codes = ""
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_backup_codes"])


def verify_backup_code(user, code: str) -> bool:
    """Consume a backup code.  Returns True if valid and removes it."""
    if not user.totp_backup_codes:
        return False
    hashed = _hash_backup_code(code.strip().upper())
    codes = [c for c in user.totp_backup_codes.splitlines() if c]
    if hashed in codes:
        codes.remove(hashed)
        user.totp_backup_codes = "\n".join(codes)
        user.save(update_fields=["totp_backup_codes"])
        return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_backup_codes() -> list[str]:
    alphabet = string.ascii_uppercase + string.digits
    return [
        "".join(secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        for _ in range(BACKUP_CODE_COUNT)
    ]


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.upper().encode()).hexdigest()
