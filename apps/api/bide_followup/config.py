from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Scripts run with apps/api as the working directory, so the repo-root .env is two levels up.
    # On Railway there is no .env; values come from service variables.
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    # Postgres in production. SQLite works for a local demo and the tests.
    database_url: str = "sqlite:///./followup.db"
    web_dist_dir: Path | None = None
    # Meetings, "today" and task buckets follow UK time.
    timezone: str = "Europe/London"

    # Public URL the browser uses; OAuth callbacks and the links in Slack and emails point here.
    app_base_url: str = "http://localhost:5175"
    # Signs the session cookie. Empty means a random key per process (sessions reset on restart).
    session_secret: str = ""
    session_days: int = 14
    # Local development only: sign in by email without Google. Has no effect unless app_base_url is http://localhost.
    auth_dev_login: bool = False
    # Email domains whose people count as internal and may sign in, comma-separated. The starting value only: Admin
    # edits the list in the app (Claude, email and schedule).
    bide_domains: str = "bidehotels.com,liddellpropertyinvestments.com"

    @property
    def bide_domain_list(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.bide_domains.split(",") if d.strip()]

    # Encrypts the stored Google and Slack tokens (a Fernet key: python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"). Required before any account is connected.
    token_encryption_key: str = ""

    # One Google OAuth app (Internal to the Bide Workspace) for both app sign-in and connecting David's account.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Base URLs, overridden by the local mock services (apps/api/mocks).
    google_oauth_url: str = "https://accounts.google.com"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_api_url: str = "https://www.googleapis.com"
    gmail_api_url: str = "https://gmail.googleapis.com"

    # Slack app (installed once by Admin; the bot token is stored encrypted in `integration`).
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""
    slack_api_url: str = "https://slack.com/api"
    slack_oauth_url: str = "https://slack.com/oauth/v2/authorize"
    # Channel for run-failure alerts to Admin.
    admin_alert_slack_channel: str = ""

    # Claude (PRD decision D1). "api": the app calls the Claude API with ANTHROPIC_API_KEY. "routine": Claude requests
    # wait in a queue that a scheduled Claude Code routine answers on Bide's Claude plan, calling the service API with
    # SERVICE_API_TOKEN (routine/README.md). Without the key or token, meetings wait in the queue.
    extraction_mode: str = "api"
    service_api_token: str = ""
    anthropic_api_key: str = ""
    anthropic_base_url: str | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"

    # Wispr Flow's voice API (exclusive access, from enterprise@wisprflow.ai). With a key, the boxes people write in
    # get a microphone button: the browser streams audio straight to Wispr with a short-lived token the app makes.
    # Without one, the buttons are hidden and Wispr Flow still works as a dictation app typing into any box.
    wispr_api_key: str = ""
    wispr_api_url: str = "https://platform-api.wisprflow.ai"

    poll_interval_minutes: int = 10
    # Gemini may still be writing a doc this soon after its last change (FR-3); notes older than this are not looked
    # at (FR-1).
    quiet_minutes: int = 15
    lookback_days: int = 3
    # A meeting that fails this many runs in a row is marked failed and surfaced (PRD §5 Reliability).
    max_attempts: int = 3
    raw_text_days: int = 30


settings = Settings()
