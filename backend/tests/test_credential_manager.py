"""N1 凭据管理：AES-256-GCM 加密、脱敏、常量时间比较。"""
import pytest

from app.services import credential_manager
from app.core.config import settings


@pytest.fixture()
def with_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "test-secret-key-1234567890")
    yield


def test_encrypt_decrypt_roundtrip(with_secret_key):
    blob = credential_manager.encrypt_secret("SuperSecretAuthKey123")
    assert blob
    assert "SuperSecretAuthKey123" not in blob
    assert credential_manager.decrypt_secret(blob) == "SuperSecretAuthKey123"


def test_encrypt_produces_random_nonce(with_secret_key):
    a = credential_manager.encrypt_secret("same-value")
    b = credential_manager.encrypt_secret("same-value")
    assert a != b  # 随机 nonce


def test_decrypt_wrong_key_fails(with_secret_key):
    blob = credential_manager.encrypt_secret("value")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings, "secret_key", "different-key-1234567890")
    with pytest.raises(Exception):
        credential_manager.decrypt_secret(blob)
    monkeypatch.undo()


def test_missing_secret_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "")
    with pytest.raises(credential_manager.SecretMissingError):
        credential_manager.encrypt_secret("value")


def test_empty_secret_roundtrip_empty():
    assert credential_manager.encrypt_secret("") == ""
    assert credential_manager.decrypt_secret("") == ""


def test_secret_digest_not_plaintext(with_secret_key):
    digest = credential_manager.secret_digest("my-token-abc")
    assert "my-token-abc" not in digest
    assert len(digest) == 12


def test_redact_never_leaks():
    out = credential_manager.redact("SuperSecret")
    assert "SuperSecret" not in out


def test_constant_time_equals():
    assert credential_manager.constant_time_equals("abc", "abc")
    assert not credential_manager.constant_time_equals("abc", "abd")