import time
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient

from web.server import create_app, verify_cloudflare_access_jwt

class MockJWKSClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        class MockKey:
            def __init__(self, key):
                self.key = key
        return MockKey(self.public_key)


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem


def test_hs256_token_rejected_by_verify_cf_jwt(rsa_keypair):
    """Round 4 Item 3: HS256 token must be strictly rejected (only RS256 allowed)."""
    token = jwt.encode(
        {"email": "user@example.com", "aud": "aud1", "iss": "https://team.cloudflareaccess.com", "exp": time.time() + 300},
        "shared-secret-key",
        algorithm="HS256"
    )
    _, pub_pem = rsa_keypair
    mock_client = MockJWKSClient(pub_pem)

    with pytest.raises(HTTPException) as exc_info:
        verify_cloudflare_access_jwt(
            jwt_assertion=token,
            team_domain="team",
            audience="aud1",
            jwks_client=mock_client
        )
    assert exc_info.value.status_code == 401
    assert "RS256" in exc_info.value.detail or "unsupported" in exc_info.value.detail.lower()


def test_alg_none_token_rejected(rsa_keypair):
    """Round 4 Item 3: alg=none token must be strictly rejected."""
    token = jwt.encode(
        {"email": "user@example.com", "aud": "aud1", "iss": "https://team.cloudflareaccess.com", "exp": time.time() + 300},
        key="",
        algorithm="none"
    )
    _, pub_pem = rsa_keypair
    mock_client = MockJWKSClient(pub_pem)

    with pytest.raises(HTTPException) as exc_info:
        verify_cloudflare_access_jwt(
            jwt_assertion=token,
            team_domain="team",
            audience="aud1",
            jwks_client=mock_client
        )
    assert exc_info.value.status_code == 401


def test_valid_rs256_token_accepted(rsa_keypair):
    """Round 4 Item 3: Valid RS256 token signed by RSA private key verified via JWKS is accepted."""
    priv_pem, pub_pem = rsa_keypair
    token = jwt.encode(
        {
            "email": "alice@company.com",
            "aud": "my-cf-aud",
            "iss": "https://company.cloudflareaccess.com",
            "exp": time.time() + 300
        },
        priv_pem,
        algorithm="RS256",
        headers={"kid": "cf-key-1"}
    )
    mock_client = MockJWKSClient(pub_pem)
    payload = verify_cloudflare_access_jwt(
        jwt_assertion=token,
        team_domain="company",
        audience="my-cf-aud",
        jwks_client=mock_client
    )
    assert payload["email"] == "alice@company.com"
    assert payload["aud"] == "my-cf-aud"


def test_expired_rs256_token_rejected(rsa_keypair):
    """Round 4 Item 3: Expired RS256 token must return 401."""
    priv_pem, pub_pem = rsa_keypair
    token = jwt.encode(
        {
            "email": "alice@company.com",
            "aud": "my-cf-aud",
            "iss": "https://company.cloudflareaccess.com",
            "exp": time.time() - 60
        },
        priv_pem,
        algorithm="RS256",
        headers={"kid": "cf-key-1"}
    )
    mock_client = MockJWKSClient(pub_pem)
    with pytest.raises(HTTPException) as exc_info:
        verify_cloudflare_access_jwt(
            jwt_assertion=token,
            team_domain="company",
            audience="my-cf-aud",
            jwks_client=mock_client
        )
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()
