"""Supabase asymmetric JWT verification with bounded, process-local JWKS caching."""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import httpx
import jwt
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Principal:
    id: str
    expires_at: float


def unauthorized():
    return HTTPException(401, "invalid_access_token", headers={"WWW-Authenticate": "Bearer"})


class JWTVerifier:
    def __init__(self, supabase_url: str, *, client=None):
        self.issuer = supabase_url.rstrip("/") + "/auth/v1"
        self.url = self.issuer + "/.well-known/jwks.json"
        self.client = client
        self.keys = {}
        self.fetched_at = float("-inf")
        self.attempted_at = float("-inf")
        self.lock = asyncio.Lock()

    async def _key(self, kid: str):
        now = time.monotonic()
        if kid in self.keys and now - self.fetched_at < 300:
            return self.keys[kid]
        async with self.lock:
            now = time.monotonic()
            # Prevent random kid values from causing one Auth request per token.
            if now - self.attempted_at >= 30:
                self.attempted_at = now
                try:
                    if self.client is None:
                        async with httpx.AsyncClient(timeout=5) as client:
                            response = await client.get(self.url)
                    else:
                        response = await self.client.get(self.url)
                    response.raise_for_status()
                    data = response.json()
                    self.keys = {k["kid"]: jwt.PyJWK.from_dict(k) for k in data["keys"]
                                 if k.get("alg") in ("ES256", "RS256") and k.get("use", "sig") == "sig"}
                    self.fetched_at = now
                except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError):
                    raise HTTPException(503, "authentication_unavailable") from None
            if now - self.fetched_at >= 300:
                raise HTTPException(503, "authentication_unavailable")
            if kid not in self.keys:
                raise unauthorized()
            return self.keys[kid]

    async def verify(self, token: str) -> Principal:
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise unauthorized()
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ("ES256", "RS256") or not isinstance(header.get("kid"), str):
                raise unauthorized()
            key = await self._key(header["kid"])
            if key.algorithm_name != header["alg"]:
                raise unauthorized()
            claims = jwt.decode(token, key.key, algorithms=[key.algorithm_name],
                                audience="authenticated", issuer=self.issuer,
                                options={"require": ["sub", "iss", "aud", "exp", "iat", "role"]})
            if claims["role"] != "authenticated":
                raise unauthorized()
            subject = str(UUID(claims["sub"]))
            return Principal(subject, float(claims["exp"]))
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
            raise unauthorized() from None


@lru_cache(maxsize=1)
def verifier():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(503, "authentication_not_configured")
    return JWTVerifier(url)


async def verify_access_token(token: str) -> Principal:
    return await verifier().verify(token)


async def current_user(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization:
        raise unauthorized()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    return await verify_access_token(token)
