import math

import pytest

from eyeexercise.core.exercises import (
    DOT_CENTER,
    DOT_PATTERNS,
    DOT_SPEED_HZ,
    EXERCISE_BLINK,
    EXERCISE_DOT_FOLLOW,
    FINISH_SECONDS,
    MESSAGES,
    MIN_DOT_SECONDS,
    PREPARE_SECONDS,
    SPOKEN,
    Phase,
    blink_timeline,
    dot_follow_timeline,
)
from eyeexercise.core.settings import BlinkSettings, DotFollowSettings, ExercisesSettings

# 기본 60초: 준비 3초, 패턴 6개(9초씩), 마무리 3초. 패턴은 좌우 → 상하 → 대각선 → 반대 대각선 → 원 → 8자.


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---- 경로 함수 ----


def test_패턴은_6가지이고_이름과_문구가_있다():
    assert [p.key for p in DOT_PATTERNS] == [
        "horizontal",
        "vertical",
        "diagonal_down",
        "diagonal_up",
        "circle",
        "figure_eight",
    ]
    assert all(p.message for p in DOT_PATTERNS)
    assert len({p.message for p in DOT_PATTERNS}) == 6


@pytest.mark.parametrize("pattern", DOT_PATTERNS, ids=lambda p: p.key)
def test_모든_시점에서_좌표가_0에서_1_범위_안이다(pattern):
    for i in range(0, 5001):  # u = 0 ~ 50바퀴
        x, y = pattern.position(i / 100)
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        assert 0.1 - 1e-9 <= x <= 0.9 + 1e-9 and 0.1 - 1e-9 <= y <= 0.9 + 1e-9  # 가장자리에 붙지 않는다


@pytest.mark.parametrize("pattern", DOT_PATTERNS, ids=lambda p: p.key)
def test_경로가_끊기지_않고_이어진다(pattern):
    # 아주 짧은 시간 동안 점이 멀리 뛰지 않는다. (가장 빠른 8자도 u당 약 4.5)
    du = 0.001
    for i in range(0, 3000):
        a, b = pattern.position(i * du), pattern.position((i + 1) * du)
        assert dist(a, b) <= 5.0 * du


@pytest.mark.parametrize("pattern", DOT_PATTERNS, ids=lambda p: p.key)
def test_한_바퀴_돌면_제자리로_돌아온다(pattern):
    start, end = pattern.position(0.0), pattern.position(1.0)
    assert dist(start, end) < 1e-9
    assert dist(pattern.position(3.0), start) < 1e-9


def test_패턴별_시작점():
    expected = {
        "horizontal": (0.5, 0.5),
        "vertical": (0.5, 0.5),
        "diagonal_down": (0.5, 0.5),
        "diagonal_up": (0.5, 0.5),
        "circle": (0.88, 0.5),  # 오른쪽 끝에서 시작해 반시계가 아닌 시계 방향(화면 기준 아래쪽)으로 돈다
        "figure_eight": (0.5, 0.5),
    }
    for p in DOT_PATTERNS:
        assert p.position(0.0) == pytest.approx(expected[p.key])


def test_패턴별_끝점은_한_바퀴_뒤_시작점과_같다():
    for p in DOT_PATTERNS:
        assert p.position(2.0) == pytest.approx(p.position(0.0))


def test_좌우는_x만_위아래는_y만_움직인다():
    horizontal, vertical = DOT_PATTERNS[0], DOT_PATTERNS[1]
    assert {round(horizontal.position(i / 50)[1], 9) for i in range(100)} == {0.5}
    assert {round(vertical.position(i / 50)[0], 9) for i in range(100)} == {0.5}
    xs = [horizontal.position(i / 100)[0] for i in range(100)]
    assert min(xs) == pytest.approx(0.1) and max(xs) == pytest.approx(0.9)


def test_대각선_두_개는_서로_반대_방향이다():
    down, up = DOT_PATTERNS[2], DOT_PATTERNS[3]
    (dx, dy), (ux, uy) = down.position(0.25), up.position(0.25)  # 오른쪽 끝
    assert dx == ux == pytest.approx(0.9)
    assert dy == pytest.approx(0.9) and uy == pytest.approx(0.1)  # 아래 vs 위


