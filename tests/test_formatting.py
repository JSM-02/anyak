import pytest

from eyeexercise.core.formatting import format_remaining


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1200, "20분"),
        (750, "12분 30초"),
        (61, "1분 1초"),
        (60, "1분"),
        (59.2, "1분"),  # 올림
        (45, "45초"),
        (0.4, "1초"),
        (0, "0초"),
        (-5, "0초"),
    ],
)
def test_남은_시간_표기(seconds, expected):
    assert format_remaining(seconds) == expected


# ---- 사이드바 타이머 알약 (9a) ----


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0, "0:00"), (0.2, "0:01"), (59, "0:59"), (60, "1:00"), (754, "12:34"), (601, "10:01"), (7200, "120:00"), (-5, "0:00")],
)
def test_타이머_시계_표시(seconds, text):
    from eyeexercise.core.formatting import format_clock

    assert format_clock(seconds) == text


def test_알약_문구는_상태마다_다르다():
    from eyeexercise.core.formatting import timer_pill
    from eyeexercise.core.scheduler import State

    assert timer_pill(State.RUNNING, 754) == ("12:34 뒤 휴식", "normal")
    assert timer_pill(State.SNOOZED, 290) == ("4:50 뒤 다시 알림", "normal")
    assert timer_pill(State.DUE, 0) == ("지금 쉴 시간이에요", "alert")
    assert timer_pill(State.PAUSED, 754) == ("일시정지 · 12:34", "paused")
    assert timer_pill(State.EXERCISING, None, "rest") == ("눈 휴식 중", "active")
    assert timer_pill(State.EXERCISING, None, "exercise") == ("눈 운동 중", "active")


def test_남은_시간을_모르면_시간_없이_문구만_만든다():
    from eyeexercise.core.formatting import timer_pill
    from eyeexercise.core.scheduler import State

    assert timer_pill(State.RUNNING, None)[0] == "휴식 대기"
    assert timer_pill(State.PAUSED, None)[0] == "일시정지"
