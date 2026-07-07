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
    mock_jwt.decode.assert_called_with("dummy_token", secret, algorithms=["HS256"], options={"verify_aud": False})
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
