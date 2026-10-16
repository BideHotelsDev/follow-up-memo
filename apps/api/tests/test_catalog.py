"""Properties, systems, the owner and the targets come from the database, so Bide edits them in Admin."""

import json

from sqlalchemy import select

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
