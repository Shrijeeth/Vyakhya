"""Unit tests for at-rest encryption of provider keys."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from vyakhya.core.security import Encryptor, mask_secret, new_salt


def test_encrypt_decrypt_roundtrip():
    enc = Encryptor("master-key-abc", new_salt())
    secret = "sk-ant-super-secret-1234567890"
    blob = enc.encrypt(secret)
    assert isinstance(blob, bytes)
    assert secret.encode() not in blob  # ciphertext, not plaintext
    assert enc.decrypt(blob) == secret


def test_nonce_makes_ciphertext_unique():
    enc = Encryptor("master-key-abc", new_salt())
    a = enc.encrypt("same")
    b = enc.encrypt("same")
    assert a != b  # random nonce per encryption
    assert enc.decrypt(a) == enc.decrypt(b) == "same"


def test_wrong_key_cannot_decrypt():
    salt = new_salt()
    blob = Encryptor("key-one", salt).encrypt("secret")
    with pytest.raises(InvalidTag):
        Encryptor("key-two", salt).decrypt(blob)


def test_wrong_salt_cannot_decrypt():
    blob = Encryptor("key", new_salt()).encrypt("secret")
    with pytest.raises(InvalidTag):
        Encryptor("key", new_salt()).decrypt(blob)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "—"),
        ("abcd", "a…d"),
        ("sk-1234567890abcd", "sk-1…abcd"),
    ],
)
def test_mask_secret(value, expected):
    assert mask_secret(value) == expected
