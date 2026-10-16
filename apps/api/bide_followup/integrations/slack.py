"""The Slack bot: installed once by Admin, its token stored encrypted. Posting happens only on approval, except the
run summary DM to David and failure alerts to Admin (PRD §9)."""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import crypto
from bide_followup.config import settings
from bide_followup.models import Integration

BOT_SCOPES = (
    "chat:write",
    "chat:write.public",  # post a digest to a public channel without being invited first
    "im:write",
    "users:read",
    "users:read.email",
    "channels:read",
    "groups:read",  # private channels the bot has been invited to
)


def integration(session: Session) -> Integration | None:
    return session.scalar(select(Integration).where(Integration.provider == "slack"))


def save(session: Session, body: dict) -> Integration:
    """Store the oauth.v2.access response from the install flow."""
    row = integration(session)
    if row is None:
        row = Integration(provider="slack", encrypted_tokens="")
        session.add(row)
    row.encrypted_tokens = crypto.encrypt({"bot_token": body["access_token"]})
    row.external_id = body.get("team", {}).get("id")
    row.account_email = body.get("team", {}).get("name")
    row.scopes = body.get("scope", "").split(",")
    row.status, row.last_error = "connected", None
    session.commit()
    return row


def client(session: Session) -> WebClient | None:
    row = integration(session)
    if row is None or row.status == "revoked":
        return None
    return WebClient(token=crypto.decrypt(row.encrypted_tokens)["bot_token"], base_url=settings.slack_api_url + "/")


class SlackNotConnected(Exception):
    """The bot isn't installed (or its token was revoked)."""


def _require(session: Session) -> WebClient:
    found = client(session)
    if found is None:
        raise SlackNotConnected("The Slack bot isn't installed")
    return found


def post(session: Session, channel: str, text: str) -> str:
    """Post to a channel or, given a Slack user ID, to that person's DM. Returns the message ts."""
    bot = _require(session)
    if channel.startswith(("U", "W")):
        channel = bot.conversations_open(users=channel)["channel"]["id"]
    return bot.chat_postMessage(channel=channel, text=text, unfurl_links=False, unfurl_media=False)["ts"]


def user_id_for(session: Session, email: str) -> str | None:
    """A person's Slack member ID from their email (users:read.email), or None when Slack doesn't know them."""
    try:
        return _require(session).users_lookupByEmail(email=email)["user"]["id"]
    except SlackApiError as exc:
        if exc.response.get("error") == "users_not_found":
            return None
        raise