def test_원은_중심에서_일정한_거리이고_8자는_가운데를_지난다():
    circle, eight = DOT_PATTERNS[4], DOT_PATTERNS[5]
    assert all(dist(circle.position(i / 100), DOT_CENTER) == pytest.approx(0.38) for i in range(100))
    assert eight.position(0.5) == pytest.approx(DOT_CENTER)  # 가운데에서 교차한다
    ys = [eight.position(i / 200)[1] for i in range(200)]
    assert min(ys) < 0.3 and max(ys) > 0.7


# ---- 타임라인 ----


def test_기본_60초는_패턴_6개가_한_번씩():
    t = dot_follow_timeline(60)
    assert (t.total_seconds, t.segments) == (60, 6)
    assert [t.pattern_at(i).key for i in range(6)] == [p.key for p in DOT_PATTERNS]


def test_준비_추적_마무리_순서이고_끝나면_바로_끝난다():
    t = dot_follow_timeline(60)
    assert t.step_at(0).phase is Phase.PREPARE
    assert t.step_at(0).dot == DOT_CENTER
    assert t.step_at(2.9).phase is Phase.PREPARE
    assert t.step_at(3.0).phase is Phase.TRACK
    assert t.step_at(56.9).phase is Phase.TRACK
    assert t.step_at(57.0).phase is Phase.FINISH
    assert t.step_at(59.9).phase is Phase.FINISH
    assert t.step_at(60.0).phase is Phase.FINISH and t.step_at(60.0).done  # 먼 곳 바라보기로 이어지지 않는다
    assert not any(t.step_at(i / 4).phase is Phase.LOOK_AWAY for i in range(0, 400))


def test_준비_문구는_고개를_가만히_두라고_알려_준다():
    step = dot_follow_timeline(60).step_at(0)
    assert "고개" in step.message and "점" in step.message


def test_추적_중에는_패턴마다_다른_문구가_나온다():
    t = dot_follow_timeline(60)
    for i, pattern in enumerate(DOT_PATTERNS):
        middle = PREPARE_SECONDS + 9 * i + 4.5
        step = t.step_at(middle)
        assert step.phase is Phase.TRACK and step.message == pattern.message


def test_추적_구간에서_점은_항상_화면_안에_있다():
    for speed in DOT_SPEED_HZ:
        t = dot_follow_timeline(60, speed)
        for i in range(0, 60 * 30):
            x, y = t.step_at(i / 30).dot
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


@pytest.mark.parametrize("speed", list(DOT_SPEED_HZ))
@pytest.mark.parametrize("duration", [12, 30, 60, 100, 600])
def test_점이_순간이동하지_않는다_패턴_전환과_마무리_포함(speed, duration):
    t = dot_follow_timeline(duration, speed)
    fps = 60
    prev = t.step_at(0).dot
    largest = 0.0
    for i in range(1, int(t.total_seconds * fps)):
        cur = t.step_at(i / fps).dot
        largest = max(largest, dist(prev, cur))
        prev = cur
    assert largest <= 0.05  # 60fps에서 한 프레임에 화면 폭의 5% 이상 움직이지 않는다


def test_마무리에는_점이_가운데로_돌아온다():
    t = dot_follow_timeline(60)
    assert t.step_at(57.0).dot != DOT_CENTER
    assert t.step_at(58.0).dot == pytest.approx(DOT_CENTER)
    assert t.step_at(59.9).dot == pytest.approx(DOT_CENTER)


def test_패턴이_바뀌는_순간에도_점은_이어진다():
    t = dot_follow_timeline(60)
    for boundary in (12.0, 21.0, 30.0, 39.0, 48.0):  # 패턴 경계(3 + 9k)
        before, after = t.step_at(boundary - 1e-4).dot, t.step_at(boundary + 1e-4).dot
        assert dist(before, after) < 1e-3


def test_속도_설정이_반영된다():
    slow, normal, fast = (dot_follow_timeline(60, s) for s in ("slow", "normal", "fast"))
    assert (slow.speed_hz, normal.speed_hz, fast.speed_hz) == (0.12, 0.2, 0.3)

    def traveled(timeline):
        pts = [timeline.step_at(3 + i / 30).dot for i in range(1, 30 * 5)]  # 첫 패턴(좌우) 5초
        return sum(dist(a, b) for a, b in zip(pts, pts[1:]))

    assert traveled(slow) < traveled(normal) < traveled(fast)


