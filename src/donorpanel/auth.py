import hashlib
import re
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .config import config

ANON_PREFIX = "anon-"
_jwks: PyJWKClient | None = None


@dataclass(frozen=True)
class Actor:
    actor_id: str
    name: str
    email: str | None
    authenticated: bool

    @property
    def prefix(self) -> str:
        return f"actors/{self.actor_id}/"


def configured() -> bool:
    return bool(config.cognito_pool_id and config.cognito_client_id)


def issuer() -> str:
    return (f"https://cognito-idp.{config.aws_region}.amazonaws.com/"
            f"{config.cognito_pool_id}")


def jwks() -> PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = PyJWKClient(f"{issuer()}/.well-known/jwks.json", cache_keys=True)
    return _jwks


def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", value)[:64]


def anonymous(seed: str | None) -> Actor:
    # A stable pseudonymous actor so an unauthenticated visitor still gets an
    # isolated sandbox. Without this, every browser shares one namespace and the
    # verifier starts rejecting requests as duplicates of someone else's.
    digest = hashlib.sha256((seed or "guest").encode()).hexdigest()[:16]
    return Actor(actor_id=f"{ANON_PREFIX}{digest}", name="Guest",
                 email=None, authenticated=False)


def verify(token: str) -> Actor:
    claims = jwt.decode(
        token,
        jwks().get_signing_key_from_jwt(token).key,
        algorithms=["RS256"],
        issuer=issuer(),
        options={"verify_aud": False, "require": ["exp", "sub", "iss"]},
    )
    # Cognito puts the app client in `client_id` on access tokens and `aud` on
    # id tokens, so accept either rather than forcing one token type on callers.
    audience = claims.get("client_id") or claims.get("aud")
    if audience != config.cognito_client_id:
        raise jwt.InvalidAudienceError("token was not issued for this app client")

    return Actor(
        actor_id=safe(claims["sub"]),
        name=claims.get("name") or claims.get("cognito:username") or "Coordinator",
        email=claims.get("email"),
        authenticated=True,
    )


def actor_from(authorization: str | None, fallback_seed: str | None = None) -> Actor:
    if configured() and authorization and authorization.lower().startswith("bearer "):
        return verify(authorization.split(" ", 1)[1].strip())
    return anonymous(fallback_seed)
