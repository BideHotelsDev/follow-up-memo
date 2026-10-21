"""Properties, systems, the owner and the targets come from the database, so Bide edits them in Admin."""

import json

from sqlalchemy import select

from bide_followup.integrations import llm
from bide_followup.models import ChannelMap, Meeting, User
from bide_followup.pipeline import run


def test_app_settings(sign_in):
    data = sign_in("sam@bidehotels.com").get("/api/app").json()
    assert data["owner_name"] == "David" and data["owner_email"] == "david@liddellpropertyinvestments.com"
    assert [p["name"] for p in data["properties"]] == ["The View", "The Hearth", "The Villa"]
    assert "PriceLabs" in data["systems"]


def test_admin_adds_renames_and_hides_properties(sign_in, db):
    client = sign_in("kyle@bidehotels.com")
    lodge = client.post("/api/admin/properties", json={"name": "  The   Lodge "}).json()
    assert lodge["name"] == "The Lodge" and lodge["color"] == 3 and lodge["sort_order"] == 3
    assert client.post("/api/admin/properties", json={"name": "the lodge"}).json()["code"] == "name_taken"

    with db() as s:
        s.add(Meeting(drive_file_id="x", title="Snagging", properties=["The View", "The Lodge"]))
        s.add(ChannelMap(property="The Lodge", slack_channel_id="C0LODGE"))
        s.commit()
    renamed = client.put(f"/api/admin/properties/{lodge['id']}", json={"name": "The Bothy"}).json()
    assert renamed["name"] == "The Bothy" and renamed["color"] == 3  # the colour stays with the property
    with db() as s:
        assert s.scalar(select(Meeting)).properties == ["The View", "The Bothy"]
        assert s.scalar(select(ChannelMap)).property == "The Bothy"

    client.put(f"/api/admin/properties/{lodge['id']}", json={"name": "The Bothy", "is_active": False})
    assert "The Bothy" not in [p["name"] for p in client.get("/api/app").json()["properties"]]
    assert "The Bothy" in [p["name"] for p in client.get("/api/admin/properties").json()]
    assert sign_in("sam@bidehotels.com").post("/api/admin/properties", json={"name": "X"}).status_code == 403


def test_systems(sign_in):
    client = sign_in("kyle@bidehotels.com")
    beds24 = client.post("/api/admin/systems", json={"name": "Beds24"}).json()
    assert "Beds24" in client.get("/api/app").json()["systems"]
    client.put(f"/api/admin/systems/{beds24['id']}", json={"name": "Beds24", "is_active": False})
    assert "Beds24" not in client.get("/api/app").json()["systems"]


def test_claude_is_given_the_current_lists_and_owner(db, mocks, connected, sign_in):
    client = sign_in("kyle@bidehotels.com")
    client.post("/api/admin/properties", json={"name": "The Lodge"})
    with db() as s:
        s.scalar(select(User).where(User.role == "owner")).name = "Davie Liddell"
        s.commit()
        run.run(s)
    body = mocks.state["last_request"]["body"]
    enum = body["output_config"]["format"]["schema"]["properties"]["meeting"]["properties"]["properties"]["items"]
    assert enum["enum"] == ["The View", "The Hearth", "The Villa", "The Lodge"]
    assert "Davie, the owner of Bide" in body["system"]
    assert "4 short-stay properties in Scotland: The View, The Hearth, The Villa and The Lodge" in body["system"]
    assert "pricing negotiations, contracts, staff performance, legal matters, HR or investors" in body["system"]
    assert "Anyone whose email is at @bidehotels.com or @liddellpropertyinvestments.com" in body["system"]


def test_claude_is_given_the_business_settings(db, mocks, connected, sign_in):
    client = sign_in("kyle@bidehotels.com")
    client.put(
        "/api/admin/settings",
        json={
            "property_region": "the Highlands",
            "sensitive_topics": ["HR", "investors"],
            "internal_domains": ["bidehotels.com", "bide.example"],
        },
    )
    with db() as s:
        run.run(s)
    system = mocks.state["last_request"]["body"]["system"]
    assert "3 short-stay properties in the Highlands" in system
    assert "when it covers HR or investors," in system
    assert "@bidehotels.com or @bide.example" in system


