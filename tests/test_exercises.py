import pytest

from eyeexercise.core.exercises import (
    CYCLE_SECONDS,
    LOOK_AWAY_SECONDS,
    MESSAGES,
    MIN_BLINK_SECONDS,
    SPOKEN,
    Phase,
    blink_timeline,
)
from eyeexercise.core.settings import Settings

# 기본 66초: 준비 3초, 사이클 10회(6초씩: 감기 2 + 유지 1 + 뜨기 2 + 쉬기 1), 마무리 3초
# 심호흡처럼 천천히. 낮은 종(감기 시작)과 높은 종(뜨기 시작)은 3초 간격이다.


def phase_at(timeline, t):
    return timeline.step_at(t).phase


def test_기본값은_한_세트_10회():
    default = Settings().exercises.blink.duration_seconds
    t = blink_timeline(default)
    assert (default, t.total_seconds, t.cycles) == (66, 66, 10)


def test_사이클은_6초():
    assert CYCLE_SECONDS == 6


def test_준비_단계():
    t = blink_timeline(66)
    step = t.step_at(0)
    assert step.phase is Phase.PREPARE and step.message == "편안하게 앉아 화면을 바라보세요"
    assert phase_at(t, 2.9) is Phase.PREPARE


@pytest.mark.parametrize(
    ("elapsed", "phase"),
    [
        (3.0, Phase.CLOSE),
        (4.9, Phase.CLOSE),
        (5.0, Phase.HOLD),
        (5.9, Phase.HOLD),
        (6.0, Phase.OPEN),  # 감기 시작 3초 뒤: 높은 종이 울리고 눈이 뜨이기 시작한다
        (7.9, Phase.OPEN),
        (8.0, Phase.REST),
        (8.9, Phase.REST),
        (9.0, Phase.CLOSE),  # 두 번째 사이클
        (15.0, Phase.CLOSE),  # 세 번째 사이클
        (57.0, Phase.CLOSE),  # 열 번째(마지막) 사이클
        (62.0, Phase.REST),
        (62.9, Phase.REST),
        (63.0, Phase.FINISH),
        (65.9, Phase.FINISH),
    ],
)
def test_시간별_단계(elapsed, phase):
    assert phase_at(blink_timeline(66), elapsed) is phase


def test_각_단계의_안내_문구():
    t = blink_timeline(66)
    for elapsed, phase in [
        (0, Phase.PREPARE),
        (3, Phase.CLOSE),
        (5, Phase.HOLD),
        (6, Phase.OPEN),
        (8, Phase.REST),
        (64, Phase.FINISH),
    ]:
        assert t.step_at(elapsed).message == MESSAGES[phase]
    assert MESSAGES[Phase.CLOSE] == "천천히 눈을 감으세요"
    assert "천천히" in MESSAGES[Phase.OPEN]
    assert "먼 곳" in MESSAGES[Phase.LOOK_AWAY]


def test_쉬는_동안에는_문구가_없다():
    t = blink_timeline(66)
    assert t.step_at(8.0).phase is Phase.REST
    assert t.step_at(8.0).message == ""
    assert all(t.step_at(i / 10).message == "" for i in range(80, 90))
    # 쉬기와 점 따라가기 전용 단계(문구는 패턴이 정한다)를 뺀 모든 단계에는 문구가 있다
    assert all(MESSAGES[p] for p in Phase if p not in (Phase.REST, Phase.TRACK))


def test_눈은_천천히_감기고_천천히_뜬다():
    t = blink_timeline(66)
    assert t.step_at(3.0).eye_openness == 1.0
    assert t.step_at(4.0).eye_openness == pytest.approx(0.5)  # 감기 2초의 절반
    assert t.step_at(5.0).eye_openness == 0.0  # 완전히 감김
    assert t.step_at(5.5).eye_openness == 0.0  # 유지
    assert t.step_at(6.0).eye_openness == 0.0  # 뜨기 시작
    assert t.step_at(7.0).eye_openness == pytest.approx(0.5)  # 뜨기 2초의 절반
    assert t.step_at(8.0).eye_openness == 1.0  # 활짝 뜸
    assert t.step_at(8.5).eye_openness == 1.0  # 쉬는 동안


def test_눈이_감기는_데_2초_뜨는_데_2초_걸린다():
    # 너무 빠르다는 피드백 반영: 감기와 뜨기가 각각 1초가 아니라 2초다
    t = blink_timeline(66)
    closing = [i / 10 for i in range(30, 50) if 0.0 < t.step_at(i / 10).eye_openness < 1.0]
    opening = [i / 10 for i in range(60, 80) if 0.0 < t.step_at(i / 10).eye_openness < 1.0]
    assert max(closing) - min(closing) == pytest.approx(1.8)
    assert max(opening) - min(opening) == pytest.approx(1.8)


def test_낮은_종과_높은_종_사이는_3초():
    # 낮은 종은 감기 시작, 높은 종은 뜨기 시작에 울린다 (소리 파일이 이 간격으로 만들어져 있다)
    t = blink_timeline(66)
    close_start = next(i / 10 for i in range(0, 660) if t.step_at(i / 10).phase is Phase.CLOSE)
    open_start = next(i / 10 for i in range(0, 660) if t.step_at(i / 10).phase is Phase.OPEN)
    assert open_start - close_start == pytest.approx(3.0)


