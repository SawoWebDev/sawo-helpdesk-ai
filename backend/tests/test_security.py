from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("supersecret")
    assert hashed != "supersecret"
    assert verify_password("supersecret", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_jwt_roundtrip():
    token = create_access_token(subject="alice", role="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_jwt_invalid_token_returns_none():
    assert decode_access_token("not-a-real-token") is None
