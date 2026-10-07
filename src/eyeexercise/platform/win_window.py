"""창 포그라운드 관련 Win32 호출."""

import ctypes
from ctypes import wintypes

_ASFW_ANY = 0xFFFFFFFF  # (DWORD)-1


def allow_any_process_to_set_foreground() -> None:
    """방금 실행된 프로세스가 가진 포그라운드 권한을 다른 프로세스(첫 인스턴스)가 쓸 수 있게 한다.

    이게 없으면 첫 인스턴스가 창을 앞으로 가져오려 해도 작업 표시줄만 깜빡이는 경우가 많다.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL
    user32.AllowSetForegroundWindow(_ASFW_ANY)


def set_app_user_model_id(app_id: str) -> None:
    """작업 표시줄이 이 앱을 파이썬이 아닌 독립된 앱으로 보고 우리 아이콘을 쓰게 한다."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