def test_모르는_속도는_보통으로_본다():
    assert dot_follow_timeline(60, "turbo").speed_hz == DOT_SPEED_HZ["normal"]


def test_너무_짧게_설정해도_패턴_1개는_보장한다():
    for seconds in (10, 11):
        t = dot_follow_timeline(seconds)
        assert t.total_seconds == MIN_DOT_SECONDS == 12
        assert t.segments == 1
    step = dot_follow_timeline(10).step_at(5.0)
    assert step.phase is Phase.TRACK


def test_긴_설정에서는_패턴이_처음부터_다시_돈다():
    t = dot_follow_timeline(600)
    assert t.segments == 66  # (600 - 6) / 9 ≈ 66
    assert t.pattern_at(6).key == t.pattern_at(0).key
    assert t.pattern_at(65).key == DOT_PATTERNS[65 % 6].key


def test_패턴_하나의_길이는_약_9초():
    for duration in (60, 120, 300):
        t = dot_follow_timeline(duration)
        assert 8.0 <= t._segment_seconds <= 10.0  # noqa: SLF001


def test_점_따라가기는_마무리가_끝나는_시점에_완료되고_바로_끝난다():
    t = dot_follow_timeline(60)
    assert not t.step_at(59.99).finished and not t.step_at(59.99).done
    end = t.step_at(60)
    assert end.finished and end.done  # 먼 곳 바라보기 없이 바로 끝난다
    assert end.phase is Phase.FINISH and end.countdown is None and end.dot == DOT_CENTER
    assert t.step_at(999).done and t.step_at(999).countdown is None


def test_진행률은_운동_동안_차오르고_끝난_뒤에도_가득이다():
    t = dot_follow_timeline(60)
    rising = [t.step_at(i / 10).progress for i in range(0, 600)]
    assert rising[0] == 0.0 and rising == sorted(rising)
    assert t.step_at(60).progress == 1.0 and t.step_at(70).progress == 1.0


def test_점_따라가기에는_눈_모양이_없고_깜빡임에는_점이_없다():
    dot_step = dot_follow_timeline(60).step_at(10)
    assert dot_step.eye_openness is None and dot_step.dot is not None
    blink_step = blink_timeline(66).step_at(10)
    assert blink_step.dot is None and blink_step.eye_openness is not None


def test_음수_경과_시간은_처음으로_본다():
    assert dot_follow_timeline(60).step_at(-5).phase is Phase.PREPARE


def test_추적_단계는_소리_없이_진행한다():
    assert SPOKEN[Phase.TRACK] is None
    assert MESSAGES[Phase.TRACK] == ""  # 문구는 패턴이 정한다
    assert set(SPOKEN) == set(Phase) == set(MESSAGES)


def test_마무리_길이는_깜빡임과_같다():
    assert FINISH_SECONDS == 3 and PREPARE_SECONDS == 3


# ---- 운동 선택 ----


def settings(blink=True, dot=True):
    return ExercisesSettings(blink=BlinkSettings(enabled=blink), dot_follow=DotFollowSettings(enabled=dot))


# ---- 운동 길이 프리셋 ----


def test_프리셋은_짧게_보통_길게_세_가지():
    from eyeexercise.core.exercises import LENGTH_PRESETS

    assert [(p.key, p.label) for p in LENGTH_PRESETS] == [("short", "짧게"), ("normal", "보통"), ("long", "길게")]
    assert [(p.blink_cycles, p.dot_seconds) for p in LENGTH_PRESETS] == [(3, 30), (5, 60), (10, 90)]


def test_보통은_현재_기본_설정과_같다():
    from eyeexercise.core.exercises import current_preset
    from eyeexercise.core.settings import Settings

    assert current_preset(Settings().exercises) == "normal"


def test_사이클_수와_설정_시간은_서로_바꿀_수_있다():
    from eyeexercise.core.exercises import blink_cycles_for_seconds, blink_seconds_for_cycles

    assert [blink_seconds_for_cycles(n) for n in (1, 5, 10, 15)] == [12, 36, 66, 96]
    assert [blink_cycles_for_seconds(s) for s in (12, 36, 66, 96)] == [1, 5, 10, 15]
    for cycles in range(1, 50):  # 어느 사이클 수든 되돌려도 같다
        assert blink_cycles_for_seconds(blink_seconds_for_cycles(cycles)) == cycles


