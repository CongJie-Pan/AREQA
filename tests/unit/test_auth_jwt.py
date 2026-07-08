import pytest
import sys
from unittest.mock import patch, MagicMock

from backend.auth import verify_supabase_jwt, JWTError

@patch("backend.auth.jwt")
def test_auth_jwt_array_aud(mock_jwt):
    secret = "super_secret_key"
    mock_jwt.decode.return_value = {
        "sub": "user_123",
        "aud": ["authenticated", "other_aud"],
        "role": "authenticated"
    }
    
    extracted_sub = verify_supabase_jwt("dummy_token", secret)
    
    # Assert jwt.decode was called with verify_aud: False
    mock_jwt.decode.assert_called_with("dummy_token", secret, algorithms=["HS256", "HS384", "HS512", "RS256", "ES256"], options={"verify_aud": False})
    assert extracted_sub == "user_123"

@patch("backend.auth.jwt")
def test_auth_jwt_string_aud(mock_jwt):
    secret = "super_secret_key"
    mock_jwt.decode.return_value = {
        "sub": "user_123",
        "aud": "authenticated",
        "role": "authenticated"
    }
    
    extracted_sub = verify_supabase_jwt("dummy_token", secret)
    assert extracted_sub == "user_123"

@patch("backend.auth.jwt")
def test_auth_jwt_invalid_aud(mock_jwt):
    secret = "super_secret_key"
    mock_jwt.decode.return_value = {
        "sub": "user_123",
        "aud": ["unauthenticated"],
        "role": "unauthenticated"
    }
    
    with pytest.raises(Exception):
        verify_supabase_jwt("dummy_token", secret)

@patch("backend.auth.jwt")
@patch("backend.auth.httpx.get")
@patch.dict("os.environ", {"NEXT_PUBLIC_SUPABASE_URL": "http://mock-supabase.url"})
def test_auth_jwt_jwks(mock_get, mock_jwt):
    secret = "dummy_secret"
    # Mock header to trigger JWKS fetching
    mock_jwt.get_unverified_header.return_value = {"alg": "ES256"}
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"keys": [{"kid": "test"}]}
    mock_get.return_value = mock_response

    mock_jwt.decode.return_value = {
        "sub": "user_123",
        "aud": "authenticated",
        "role": "authenticated"
    }

    # Reset cache to ensure fetch
    import backend.auth
    backend.auth._jwks_cache = None

    extracted_sub = verify_supabase_jwt("dummy_token", secret)
    
    mock_get.assert_called_with("http://mock-supabase.url/auth/v1/.well-known/jwks.json")
    mock_jwt.decode.assert_called_with("dummy_token", {"keys": [{"kid": "test"}]}, algorithms=["HS256", "HS384", "HS512", "RS256", "ES256"], options={"verify_aud": False})
    assert extracted_sub == "user_123"
