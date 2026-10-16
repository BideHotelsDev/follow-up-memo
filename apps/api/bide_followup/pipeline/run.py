"""One polling run (PRD §6 Pipeline stages): Discover new Gemini notes; Fetch, Extract and Generate each queued
meeting's outputs; send David the run Summary; Log the run. Each meeting is processed on its own, so one failure never blocks the others.

Logs carry IDs and counts only, never note content (PRD §5 Privacy).
"""

import logging
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import clock
from bide_followup.config import settings
from bide_followup.integrations import google_api, google_oauth, llm
from bide_followup.models import ActionItem, Attendee, Meeting, Question, Run, SkipRule, User
from bide_followup.pipeline import extract, outputs, summary
from bide_followup.schemas.extraction import NEEDS_DAVID

log = logging.getLogger(__name__)

# "Weekly revenue - 2026/10/13 14:00 BST - Notes by Gemini"
NOTE_NAME = re.compile(r"^(?P<title>.*?)\s+-\s+\d{4}/\d{2}/\d{2}[^-]*-\s+Notes by Gemini\s*$")


def meeting_title(doc_name: str) -> str:
    match = NOTE_NAME.match(doc_name)
    if match:
        return match["title"].strip()
    return doc_name.replace("Notes by Gemini", "").strip(" -") or doc_name


def _rules(session: Session) -> tuple[list[str], set[str]]:
    rules = session.scalars(select(SkipRule)).all()
    keywords = [r.value.lower() for r in rules if r.type == "title_keyword"]
    emails = {r.value.lower() for r in rules if r.type == "attendee_email"}
    return keywords, emails


def discover(session: Session, token: str, run: Run) -> None:
    """New notes become queued meetings; notes still being written wait for the next run (FR-1 to FR-4)."""
    now = clock.utcnow()
    notes = google_api.list_gemini_notes(token, now - timedelta(days=settings.lookback_days))
    run.found = len(notes)
    seen = set(session.scalars(select(Meeting.drive_file_id).where(Meeting.drive_file_id.in_([n.id for n in notes]))))
    keywords, _ = _rules(session)
    for note in notes:
        if note.id in seen or now - note.modified_at < timedelta(minutes=settings.quiet_minutes):
            continue
        title = meeting_title(note.name)
        meeting = Meeting(
            drive_file_id=note.id, drive_modified_at=note.modified_at, title=title, started_at=note.created_at
        )
        keyword = next((k for k in keywords if k in title.lower()), None)
        if keyword:
            meeting.status, meeting.skip_reason = "skipped", f"Title contains “{keyword}”"
            run.skipped += 1
        session.add(meeting)
    session.commit()


def _owner(owner: str, people: list[User]) -> tuple[User | None, str | None, str]:
    """Who an action belongs to: a Bide person (by first or full name), an external person, or Needs David."""
    name = owner.strip()
    if not name or name.upper() == NEEDS_DAVID:
        return None, None, "needs_david"
    lowered = name.lower()
    for person in people:
        full = person.name.lower()
        if lowered in (full, full.split()[0]):
            return person, None, "assigned"
    return None, name, "assigned"