def test_사이클_수가_0이하여도_최소_한_사이클():
    from eyeexercise.core.exercises import blink_seconds_for_cycles

    assert blink_seconds_for_cycles(0) == blink_seconds_for_cycles(1) == 12


def test_사이클_수로_만든_시간은_설정_범위_안이다():
    from eyeexercise.core.exercises import blink_cycles_for_seconds, blink_seconds_for_cycles
    from eyeexercise.core.settings import BLINK_SECONDS_RANGE

    top = blink_cycles_for_seconds(BLINK_SECONDS_RANGE[1])  # 설정 최댓값(96초)이 몇 사이클인지
    assert BLINK_SECONDS_RANGE[0] <= blink_seconds_for_cycles(1) and blink_seconds_for_cycles(top) <= BLINK_SECONDS_RANGE[1]
    assert (blink_cycles_for_seconds(BLINK_SECONDS_RANGE[0]), top) == (1, 15)  # 깜빡임은 1~15회


def test_프리셋을_고르면_두_운동의_시간이_함께_바뀐다():
    from eyeexercise.core.exercises import preset_changes
    from eyeexercise.core.settings import Settings, with_changes

    s = with_changes(Settings(), preset_changes("long"))
    assert s.exercises.blink.duration_seconds == 66 and s.exercises.dot_follow.duration_seconds == 90
    s = with_changes(Settings(), preset_changes("short"))
    assert s.exercises.blink.duration_seconds == 24 and s.exercises.dot_follow.duration_seconds == 30


def test_모든_프리셋의_값은_설정_범위를_벗어나지_않아_보정되지_않는다():
    from eyeexercise.core.exercises import LENGTH_PRESETS, current_preset, preset_changes
    from eyeexercise.core.settings import Settings, with_changes

    for preset in LENGTH_PRESETS:
        s = with_changes(Settings(), preset_changes(preset.key))
        assert current_preset(s.exercises) == preset.key  # 보정 때문에 다른 값이 되면 프리셋으로 인식되지 않는다


def test_고급_설정에서_따로_정하면_프리셋이_없다():
    from eyeexercise.core.exercises import current_preset
    from eyeexercise.core.settings import Settings, with_changes

    assert current_preset(with_changes(Settings(), {"exercises.blink.duration_seconds": 70}).exercises) is None
    assert current_preset(with_changes(Settings(), {"exercises.dot_follow.duration_seconds": 45}).exercises) is None
    assert current_preset(with_changes(Settings(), {"exercises.blink.duration_seconds": 24}).exercises) is None  # 한쪽만 짧게는 프리셋이 아니다


def test_알_수_없는_프리셋은_거부한다():
    import pytest

    from eyeexercise.core.exercises import preset_changes

    with pytest.raises(KeyError):
        preset_changes("huge")


def test_프리셋_길이는_짧게_보통_길게_순으로_길어진다():
    from eyeexercise.core.exercises import LENGTH_PRESETS, blink_seconds_for_cycles

    blink = [blink_seconds_for_cycles(p.blink_cycles) for p in LENGTH_PRESETS]
    dot = [p.dot_seconds for p in LENGTH_PRESETS]
    assert blink == sorted(blink) and dot == sorted(dot) and len(set(blink)) == 3 and len(set(dot)) == 3


def test_점을_따라가는_동안에만_지금_경로_번호를_알려_준다():
    timeline = dot_follow_timeline(60)  # 패턴 6개, 9초씩
    assert timeline.step_at(1).pattern is None  # 준비
    for index in range(6):
        assert timeline.step_at(PREPARE_SECONDS + index * 9 + 4).pattern == index
    assert timeline.step_at(58).pattern is None  # 마무리
    assert timeline.step_at(60 + 5).pattern is None  # 먼 곳 바라보기
    assert [timeline.step_at(PREPARE_SECONDS + i * 9 + 4).message for i in range(6)] == [p.message for p in DOT_PATTERNS]


def test_패턴이_6개보다_많이_필요하면_번호가_처음부터_다시_돈다():
    timeline = dot_follow_timeline(3 + 8 * 9 + 3)  # 패턴 8개
    assert [timeline.step_at(PREPARE_SECONDS + i * 9 + 4).pattern for i in range(8)] == [0, 1, 2, 3, 4, 5, 0, 1]
