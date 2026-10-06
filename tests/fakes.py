from datetime import datetime, timedelta, timezone


class FakeClock:
    def __init__(self) -> None:
        self._t = 1000.0
        self._start = datetime(2026, 10, 6, 9, 0, 0, tzinfo=timezone(timedelta(hours=9)))

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def monotonic(self) -> float:
        return self._t

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._t - 1000.0)


class FakeIdle:
    def __init__(self) -> None:
        self.value = 0.0

    def idle_seconds(self) -> float:
        return self.value
