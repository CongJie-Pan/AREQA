from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

import httpx

_jwks_cache = None

def get_jwks():
    global _jwks_cache
    if not _jwks_cache:
        jwks_url = f"{os.environ.get('NEXT_PUBLIC_SUPABASE_URL')}/auth/v1/.well-known/jwks.json"
        response = httpx.get(jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache

def verify_supabase_jwt(token: str, secret: str) -> str:
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg")
        
        key = secret if alg and alg.startswith("HS") else get_jwks()
        
        payload = jwt.decode(
            token, 
            key, 
            algorithms=["HS256", "HS384", "HS512", "RS256", "ES256"], 
            options={"verify_aud": False}
        )
        aud = payload.get("aud")
        aud_set = set(aud) if isinstance(aud, list) else {aud} if aud else set()
        if "authenticated" not in aud_set:
            raise JWTError("Invalid audience")
        sub = payload.get("sub")
        if not sub:
            logger.warning("JWT validation failed: No sub in token")
            raise JWTError("No sub in token")
        logger.info(f"JWT successfully verified for user_id: {sub}")
        return sub
    except JWTError as e:
        try:
            unverified_header = jwt.get_unverified_header(token)
            logger.error(f"JWT verification error: {e}. Token header: {unverified_header}")
        except Exception:
            logger.error(f"JWT verification error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid authentication credentials: {e}")


async def verify_supabase_user(token: str, expected_user_id: str) -> None:
    """Confirm the JWT subject still exists in Supabase Auth.

    Local JWT verification alone cannot detect an account deleted from
    ``auth.users`` until the token expires. The Auth user endpoint provides
    the server-side revocation check for protected backend requests.
    """
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        logger.error("Supabase Auth verification configuration is missing")
        raise HTTPException(status_code=500, detail="Internal Server Error: Auth configuration missing")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": anon_key,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.RequestError as error:
        logger.error("Supabase Auth verification request failed: %s", error)
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from error

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    try:
        user_id = response.json().get("id")
    except (TypeError, ValueError):
        user_id = None

    if user_id != expected_user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    token = credentials.credentials
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        logger.error("JWT_SECRET environment variable is missing")
        raise HTTPException(status_code=500, detail="Internal Server Error: Auth configuration missing")
    user_id = verify_supabase_jwt(token, secret)
    await verify_supabase_user(token, user_id)
    return user_id


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(optional_security),
) -> str | None:
    """Return the authenticated user when present, without requiring a token.

    A supplied but invalid token still fails closed with the same 401 response as
    the required-auth dependency. Only a genuinely missing token is anonymous.
    """
    if credentials is None:
        return None

    secret = os.environ.get("JWT_SECRET")
    if not secret:
        logger.error("JWT_SECRET environment variable is missing")
        raise HTTPException(status_code=500, detail="Internal Server Error: Auth configuration missing")

    user_id = verify_supabase_jwt(credentials.credentials, secret)
    await verify_supabase_user(credentials.credentials, user_id)
    return user_id
