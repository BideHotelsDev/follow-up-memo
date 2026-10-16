"""Encryption at rest for OAuth tokens (PRD §5 Security). The key lives in TOKEN_ENCRYPTION_KEY, never the database."""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from bide_followup.config import settings
from bide_followup.errors import DomainError


def _fernet() -> Fernet:
    if not settings.token_encryption_key:
        raise DomainError("encryption_not_configured", "TOKEN_ENCRYPTION_KEY is not set", 503)
    return Fernet(settings.token_encryption_key.encode())


def encrypt(tokens: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(tokens).encode()).decode()


def decrypt(blob: str) -> dict[str, Any]:
    try:
        return json.loads(_fernet().decrypt(blob.encode()))
    except InvalidToken:
        # A rotated or wrong key: the account has to be reconnected.
        raise DomainError("token_unreadable", "Stored tokens can't be decrypted; reconnect the account", 409)