def test_unlisted_properties_are_asked_about_then_dropped(db, mocks, connected, monkeypatch):
    from bide_followup.integrations import llm
    from mocks.samples import SAMPLES

    answer = json.loads(json.dumps(SAMPLES[1]["extraction"]))
    answer["meeting"]["properties"] = ["The Villa", "The Castle"]
    calls = []

    def complete(system, messages, schema, **kwargs):
        calls.append(messages)
        return llm.Completion(text=json.dumps(answer), model="m", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(llm, "complete", complete)
    mocks.state["files"].pop("doc-revenue-weekly")
    with db() as s:
        run.run(s)
        assert s.scalar(select(Meeting)).properties == ["The Villa"]
    assert "The Castle" in calls[1][-1]["content"]  # the retry named it


def test_needs_label_and_targets_follow_settings(sign_in, db, mocks, connected, slack_bot):
    with db() as s:
        s.scalar(select(User).where(User.role == "owner")).name = "Davie"
        s.commit()
        run.run(s)
    client = sign_in("kyle@bidehotels.com")
    revenue = next(m for m in client.get("/api/meetings").json() if m["title"] == "Weekly revenue")
    digest_or_email = [o["body"] for o in client.get(f"/api/meetings/{revenue['id']}").json()["outputs"]]
    assert any("(Needs Davie)" in b for b in digest_or_email)

    client.put("/api/admin/settings", json={"target_unedited_rate": 80, "followup_within_hours": 48})
    targets = client.get("/api/impact").json()["targets"]
    assert targets["target_unedited_rate"] == 80 and targets["followup_within_hours"] == 48
    assert client.get("/api/impact").json()["owner_name"] == "Davie"


def test_david_runs_admin_too(sign_in):
    client = sign_in("david@liddellpropertyinvestments.com")
    people = {p["name"]: p for p in client.get("/api/admin/people").json()}
    assert client.put("/api/admin/settings", json={"email_signature": "D"}).status_code == 200
    resp = client.put(f"/api/admin/people/{people['David']['id']}", json={**people["David"], "role": "member"})
    assert resp.json()["code"] == "own_access"


def test_categories_are_edited_in_admin(sign_in, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    legal = client.post(
        "/api/admin/categories",
        json={"name": " Legal ", "description": "Contracts and  disputes", "is_sensitive": True},
    ).json()
    assert (legal["name"], legal["description"], legal["color"], legal["sort_order"]) == (
        "Legal",
        "Contracts and disputes",
        2,
        2,
    )
    assert client.post("/api/admin/categories", json={"name": "legal"}).json()["code"] == "name_taken"
    with db() as s:
        s.add(Meeting(drive_file_id="x", title="Lease", category="Legal"))
        s.add(ChannelMap(category="Legal", slack_channel_id="C0LEGAL"))
        s.commit()
    client.put(f"/api/admin/categories/{legal['id']}", json={"name": "Contracts", "is_sensitive": True})
    with db() as s:
        assert s.scalar(select(Meeting)).category == "Contracts"
        assert s.scalar(select(ChannelMap)).category == "Contracts"
    assert [m["category"] for m in client.get("/api/meetings", params={"category": "Contracts"}).json()] == [
        "Contracts"
    ]
    assert client.get("/api/meetings", params={"category": "Revenue"}).json() == []
    assert "Contracts" in [c["name"] for c in client.get("/api/app").json()["categories"]]
    assert sign_in("sam@bidehotels.com").post("/api/admin/categories", json={"name": "X"}).status_code == 403


def test_claude_sorts_meetings_into_categories(db, mocks, connected, sign_in):
    client = sign_in("kyle@bidehotels.com")
    ops = next(c for c in client.get("/api/admin/categories").json() if c["name"] == "Operations")
    client.put(
        f"/api/admin/categories/{ops['id']}",
        json={"name": "Operations", "description": "Housekeeping and cleaning", "is_sensitive": True},
    )
    with db() as s:
        run.run(s)
        found = {m.title: m for m in s.scalars(select(Meeting))}
    body = mocks.state["last_request"]["body"]
    category = body["output_config"]["format"]["schema"]["properties"]["meeting"]["properties"]["category"]
    assert category["anyOf"][0]["enum"] == ["Revenue", "Operations"]
    assert "- Operations: Housekeeping and cleaning" in body["system"]
    assert found["Weekly revenue"].category == "Revenue" and not found["Weekly revenue"].is_sensitive
    # Claude didn't call the housekeeping meeting sensitive; its category is.
    assert found["Housekeeping sync"].category == "Operations" and found["Housekeeping sync"].is_sensitive


def test_claude_follows_davids_own_instructions(db, mocks, connected, sign_in, slack_bot, monkeypatch):
    sent: dict[str, str] = {}
    real = llm.complete

    def spy(system, messages, schema, **kw):
        sent[kw.get("kind", "extract")] = system
        return real(system, messages, schema, **kw)

    monkeypatch.setattr(llm, "complete", spy)
    client = sign_in("david@liddellpropertyinvestments.com")
    resp = client.put(
        "/api/admin/settings",
        json={"extract_instructions": "Linen orders are always Russell's.", "email_instructions": "  "},
    )
    assert resp.json()["extract_instructions"] == "Linen orders are always Russell's."
    assert client.put("/api/admin/settings", json={"email_instructions": "x" * 4001}).status_code == 422
    with db() as s:
        run.run(s)
    assert "## David's own instructions" in sent["extract"]
    assert "<instructions>\nLinen orders are always Russell's.\n</instructions>" in sent["extract"]
    assert "own instructions" not in sent["email"]  # blank: the prompt is unchanged
