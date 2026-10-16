from datetime import date

from bide_followup.pipeline import validate
from bide_followup.schemas.extraction import Extraction

NOTES = """Sam will update the PriceLabs minimum-stay rule for The View by Friday.
Russell to look at the boiler at The Hearth. Contact: jo@plumbers.example"""
DAY = date(2026, 10, 13)


def extraction(actions, attendees=(), questions=()):
    return Extraction.model_validate(
        {
            "meeting": {
                "title": "t",
                "purpose": "p",
                "properties": [],
                "is_sensitive": False,
                "sensitive_reason": None,
            },
            "attendees": list(attendees),
            "key_points": [],
            "decisions": [],
            "action_items": actions,
            "open_threads": [],
            "questions_for_david": list(questions),
            "systems_mentioned": [],
            "notes_quality": "good",
        }
    )


def action(quote, owner="Sam", due=None, description="Do it"):
    return {"description": description, "owner": owner, "due_date": due, "source_quote": quote}


def test_grounded_allows_spacing_case_and_small_slips():
    assert validate.grounded("sam will update the PriceLabs minimum-stay rule", NOTES)
    assert validate.grounded("Sam will update the PriceLabs minimum stay rule for The View, by Friday", NOTES)
    assert not validate.grounded("Sam will cancel the Mews contract", NOTES)
    assert not validate.grounded("by", NOTES)  # too short to prove anything


def test_check_reports_ungrounded_quotes_bad_dates_and_unknown_emails():
    e = extraction(
        [action("Sam will email the investors"), action("Russell to look at the boiler", due="2031-01-01")],
        attendees=[{"name": "Jo", "email": "jo@elsewhere.example", "is_internal": False}],
    )
    problems = validate.check(e, NOTES, validate.emails_in(NOTES), DAY)
    assert len(problems) == 3


def test_ground_drops_ungrounded_and_unsupported_dates():
    e = extraction(
        [
            action("Sam will update the PriceLabs minimum-stay rule for The View by Friday", due="2026-10-16"),
            action("Russell to look at the boiler at The Hearth", owner="Russell", due="2026-10-20"),
            action("Sam will email the investors", description="Email investors"),
        ],
        attendees=[{"name": "Jo", "email": "jo@elsewhere.example", "is_internal": False}],
    )
    g = validate.ground(e, NOTES, validate.emails_in(NOTES), DAY)
    assert [a.due for a in g.actions] == [date(2026, 10, 16), None]  # the boiler quote states no deadline
    assert g.dropped == ["Email investors"]
    assert g.questions == [("When is this due: Do it?", 1)]
    assert e.attendees[0].email is None


def test_needs_david_becomes_a_question_and_questions_cap_at_five():
    e = extraction(
        [action("Russell to look at the boiler at The Hearth", owner="NEEDS_DAVID", description="Fix boiler")],
        questions=[f"Q{i}?" for i in range(6)],
    )
    g = validate.ground(e, NOTES, set(), DAY)
    assert g.questions[0] == ("Who should own this: Fix boiler?", 0)
    assert len(g.questions) == 5
