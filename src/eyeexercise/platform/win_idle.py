"""Win32 GetLastInputInfo 기반 유휴 시간. 키보드 훅 없이 '마지막 입력 시각'만 읽는다."""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)


def elapsed_ms(now_tick: int, last_input_tick: int) -> int:
    """32비트 틱 카운트(약 49.7일마다 한 바퀴)가 한 바퀴 돌아도 올바르게 뺀다."""
    return (now_tick - last_input_tick) & 0xFFFFFFFF


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class WinIdleSource:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
        self._user32.GetLastInputInfo.restype = wintypes.BOOL
        self._kernel32.GetTickCount.argtypes = []
        self._kernel32.GetTickCount.restype = wintypes.DWORD
        self._failure_logged = False

    def idle_seconds(self) -> float:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            if not self._failure_logged:
                log.error("GetLastInputInfo 실패 (오류 %s). 유휴 시간을 0으로 간주합니다.", ctypes.get_last_error())
                self._failure_logged = True
            return 0.0
        return elapsed_ms(self._kernel32.GetTickCount(), info.dwTime) / 1000.0
