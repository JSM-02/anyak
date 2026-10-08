"""Windows 로그인 때 자동 실행: 현재 사용자(HKCU)의 Run 키에만 쓴다.

관리자 권한이 필요 없고, 다른 사용자나 시스템 전체에는 영향이 없다. 사용자가 설정에서 켤 때만 등록한다.
"""

import logging
import sys

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Swieom"


def startup_command() -> str | None:
    """등록할 실행 명령. exe로 묶였을 때만 있다 (소스로 실행 중이면 경로가 파이썬이라 등록하지 않는다)."""
    if not getattr(sys, "frozen", False):
        return None
    return f'"{sys.executable}"'  # 공백이 든 경로도 하나로 읽히게 따옴표로 감싼다


class WinAutoStart:
    def __init__(self, command: str | None = None, key_path: str = RUN_KEY) -> None:
        self._command = startup_command() if command is None else command
        self._key_path = key_path

    def is_available(self) -> bool:
        return self._command is not None

    def _read(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
        except OSError:
            return None
        return value if isinstance(value, str) else None

    def is_enabled(self) -> bool:
        return self._read() is not None

    def set_enabled(self, enabled: bool) -> bool:
        if self._command is None:
            return not enabled  # 등록할 수 없으니 켜 달라는 요청만 실패다
        import winreg

        try:
            if enabled:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, self._command)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass  # 이미 없다
        except OSError:
            log.warning("자동 실행 설정을 바꾸지 못했습니다.", exc_info=True)
            return False
        return True

    def refresh(self) -> None:
        if self._command is None:
            return
        current = self._read()
        if current is not None and current != self._command:
            self.set_enabled(True)
