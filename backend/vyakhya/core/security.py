"""Encryption of provider API keys at rest.

Provider secrets are encrypted with AES-256-GCM (authenticated encryption). The
symmetric key is derived from the env-provided master key (`VYAKHYA_ENCRYPTION_KEY`)
plus a per-install random salt (persisted in the DB) via scrypt. Only ciphertext
is ever stored; plaintext keys never hit the DB or the browser.

Threat model (see docs/architecture.md §4): protects DB dumps/backups. An
attacker needs BOTH the database AND `.env` to recover keys.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


def _derive_key(master_key: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=_KEY_BYTES, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(master_key.encode("utf-8"))


class Encryptor:
    """AES-256-GCM encrypt/decrypt with an env-master-key + per-install salt."""

    def __init__(self, master_key: str, salt: bytes) -> None:
        self._aes = AESGCM(_derive_key(master_key, salt))

    def encrypt(self, plaintext: str) -> bytes:
        """Return `nonce || ciphertext` (safe to store as bytea)."""
        nonce = os.urandom(_NONCE_BYTES)
        ct = self._aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ct

    def decrypt(self, blob: bytes) -> str:
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return self._aes.decrypt(nonce, ct, None).decode("utf-8")


def new_salt() -> bytes:
    return os.urandom(16)


def mask_secret(secret: str) -> str:
    """Produce a UI-safe masked form, e.g. `sk-abcd…wxyz`."""
    s = secret.strip()
    if not s:
        return "—"
    if len(s) <= 8:
        return f"{s[0]}…{s[-1]}"
    return f"{s[:4]}…{s[-4:]}"
