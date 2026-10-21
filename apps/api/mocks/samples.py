"""Made-up meetings for local development and tests: Gemini-style notes, their calendar events, and the extraction
Claude would be expected to return. No real Bide data here."""

from datetime import datetime, timedelta

SAMPLES = [
    {
        "key": "revenue",
        "file_id": "doc-revenue-weekly",
        "title": "Weekly revenue",
        "start_offset": timedelta(hours=-3),  # relative to "now" in the mock
        "minutes": 45,
        "attendees": [
            ("David", "david@liddellpropertyinvestments.com"),
            ("Sam", "sam@bidehotels.com"),
            ("Priya Shah", "priya@pricelabs.example"),
        ],
        "notes": """Summary
David, Sam and Priya Shah from PriceLabs reviewed October pace for The View and The Hearth.

Details
Occupancy at The View is behind last year for half-term. Priya suggested lowering the minimum stay to two nights.
David agreed to lower the minimum stay at The View to two nights for half-term.
Sam will update the PriceLabs minimum-stay rule for The View by Friday.
Priya will send the comparison report for Highland short stays to David.
Someone needs to check the Canary upsell settings for The Hearth.

Suggested next steps
Sam to update the PriceLabs minimum-stay rule for The View by Friday.
Priya to send the comparison report for Highland short stays.
""",
        "extraction": {
            "meeting": {
                "title": "Weekly revenue",
                "purpose": "Review October pace for The View and The Hearth with PriceLabs.",
                "properties": ["The View", "The Hearth"],
                "is_sensitive": False,
                "sensitive_reason": None,
            },
            "attendees": [
                {"name": "David", "email": "david@liddellpropertyinvestments.com", "is_internal": True},
                {"name": "Sam", "email": "sam@bidehotels.com", "is_internal": True},
                {"name": "Priya Shah", "email": "priya@pricelabs.example", "is_internal": False},
            ],
            "key_points": ["Occupancy at The View is behind last year for half-term."],
            "decisions": ["Lower the minimum stay at The View to two nights for half-term."],
            "action_items": [
                {
                    "description": "Update the PriceLabs minimum-stay rule for The View to two nights",
                    "owner": "Sam",
                    "due_date": "{friday}",
                    "source_quote": "Sam will update the PriceLabs minimum-stay rule for The View by Friday.",
                },
                {
                    "description": "Send David the comparison report for Highland short stays",
                    "owner": "Priya Shah",
                    "due_date": None,
                    "source_quote": "Priya will send the comparison report for Highland short stays to David.",
                },
                {
                    "description": "Check the Canary upsell settings for The Hearth",
                    "owner": "NEEDS_OWNER",
                    "due_date": None,
                    "source_quote": "Someone needs to check the Canary upsell settings for The Hearth.",
                },
            ],
            "open_threads": [],
            "questions_for_david": [],
            "systems_mentioned": ["PriceLabs", "Canary"],
            "notes_quality": "good",
        },
    },
    {
        "key": "housekeeping",
        "file_id": "doc-housekeeping-sync",
        "title": "Housekeeping sync",
        "start_offset": timedelta(hours=-2),
        "minutes": 30,
        "attendees": [("David", "david@liddellpropertyinvestments.com"), ("Russell", "russell@bidehotels.com")],
        "notes": """Summary
David and Russell went through linen stock and the Operto cleaning schedule for The Villa.

Details
Russell said two cleans at The Villa overlapped last weekend in Operto.
Russell will fix the Operto cleaning schedule for The Villa so turnovers don't overlap.
David will ask the laundry about a second delivery day.
""",
        "extraction": {
            "meeting": {
                "title": "Housekeeping sync",
                "purpose": "Go through linen stock and the Operto cleaning schedule for The Villa.",
                "properties": ["The Villa"],
                "is_sensitive": False,
                "sensitive_reason": None,
            },
            "attendees": [
                {"name": "David", "email": "david@liddellpropertyinvestments.com", "is_internal": True},
                {"name": "Russell", "email": "russell@bidehotels.com", "is_internal": True},
            ],
            "key_points": ["Two cleans at The Villa overlapped last weekend in Operto."],
            "decisions": [],
            "action_items": [
                {
                    "description": "Fix the Operto cleaning schedule for The Villa so turnovers don't overlap",
                    "owner": "Russell",
                    "due_date": None,
                    "source_quote": "Russell will fix the Operto cleaning schedule for The Villa",
                },
                {
                    "description": "Ask the laundry about a second delivery day",
                    "owner": "David",
                    "due_date": None,
                    "source_quote": "David will ask the laundry about a second delivery day.",
                },
            ],
            "open_threads": [],
            "questions_for_david": ["Should the second laundry delivery day start before half-term?"],
            "systems_mentioned": ["Operto"],
            "notes_quality": "good",
        },
    },
]


def doc_name(sample: dict, start: datetime) -> str:
    return f"{sample['title']} - {start:%Y/%m/%d %H:%M} BST - Notes by Gemini"


def friday_after(day: datetime) -> str:
    return (day + timedelta(days=(4 - day.weekday()) % 7 or 7)).date().isoformat()
