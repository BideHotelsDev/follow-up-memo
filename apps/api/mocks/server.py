"""Stand-ins for Google (OAuth token, Drive, Calendar) and Claude, for local development and tests.

    pnpm dev:mocks          # http://localhost:8400
    pnpm dev:api:mock       # the API wired to it (.env.mock)

Drive serves the sample notes in mocks/samples.py, timed relative to when the mock started. Claude answers with each
sample's expected extraction; an unknown note gets a thin, empty one.
"""

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from mocks.samples import SAMPLES, doc_name, friday_after

app = FastAPI(title="Bide Follow-up mocks")

# Times are fixed when the mock starts, so a restarted API sees the same notes. Tests reset them with `reset`.
state: dict = {}


def reset(now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    state["now"] = now
    state["files"] = {}
    for s in SAMPLES:
        start = now + s["start_offset"]
        end = start + timedelta(minutes=s["minutes"])
        state["files"][s["file_id"]] = {
            "sample": s,
            "name": doc_name(s, start),
            "created": start,
            "modified": end + timedelta(minutes=5),
            "start": start,
            "end": end,
        }


reset()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@app.post("/google/token")
def google_token() -> dict:
    return {"access_token": f"mock-access-{uuid.uuid4().hex[:8]}", "expires_in": 3599, "token_type": "Bearer"}


@app.get("/google/drive/v3/files")
def drive_list(q: str) -> dict:
    after = q.split("modifiedTime > '")[1].split("'")[0]
    since = datetime.fromisoformat(after).replace(tzinfo=UTC)
    files = [
        {
            "id": file_id,
            "name": f["name"],
            "createdTime": _iso(f["created"]),
            "modifiedTime": _iso(f["modified"]),
            "webViewLink": f"https://docs.google.com/document/d/{file_id}/edit",
        }
        for file_id, f in state["files"].items()
        if f["modified"] > since
    ]
    return {"files": sorted(files, key=lambda f: f["modifiedTime"])}


@app.get("/google/drive/v3/files/{file_id}/export", response_class=PlainTextResponse)
def drive_export(file_id: str, mimeType: str) -> str:  # Google's parameter name
    if file_id not in state["files"]:
        raise HTTPException(status_code=404, detail={"error": {"status": "NOT_FOUND"}})
    return state["files"][file_id]["sample"]["notes"]


@app.get("/google/calendar/v3/calendars/primary/events")
def calendar_events(timeMin: str, timeMax: str) -> dict:
    low, high = datetime.fromisoformat(timeMin), datetime.fromisoformat(timeMax)
    items = []
    for file_id, f in state["files"].items():
        if low <= f["start"] <= high:
            items.append(
                {
                    "id": f"event-{file_id}",
                    "summary": f["sample"]["title"],
                    "start": {"dateTime": f["start"].isoformat()},
                    "end": {"dateTime": f["end"].isoformat()},
                    "attendees": [{"displayName": n, "email": e} for n, e in f["sample"]["attendees"]]
                    + [{"email": "room-1@resource.calendar.google.com", "resource": True}],
                    "attachments": [{"fileId": file_id, "title": f["name"]}],
                }
            )
    return {"items": items}


def _extraction_for(prompt: str) -> dict:
    for f in state["files"].values():
        sample = f["sample"]
        if sample["notes"].strip() in prompt:
            extraction = copy.deepcopy(sample["extraction"])
            for action in extraction["action_items"]:
                if action["due_date"] == "{friday}":
                    action["due_date"] = friday_after(f["start"])
            return extraction
    return {
        "meeting": {
            "title": "Meeting",
            "purpose": "",
            "properties": [],
            "is_sensitive": False,
            "sensitive_reason": None,
        },
        "attendees": [],
        "key_points": [],
        "decisions": [],
        "action_items": [],
        "open_threads": [],
        "questions_for_david": [],
        "systems_mentioned": [],
        "notes_quality": "thin",
    }


@app.post("/anthropic/v1/messages")
async def messages(request: Request) -> dict:
    body = await request.json()
    state["last_request"] = {"body": body, "beta": request.headers.get("anthropic-beta", "")}
    prompt = "\n".join(m["content"] for m in body["messages"] if m["role"] == "user" and isinstance(m["content"], str))
    text = json.dumps(_extraction_for(prompt))
    return {
        "id": f"msg_mock_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": body["model"],
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4},
    }
