def test_me_without_token_is_401(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_with_valid_token(client, make_token):
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 200
    assert r.json()["id"] == "user-1"


def test_expired_token_is_401(client, make_token):
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {make_token(exp_in=-10)}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_wrong_audience_is_401(client, make_token):
    token = make_token(aud="https://evil.example")
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
