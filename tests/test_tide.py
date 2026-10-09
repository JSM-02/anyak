import math

from eyeexercise.core.scheduler import State
from eyeexercise.core.tide import (
    WAVE_MID,
    WAVE_STRONG,
    WAVE_WEAK,
    display_level,
    eye_row,
    wave_margin,
    wave_offset,
    water_level,
)

STYLES = (WAVE_WEAK, WAVE_MID, WAVE_STRONG)


def samples(width=900):
    """여러 위치와 시각에서 값을 살펴본다."""
    for step in range(0, 600):
        t = step * 0.37
        for x in range(0, width + 1, 30):
            yield x, t


# ---- 수위 ----


def test_수위는_기다리는_동안_타이머_진행을_따른다():
    assert water_level(State.RUNNING, 1200, 1200) == 0.0
    assert water_level(State.RUNNING, 600, 1200) == 0.5
    assert water_level(State.SNOOZED, 300, 300) == 0.0
    assert water_level(State.SNOOZED, 150, 300) == 0.5


def test_일시정지_중에는_멈춘_자리의_수위를_그대로_보여_준다():
    assert water_level(State.PAUSED, 300, 1200) == 0.75


def test_알림이_떠_있으면_물이_가득_찬다():
    assert water_level(State.DUE, None, 1200) == 1.0


def test_휴식_운동_중에는_물이_비어_있다():
    assert water_level(State.EXERCISING, None, None) == 0.0


def test_세고_있지_않으면_수위는_0이다():
    assert water_level(State.RUNNING, None, None) == 0.0


def test_수위는_0에서_1_사이다():
    assert water_level(State.RUNNING, -5, 1200) == 1.0
    assert water_level(State.RUNNING, 5000, 1200) == 0.0


# ---- 파도 ----


def test_수면_높이는_여백_안에서만_움직인다():
    # 여백이 파도 높이보다 크면 수위 0·1에서 파도가 화면 안으로 삐져나오지 않는다
    for style in STYLES:
        margin = wave_margin(style)
        for x, t in samples():
            assert abs(wave_offset(x, t, 900, style)) <= margin


def test_파도는_세기가_셀수록_더_크게_일렁인다():
    def peak(style):
        return max(abs(wave_offset(x, t, 900, style)) for x, t in samples())

    assert peak(WAVE_WEAK) < peak(WAVE_MID) < peak(WAVE_STRONG)
    assert wave_margin(WAVE_WEAK) < wave_margin(WAVE_MID) < wave_margin(WAVE_STRONG)


def test_파도는_시간이_지나면_모양이_바뀐다():
    first = [wave_offset(x, 0.0, 900, WAVE_MID) for x in range(0, 900, 60)]
    later = [wave_offset(x, 3.0, 900, WAVE_MID) for x in range(0, 900, 60)]
    assert first != later


def test_같은_시각과_위치에서는_항상_같은_값이다():
    assert wave_offset(120, 4.2, 900, WAVE_MID) == wave_offset(120, 4.2, 900, WAVE_MID)


def test_값은_유한하다():
    for x, t in samples():
        for style in STYLES:
            assert math.isfinite(wave_offset(x, t, 900, style))


# ---- 눈 아이콘 줄 ----


def test_쉰_횟수만큼_감은_눈_나머지_권장_횟수만큼_뜬_눈이다():
    row = eye_row(rests=6, recommended=12)
    assert (row.closed, row.open, row.hidden) == (6, 6, 0)


def test_권장_횟수를_넘겨_쉬어도_감은_눈이_모두_보인다():
    row = eye_row(rests=14, recommended=12)
    assert (row.closed, row.open, row.hidden) == (14, 0, 0)


def test_사용_시간이_짧아_권장이_0이면_뜬_눈이_없다():
    row = eye_row(rests=0, recommended=0)
    assert (row.closed, row.open, row.hidden) == (0, 0, 0)
    assert eye_row(rests=2, recommended=0).closed == 2


def test_아이콘이_너무_많으면_상한까지만_그리고_넘는_수를_알려_준다():
    row = eye_row(rests=10, recommended=40, max_icons=24)
    assert row.closed + row.open == 24
    assert row.closed == 10 and row.open == 14
    assert row.hidden == 40 - 24
    many = eye_row(rests=30, recommended=40, max_icons=24)
    assert many.closed == 24 and many.open == 0 and many.hidden == 40 - 24


def test_아이콘_수는_음수가_되지_않는다():
    row = eye_row(rests=-3, recommended=-1)
    assert (row.closed, row.open, row.hidden) == (0, 0, 0)


# ---- 화면에 그리는 수위 ----


def test_수위가_0이어도_물결이_보이도록_바닥에_얇게_깔린다():
    assert 0.03 <= display_level(0.0) <= 0.12


def test_가득_찬_수위는_그대로_가득이다():
    assert display_level(1.0) == 1.0


def test_그리는_수위는_차오를수록_계속_높아진다():
    levels = [display_level(i / 20) for i in range(21)]
    assert levels == sorted(levels) and len(set(levels)) == len(levels)


def test_그리는_수위는_범위_밖_값도_0에서_1_사이로_보정한다():
    assert display_level(-1) == display_level(0.0)
    assert display_level(2) == 1.0
