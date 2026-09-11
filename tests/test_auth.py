from dataclasses import replace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from donorpanel import auth


def with_cognito(monkeypatch, pool="ap-southeast-2_test", client="client-abc"):
    # config is a frozen dataclass, so swap the whole object rather than a field.
    monkeypatch.setattr(auth, "config", replace(auth.config, cognito_pool_id=pool,
                                                cognito_client_id=client))


def fake_jwks(monkeypatch, key):
    monkeypatch.setattr(auth, "jwks", lambda: type(
        "K", (), {"get_signing_key_from_jwt": lambda self, t: type(
            "S", (), {"key": key.public_key()})()})())


def test_an_unauthenticated_visitor_still_gets_a_stable_actor():
    a = auth.anonymous("browser-session-1")
    b = auth.anonymous("browser-session-1")
    c = auth.anonymous("browser-session-2")
    assert a.actor_id == b.actor_id
    assert a.actor_id != c.actor_id
    assert a.authenticated is False


def test_actors_get_separate_storage_prefixes():
    a, b = auth.anonymous("one"), auth.anonymous("two")
    assert a.prefix.startswith("actors/") and a.prefix.endswith("/")
    assert a.prefix != b.prefix


def test_actor_ids_are_safe_for_object_keys():
    assert auth.safe("us-east-1:ab/cd ef") == "us-east-1-ab-cd-ef"
    assert len(auth.safe("x" * 200)) == 64


def test_no_cognito_configured_means_anonymous(monkeypatch):
    with_cognito(monkeypatch, pool=None)
    actor = auth.actor_from("Bearer whatever", fallback_seed="seed")
    assert actor.authenticated is False


def test_a_valid_token_yields_an_authenticated_actor(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with_cognito(monkeypatch)
    fake_jwks(monkeypatch, key)

    token = jwt.encode({"sub": "user-42", "iss": auth.issuer(),
                        "client_id": "client-abc", "email": "a@b.test",
                        "name": "Anita", "exp": 4102444800}, key, algorithm="RS256")
    actor = auth.actor_from(f"Bearer {token}")
    assert actor.authenticated is True
    assert actor.actor_id == "user-42"
    assert actor.name == "Anita"


def test_a_token_for_another_app_client_is_rejected(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with_cognito(monkeypatch)
    fake_jwks(monkeypatch, key)

    token = jwt.encode({"sub": "user-42", "iss": auth.issuer(),
                        "client_id": "someone-else", "exp": 4102444800},
                       key, algorithm="RS256")
    with pytest.raises(jwt.InvalidAudienceError):
        auth.verify(token)
