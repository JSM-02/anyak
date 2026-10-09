from eyeexercise.core.exercises import (
    EXERCISE_DOT_FOLLOW,
    EXERCISE_REST,
    LOOK_AWAY_SECONDS,
    MESSAGES,
    SPOKEN,
    ExerciseStep,
    LookAwayTimeline,
    Phase,
    exercise_timeline,
)
from eyeexercise.core.settings import Settings, with_changes

# 눈 휴식은 알림 팝업 안에서 먼 곳을 20초 바라보는 것이다(LookAwayTimeline). 점 따라가기는 test_dot_follow.py에서 시험한다.


# ---- 눈 휴식: 먼 곳 바라보기 20초 ----


def test_눈_휴식은_먼_곳_바라보기_20초_카운트다운이다():
    t = LookAwayTimeline()
    assert LOOK_AWAY_SECONDS == 20 and t.total_seconds == 0
    first = t.step_at(0)
    assert first.phase is Phase.LOOK_AWAY and first.countdown == 20 and not first.done
    assert t.step_at(10.5).countdown == 10
    assert t.step_at(19.99).countdown == 1 and not t.step_at(19.99).done


def test_20초가_지나야_끝난다():
    t = LookAwayTimeline()
    end = t.step_at(LOOK_AWAY_SECONDS)
    assert end.done and end.countdown == 0
    assert t.step_at(999).done


def test_음수_경과_시간은_처음으로_본다():
    assert LookAwayTimeline().step_at(-3).countdown == 20


def test_진행률은_먼_곳_바라보기_동안_1에서_0으로_줄어든다():
    t = LookAwayTimeline()
    values = [t.step_at(i / 10).progress for i in range(0, 200)]
    assert values[0] == 1.0 and values == sorted(values, reverse=True) and values[-1] > 0


def test_눈_휴식은_기록에서_휴식_이름으로_남는다():
    # 저장된 기록의 이름은 예전 깜빡임 운동의 "blink"를 그대로 써서 이미 쌓인 기록이 이어진다
    assert LookAwayTimeline.exercise == EXERCISE_REST == "blink"
    assert EXERCISE_REST != EXERCISE_DOT_FOLLOW


def test_눈_휴식_단계에는_점이_없고_경로_번호도_없다():
    step = LookAwayTimeline().step_at(5)
    assert step.dot is None and step.pattern is None


def test_단계는_네_가지뿐이다():
    assert {p.name for p in Phase} == {"PREPARE", "TRACK", "FINISH", "LOOK_AWAY"}  # 깜빡임 단계(감기·유지·뜨기·쉬기)는 없앴다


# ---- 안내 문구와 소리 ----


def test_단계마다_문구와_음성_정의가_있다():
    assert set(MESSAGES) == set(Phase) == set(SPOKEN)
    assert "먼 곳" in MESSAGES[Phase.LOOK_AWAY]
    assert SPOKEN[Phase.LOOK_AWAY] and "먼 곳" in SPOKEN[Phase.LOOK_AWAY]
    assert SPOKEN[Phase.TRACK] is None  # 눈을 뜨고 점을 보는 운동이라 소리 없이 진행한다


def test_운동_단계에는_눈_모양_정보가_없다():
    assert not hasattr(ExerciseStep(Phase.LOOK_AWAY, "", 1.0, True), "eye_openness")


# ---- 눈 운동 선택 ----


def test_운동은_점_따라가기이고_꺼져_있으면_없다():
    assert exercise_timeline(Settings().exercises).total_seconds == 60
    assert exercise_timeline(with_changes(Settings(), {"exercises.dot_follow.enabled": False}).exercises) is None
