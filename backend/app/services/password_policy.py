"""What a NEW password must satisfy — and nothing about verifying an old one.

The standard this implements is NIST SP 800-63B, with OWASP ASVS V2.1 supplying
the stricter of the two length floors. Four decisions follow from it, and each
one is the opposite of what a password rule usually looks like.

**Length carries the policy; composition does not.** There is no "one uppercase,
one digit, one symbol" rule in the default configuration, because 800-63B says a
verifier SHALL NOT impose one. Composition rules produce a predictable shape —
capital in front, digit and bang on the end — and push users toward reuse and
sticky notes. What replaces them is a longer minimum and a list of the passwords
people actually pick. ``PASSWORD_REQUIRE_CHARACTER_CLASSES`` exists for a
deployment that answers to a compliance regime mandating the worse rule; it is
off, and turning it on makes passwords weaker rather than stronger.

**The strength score is advisory and is never a gate.** :attr:`PolicyResult.score`
drives a meter in the UI and nothing else. It is deliberately not enforced,
because a score threshold high enough to be interesting is a composition rule
wearing a disguise: at twelve characters, only a mixed-case-plus-digits password
clears "strong", so enforcing it would reintroduce through arithmetic exactly the
rule the paragraph above rejects. Rejection is done by rules that can be
explained in one sentence to the person who tripped them.

**A candidate is reduced before it is looked up.** ``P@ssw0rd2026!`` and
``password`` are the same password to an attacker's rule engine, so they are the
same password here: :func:`_canonical_forms` folds case, unwinds the common leet
substitutions, and strips separators and decorative digits, then every resulting
form is checked against the blocklist. This is what lets a few hundred curated
base words reject a space many orders of magnitude larger — see the header of
``data/common_passwords.txt``.

**This module is pure.** No session, no I/O beyond one file read at import, no
knowledge of HTTP. It is called by the routes that let somebody CHOOSE a
password — signup and invitation accept today, password reset and change when
they exist — and never by anything that verifies one. Enforcing a policy at
login would lock out every account that predates the policy and would tell a
guesser what the rules are; ``LoginRequest.password`` therefore keeps its
``min_length=1`` and always will.

Deliberately NOT enforced in :func:`app.services.auth.create_user`. That
function also registers Google and Apple accounts, which have no password at
all, and is the seam scripts and fixtures use. The gate belongs where untrusted
input arrives, which is the route.

The breach-corpus check (Have I Been Pwned, k-anonymity) is not here yet. It
lands with the password-reset endpoint, where ``docs/admin-panel-plan.md``
already schedules it; the rule list below is the seam it plugs into, so adding
it is one function and one setting rather than a rewrite.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Rule identifiers
# ---------------------------------------------------------------------------
#
# Stable strings rather than an enum, and part of the API contract: the 422 body
# carries them so a client can key off a rule without parsing English, and the
# frontend mirror in `lib/password-policy.ts` uses the same ids so the two
# cannot disagree about which rule fired.

TOO_SHORT = "too_short"
TOO_LONG = "too_long"
COMMON = "common"
CONTEXT = "context"
REPETITIVE = "repetitive"
LOW_VARIETY = "low_variety"
SEQUENTIAL = "sequential"
CHARACTER_CLASSES = "character_classes"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyFailure:
    """One broken rule, with the sentence shown to the person who broke it."""

    rule: str
    message: str


@dataclass(frozen=True)
class PasswordContext:
    """What this password must not be built out of.

    Optional because not every caller has it: invitation accept knows the email
    from the invitation row and nothing about an organization name, while signup
    knows both. A missing field simply contributes no tokens.
    """

    email: str | None = None
    organization_name: str | None = None


@dataclass(frozen=True)
class PolicyResult:
    """The verdict, plus an advisory 0-4 strength score for the meter."""

    failures: tuple[PolicyFailure, ...] = ()
    score: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def rules(self) -> tuple[str, ...]:
        """The broken rule ids — safe to log, unlike anything derived from the
        password itself."""

        return tuple(failure.rule for failure in self.failures)


class PasswordPolicyViolation(Exception):
    """A chosen password does not meet the policy.

    Translated to a 422 by the handler in ``api.main``, the same way the billing
    exceptions become 429/402/503 — so a route that forgets to catch it still
    answers correctly instead of returning a 500.
    """

    def __init__(self, failures: Sequence[PolicyFailure]) -> None:
        self.failures: tuple[PolicyFailure, ...] = tuple(failures)
        super().__init__(self.detail)

    @property
    def detail(self) -> str:
        """Every broken rule in one sentence-per-rule string.

        All of them rather than the first, so somebody fixing a password is told
        everything that is wrong at once instead of discovering the next rule on
        the next submit.
        """

        return " ".join(failure.message for failure in self.failures)

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(failure.rule for failure in self.failures)


# ---------------------------------------------------------------------------
# Normalization and canonicalization
# ---------------------------------------------------------------------------

# 800-63B asks for NFKC or NFKD before hashing so that the same password typed
# on a different keyboard or platform produces the same bytes. NFKC is the
# composed form and the more common choice. It is the identity transform for
# ASCII, so no existing hash in this database is affected by its introduction.
#
# It has to be applied at BOTH ends or it is worse than not applying it at all:
# normalizing at set time only would store a hash of a string the user can never
# type again. `services.auth` owns that pairing.


def normalize(password: str) -> str:
    """The exact string that gets hashed, measured and compared."""

    return unicodedata.normalize("NFKC", password)


# The substitutions that show up in real passwords. '2' is deliberately absent:
# it stands for 'z' rarely and for the digit two almost always, and folding it
# would collapse distinct passwords onto each other for no gain.
_LEET_BASE = {
    "@": "a",
    "4": "a",
    "8": "b",
    "(": "c",
    "<": "c",
    "3": "e",
    "6": "g",
    "9": "g",
    "!": "i",
    "|": "i",
    "0": "o",
    "5": "s",
    "$": "s",
    "7": "t",
    "+": "t",
}

# '1' is the one genuinely ambiguous glyph — it stands in for both 'i' and 'l'
# often enough that picking one loses half the coverage. Both readings are
# generated and both are looked up.
_LEET_AS_I = str.maketrans({**_LEET_BASE, "1": "i"})
_LEET_AS_L = str.maketrans({**_LEET_BASE, "1": "l"})

_NON_ALNUM = re.compile(r"[^0-9a-z]", re.ASCII)
_NON_ALPHA = re.compile(r"[^a-z]", re.ASCII)
# The decoration on either end of a password: a leading capital's worth of
# punctuation, a trailing year, the obligatory exclamation mark.
_EDGE_NOISE = re.compile(r"^[^a-z]+|[^a-z]+$", re.ASCII)

# Turkish letters that NFKD does not take apart. 'ş' and 'ğ' decompose to a base
# letter plus a combining mark, so stripping marks handles them; dotless 'ı' and
# dotted 'İ' are letters in their own right and need naming.
_ASCII_FOLD = str.maketrans({"ı": "i", "İ": "i", "ﬂ": "fl", "ﬁ": "fi"})


def _fold_to_ascii(value: str) -> str:
    """'şifre' and 'sifre' are the same password to anyone guessing.

    Without this the Turkish half of the blocklist would only ever match users
    who typed their password on an English keyboard — which is to say, it would
    match the easy case and miss the one it was written for.
    """

    decomposed = unicodedata.normalize("NFKD", value.translate(_ASCII_FOLD))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _canonical_forms(password: str) -> frozenset[str]:
    """Every reduced spelling of ``password`` worth looking up.

    Case, leet substitutions, separators and decorative digits are all things an
    attacker's rule engine undoes for free, so the blocklist is consulted with
    them undone. Producing a handful of forms rather than one canonical string
    is what covers the ambiguous cases ('1' as i or l) without guessing.
    """

    lowered = _fold_to_ascii(normalize(password).casefold())
    # Stripping the ends BEFORE folding is what makes 'P@ssw0rd2026!' and
    # 'password123456' land on the same entry. Folding first does not: the leet
    # table turns the trailing '!' into an i and the year into letters, and the
    # word it was decorating stops being recognisable.
    trimmed = _EDGE_NOISE.sub("", lowered)

    forms: set[str] = set()
    for base in (lowered, trimmed):
        if not base:
            continue

        candidates = [base]
        for table in (None, _LEET_AS_I, _LEET_AS_L):
            folded = base if table is None else base.translate(table)
            candidates.append(folded)
            # Separators removed: 'c-o-r-r-e-c-t' and 'correct' are one password.
            candidates.append(_NON_ALNUM.sub("", folded))
            # Digits removed too. Kept as its own variant of the UNFOLDED string
            # as well, because a password whose digits are a suffix rather than
            # a substitution ('password123456') needs them dropped, not read as
            # letters.
            candidates.append(_NON_ALPHA.sub("", folded))

        for candidate in candidates:
            # Below three characters a form carries no information — every short
            # fragment would collide with something — so it is not looked up.
            if len(candidate) >= 3:
                forms.add(candidate)

    return frozenset(forms)


# ---------------------------------------------------------------------------
# The blocklist
# ---------------------------------------------------------------------------

_BLOCKLIST_FILE = Path(__file__).resolve().parents[1] / "data" / "common_passwords.txt"


@lru_cache(maxsize=8)
def load_blocklist(path: Path | None = None) -> frozenset[str]:
    """The common-password set, read once and held as a frozenset.

    Cached because the lookup sits in the signup path: a file read per request
    for a list that never changes at runtime would be a per-signup disk hit for
    nothing. A missing file yields an EMPTY set rather than raising — the rest
    of the policy is still worth enforcing, and a deployment whose image lost a
    data file should refuse passwords no worse than it did yesterday, not refuse
    signups entirely.
    """

    source = path or _BLOCKLIST_FILE
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - a packaging failure, not a code path
        return frozenset()

    entries = set()
    for line in raw.splitlines():
        entry = line.strip().casefold()
        if entry and not entry.startswith("#"):
            entries.add(entry)

    return frozenset(entries)


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------
#
# Each returns a failure or None, takes only what it needs, and is tested on its
# own. Adding a rule means writing one of these and listing it in `evaluate`.


def _check_length(password: str, *, minimum: int, maximum: int) -> PolicyFailure | None:
    # Code points, not bytes: a password of twelve Turkish or CJK characters is
    # twelve characters, however many bytes UTF-8 needs for it.
    length = len(password)
    if length < minimum:
        return PolicyFailure(TOO_SHORT, f"Use at least {minimum} characters.")
    if length > maximum:
        return PolicyFailure(TOO_LONG, f"Use at most {maximum} characters.")
    return None


def _check_blocklist(forms: Iterable[str], blocklist: frozenset[str]) -> PolicyFailure | None:
    if not blocklist:
        return None
    if any(form in blocklist for form in forms):
        return PolicyFailure(
            COMMON,
            "This password is one of the ones people pick most often. Choose something else.",
        )
    return None


def _context_tokens(context: PasswordContext | None) -> frozenset[str]:
    """The words this password must not be assembled from.

    Short tokens are dropped: a three-letter local part like 'ali' appears
    inside far too many legitimate passwords to be evidence of anything, and
    banning it would tell that user their own name is forbidden.
    """

    words: list[str] = ["yanki"]

    if context is not None:
        if context.email:
            # Folded the same way the password is, or 'Şirket' in an org name
            # would never match 'sirket' in the password it was copied into.
            local, _, domain = _fold_to_ascii(normalize(context.email).casefold()).partition("@")
            words.extend(re.split(r"[^0-9a-z]+", local))
            # The first label only — everybody on gmail shares 'com'.
            words.append(domain.split(".")[0] if domain else "")
        if context.organization_name:
            folded = _fold_to_ascii(normalize(context.organization_name).casefold())
            words.extend(re.split(r"[^0-9a-z]+", folded))

    return frozenset(word for word in words if len(word) >= 4)


def _check_context(forms: Iterable[str], tokens: frozenset[str]) -> PolicyFailure | None:
    # Containment, not equality — unlike the blocklist. 'ahmet' inside
    # 'ahmetgizli' is still the user's own address doing the work, wherever in
    # the string it sits.
    if any(token in form for form in forms for token in tokens):
        return PolicyFailure(
            CONTEXT,
            "Do not build your password out of your email address, "
            "your organization name, or the word Yanki.",
        )
    return None


# A block repeated three or more times is the pattern this catches: 'abcabcabc',
# 'aaaaaaaaaaaa', 'ababababab'. Units longer than four are left alone — doubling
# a real word is weak, but it is not the same class of thing, and the blocklist
# and length rule are the honest tools for it.
_MAX_REPEATED_UNIT = 4
_MIN_REPEATS = 3


def _check_repetition(password: str) -> PolicyFailure | None:
    lowered = password.casefold()
    for size in range(1, _MAX_REPEATED_UNIT + 1):
        if len(lowered) < size * _MIN_REPEATS:
            break
        unit = lowered[:size]
        if unit * (len(lowered) // size) == lowered and len(lowered) % size == 0:
            return PolicyFailure(
                REPETITIVE,
                "Avoid a password that is one short block repeated.",
            )
    return None


# Four distinct characters over a twelve-character minimum. Set low on purpose:
# the repetition rule above already takes the periodic cases, so this only has
# to catch what it misses, and a threshold high enough to be clever would start
# rejecting legitimate passwords in scripts with small alphabets.
_MIN_DISTINCT_CHARACTERS = 4


def _check_variety(password: str) -> PolicyFailure | None:
    if len(set(password.casefold())) < _MIN_DISTINCT_CHARACTERS:
        return PolicyFailure(
            LOW_VARIETY,
            "Use more than a couple of different characters.",
        )
    return None


# Rows read left to right. The Turkish Q layout's tails are here for the same
# reason the blocklist has a Turkish section — 'qwertyuiopğü' is a keyboard walk
# to this product's users even though it is not one to an English corpus.
_SEQUENCES = (
    "0123456789",
    "1234567890",
    "abcdefghijklmnopqrstuvwxyz",
    "qwertyuiopğü",
    "asdfghjklşi",
    "zxcvbnmöç",
)

# Six, because '123456' and 'qwerty' are six and are the two most common
# passwords ever recorded. Shorter windows start matching ordinary words.
_MAX_SEQUENCE_RUN = 6


def _check_sequences(password: str) -> PolicyFailure | None:
    lowered = normalize(password).casefold()
    if len(lowered) < _MAX_SEQUENCE_RUN:
        return None

    haystacks = list(_SEQUENCES) + [row[::-1] for row in _SEQUENCES]
    for start in range(len(lowered) - _MAX_SEQUENCE_RUN + 1):
        window = lowered[start : start + _MAX_SEQUENCE_RUN]
        if any(window in row for row in haystacks):
            return PolicyFailure(
                SEQUENTIAL,
                "Avoid long runs off the keyboard or the alphabet, like 123456 or qwerty.",
            )
    return None


# Punctuation spelled out as ASCII ranges rather than as "not alphanumeric", so
# that a Turkish letter is not counted as a symbol — it would inflate both the
# class count and the search-space estimate below for a character that is
# neither.
_CLASS_PATTERNS = (
    re.compile(r"[a-z]", re.ASCII),
    re.compile(r"[A-Z]", re.ASCII),
    re.compile(r"[0-9]", re.ASCII),
    re.compile(r"[\x20-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]"),
)


def _character_classes(password: str) -> int:
    return sum(1 for pattern in _CLASS_PATTERNS if pattern.search(password))


def _check_character_classes(password: str, *, minimum: int) -> PolicyFailure | None:
    if _character_classes(password) >= minimum:
        return None
    return PolicyFailure(
        CHARACTER_CLASSES,
        f"Use at least {minimum} of: lowercase letters, uppercase letters, digits, symbols.",
    )


# ---------------------------------------------------------------------------
# The advisory score
# ---------------------------------------------------------------------------

# Search-space size per character, by the classes present. The last entry covers
# anything outside ASCII: a conservative 40 rather than the real size of Unicode,
# because an attacker targeting a Turkish user is not searching all of Unicode.
_CLASS_POOLS = (26, 26, 10, 33)
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_NON_ASCII_POOL = 40

# Bit thresholds for 1/2/3/4. Chosen so that length alone can reach the top: a
# sixteen-character all-lowercase passphrase scores 3 and a twenty-character one
# scores 4, which is the behaviour that makes the meter reward the thing the
# policy actually wants.
_SCORE_THRESHOLDS = (45.0, 60.0, 80.0)


def _score(password: str) -> int:
    """A 0-4 strength estimate. Advisory — see the module docstring."""

    if not password:
        return 0

    pool = sum(
        size for pattern, size in zip(_CLASS_PATTERNS, _CLASS_POOLS) if pattern.search(password)
    )
    if _NON_ASCII.search(password):
        pool += _NON_ASCII_POOL
    if pool <= 1:
        return 0

    bits = len(password) * math.log2(pool)
    return 1 + sum(1 for threshold in _SCORE_THRESHOLDS if bits >= threshold)


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Policy:
    """The settings this module reads, resolved once per call."""

    min_length: int
    max_length: int
    blocklist_enabled: bool
    require_character_classes: bool
    min_character_classes: int
    blocklist: frozenset[str] = field(default_factory=frozenset)


def _policy(settings: Settings | None) -> _Policy:
    resolved = settings or get_settings()
    return _Policy(
        min_length=resolved.password_min_length,
        max_length=resolved.password_max_length,
        blocklist_enabled=resolved.password_blocklist_enabled,
        require_character_classes=resolved.password_require_character_classes,
        min_character_classes=resolved.password_min_character_classes,
        blocklist=load_blocklist() if resolved.password_blocklist_enabled else frozenset(),
    )


def evaluate(
    password: str,
    *,
    context: PasswordContext | None = None,
    settings: Settings | None = None,
) -> PolicyResult:
    """Judge a candidate password without raising.

    Used by the meter path and by :func:`enforce`. A length failure returns on
    its own: telling somebody who typed four characters that their password is
    also predictable and also lacks variety is three true statements and one
    useful one.
    """

    policy = _policy(settings)
    normalized = normalize(password)

    length_failure = _check_length(
        normalized,
        minimum=policy.min_length,
        maximum=policy.max_length,
    )
    if length_failure is not None:
        return PolicyResult(failures=(length_failure,), score=0)

    forms = _canonical_forms(normalized)
    candidates = (
        _check_blocklist(forms, policy.blocklist),
        _check_context(forms, _context_tokens(context)),
        _check_repetition(normalized),
        _check_variety(normalized),
        _check_sequences(normalized),
        _check_character_classes(normalized, minimum=policy.min_character_classes)
        if policy.require_character_classes
        else None,
    )
    failures = tuple(failure for failure in candidates if failure is not None)

    return PolicyResult(failures=failures, score=0 if failures else _score(normalized))


def enforce(
    password: str,
    *,
    context: PasswordContext | None = None,
    settings: Settings | None = None,
) -> None:
    """Raise :class:`PasswordPolicyViolation` unless the password is acceptable.

    Call this BEFORE hashing. Argon2 is deliberately expensive, and spending it
    on a password that is about to be rejected is a free denial-of-service knob
    for anyone posting to an unauthenticated signup endpoint.
    """

    result = evaluate(password, context=context, settings=settings)
    if not result.ok:
        raise PasswordPolicyViolation(result.failures)
