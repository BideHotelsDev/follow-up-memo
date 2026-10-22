"""Wispr Flow's voice API: speech to text that drops filler words, applies self-corrections and spells names right.

The browser streams the microphone to Wispr over a WebSocket. The app's part is only to make it a short-lived client
token (the org API key never leaves the server) and to tell it the words to spell right. Docs:
https://api-docs.wisprflow.ai (client-side auth, WebSocket API).
"""

import httpx

from bide_followup.config import settings
from bide_followup.models import User

TOKEN_SECONDS = 15 * 60


class WisprError(Exception):
    pass


def configured() -> bool:
    return bool(settings.wispr_api_key)


def ws_url() -> str:
    base = settings.wispr_api_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return f"{base}/api/v1/dash/client_ws"


def access_token(user: User) -> tuple[str, int]:
    """A client token for this person, valid for TOKEN_SECONDS. Wispr's usage shows the app's user ID only."""
    try:
        resp = httpx.post(
            f"{settings.wispr_api_url.rstrip('/')}/api/v1/dash/generate_access_token",
            headers={"Authorization": f"Bearer {settings.wispr_api_key}"},
            json={"client_id": str(user.id), "duration_secs": TOKEN_SECONDS},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise WisprError("unreachable") from exc
    if resp.is_error:
        raise WisprError("invalid_key" if resp.status_code == 401 else f"http_{resp.status_code}")
    body = resp.json()
    return body["access_token"], int(body.get("expires_in", TOKEN_SECONDS))
