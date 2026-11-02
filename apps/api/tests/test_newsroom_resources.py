from tests.test_workspaces import _workspace


def invite(owner, ws, client):
    response = owner.post(f"/api/v1/workspaces/{ws}/invitations")
    assert response.status_code == 201
    accepted = client.post(f"/api/v1/invitations/{response.json()['token']}/accept")
    assert accepted.status_code == 200


def test_contacts_figures_and_originals_are_workspace_scoped(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob)
    contact = {
        "name": "Port office",
        "role": "Navigation alerts",
        "website": "https://port.example",
        "phone": "+261 1234567",
    }
    assert alice.post(f"/api/v1/workspaces/{ws}/contacts", json=contact).status_code == 201
    assert bob.get(f"/api/v1/workspaces/{ws}/contacts").status_code == 404
    assert bob.get(f"/api/v1/workspaces/{other}/contacts").json() == []
    assert (
        alice.post(
            f"/api/v1/workspaces/{ws}/contacts", json={**contact, "website": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    original = {
        "title": "Hours",
        "issuer": "Port office",
        "text": "Le port est ouvert de huit heures à dix-huit heures.",
        "url": "https://port.example/notice",
    }
    assert alice.post(f"/api/v1/workspaces/{ws}/registry", json=original).status_code == 201
    assert bob.get(f"/api/v1/workspaces/{other}/registry").json() == []
    figure = {
        "label": "Traffic",
        "topic": "transport",
        "value": "25",
        "as_of": "2025",
        "source_name": "Port",
        "source_url": "https://port.example/stats",
    }
    assert alice.post(f"/api/v1/workspaces/{ws}/figures", json=figure).status_code == 201
    assert (
        alice.post(f"/api/v1/workspaces/{ws}/figures", json={**figure, "as_of": "2999"}).status_code
        == 422
    )


def test_publication_needs_a_verdict_and_keeps_signed_content(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    invite(alice, ws, bob)
    base = f"/api/v1/workspaces/{ws}"
    item = alice.post(base + "/items", json={"title": "Port hours"}).json()
    path = base + "/items/" + item["id"]
    assert alice.patch(path, json={"status": "published"}).status_code == 409  # no verdict
    assert alice.patch(path, json={"data": {"signed_by": "bob"}}).status_code == 422
    signed = alice.post(
        path + "/sign",
        json={
            "verdict": "true",
            "reason": "The dated notice states opening hours.",
            "publish": True,
        },
    )
    assert signed.status_code == 200 and signed.json()["status"] == "published"
    # Published content cannot be silently replaced while retaining the old signature.
    assert alice.patch(path, json={"title": "Entirely different assertion"}).status_code == 409
