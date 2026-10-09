import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")
def test_애니메이션_설정은_참_거짓으로_읽힌다():
    from eyeexercise.platform.win_motion import animations_enabled

    assert animations_enabled() in (True, False)
