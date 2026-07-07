from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os

security = HTTPBearer()

def verify_supabase_jwt(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(
            token, 
            secret, 
            algorithms=["HS256"], 
            options={"verify_aud": False}
        )
        aud = payload.get("aud")
        aud_set = set(aud) if isinstance(aud, list) else {aud} if aud else set()
        if "authenticated" not in aud_set:
            raise JWTError("Invalid audience")
        sub = payload.get("sub")
        if not sub:
            raise JWTError("No sub in token")
        return sub
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication credentials: {e}")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    token = credentials.credentials
    secret = os.environ.get("JWT_SECRET", "dummy_secret")
    user_id = verify_supabase_jwt(token, secret)
    return user_id
