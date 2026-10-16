"""Store a Slack bot token that came from installing the app on Slack's own page rather than from Admin →
Connections (which stores it itself). Reads the token from stdin so it never lands in shell history:

    pnpm slack:token          # then paste the xoxb- token and press Enter
"""

import sys

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from bide_followup.config import settings
from bide_followup.db import SessionLocal
from bide_followup.integrations import slack


def main() -> int:
    token = sys.stdin.readline().strip()
    if not token.startswith("xoxb-"):
        print("That isn't a bot token (they start with xoxb-).", file=sys.stderr)
        return 1
    try:
        resp = WebClient(token=token, base_url=settings.slack_api_url + "/").auth_test()
    except SlackApiError as exc:
        print(f"Slack rejected the token: {exc.response.get('error')}", file=sys.stderr)
        return 1
    scopes = resp.headers.get("x-oauth-scopes", "")
    missing = set(slack.BOT_SCOPES) - set(scopes.split(","))
    if missing:
        print(f"The token is missing scopes: {', '.join(sorted(missing))}. Reinstall the app.", file=sys.stderr)
        return 1
    with SessionLocal() as session:
        slack.save(
            session,
            {"access_token": token, "scope": scopes, "team": {"id": resp["team_id"], "name": resp["team"]}},
        )
    print(f"Stored the bot token for {resp['team']} ({resp['user']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
