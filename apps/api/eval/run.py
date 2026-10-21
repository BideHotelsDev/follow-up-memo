"""The golden set (PRD §10 Testing): run extraction on real notes with hand-written expected actions and score it.

    pnpm eval                  # every case in eval/cases
    pnpm eval -- revenue       # cases whose folder name contains "revenue"

Each case is a folder in eval/cases with notes.txt (the Gemini doc as plain text), meeting.json
({"title", "date": "YYYY-MM-DD", "attendees": [{"name", "email"}]}) and expected.json
({"action_items": [{"description", "owner", "due_date"}]}). Real notes stay out of git: only example-* folders are
committed. Calls the real Claude API (ANTHROPIC_API_KEY), so every run costs money; the cost is printed at the end.

Scores, over all cases:
  found     expected actions the extraction contains (missed actions are the rest)
  owner     of those found, the share with the right owner
  due       of those found, the share with the right due date (null counts)
  invented  extracted actions that match nothing expected
Actions are matched by description similarity, so read the per-case lines too.
"""

import json
import re
import sys
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bide_followup import seed
from bide_followup.config import settings
from bide_followup.integrations import llm
from bide_followup.models import Base
from bide_followup.pipeline import extract

HERE = Path(__file__).resolve().parent
MATCH = 0.55
# $ per million tokens (input, output), for the cost line. Update when the model or prices change.
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def match(expected: list[dict], actual: list[dict]) -> list[tuple[dict, dict | None]]:
    """Pair each expected action with its most similar unused extracted action, best pairs first."""
    scored = sorted(
        (
            (SequenceMatcher(None, _norm(e["description"]), _norm(a["description"])).ratio(), i, j)
            for i, e in enumerate(expected)
            for j, a in enumerate(actual)
        ),
        reverse=True,
    )
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for ratio, i, j in scored:
        if ratio >= MATCH and i not in pairs and j not in used:
            pairs[i] = j
            used.add(j)
    return [(e, actual[pairs[i]] if i in pairs else None) for i, e in enumerate(expected)]


def _same_owner(expected: str, actual: str) -> bool:
    return _norm(expected).split()[:1] == _norm(actual).split()[:1]


def session_factory():
    """The Bide context the prompt carries: the seeded people (with the demo team) and categories."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        seed.base(s)
        seed.demo(s)
    return factory


def main(argv: list[str]) -> int:
    if not llm.enabled():
        print("Set ANTHROPIC_API_KEY first: the eval calls Claude.", file=sys.stderr)
        return 1
    wanted = argv[0] if argv else ""
    cases = sorted(p for p in (HERE / "cases").iterdir() if p.is_dir() and wanted in p.name)
    if not cases:
        print("No cases found in eval/cases.", file=sys.stderr)
        return 1
    factory = session_factory()
    totals = {"expected": 0, "found": 0, "owner": 0, "due": 0, "actual": 0, "invented": 0, "in": 0, "out": 0}
    report = []
    for case in cases:
        meeting = json.loads((case / "meeting.json").read_text())
        expected = json.loads((case / "expected.json").read_text())["action_items"]
        notes = (case / "notes.txt").read_text()
        attendees = [(a["name"], a["email"]) for a in meeting.get("attendees", [])]
        with factory() as s:
            result = extract.extract(s, meeting["title"], date.fromisoformat(meeting["date"]), attendees, notes)
        actual = [
            {"description": g.action.description, "owner": g.action.owner, "due_date": g.due and g.due.isoformat()}
            for g in result.grounded.actions
        ]
        pairs = match(expected, actual)
        found = [(e, a) for e, a in pairs if a]
        row = {
            "case": case.name,
            "expected": len(expected),
            "found": len(found),
            "owner": sum(_same_owner(e["owner"], a["owner"]) for e, a in found),
            "due": sum(e.get("due_date") == a["due_date"] for e, a in found),
            "actual": len(actual),
            "invented": len(actual) - len(found),
            "dropped_by_validator": result.grounded.dropped,
            "missed": [e["description"] for e, a in pairs if a is None],
            "pairs": [{"expected": e, "actual": a} for e, a in pairs],
            "extra": [a for a in actual if all(a is not m for _, m in found)],
        }
        report.append(row)
        for key in ("expected", "found", "owner", "due", "actual", "invented"):
            totals[key] += row[key]
        totals["in"] += result.input_tokens
        totals["out"] += result.output_tokens
        print(
            f"{case.name}: found {row['found']}/{row['expected']}, owner {row['owner']}/{row['found']}, "
            f"due {row['due']}/{row['found']}, invented {row['invented']}/{row['actual']}"
            + (f", missed: {'; '.join(row['missed'])}" if row["missed"] else "")
        )

    def pct(n: int, d: int) -> str:
        return f"{100 * n / d:.0f}%" if d else "n/a"

    print(
        f"\nfound {pct(totals['found'], totals['expected'])}, owner {pct(totals['owner'], totals['found'])}, "
        f"due {pct(totals['due'], totals['found'])}, invented {pct(totals['invented'], totals['actual'])} "
        f"over {len(cases)} cases"
    )
    price_in, price_out = PRICES.get(settings.llm_model, (0, 0))
    cost = totals["in"] / 1e6 * price_in + totals["out"] / 1e6 * price_out
    print(f"{totals['in']} input / {totals['out']} output tokens on {settings.llm_model}, about ${cost:.2f}")
    out = HERE / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{extract.PROMPT_VERSION}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"model": settings.llm_model, "totals": totals, "cases": report}, indent=2))
    print(f"details: {out.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
