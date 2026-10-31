import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Final

from slen._errors import WebhookSignatureReason

SIGNATURE_HEADER: Final = "Slen-Signature"

# HMAC-SHA256 in lower-case hex: anything else cannot be the signature, whatever bytes it spells.
SIGNATURE: Final = re.compile(r"[0-9a-f]{64}")
DIGITS: Final = re.compile(r"[0-9]+")


@dataclass(frozen=True, slots=True, kw_only=True)
class SignatureRule:
    secret: str
    tolerance_seconds: int
    now_seconds: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SignatureCheck:
    reason: WebhookSignatureReason | None
    age_seconds: int | None

    @property
    def accepted(self) -> bool:
        return self.reason is None


@dataclass(frozen=True, slots=True, kw_only=True)
class SignatureHeader:
    timestamp: int
    signatures: tuple[str, ...]


def check_signature(body: bytes, header: str | None, rule: SignatureRule) -> SignatureCheck:
    if header is None or not header.strip():
        return SignatureCheck(reason="missing_header", age_seconds=None)

    parsed = header_of(header)

    if parsed is None:
        return SignatureCheck(reason="malformed_header", age_seconds=None)

    age = rule.now_seconds - parsed.timestamp

    if abs(age) > rule.tolerance_seconds:
        return SignatureCheck(reason="outside_tolerance", age_seconds=age)

    signed = f"{parsed.timestamp}.".encode() + body
    expected = hmac.new(rule.secret.encode(), signed, hashlib.sha256).digest()
    candidates = [bytes.fromhex(candidate) for candidate in parsed.signatures if SIGNATURE.fullmatch(candidate)]

    # A candidate is compared in constant time, over the raw bytes; no string is compared anywhere.
    if any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        return SignatureCheck(reason=None, age_seconds=age)

    return SignatureCheck(reason="no_matching_signature", age_seconds=age)


def header_of(header: str) -> SignatureHeader | None:
    pairs = [part.strip().partition("=") for part in header.split(",")]
    stamps = [value for name, equals, value in pairs if equals and name == "t"]
    signatures = tuple(value for name, equals, value in pairs if equals and name == "v1")

    if len(stamps) != 1 or not DIGITS.fullmatch(stamps[0]) or not signatures:
        return None

    return SignatureHeader(timestamp=int(stamps[0]), signatures=signatures)
