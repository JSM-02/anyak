from datetime import datetime, timedelta, timezone

from eyeexercise.core.formatting import home_timer
from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.home import (
    GAUGE_MID,
    GAUGE_TARGET,
    gauge_tone,
    home_summary,
    timer_progress,
)
from eyeexercise.core.scheduler import State
from eyeexercise.core.usage import UsageLog

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)


def at(hour, minute=0, day=7):
    return datetime(2026, 10, day, hour, minute, tzinfo=KST)


def rest(ts):
    return HistoryEvent(ts, "completed", "blink", 36)


def exercise(ts):
    return HistoryEvent(ts, "completed", "dot_follow", 60)


# ---- 게이지 색 단계 ----


def test_달성률_색_단계는_80_50을_경계로_나뉜다():
    assert gauge_tone(1.0) == "good"
    assert gauge_tone(GAUGE_TARGET) == "good"
    assert gauge_tone(0.79) == "mid"
    assert gauge_tone(GAUGE_MID) == "mid"
    assert gauge_tone(0.49) == "low"
    assert gauge_tone(0.0) == "low"


def test_달성률이_없으면_색_단계도_없다():
    assert gauge_tone(None) == "none"


# ---- 타이머 진행률 ----


def test_진행률은_지난_비율이다():
    assert timer_progress(1200, 1200) == 0.0
    assert timer_progress(600, 1200) == 0.5
    assert timer_progress(0, 1200) == 1.0


def test_세고_있지_않으면_진행률은_0이다():
    assert timer_progress(None, None) == 0.0
    assert timer_progress(None, 1200) == 0.0
    assert timer_progress(30, 0) == 0.0


def test_진행률은_0에서_1_사이로_보정한다():
    assert timer_progress(-5, 100) == 1.0
    assert timer_progress(500, 100) == 0.0



# ---- 홈 타이머 문구 ----


def test_홈_타이머_문구는_상태마다_다르다():
    assert home_timer(State.RUNNING, 754) == ("다음 눈 휴식까지", "12:34")
    assert home_timer(State.SNOOZED, 290) == ("다시 알림까지", "4:50")
    assert home_timer(State.PAUSED, 754) == ("일시정지됨", "12:34")
    assert home_timer(State.DUE, None) == ("눈 휴식 시간", "지금")
    assert home_timer(State.EXERCISING, None, "rest") == ("눈 휴식 중", "–")
    assert home_timer(State.EXERCISING, None, "exercise") == ("눈 운동 중", "–")


# ---- 오늘 요약 ----


def test_오늘_요약은_휴식_달성률과_스크린_타임과_운동_횟수를_모은다():
    usage = UsageLog()
    for hour in (9, 10, 11, 13):  # 4시간 사용 → 20분 주기에서 권장 12회
        usage.add(at(hour, 59), 3600)
    events = [rest(at(9, 30)) for _ in range(6)] + [exercise(at(10)), exercise(at(11))]
    s = home_summary(events, usage, NOW, interval_minutes=20, exercise_goal=2, tz=KST)
    assert (s.rests, s.recommended, s.rate) == (6, 12, 0.5)
    assert s.screen_seconds == 4 * 3600
    assert s.exercises == 2 and s.exercise_goal == 2
    assert s.longest_seconds > 0


def test_어제_기록은_오늘_요약에_들어가지_않는다():
    usage = UsageLog()
    usage.add(at(10, 59, day=6), 3600)
    events = [rest(at(10, 0, day=6)), exercise(at(11, 0, day=6))]
    s = home_summary(events, usage, NOW, 20, 2, KST)
    assert (s.rests, s.recommended, s.rate, s.screen_seconds, s.exercises) == (0, 0, None, 0, 0)


def test_사용_시간이_1분도_안_되면_달성률이_없다():
    usage = UsageLog()
    usage.add(at(10, 10), 30)
    s = home_summary([rest(at(10, 5))], usage, NOW, 20, 2, KST)
    assert s.recommended == 0 and s.rate is None


def test_권장보다_많이_쉬어도_달성률은_100퍼센트가_최대다():
    usage = UsageLog()
    usage.add(at(10, 59), 3600)  # 권장 3회
    events = [rest(at(10, m)) for m in range(0, 50, 10)]  # 5회
    s = home_summary(events, usage, NOW, 20, 2, KST)
    assert s.rests == 5 and s.rate == 1.0


def test_휴식_주기가_바뀌면_권장_횟수가_바뀐다():
    usage = UsageLog()
    usage.add(at(10, 59), 3600)
    assert home_summary([], usage, NOW, 20, 2, KST).recommended == 3
    assert home_summary([], usage, NOW, 30, 2, KST).recommended == 2


def test_건너뜀과_미룸과_눈_운동은_휴식_횟수에_세지_않는다():
    usage = UsageLog()
    usage.add(at(10, 59), 3600)
    events = [
        HistoryEvent(at(10, 5), "skipped", activity="rest"),
        HistoryEvent(at(10, 6), "snoozed", activity="rest"),
        exercise(at(10, 7)),
    ]
    s = home_summary(events, usage, NOW, 20, 2, KST)
    assert s.rests == 0 and s.exercises == 1
