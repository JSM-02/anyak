"""Windows 11의 창 제목 막대 색을 앱 바탕색에 맞춘다 (DWM 창 속성).

제목 막대를 직접 그리는 대신 Windows가 그리는 막대의 색만 바꾼다. 그래서 최소화·최대화·닫기 버튼, 끌어서 옮기기,
화면 가장자리에 붙이기는 모두 그대로 동작한다. 지원하지 않는 Windows(10 등)에서는 아무 일도 하지 않는다.
"""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def colorref(hex_color: str) -> int:
    """'#RRGGBB'를 Windows의 COLORREF(0x00BBGGRR)로 바꾼다."""
    value = hex_color.lstrip("#")
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (blue << 16) | (green << 8) | red


def set_caption_colors(hwnd: int, background: str, text: str) -> bool:
    """창의 제목 막대 바탕·글자·테두리 색을 정한다. 적용하지 못하면 False(조용히 넘어간다)."""
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        ok = True
        for attribute, color in (
            (_DWMWA_CAPTION_COLOR, background),
            (_DWMWA_BORDER_COLOR, background),
            (_DWMWA_TEXT_COLOR, text),
        ):
            value = wintypes.DWORD(colorref(color))
            ok = dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0 and ok
        return ok
    except (OSError, AttributeError, ValueError):  # Windows가 아니거나 호출할 수 없는 환경
        log.debug("제목 막대 색을 바꾸지 못했습니다.", exc_info=True)
        return False
