import base64
import time
import uuid
from typing import Annotated, Any

import httpx
import jwt
import pytest
import respx
from fastapi import Depends, FastAPI

from feedback_hub.auth import (
    AuthenticatedUser,
    InvalidTokenError,
    SupabaseJwtVerifier,
    get_current_user,
)
from tests.auth_helpers import ISSUER, SUPABASE_URL, TokenFactory

JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"


def make_verifier(http: httpx.AsyncClient, **kwargs: object) -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        http,
        supabase_url=SUPABASE_URL + "/",
        audience="authenticated",
        cache_seconds=600,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def tokens() -> TokenFactory:
    return TokenFactory()


@respx.mock
async def test_valid_token_is_verified_with_fetched_jwks(tokens: TokenFactory) -> None:
    route = respx.get(JWKS_URL).respond(200, json=tokens.jwks)
    user_id = uuid.uuid4()

    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http)
        user = await verifier.verify(tokens.token(user_id))
        await verifier.verify(tokens.token(user_id))

    assert user.id == user_id
    assert user.email == "pm@example.com"
    assert verifier.issuer == ISSUER
    assert route.call_count == 1


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 3600},
        {"aud": "anon"},
        {"iss": "https://evil.example/auth/v1"},
        {"role": "anon"},
        {"role": "service_role"},
        {"sub": "not-a-uuid"},
        {"sub": None},
    ],
)
async def test_rejects_bad_claims(tokens: TokenFactory, claims: dict[str, Any]) -> None:
    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        with pytest.raises(InvalidTokenError):
            await verifier.verify(tokens.token(**claims))


async def test_rejects_token_signed_by_another_key(tokens: TokenFactory) -> None:
    attacker = TokenFactory(kid=tokens.kid)
    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        with pytest.raises(InvalidTokenError, match="verification failed"):
            await verifier.verify(attacker.token())


async def test_rejects_symmetric_and_unsigned_tokens(tokens: TokenFactory) -> None:
    hs256 = jwt.encode(
        {"sub": str(uuid.uuid4())}, "k" * 32, algorithm="HS256", headers={"kid": "test-key-1"}
    )
    header = base64.urlsafe_b64encode(b'{"alg":"none","kid":"test-key-1"}').rstrip(b"=")
    body = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=")
    unsigned = f"{header.decode()}.{body.decode()}."

    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        for token in (hs256, unsigned, "not.a.jwt"):
            with pytest.raises(InvalidTokenError):
                await verifier.verify(token)


@respx.mock
async def test_unknown_kid_triggers_refresh_for_key_rotation(tokens: TokenFactory) -> None:
    rotated = TokenFactory(kid="rotated-key")
    respx.get(JWKS_URL).respond(200, json={"keys": [tokens.jwk, rotated.jwk]})

    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http)
        verifier._fetched_at = float("-inf")
        user = await verifier.verify(rotated.token())

    assert isinstance(user, AuthenticatedUser)


@respx.mock
async def test_jwks_outage_without_cached_keys_fails_closed(tokens: TokenFactory) -> None:
    respx.get(JWKS_URL).respond(503)

    async with httpx.AsyncClient() as http:
        with pytest.raises(InvalidTokenError, match="unavailable"):
            await make_verifier(http).verify(tokens.token())


@respx.mock
async def test_jwks_outage_keeps_serving_cached_keys(tokens: TokenFactory) -> None:
    respx.get(JWKS_URL).respond(503)

    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        verifier._fetched_at = float("-inf")
        user = await verifier.verify(tokens.token())

    assert user.email == "pm@example.com"


async def test_unknown_kid_is_rejected(tokens: TokenFactory) -> None:
    async with httpx.AsyncClient() as http:
        verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        with pytest.raises(InvalidTokenError, match="Unknown signing key"):
            await verifier.verify(TokenFactory(kid="other").token())


async def test_current_user_dependency(tokens: TokenFactory) -> None:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> str:
        return str(user.id)

    user_id = uuid.uuid4()
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient() as http,
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        unconfigured = await client.get("/whoami")
        app.state.jwt_verifier = make_verifier(http, static_keys={tokens.kid: tokens.pyjwk()})
        missing = await client.get("/whoami")
        invalid = await client.get("/whoami", headers={"Authorization": "Bearer nope"})
        ok = await client.get(
            "/whoami", headers={"Authorization": f"Bearer {tokens.token(user_id)}"}
        )

    assert unconfigured.status_code == 503
    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert ok.json() == str(user_id)
