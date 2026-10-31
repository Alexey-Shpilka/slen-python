from dataclasses import dataclass

from slen._http._async import AsyncTransport
from slen._http._sync import SyncTransport
from slen._observability._recorders import SpanRecorder


# What a module of one client works with: its chain and its span recorder. Nothing of a call is kept here.
@dataclass(frozen=True, slots=True)
class SyncContext:
    transport: SyncTransport
    spans: SpanRecorder


@dataclass(frozen=True, slots=True)
class AsyncContext:
    transport: AsyncTransport
    spans: SpanRecorder
