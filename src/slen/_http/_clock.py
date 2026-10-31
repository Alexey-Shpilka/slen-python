import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final


# The seams of time: what the SDK reads the clocks with, draws its jitter from and sleeps with.
@dataclass(frozen=True, slots=True, kw_only=True)
class Clock:
    monotonic: Callable[[], float] = time.monotonic
    now: Callable[[], float] = time.time
    random: Callable[[], float] = random.random
    sleep: Callable[[float], None] = time.sleep
    sleep_async: Callable[[float], Awaitable[None]] = asyncio.sleep


SYSTEM_CLOCK: Final = Clock()
