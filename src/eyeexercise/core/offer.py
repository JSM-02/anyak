"""눈 운동을 제안할지 판단한다 (GUI·파일 없음).

눈 운동(점 따라가기)은 하루 목표 횟수(`exercises.daily_goal`)만 정해 두고, 20분마다 오는 눈 휴식 알림 때
'운동도 할래요?'로 슬쩍 제안한다. 오늘 목표를 채웠거나 운동이 꺼져 있으면 제안하지 않는다.
"""

from collections.abc import Iterable
from datetime import datetime, tzinfo

from eyeexercise.core.history import ACTIVITY_EXERCISE, EVENT_COMPLETED, HistoryEvent, activity_of
from eyeexercise.core.settings import ExercisesSettings


def exercises_done_today(events: Iterable[HistoryEvent], now: datetime, tz: tzinfo | None = None) -> int:
    """오늘(로컬 날짜) 끝까지 마친 눈 운동 횟수. 눈 휴식은 세지 않는다."""
    today = now.astimezone(tz).date()
    return sum(
        1
        for e in events
        if e.type == EVENT_COMPLETED and activity_of(e) == ACTIVITY_EXERCISE and e.ts.astimezone(tz).date() == today
    )


def should_offer_exercise(
    events: Iterable[HistoryEvent], now: datetime, settings: ExercisesSettings, tz: tzinfo | None = None
) -> bool:
    """휴식 알림 때 '운동도 할래요?'를 보여 줄지."""
    if not settings.dot_follow.enabled or settings.daily_goal <= 0:
        return False
    return exercises_done_today(events, now, tz) < settings.daily_goal
