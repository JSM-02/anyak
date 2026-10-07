"""깜빡임 감지 인터페이스. 구현은 9단계(opt-in)에서 추가한다.

카메라는 어떤 핵심 기능의 전제 조건도 아니다. 감지기가 없어도 운동은 그대로 동작해야 하며,
구현체는 프레임을 저장하거나 전송하지 않고 운동이 끝나면 즉시 카메라를 꺼야 한다.
"""

from typing import Protocol


class BlinkDetector(Protocol):
    def start(self) -> None:
        """운동이 시작될 때 호출한다."""
        ...

    def stop(self) -> None:
        """운동이 끝나거나 중단되면 즉시 호출한다."""
        ...

    def blink_count(self) -> int:
        """start() 이후 감지한 깜빡임 횟수."""
        ...


class NullDetector:
    """카메라를 쓰지 않을 때의 기본 구현. 아무것도 하지 않는다."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def blink_count(self) -> int:
        return 0