def test_높은_종_뒤_3초_지나면_다음_사이클이_시작된다():
    t = blink_timeline(66)
    assert phase_at(t, 6.0) is Phase.OPEN and phase_at(t, 9.0) is Phase.CLOSE


def test_쉬기는_1초():
    t = blink_timeline(66)
    rest = [i / 10 for i in range(30, 90) if t.step_at(i / 10).phase is Phase.REST]  # 첫 사이클(3~9초)
    assert rest[0] == 8.0 and rest[-1] == pytest.approx(8.9)


def test_눈_뜬_정도는_항상_0에서_1_사이():
    t = blink_timeline(66)
    assert all(0.0 <= t.step_at(i / 10).eye_openness <= 1.0 for i in range(0, 900))


def test_진행률은_운동_동안_차오르고_먼_곳_보기_동안_줄어든다():
    t = blink_timeline(66)
    rising = [t.step_at(i / 10).progress for i in range(0, 660)]
    assert rising[0] == 0.0 and rising == sorted(rising)
    falling = [t.step_at(66 + i / 10).progress for i in range(0, 200)]
    assert falling[0] == 1.0 and falling == sorted(falling, reverse=True)
    assert t.step_at(86).progress == 0.0


def test_깜빡임_운동이_끝나는_시점에_finished가_된다():
    t = blink_timeline(66)
    assert not t.step_at(65.99).finished
    assert t.step_at(66).finished
    assert not t.step_at(66).done


def test_운동_직후부터_먼_곳_바라보기_20초_카운트다운():
    t = blink_timeline(66)
    first = t.step_at(66)
    assert first.phase is Phase.LOOK_AWAY and first.countdown == 20
    assert t.step_at(66.5).countdown == 20
    assert t.step_at(67.0).countdown == 19
    assert t.step_at(85.0).countdown == 1
    assert t.step_at(85.9).countdown == 1


def test_카운트다운이_끝나면_done이_된다():
    t = blink_timeline(66)
    assert not t.step_at(85.99).done
    end = t.step_at(66 + LOOK_AWAY_SECONDS)
    assert end.done and end.finished and end.countdown == 0
    assert t.step_at(999).done


def test_카운트다운은_먼_곳_보기_구간에만_있다():
    t = blink_timeline(66)
    assert all(t.step_at(i / 10).countdown is None for i in range(0, 660))


def test_음수_경과_시간은_처음으로_본다():
    assert phase_at(blink_timeline(66), -5) is Phase.PREPARE


def test_남는_시간은_마지막_쉬기가_흡수한다():
    t = blink_timeline(69)  # 69 - 6 = 63 → 사이클 10회(60초) + 남는 3초
    assert t.cycles == 10 and t.total_seconds == 69
    last_cycle_start = 3 + 9 * CYCLE_SECONDS  # 57초
    assert phase_at(t, last_cycle_start + 3) is Phase.OPEN
    assert phase_at(t, last_cycle_start + 5) is Phase.REST  # 62초: 마지막 쉬기 시작
    assert phase_at(t, 65.9) is Phase.REST  # 남는 시간까지 쉰다
    assert phase_at(t, 66.0) is Phase.FINISH
    assert phase_at(t, 9.0) is Phase.CLOSE  # 마지막 사이클 외에는 6초 그대로


def test_사이클_수는_시간에_비례한다():
    assert blink_timeline(30).cycles == 4
    assert blink_timeline(300).cycles == 49


def test_너무_짧게_설정해도_사이클_1회는_보장한다():
    for seconds in (5, 11):
        t = blink_timeline(seconds)
        assert t.total_seconds == MIN_BLINK_SECONDS == 12
        assert t.cycles == 1
    assert phase_at(blink_timeline(5), 3.0) is Phase.CLOSE


def test_모든_시간에서_끝까지_단계가_빠짐없이_이어진다():
    # 총 시간이 달라도 처음엔 준비, 끝엔 마무리 뒤 먼 곳 보기이고 중간에 깜빡임의 모든 단계가 한 번 이상 나온다
    # (점 따라가기 전용 TRACK 단계는 깜빡임에 나오지 않는다)
    for seconds in (12, 17, 66, 99, 300):
        t = blink_timeline(seconds)
        total = t.total_seconds
        phases = {t.step_at(i / 4).phase for i in range(0, (total + LOOK_AWAY_SECONDS) * 4)}
        assert phases == set(Phase) - {Phase.TRACK}
        assert phase_at(t, 0) is Phase.PREPARE
        assert phase_at(t, total - 0.1) is Phase.FINISH
        assert phase_at(t, total) is Phase.LOOK_AWAY


def test_음성_안내는_눈_감고_뜰_때와_먼_곳_보기_때_나온다():
    assert SPOKEN[Phase.CLOSE] == "눈을 감으세요"
    assert SPOKEN[Phase.OPEN] == "눈을 뜨세요"
    assert SPOKEN[Phase.LOOK_AWAY] and "먼 곳" in SPOKEN[Phase.LOOK_AWAY]
    assert SPOKEN[Phase.HOLD] is None and SPOKEN[Phase.REST] is None


def test_모든_단계에_음성_정의가_있다():
    assert set(SPOKEN) == set(Phase)
