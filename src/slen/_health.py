from dataclasses import dataclass, field

from slen._http._answer import Answered, Call
from slen._http._endpoints import Endpoint
from slen._http._fields import Fields
from slen._http._request import ApiRequest, Sending


@dataclass(frozen=True, slots=True, kw_only=True)
class Health:
    """The body of GET /health: the process serves, and how each dependency answered (ok, or down: and why)."""

    app: str
    release: str | None
    server: str
    mysql: str
    redis: str
    queue: str | None
    broadcast: str | None
    opcache_preloaded_files: int | None
    opcache_cached_scripts: int | None
    request_id: str | None = field(default=None, compare=False)


def health_of(answered: Answered) -> Health:
    body = Fields(answered.data, "body")

    return Health(
        app=body.text("app"),
        release=body.nullable_text("release"),
        server=body.text("server"),
        mysql=body.text("mysql"),
        redis=body.text("redis"),
        queue=body.nullable_text("queue"),
        broadcast=body.nullable_text("broadcast"),
        opcache_preloaded_files=body.nullable_integer("opcache_preloaded_files"),
        opcache_cached_scripts=body.nullable_integer("opcache_cached_scripts"),
        request_id=answered.request_id,
    )


def health_call(sending: Sending) -> Call[Health]:
    return Call(ApiRequest(endpoint=Endpoint.HEALTH, envelope="body", sending=sending), health_of)
