"""Windows의 '애니메이션 효과' 설정을 읽는다 (설정 > 접근성 > 시각 효과). 끄면 앱도 움직임을 줄인다.

읽는 값은 이 켜짐/꺼짐 하나뿐이다. 읽지 못하면 켜져 있다고 본다.
"""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_SPI_GETCLIENTAREAANIMATION = 0x1042


def animations_enabled() -> bool:
    """창 안의 애니메이션 효과가 켜져 있는지. 읽지 못하면 True."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        user32.SystemParametersInfoW.restype = wintypes.BOOL
        enabled = wintypes.BOOL()
        if not user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0):
            log.warning("애니메이션 설정을 읽지 못했습니다 (오류 %s). 켜져 있다고 봅니다.", ctypes.get_last_error())
            return True
        return bool(enabled.value)
    except (OSError, AttributeError):  # Windows가 아니거나 호출할 수 없는 환경
        return True
