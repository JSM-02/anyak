"""홈 화면에 쓰는 판단과 값 (GUI·파일 없음).

오늘 하루를 한눈에 보여 주는 값(휴식 달성률, 스크린 타임, 눈 운동 진행)과, 타이머 진행률·게이지 색 같은
화면 규칙을 Qt 없이 계산해 테스트할 수 있게 한다.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, tzinfo

from eyeexercise.core.history import ACTIVITY_REST, HistoryEvent
from eyeexercise.core.offer import exercises_done_today
from eyeexercise.core.stats import Period, events_of, rest_stats
from eyeexercise.core.usage import UsageLog

GAUGE_TARGET = 0.8  # 휴식 달성률 목표선
GAUGE_MID = 0.5  # 이보다 낮으면 빨강

TONE_GOOD, TONE_MID, TONE_LOW, TONE_NONE = "good", "mid", "low", "none"


def gauge_tone(rate: float | None) -> str:
    """달성률(0~1)의 색 단계. 80% 이상 good(초록), 50~79% mid(노랑), 50% 미만 low(빨강). 달성률이 없으면 none."""
    if rate is None:
        return TONE_NONE
    if rate >= GAUGE_TARGET:
        return TONE_GOOD
    if rate >= GAUGE_MID:
        return TONE_MID
    return TONE_LOW


def timer_progress(remaining: float | None, target: float | None) -> float:
    """카운트다운이 얼마나 지났는지(0~1). 세고 있지 않으면 0."""
    if remaining is None or not target or target <= 0:
        return 0.0
    return min(1.0, max(0.0, 1.0 - remaining / target))



@dataclass(frozen=True)
class HomeSummary:
    """오늘의 요약. 홈 화면의 게이지와 타일이 이 값을 그린다."""

    rests: int  # 오늘 마친 눈 휴식 횟수
    recommended: int  # 오늘 사용 시간에 맞는 권장 휴식 횟수
    rate: float | None  # 휴식 달성률(0~1). 권장 횟수가 0이면 None
    screen_seconds: float  # 오늘 스크린 타임(초)
    longest_seconds: float  # 오늘의 최장 연속 사용 시간(초)
    exercises: int  # 오늘 마친 눈 운동 횟수
    exercise_goal: int  # 하루 운동 목표


def home_summary(
    events: Iterable[HistoryEvent],
    usage: UsageLog,
    now: datetime,
    interval_minutes: int,
    exercise_goal: int,
    tz: tzinfo | None = None,
) -> HomeSummary:
    events = list(events)
    today = now.astimezone(tz).date()
    stats = rest_stats(Period.DAY, today, usage, events_of(events, ACTIVITY_REST), now, tz, interval_minutes)
    return HomeSummary(
        rests=stats.rests,
        recommended=stats.recommended,
        rate=stats.rate,
        screen_seconds=usage.total(today),
        longest_seconds=stats.longest_seconds,
        exercises=exercises_done_today(events, now, tz),
        exercise_goal=exercise_goal,
    )
