"""Drive and Calendar, read-only, as David (PRD §8). Plain httpx with configurable base URLs, so the local mock
services (apps/api/mocks) can stand in for Google."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from bide_followup.config import settings

GEMINI_TITLE = "Notes by Gemini"
GOOGLE_DOC = "application/vnd.google-apps.document"


class GoogleApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Google API {status}: {message}")
        self.status = status


def _get(token: str, url: str, params: dict | None = None) -> httpx.Response:
    resp = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.is_error:
        # The body can quote document content; keep only the status and Google's short reason.
        reason = ""
        if resp.headers.get("content-type", "").startswith("application/json"):
            reason = resp.json().get("error", {}).get("status", "")
        raise GoogleApiError(resp.status_code, reason or resp.reason_phrase)
    return resp


@dataclass
class NoteFile:
    id: str
    name: str
    created_at: datetime
    modified_at: datetime
    url: str


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def list_gemini_notes(token: str, modified_after: datetime) -> list[NoteFile]:
    """Gemini notes docs in David's Drive modified after the given moment (FR-1), oldest first."""
    since = modified_after.strftime("%Y-%m-%dT%H:%M:%S")
    query = (
        f"name contains '{GEMINI_TITLE}' and mimeType = '{GOOGLE_DOC}' and modifiedTime > '{since}' and trashed = false"
    )
    files: list[NoteFile] = []
    page: str | None = None
    while True:
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,createdTime,modifiedTime,webViewLink)",
            "orderBy": "modifiedTime",
            "pageSize": 100,
        }
        if page:
            params["pageToken"] = page
        body = _get(token, f"{settings.google_api_url}/drive/v3/files", params).json()
        for f in body.get("files", []):
            files.append(
                NoteFile(
                    id=f["id"],
                    name=f["name"],
                    created_at=_ts(f["createdTime"]),
                    modified_at=_ts(f["modifiedTime"]),
                    url=f.get("webViewLink") or f"https://docs.google.com/document/d/{f['id']}/edit",
                )
            )
        page = body.get("nextPageToken")
        if not page:
            return files


def export_text(token: str, file_id: str) -> str:
    return _get(token, f"{settings.google_api_url}/drive/v3/files/{file_id}/export", {"mimeType": "text/plain"}).text


@dataclass
class EventAttendee:
    name: str
    email: str


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime | None
    end: datetime | None
    attendees: list[EventAttendee] = field(default_factory=list)


def _event(e: dict) -> CalendarEvent:
    def moment(part: dict | None) -> datetime | None:
        return _ts(part["dateTime"]) if part and part.get("dateTime") else None

    attendees = [
        EventAttendee(name=a.get("displayName") or a["email"].split("@")[0], email=a["email"].lower())
        for a in e.get("attendees", [])
        if a.get("email") and not a.get("resource")  # meeting rooms are attendees too
    ]
    return CalendarEvent(
        id=e["id"],
        title=e.get("summary", ""),
        start=moment(e.get("start")),
        end=moment(e.get("end")),
        attendees=attendees,
    )


def find_event(token: str, note: NoteFile, meeting_title: str) -> CalendarEvent | None:
    """The calendar event a Gemini note belongs to (FR-5). Gemini attaches its notes to the event, so a matching
    attachment decides it; failing that, the event whose title matches, nearest in time to when the doc was made."""
    params = {
        "timeMin": (note.created_at - timedelta(hours=3)).isoformat(),
        "timeMax": (note.created_at + timedelta(hours=3)).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 50,
    }
    events = _get(token, f"{settings.google_api_url}/calendar/v3/calendars/primary/events", params).json()
    items = events.get("items", [])
    for e in items:
        if any(a.get("fileId") == note.id for a in e.get("attachments", [])):
            return _event(e)
    wanted = meeting_title.strip().lower()
    titled = [e for e in items if e.get("summary", "").strip().lower() == wanted and e.get("start", {}).get("dateTime")]
    if not titled:
        return None
    return _event(min(titled, key=lambda e: abs(_ts(e["start"]["dateTime"]) - note.created_at)))
