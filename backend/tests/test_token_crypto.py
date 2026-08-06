"""Encryption for stored third-party secrets (Phase 9 / M3 foundation).

The properties worth pinning are the ones whose absence would be silent. A
round trip that works is easy to notice; a cipher that produces the same bytes
for the same input, or a decrypt that quietly returns garbage under the wrong
key, is not — and both would look fine in a demo.

No real key and no Google credential appears here: every key is generated in
the test itself.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.token_crypto import (
    ENCRYPTION_KEY_VERSION,
    SecretDecryptionError,
    SecretEncryptionConfigError,
    decrypt_secret,
    encrypt_secret,
    generate_encryption_key,
)

SECRET = "1//0gFAKE-refresh-token-value-for-tests"


def _settings(key: str | None = None) -> Settings:
    return Settings(token_encryption_key=key if key is not None else generate_encryption_key())


def test_round_trip_returns_the_original_secret():
    settings = _settings()

    ciphertext = encrypt_secret(SECRET, settings=settings)

    assert isinstance(ciphertext, bytes)
    assert decrypt_secret(ciphertext, settings=settings) == SECRET


def test_ciphertext_never_contains_the_plaintext():
    """The stored bytes must not be a thin wrapper around the token."""

    settings = _settings()

    ciphertext = encrypt_secret(SECRET, settings=settings)

    assert SECRET.encode("utf-8") not in ciphertext


def test_the_same_secret_encrypts_to_different_ciphertexts():
    """Fernet's random IV, asserted rather than assumed.

    Without it, two organizations storing the same token would hold identical
    rows — the column would leak "these are the same account" to anyone who can
    read the table, and would be searchable by known-token.
    """

    settings = _settings()

    first = encrypt_secret(SECRET, settings=settings)
    second = encrypt_secret(SECRET, settings=settings)

    assert first != second
    assert decrypt_secret(first, settings=settings) == SECRET
    assert decrypt_secret(second, settings=settings) == SECRET


def test_decrypting_with_the_wrong_key_raises_rather_than_returning_garbage():
    ciphertext = encrypt_secret(SECRET, settings=_settings())

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(ciphertext, settings=_settings())


def test_tampered_ciphertext_is_refused():
    settings = _settings()
    ciphertext = encrypt_secret(SECRET, settings=settings)

    tampered = ciphertext[:-4] + b"AAAA"

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(tampered, settings=settings)


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"not-base64-at-all", id="not-fernet"),
        pytest.param(b"gAAAAA", id="truncated"),
    ],
)
def test_corrupt_ciphertext_raises_the_domain_error(corrupt):
    """Never a raw cryptography exception: callers catch one type."""

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(corrupt, settings=_settings())


def test_an_unknown_key_version_fails_closed():
    """A row written by a future rotation must not be decrypted with today's key."""

    settings = _settings()
    ciphertext = encrypt_secret(SECRET, settings=settings)

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(ciphertext, settings=settings, key_version=ENCRYPTION_KEY_VERSION + 1)


def test_a_missing_key_fails_closed_instead_of_storing_plaintext():
    settings = _settings(key="")

    with pytest.raises(SecretEncryptionConfigError):
        encrypt_secret(SECRET, settings=settings)


def test_a_malformed_key_is_refused_without_quoting_it_back():
    settings = _settings(key="obviously-not-a-fernet-key")

    with pytest.raises(SecretEncryptionConfigError) as caught:
        encrypt_secret(SECRET, settings=settings)

    assert "obviously-not-a-fernet-key" not in str(caught.value)


def test_an_empty_secret_is_refused():
    """Encrypting "" would store a valid row that decrypts to no credential."""

    with pytest.raises(SecretEncryptionConfigError):
        encrypt_secret("", settings=_settings())


def test_generated_keys_are_usable_and_distinct():
    first, second = generate_encryption_key(), generate_encryption_key()

    assert first != second
    assert (
        decrypt_secret(encrypt_secret(SECRET, settings=_settings(first)), settings=_settings(first))
        == SECRET
    )
