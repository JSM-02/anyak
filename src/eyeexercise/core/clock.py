"""시간 소스. 테스트에서 FakeClock으로 대체할 수 있도록 프로토콜로 분리한다."""

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """경과 시간 측정용 (초). 시계를 바꿔도 거꾸로 가지 않는다."""
        ...

    def now(self) -> datetime:
        """기록용 현재 시각 (시간대 포함)."""
        ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now().astimezone()
