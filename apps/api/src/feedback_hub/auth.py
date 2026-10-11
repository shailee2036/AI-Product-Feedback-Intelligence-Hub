import time
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})
_MIN_REFRESH_INTERVAL_SECONDS = 30.0


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    email: str | None
    claims: dict[str, Any]


class SupabaseJwtVerifier:
    """Verify Supabase access tokens against the project's published signing keys (JWKS)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        supabase_url: str,
        audience: str,
        cache_seconds: float,
        static_keys: dict[str, jwt.PyJWK] | None = None,
    ) -> None:
        base = supabase_url.rstrip("/")
        self._http = http
        self._jwks_url = f"{base}/auth/v1/.well-known/jwks.json"
        self._issuer = f"{base}/auth/v1"
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._keys: dict[str, jwt.PyJWK] = dict(static_keys or {})
        self._fetched_at = time.monotonic() if static_keys else float("-inf")

    @property
    def issuer(self) -> str:
        return self._issuer

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Malformed token.") from exc

        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in ALLOWED_ALGORITHMS or not isinstance(kid, str):
            raise InvalidTokenError("Unsupported token signature.")

        key = await self._key_for(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Token verification failed.") from exc

        if claims.get("role") != "authenticated":
            raise InvalidTokenError("Token is not for an authenticated user.")
        try:
            user_id = UUID(str(claims["sub"]))
        except ValueError as exc:
            raise InvalidTokenError("Token subject is not a user id.") from exc
        email = claims.get("email")
        return AuthenticatedUser(
            id=user_id, email=email if isinstance(email, str) else None, claims=claims
        )

    async def _key_for(self, kid: str) -> jwt.PyJWK:
        now = time.monotonic()
        expired = now - self._fetched_at > self._cache_seconds
        unknown_kid_may_refresh = (
            kid not in self._keys and now - self._fetched_at > _MIN_REFRESH_INTERVAL_SECONDS
        )
        if expired or unknown_kid_may_refresh:
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            raise InvalidTokenError("Unknown signing key.")
        return key

    async def _refresh(self) -> None:
        try:
            response = await self._http.get(self._jwks_url)
            response.raise_for_status()
            keys = jwt.PyJWKSet.from_dict(response.json()).keys
        except (httpx.HTTPError, jwt.PyJWTError, ValueError) as exc:
            if self._keys:
                return
            raise InvalidTokenError("Signing keys are unavailable.") from exc
        self._keys = {key.key_id: key for key in keys if key.key_id}
        self._fetched_at = time.monotonic()


_bearer = HTTPBearer(auto_error=False)


def get_jwt_verifier(request: Request) -> SupabaseJwtVerifier:
    verifier: SupabaseJwtVerifier | None = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is not configured."
        )
    return verifier


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[SupabaseJwtVerifier, Depends(get_jwt_verifier)],
) -> AuthenticatedUser:
    challenge = {"WWW-Authenticate": "Bearer"}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.", challenge)
    try:
        return await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc), challenge) from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
