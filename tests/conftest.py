import pytest

from slen._http import _clock
from support.harness import KINDS, FakeClock, Kind


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Every client a test builds reads this clock: a wait or a retry pause takes no real time."""
    fake = FakeClock()
    monkeypatch.setattr(_clock, "SYSTEM_CLOCK", fake.clock())
    monkeypatch.delenv("SLEN_API_KEY", raising=False)

    return fake


@pytest.fixture(params=KINDS)
def kind(request: pytest.FixtureRequest) -> Kind:
    """The client of each test: Slen, then AsyncSlen."""
    value: Kind = request.param

    return value
