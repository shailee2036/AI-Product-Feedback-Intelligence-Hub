import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


@dataclass
class TokenFactory:
    kid: str = "test-key-1"
    private_key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )

    @property
    def jwk(self) -> dict[str, Any]:
        public = ECAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "alg": "ES256", "use": "sig"}

    @property
    def jwks(self) -> dict[str, Any]:
        return {"keys": [self.jwk]}

    def pyjwk(self) -> jwt.PyJWK:
        return jwt.PyJWK(self.jwk)

    def token(
        self,
        user_id: uuid.UUID | None = None,
        *,
        headers: dict[str, Any] | None = None,
        **claims: Any,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": str(user_id or uuid.uuid4()),
            "aud": "authenticated",
            "iss": ISSUER,
            "role": "authenticated",
            "email": "pm@example.com",
            "iat": now,
            "exp": now + 3600,
        }
        payload.update(claims)
        payload = {key: value for key, value in payload.items() if value is not None}
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.kid, **(headers or {})},
        )
