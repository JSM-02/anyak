from datetime import datetime, timedelta, timezone

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.offer import exercises_done_today, should_offer_exercise
from eyeexercise.core.settings import ExercisesSettings, with_changes, Settings

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=KST)


def dot(day, hour):
    return HistoryEvent(at(day, hour), "completed", "dot_follow", 60)


def blink(day, hour):
    return HistoryEvent(at(day, hour), "completed", "blink", 24)


def settings(**changes) -> ExercisesSettings:
    return with_changes(Settings(), changes).exercises


def test_휴식은_운동_횟수에_세지_않는다():
    events = [blink(7, 9), blink(7, 10), dot(7, 11)]
    assert exercises_done_today(events, NOW, KST) == 1


def test_어제와_자정_전후는_오늘이_아니다():
    events = [dot(6, 23), HistoryEvent(datetime(2026, 10, 7, 0, 1, tzinfo=KST), "completed", "dot_follow", 60)]
    assert exercises_done_today(events, NOW, KST) == 1


def test_건너뜀과_미룸은_운동으로_세지_않는다():
    events = [HistoryEvent(at(7, 9), "skipped", activity="exercise"), HistoryEvent(at(7, 10), "snoozed", activity="exercise")]
    assert exercises_done_today(events, NOW, KST) == 0


def test_목표를_채우기_전에는_운동을_제안한다():
    assert should_offer_exercise([], NOW, settings(), KST)
    assert should_offer_exercise([dot(7, 9)], NOW, settings(), KST)  # 목표 2회 중 1회


def test_목표를_채우면_제안하지_않는다():
    assert not should_offer_exercise([dot(7, 9), dot(7, 11)], NOW, settings(), KST)


def test_다음날에는_다시_제안한다():
    events = [dot(6, 9), dot(6, 11)]
    assert should_offer_exercise(events, NOW, settings(), KST)


def test_목표가_0이면_제안하지_않는다():
    assert not should_offer_exercise([], NOW, settings(**{"exercises.daily_goal": 0}), KST)


def test_점_따라가기가_꺼져_있으면_제안하지_않는다():
    assert not should_offer_exercise([], NOW, settings(**{"exercises.dot_follow.enabled": False}), KST)


def test_휴식만_많이_해도_운동은_계속_제안한다():
    events = [blink(7, h) for h in range(9, 14)]
    assert should_offer_exercise(events, NOW, settings(), KST)
