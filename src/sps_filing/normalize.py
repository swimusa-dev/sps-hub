"""Subject-line normalization.

Both sides of every comparison are normalized the same way: incoming subject
lines here, and the match tokens stored in the mapping list. That is what makes
the punctuation chaos in the live SPS feed stop mattering.

Rules, applied in order:

1. Remove apostrophes, straight and typographic, so MACY'S becomes MACYS.
2. Uppercase.
3. Replace every character that is not A-Z, 0-9, space or & with a space.
4. Collapse runs of whitespace to one, and trim.
5. Strip a leading sequence number, the "1. " / "2. " that SPS prefixes.

Rule 1 must precede rule 3. Reversed, MACY'S becomes "MACY S" and stops
matching MACYS.
"""

import re

_APOSTROPHES = re.compile(r"[‘’ʼ´'`]")
_NOT_ALLOWED = re.compile(r"[^A-Z0-9 &]")
_WHITESPACE = re.compile(r"\s+")
# By this point "1. SALES" already reads "1 SALES": the period became a space.
_LEADING_SEQUENCE = re.compile(r"^\d{1,2}\s+")


def normalize_token(raw: str | None) -> str:
    """Canonical form of a match token: rules 1 to 4, without rule 5.

    Tokens must skip the sequence-number strip. `4-5-4 Calendar` normalizes to
    `4 5 4 CALENDAR`, whose leading "4 " looks exactly like an SPS sequence
    prefix; applying rule 5 would silently shorten the token to `5 4 CALENDAR`
    and every Macys 4-5-4 rollup would lose its calendar segment.
    """
    if not raw:
        return ""
    text = _APOSTROPHES.sub("", raw).upper()
    text = _NOT_ALLOWED.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_subject(raw: str | None) -> str:
    """Canonical form of a subject line: all five rules.

    Subjects genuinely do start with an SPS sequence number, so rule 5 applies
    here and only here.
    """
    return _LEADING_SEQUENCE.sub("", normalize_token(raw)).strip()


def pad(text: str) -> str:
    """Wrap in spaces so bounded-token matching can use plain containment.

    Without this, the brand token TS matches inside TOP 6 ACCTS and every
    cross-retailer rollup is filed under brand TS.
    """
    return f" {text} "


def contains_token(haystack: str, token: str) -> bool:
    """True when `token` appears in `haystack` as whole words."""
    if not token:
        return False
    return pad(token) in pad(haystack)