def process(session: Session, token: str, meeting: Meeting) -> None:
    """Fetch and Extract one meeting, replacing anything an earlier attempt stored."""
    _, skip_emails = _rules(session)
    note = google_api.NoteFile(
        id=meeting.drive_file_id,
        name=meeting.title,
        created_at=meeting.started_at or clock.utcnow(),
        modified_at=meeting.drive_modified_at or clock.utcnow(),
        url="",
    )
    notes = google_api.export_text(token, meeting.drive_file_id)
    event = google_api.find_event(token, note, meeting.title)
    invite = [(a.name, a.email) for a in event.attendees] if event else []
    if event:
        meeting.calendar_event_id = event.id
        meeting.started_at, meeting.ended_at = event.start or meeting.started_at, event.end
    skipped = next((email for _, email in invite if email in skip_emails), None)
    if skipped:
        meeting.status, meeting.skip_reason = "skipped", f"Attendee {skipped} is on the skip list"
        return

    meeting_day = (meeting.started_at or clock.utcnow()).astimezone(clock.now().tzinfo).date()
    result = extract.extract(session, meeting.title, meeting_day, invite, notes)
    grounded = result.grounded
    info = grounded.extraction

    for collection in (meeting.attendees, meeting.action_items, meeting.questions):
        collection.clear()
    session.flush()

    people = session.scalars(select(User).where(User.is_active)).all()
    by_email = {p.email.lower(): p for p in people}
    attendees = {email: name for name, email in invite}
    for a in info.attendees:
        if a.email and a.email.lower() not in attendees:
            attendees[a.email.lower()] = a.name
    named = {name.lower() for name in attendees.values()}
    for a in info.attendees:
        if not a.email and a.name.lower() not in named:
            attendees[f"name:{a.name}"] = a.name
            named.add(a.name.lower())
    for key, name in attendees.items():
        email = None if key.startswith("name:") else key
        user = by_email.get(email) if email else next((p for p in people if p.name.lower() == name.lower()), None)
        internal = user is not None or (email is not None and email.rsplit("@", 1)[-1] in settings.bide_domain_list)
        meeting.attendees.append(
            Attendee(name=name, email=email, is_internal=internal, user_id=user.id if user else None)
        )

    items: list[ActionItem] = []
    for g in grounded.actions:
        user, external, status = _owner(g.action.owner, people)
        item = ActionItem(
            description=g.action.description,
            owner_user_id=user.id if user else None,
            owner_name=external,
            owner_status=status,
            due_date=g.due,
            source_quote=g.action.source_quote,
        )
        meeting.action_items.append(item)
        items.append(item)
    session.flush()
    for text, index, kind in grounded.questions:
        action_id = items[index].id if index is not None else None
        meeting.questions.append(Question(text=text, kind=kind, action_item_id=action_id))

    meeting.properties = list(info.meeting.properties)
    meeting.is_sensitive = info.meeting.is_sensitive
    meeting.extraction = {**extract.summary(info), "dropped_actions": grounded.dropped}
    meeting.prompt_version = extract.PROMPT_VERSION
    meeting.input_tokens += result.input_tokens
    meeting.output_tokens += result.output_tokens
    meeting.raw_text = notes
    meeting.raw_text_expires_at = clock.utcnow() + timedelta(days=settings.raw_text_days)
    meeting.status, meeting.error = "done", None  # until its outputs are generated


def run(session: Session) -> Run:
    record = Run(started_at=clock.utcnow())
    session.add(record)
    session.commit()
    touched: list = []
    try:
        token = google_oauth.access_token(session)
        outputs.retry_failed(session)
        summary.retry_failed(session)
        discover(session, token, record)
        if not llm.enabled():
            record.error = "Extraction is off (ANTHROPIC_API_KEY not set); meetings wait in the queue"
        else:
            # A meeting left "processing" was interrupted by a restart; the worker runs one job at a time.
            queued = session.scalars(
                select(Meeting).where(Meeting.status.in_(("queued", "processing"))).order_by(Meeting.started_at)
            ).all()
            for meeting in queued:
                _process_one(session, token, meeting, record, touched)
    except google_oauth.GoogleAuthError as exc:
        session.rollback()
        record.error = f"Paused: {exc}"
    except google_api.GoogleApiError as exc:
        session.rollback()
        record.error = str(exc)
    record.finished_at = clock.utcnow()
    session.add(record)
    session.commit()
    summary.send(session, record, touched)
    summary.alert_if_failing(session, record)
    log.info(
        "run %s: found %s, processed %s, skipped %s, failed %s%s",
        record.id,
        record.found,
        record.processed,
        record.skipped,
        record.failed,
        f" ({record.error})" if record.error else "",
    )
    return record


def _process_one(session: Session, token: str, meeting: Meeting, record: Run, touched: list) -> None:
    meeting.status = "processing"
    meeting.attempts += 1
    session.commit()
    try:
        process(session, token, meeting)
        session.commit()
        if meeting.status == "skipped":
            record.skipped += 1
            return
        # The extraction is saved first, so an output failure never loses it; outputs record their own failures.
        outputs.generate(session, meeting)
        session.commit()
        record.processed += 1
        touched.append(meeting.id)
    except google_oauth.GoogleAuthError:
        session.rollback()
        meeting.status = "queued"
        session.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - one meeting's failure is recorded, never fatal to the run
        session.rollback()
        log.warning("meeting %s attempt %s failed: %s", meeting.id, meeting.attempts, exc.__class__.__name__)
        meeting.error = f"{exc.__class__.__name__}: {exc}"[:2000]
        if meeting.attempts >= settings.max_attempts:
            meeting.status = "failed"
            record.failed += 1
            touched.append(meeting.id)
        else:
            meeting.status = "queued"  # the next run retries it
        session.commit()


def purge_raw_text(session: Session) -> int:
    """Delete stored note text past its expiry (PRD §5 Privacy). Returns the meetings cleared."""
    expired = session.scalars(
        select(Meeting).where(Meeting.raw_text.is_not(None), Meeting.raw_text_expires_at <= clock.utcnow())
    ).all()
    for meeting in expired:
        meeting.raw_text = None
    session.commit()
    return len(expired)
