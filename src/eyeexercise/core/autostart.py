"""Windows를 켤 때 같이 실행하는 기능의 인터페이스. Windows 구현은 platform/win_startup.py에 둔다."""

from typing import Protocol


class AutoStart(Protocol):
    def is_available(self) -> bool:
        """이 실행 방식에서 자동 실행을 등록할 수 있는지 (소스로 개발 중이면 False)."""
        ...

    def is_enabled(self) -> bool:
        """지금 등록되어 있는지."""
        ...

    def set_enabled(self, enabled: bool) -> bool:
        """등록하거나 지운다. 바뀐 상태가 요청과 같으면 True, 실패하면 False."""
        ...

    def refresh(self) -> None:
        """등록되어 있으면 지금 실행 파일 경로로 값을 맞춘다 (폴더를 옮긴 경우)."""
        ...
