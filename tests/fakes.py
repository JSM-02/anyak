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


class FakeAutoStart:
    """Windows 레지스트리 대신 쓰는 자동 실행 가짜."""

    def __init__(self, enabled: bool = False, available: bool = True, succeeds: bool = True) -> None:
        self.enabled = enabled
        self.available = available
        self.succeeds = succeeds
        self.calls: list[bool] = []
        self.refreshed = 0

    def is_available(self) -> bool:
        return self.available

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> bool:
        self.calls.append(enabled)
        if not self.succeeds:
            return False
        self.enabled = enabled
        return True

    def refresh(self) -> None:
        self.refreshed += 1
