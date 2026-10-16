def test_admin_only(sign_in):
    client = sign_in("sam@bidehotels.com")
    assert client.get("/api/admin/people").status_code == 403


def test_people(sign_in):
    client = sign_in("kyle@bidehotels.com")
    resp = client.post("/api/admin/people", json={"email": " New@BideHotels.com ", "name": "Nia"})
    assert resp.status_code == 201 and resp.json()["email"] == "new@bidehotels.com"
    assert client.post("/api/admin/people", json={"email": "new@bidehotels.com", "name": "Nia"}).json()["code"] == (
        "email_taken"
    )
    people = {p["name"]: p for p in client.get("/api/admin/people").json()}
    kyle = people["Kyle"]
    resp = client.put(f"/api/admin/people/{kyle['id']}", json={**kyle, "role": "member"})
    assert resp.json()["code"] == "own_access"
    russ = people["Russell"]
    resp = client.put(f"/api/admin/people/{russ['id']}", json={**russ, "ownership_areas": ["Operto"]})
    assert resp.json()["ownership_areas"] == ["Operto"]


def test_settings(sign_in):
    client = sign_in("kyle@bidehotels.com")
    assert client.get("/api/admin/settings").json()["slack_mode"] == "approve"
    resp = client.put("/api/admin/settings", json={"email_signature": "Cheers,\nD"})
    assert resp.json()["email_signature"] == "Cheers,\nD"
    assert client.put("/api/admin/settings", json={"poll_interval_minutes": 1}).status_code == 422


def test_channels_and_skip_rules(sign_in):
    client = sign_in("kyle@bidehotels.com")
    resp = client.put("/api/admin/channels", json=[{"topic": "revenue", "slack_channel_id": "C1"}])
    assert len(resp.json()) == 1
    assert client.put("/api/admin/channels", json=[{"slack_channel_id": "C1"}]).status_code == 422
    rules = [{"type": "title_keyword", "value": "1:1"}, {"type": "title_keyword", "value": "1:1 "}]
    assert len(client.put("/api/admin/skip-rules", json=rules).json()) == 1
