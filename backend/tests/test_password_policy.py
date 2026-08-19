"""The password policy (NIST SP 800-63B / OWASP ASVS V2.1).

Three kinds of test, and the middle one is the point of the module.

The first enumerates the rules: a short password is short, a repeated block is
repeated. Necessary, and the easy half.

The second asserts that **decoration does not help** — that ``P@ssw0rd2026!``
and ``password`` are the same password here, because they are the same password
to the rule engine that will be pointed at this application. A blocklist that
only catches the undecorated spelling is a blocklist that catches nothing, so
these are the tests that would notice the canonicalizer regressing into
uselessness while every rule test above stayed green.

The third asserts what the policy must NOT do: no character-class requirement in
the default configuration, no gate on the advisory score, and no opinion about
passwords that already exist. Those are properties a well-meaning change could
quietly reverse, and reversing them is how a policy that follows the standard
turns into one that fights its users.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services import password_policy as policy
from app.services.password_policy import (
    PasswordContext,
    PasswordPolicyViolation,
    enforce,
    evaluate,
)


@pytest.fixture
def settings() -> Settings:
    """Defaults, constructed explicitly so a stray .env cannot steer a test."""

    return Settings(
        jwt_secret_key="test-key",
        password_min_length=12,
        password_max_length=128,
        password_blocklist_enabled=True,
        password_require_character_classes=False,
    )


def ok(password: str, settings: Settings, context: PasswordContext | None = None) -> bool:
    return evaluate(password, context=context, settings=settings).ok


def rules(password: str, settings: Settings, context: PasswordContext | None = None) -> tuple:
    return evaluate(password, context=context, settings=settings).rules


# --------------------------------------------------------------------------
# Length
# --------------------------------------------------------------------------


def test_a_password_shorter_than_the_minimum_is_rejected(settings):
    assert rules("short", settings) == (policy.TOO_SHORT,)
    assert rules("elevenchars", settings) == (policy.TOO_SHORT,)


def test_the_minimum_is_inclusive(settings):
    assert len("twelvechars!") == 12
    assert ok("twelvechars!", settings)


def test_length_is_reported_alone(settings):
    """A four-character password is also predictable and also low-variety.

    Saying all three is three true statements and one useful one, so the length
    failure short-circuits. This is a UX property, and it is asserted because
    the obvious refactor — run every rule, collect every failure — silently
    undoes it.
    """

    assert rules("aaa", settings) == (policy.TOO_SHORT,)


def test_a_password_longer_than_the_maximum_is_rejected(settings):
    assert rules("a" * 129, settings) == (policy.TOO_LONG,)


def test_length_counts_code_points_not_bytes(settings):
    """Twelve Turkish characters are twelve characters, not twenty-odd bytes."""

    password = "ĞÜŞİÖÇğüşıöç"
    assert len(password) == 12
    assert len(password.encode("utf-8")) > 12
    assert policy.TOO_SHORT not in rules(password, settings)


def test_settings_refuse_a_minimum_above_the_maximum():
    """Caught at boot, not at the first signup of the day."""

    with pytest.raises(ValueError):
        Settings(jwt_secret_key="k", password_min_length=100, password_max_length=64)


# --------------------------------------------------------------------------
# The blocklist, and the decoration that does not save you
# --------------------------------------------------------------------------


def test_the_blocklist_loaded(settings):
    """A missing data file degrades to an empty set, which would make every
    test below pass vacuously."""

    assert len(policy.load_blocklist()) > 100


@pytest.mark.parametrize(
    "password",
    [
        "password123456",  # a common word plus the most common suffix there is
        "P@ssw0rd2026!",  # leet substitution, a year, and a bang
        "l3tm31n!!2026",  # substitutions in the middle rather than the ends
        "iloveyou12345",
        "qwertyuiop12",
        "Galatasaray1905!",  # the Turkish half of the list
        "sifre123456789",
        "m-o-n-k-e-y-2026",  # separators removed before lookup
    ],
)
def test_common_passwords_are_rejected_however_they_are_dressed_up(password, settings):
    assert policy.COMMON in rules(password, settings)


def test_turkish_spelling_reaches_the_turkish_blocklist(settings):
    """'şifre' and 'sifre' are one password to anyone guessing.

    Without the ASCII fold the Turkish section would only ever match users who
    typed on an English keyboard — matching the easy case and missing the one it
    was written for.
    """

    assert policy.COMMON in rules("Şifre1234!!!", settings)


def test_a_long_passphrase_of_ordinary_words_is_accepted(settings):
    """The policy wants length, so length has to actually be enough."""

    assert ok("korkuluksaat", settings)
    assert ok("bulut-kahve-masa", settings)
    assert ok("correct-horse-battery", settings)


def test_the_blocklist_matches_whole_forms_not_substrings(settings):
    """Substring matching would reject 'abrandnewpassword' for containing
    'password', and with it most of the passphrases the policy is trying to
    encourage."""

    assert ok("a-brand-new-password", settings)


def test_the_blocklist_can_be_switched_off(settings):
    relaxed = settings.model_copy(update={"password_blocklist_enabled": False})
    assert policy.COMMON in rules("password123456", settings)
    assert policy.COMMON not in rules("password123456", relaxed)


# --------------------------------------------------------------------------
# Context — your own address is not a secret
# --------------------------------------------------------------------------


def test_a_password_built_from_the_email_is_rejected(settings):
    context = PasswordContext(email="ahmet@yankiapp.com")
    assert policy.CONTEXT in rules("ahmetgizlisifre", settings, context)
    assert policy.CONTEXT in rules("yankiapp-parola", settings, context)


def test_a_password_built_from_the_organization_name_is_rejected(settings):
    context = PasswordContext(email="a@b.com", organization_name="Şirket Ltd")
    assert policy.CONTEXT in rules("sirket-parolasi", settings, context)


def test_the_product_name_is_always_context(settings):
    """No caller has to remember to pass it."""

    assert policy.CONTEXT in rules("yanki-platform-1", settings)


def test_short_local_parts_are_not_treated_as_context(settings):
    """Banning 'ali' would tell that user their own name is forbidden, and it
    appears inside far too many legitimate passwords to be evidence."""

    context = PasswordContext(email="ali@example.com")
    assert ok("aliminkorkulugu", settings, context)


def test_context_is_optional(settings):
    assert ok("bulutkahvemasa", settings, None)


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------


@pytest.mark.parametrize("password", ["abcabcabcabc", "aaaaaaaaaaaa", "ababababababab"])
def test_a_repeated_block_is_rejected(password, settings):
    assert policy.REPETITIVE in rules(password, settings)


def test_a_doubled_word_is_not_treated_as_a_repeated_block(settings):
    """The rule takes blocks of four or less. Doubling a longer word is weaker
    than not doing so, but it is not the same class of thing, and widening the
    rule to catch it starts rejecting ordinary passwords."""

    assert ok("hunter2hunter2", settings)


@pytest.mark.parametrize(
    "password",
    ["mysecret123456", "zzqwertyzz-ok", "alphabetabcdefg", "onmykeyboardpoiuytre"],
)
def test_long_runs_off_the_keyboard_or_alphabet_are_rejected(password, settings):
    assert policy.SEQUENTIAL in rules(password, settings)


def test_runs_are_caught_backwards_too(settings):
    assert policy.SEQUENTIAL in rules("secret654321x", settings)


def test_a_password_of_two_characters_is_low_variety(settings):
    assert policy.LOW_VARIETY in rules("abababababab", settings)


# --------------------------------------------------------------------------
# What the policy must NOT do
# --------------------------------------------------------------------------


def test_no_character_class_requirement_by_default(settings):
    """800-63B says a verifier SHALL NOT impose composition rules. An
    all-lowercase password of sufficient length is acceptable, and this test is
    what stops that being 'fixed'."""

    assert ok("korkuluksaat", settings)
    assert ok("bulutkahvemasa", settings)


def test_character_classes_can_be_required_for_a_compliance_regime(settings):
    strict = settings.model_copy(
        update={"password_require_character_classes": True, "password_min_character_classes": 3}
    )
    assert ok("korkuluksaat", settings)
    assert policy.CHARACTER_CLASSES in rules("korkuluksaat", strict)
    assert ok("Korkuluk-Saat1", strict)


def test_the_score_is_advisory_and_gates_nothing(settings):
    """A score threshold high enough to matter is a composition rule in
    disguise: at twelve characters only mixed case plus digits clears 'strong'.
    So a low score must still be an accepted password."""

    result = evaluate("korkuluksaat", settings=settings)
    assert result.ok
    assert result.score <= 2


def test_the_score_rewards_length_not_only_variety(settings):
    """The meter has to point at the thing the policy actually wants."""

    short_and_mixed = evaluate("Ab1!Cd2@Ef3#", settings=settings).score
    long_and_plain = evaluate("bulutkahvemasadeniz", settings=settings).score
    assert long_and_plain >= short_and_mixed


def test_a_failing_password_scores_zero(settings):
    assert evaluate("short", settings=settings).score == 0


# --------------------------------------------------------------------------
# enforce()
# --------------------------------------------------------------------------


def test_enforce_is_silent_on_an_acceptable_password(settings):
    assert enforce("bulut-kahve-masa", settings=settings) is None


def test_enforce_raises_with_every_broken_rule(settings):
    with pytest.raises(PasswordPolicyViolation) as caught:
        enforce("password123456", settings=settings)

    assert policy.COMMON in caught.value.rules
    assert policy.SEQUENTIAL in caught.value.rules
    # Every rule gets a sentence, so nobody discovers the next one on the next
    # submit.
    assert all(message in caught.value.detail for message in _messages(caught.value))


def test_the_violation_never_carries_the_password(settings):
    """It becomes an HTTP body and, if anything ever logs it, an audit row."""

    secret = "password123456"
    with pytest.raises(PasswordPolicyViolation) as caught:
        enforce(secret, settings=settings)

    assert secret not in caught.value.detail
    assert secret not in str(caught.value)


def _messages(violation: PasswordPolicyViolation) -> list[str]:
    return [failure.message for failure in violation.failures]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def test_normalize_is_nfkc_and_leaves_ascii_alone():
    """Identity on ASCII is why introducing it does not invalidate a single
    hash already in the database."""

    assert policy.normalize("correct-horse") == "correct-horse"


def test_normalize_folds_the_compatibility_forms_that_a_keyboard_may_produce():
    composed = "šifre"  # š, precomposed
    decomposed = "šifre"  # s + combining caron
    assert policy.normalize(composed) == policy.normalize(decomposed)
