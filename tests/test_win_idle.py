import sys

import pytest

from eyeexercise.platform.win_idle import elapsed_ms


def test_틱_차이_계산():
    assert elapsed_ms(10_000, 7_000) == 3_000
    assert elapsed_ms(5, 5) == 0


def test_32비트_틱_카운트가_한_바퀴_돌아도_올바르게_계산한다():
    # 마지막 입력은 한 바퀴 직전(0xFFFFFFFB), 지금은 한 바퀴 돈 직후(5) -> 10ms 경과
    assert elapsed_ms(5, 0xFFFFFFFB) == 10


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")
def test_실제_유휴_시간은_0_이상의_실수():
    from eyeexercise.platform.win_idle import WinIdleSource

    idle = WinIdleSource().idle_seconds()
    assert isinstance(idle, float)
    assert 0.0 <= idle < 10 * 365 * 24 * 3600  # 터무니없는 값(음수, 거대한 값)이 아닌지
