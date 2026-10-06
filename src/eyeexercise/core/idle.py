"""유휴 시간 소스. Windows 구현은 platform/win_idle.py에 둔다."""

from typing import Protocol


class IdleSource(Protocol):
    def idle_seconds(self) -> float:
        """마지막 키보드·마우스 입력 이후 경과한 시간 (초)."""
        ...
