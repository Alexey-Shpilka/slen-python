import math
import time
from dataclasses import dataclass
from datetime import datetime

from slen._config import logger_of, secret_of, whole
from slen._errors import WEBHOOK_PAYLOAD_INVALID, InvalidResponseError, WebhookSignatureError
from slen._logger import SlenLogger, write_log
from slen._modules.webhooks._events import event_of
from slen._modules.webhooks._signature import SignatureCheck, SignatureRule, check_signature
from slen._modules.webhooks._types import WebhookEvent, WebhookPayload


@dataclass(frozen=True, slots=True, kw_only=True)
class Delivery:
    payload: WebhookPayload
    header: str | None
    secret: str | None
    tolerance_seconds: int | None
    now: datetime | None


class Webhooks:
    """Checks the Slen-Signature of a webhook and reads its event, from the raw body as it arrived; needs no client."""

    def __init__(
        self,
        *,
        secret: str | None = None,
        tolerance_seconds: int = 300,
        logger: SlenLogger | None = None,
    ) -> None:
        self._secret = secret_of(secret)
        self._tolerance_seconds = whole("tolerance_seconds", tolerance_seconds, 1)
        self._logger = logger_of(logger)

    def verify(
        self,
        payload: WebhookPayload,
        signature_header: str | None,
        *,
        secret: str | None = None,
        tolerance_seconds: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """True when the header signs exactly this body with the secret, within the tolerance."""
        delivery = Delivery(
            payload=payload,
            header=signature_header,
            secret=secret,
            tolerance_seconds=tolerance_seconds,
            now=now,
        )

        return self._check(delivery).accepted

    def construct_event(
        self,
        payload: WebhookPayload,
        signature_header: str | None,
        *,
        secret: str | None = None,
        tolerance_seconds: int | None = None,
        now: datetime | None = None,
    ) -> WebhookEvent:
        """The event of an accepted delivery; isinstance() or match tells its type."""
        delivery = Delivery(
            payload=payload,
            header=signature_header,
            secret=secret,
            tolerance_seconds=tolerance_seconds,
            now=now,
        )
        check = self._check(delivery)

        if check.reason is not None:
            raise WebhookSignatureError(
                f"Slen: the webhook signature was not accepted ({check.reason}); do not act on this body.",
                reason=check.reason,
            )

        event = event_of(text_of(payload))

        if event is None:
            self._rejected("invalid_payload", check.age_seconds)
            raise InvalidResponseError(
                "Slen: the webhook is signed, but its body is not an event: JSON with id, type, created_at and data.",
                code=WEBHOOK_PAYLOAD_INVALID,
            )

        return event

    def _check(self, delivery: Delivery) -> SignatureCheck:
        key = self._secret if delivery.secret is None else secret_of(delivery.secret)

        if key is None:
            raise ValueError(
                "Slen: checking a webhook needs the signing secret of its endpoint (pass secret, or set one here)."
            )

        tolerance = delivery.tolerance_seconds
        rule = SignatureRule(
            secret=key,
            tolerance_seconds=self._tolerance_seconds
            if tolerance is None
            else whole("tolerance_seconds", tolerance, 1),
            now_seconds=seconds_of(delivery.now),
        )
        check = check_signature(bytes_of(delivery.payload), delivery.header, rule)

        if check.reason is not None:
            self._rejected(check.reason, check.age_seconds)

        return check

    # The body, the secret and the header are never written: they are the delivery itself.
    def _rejected(self, reason: str, age_seconds: int | None) -> None:
        write_log(self._logger, "slen.webhook.rejected", {"reason": reason, "age_seconds": age_seconds})


def seconds_of(now: datetime | None) -> int:
    if now is None:
        return math.floor(time.time())

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Slen: now of a webhook check is a datetime with its time zone.")

    return math.floor(now.timestamp())


def bytes_of(payload: WebhookPayload) -> bytes:
    if isinstance(payload, str):
        return payload.encode()

    if isinstance(payload, bytes):
        return payload

    raise TypeError("Slen: the webhook body is the raw body, as str or bytes.")


# Bytes that are not UTF-8 are no event: an empty text reads as none.
def text_of(payload: WebhookPayload) -> str:
    if isinstance(payload, str):
        return payload

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return ""
