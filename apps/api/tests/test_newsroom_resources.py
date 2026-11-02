from datetime import UTC, datetime

from tests.test_workspaces import _workspace


def invite(owner, ws, client, role):
    response = owner.post(f"/api/v1/workspaces/{ws}/invitations", json={"role": role})
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


def test_double_signature_cannot_be_bypassed_and_requires_current_version(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    invite(alice, ws, bob, "editor")
    base = f"/api/v1/workspaces/{ws}"
    assert alice.patch(base, json={"settings": {"double_signature": True}}).status_code == 200
    item = alice.post(base + "/items", json={"title": "Port hours"}).json()
    path = base + "/items/" + item["id"]
    assert (
        alice.patch(path, json={"status": "published", "data": {"verdict": "true"}}).status_code
        == 409
    )
    assert alice.patch(path, json={"data": {"signed_by": "bob"}}).status_code == 422
    signed = alice.post(
        path + "/sign",
        json={
            "verdict": "true",
            "reason": "The dated notice states opening hours.",
            "publish": True,
        },
    )
    assert signed.status_code == 200 and signed.json()["status"] == "verified"
    assert alice.patch(path, json={"status": "published"}).status_code == 409
    assert alice.patch(path, json={"title": "Changed assertion"}).status_code == 200
    assert bob.patch(path, json={"status": "published"}).status_code == 409
    alice.post(
        path + "/sign",
        json={"verdict": "true", "reason": "The revised assertion matches the notice."},
    )
    assert bob.patch(path, json={"status": "published"}).status_code == 200
    # Published content cannot be silently replaced while retaining the old signature.
    assert bob.patch(path, json={"title": "Entirely different assertion"}).status_code == 409


def test_issuer_can_only_read_own_entries_and_veilleur_cannot_read_desk(as_user):
    owner, issuer, watcher = as_user("alice"), as_user("bob"), as_user("eve")
    ws = _workspace(owner)
    base = f"/api/v1/workspaces/{ws}"
    invite(owner, ws, issuer, "issuer")
    invite(owner, ws, watcher, "veilleur")
    original = {
        "title": "Notice",
        "issuer": "Office",
        "text": "Le port de Rio reste ouvert aujourd’hui.",
        "url": "https://example.org/original",
    }
    owner.post(base + "/registry", json=original)
    assert issuer.get(base + "/registry").json() == []
    assert issuer.post(base + "/registry", json=original).status_code == 201
    assert len(issuer.get(base + "/registry").json()) == 1
    for client in (issuer, watcher):
        assert client.get(base + "/items").status_code == 403
        assert client.post(base + "/crew", json={"text": "Un test"}).status_code == 403
    assert watcher.get(base + "/registry").status_code == 403
    assert (
        watcher.post(
            base + "/radio-clips",
            json={
                "station": "Radio",
                "heard_text": "Le port est fermé demain.",
                "recorded_at": datetime.now(UTC).isoformat(),
            },
        ).status_code
        == 201
    )
    assert len(watcher.get(base + "/radio-clips").json()) == 1
