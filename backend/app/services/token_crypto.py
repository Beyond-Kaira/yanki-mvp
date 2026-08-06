"""Symmetric encryption for third-party secrets we must be able to read back.

Everything else this codebase stores about a credential is *hashed*: passwords
(argon2), refresh-token jtis (keyed HMAC), invitation tokens (SHA-256). Hashing
works there because nothing ever needs the original value again — the check is
always "does this match", never "what was it".

A Google refresh token breaks that. Calling Search Console on a user's behalf
means presenting the token itself, so it has to survive the round trip, and a
one-way hash cannot store it. This module is the first reversible-secret
storage in the repo, and it is deliberately narrow: two functions, one key, no
key-derivation options for a caller to get wrong.

Three decisions worth stating:

**The key is not ``jwt_secret_key``.** Reusing it would tie two unrelated
rotation stories together — rotating the JWT secret to invalidate sessions
would silently make every stored Google connection undecryptable, and the
symptom would appear later, in a different feature, as "reconnect your
account". ``TOKEN_ENCRYPTION_KEY`` is its own setting for that reason.

**Every failure is the same failure.** A wrong key and a corrupted ciphertext
both raise :class:`SecretDecryptionError`. Fernet cannot distinguish them
either, and a caller that could would be a caller able to probe which of the
two it is holding.

**The key version travels with the ciphertext, not with the code.** Rows carry
``encryption_key_version`` so a future rotation can decrypt old rows with an old
key. This slice implements no rotation: it accepts exactly
:data:`ENCRYPTION_KEY_VERSION` and refuses anything else, which keeps an
un-rotatable row from being written under a version nobody can read.

No function here logs, and no plaintext or key material appears in any exception
message — the messages name settings and versions, never values.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

# The version stamped onto anything this module encrypts. Bump only alongside a
# real rotation implementation that can still read the versions below it.
ENCRYPTION_KEY_VERSION = 1


class SecretEncryptionConfigError(RuntimeError):
    """Raised when ``TOKEN_ENCRYPTION_KEY`` is missing or unusable."""


class SecretDecryptionError(ValueError):
    """Raised when stored ciphertext cannot be recovered.

    Covers a wrong key, a truncated or tampered value, and anything that does
    not decode as UTF-8 afterwards. Deliberately one exception for all three.
    """


def _fernet(settings: Settings) -> Fernet:
    """Build the cipher, failing closed when the key is absent or malformed."""

    key = settings.token_encryption_key.get_secret_value().strip()
    if not key:
        raise SecretEncryptionConfigError("TOKEN_ENCRYPTION_KEY is not configured")

    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        # The key itself is never quoted back — a malformed key in a log is
        # still a key in a log.
        raise SecretEncryptionConfigError(
            "TOKEN_ENCRYPTION_KEY must be a url-safe base64-encoded 32-byte key"
        ) from exc


def encrypt_secret(plaintext: str, *, settings: Settings) -> bytes:
    """Encrypt one secret for storage. Returns the ciphertext to persist.

    Fernet embeds a random IV, so encrypting the same plaintext twice yields
    different ciphertexts — a stored value is not a fingerprint of the token,
    and two rows holding the same token do not look alike.
    """

    if not plaintext:
        raise SecretEncryptionConfigError("refusing to encrypt an empty secret")

    return _fernet(settings).encrypt(plaintext.encode("utf-8"))


def decrypt_secret(
    ciphertext: bytes,
    *,
    settings: Settings,
    key_version: int = ENCRYPTION_KEY_VERSION,
) -> str:
    """Recover a stored secret, or raise :class:`SecretDecryptionError`."""

    if key_version != ENCRYPTION_KEY_VERSION:
        raise SecretDecryptionError(f"no key available for encryption_key_version {key_version}")

    try:
        return _fernet(settings).decrypt(ciphertext).decode("utf-8")
    except (InvalidToken, TypeError, UnicodeDecodeError) as exc:
        raise SecretDecryptionError("stored secret could not be decrypted") from exc


def generate_encryption_key() -> str:
    """A fresh key in the format ``TOKEN_ENCRYPTION_KEY`` expects.

    Exists so tests and the operator runbook have one definition of "valid key"
    rather than each inventing base64 by hand. It is never called by app code.
    """

    return Fernet.generate_key().decode("utf-8")
