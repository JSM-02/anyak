"""휴식·운동 기록 모델. 이벤트 단위로 쌓고, 일별 집계는 여기서 계산한다 (파일 I/O 없음).

눈 휴식(깜빡임 + 먼 곳 바라보기)과 눈 운동(점 따라가기)을 구분한다. 완료 이벤트는 운동 종류(`exercise`)로,
건너뜀·미룸은 `activity`에 저장한 값으로 구분한다. `activity`가 없는 옛 건너뜀·미룸은 휴식인지 운동인지
알 수 없어서 `events`(집계에 쓰는 목록)에서 빠진다. 파일에는 그대로 남는다.

저장은 주입받은 `save` 콜백이 맡는다. core는 파일을 모르고, 저장 실패가 앱을 멈추게 하지도 않는다.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Any

from eyeexercise.core.exercises import EXERCISE_BLINK

log = logging.getLogger(__name__)

HISTORY_VERSION = 1
EVENT_COMPLETED = "completed"
EVENT_SNOOZED = "snoozed"
EVENT_SKIPPED = "skipped"
EVENT_TYPES = (EVENT_COMPLETED, EVENT_SNOOZED, EVENT_SKIPPED)

ACTIVITY_REST = "rest"  # 눈 휴식: 깜빡임 + 먼 곳 바라보기
ACTIVITY_EXERCISE = "exercise"  # 눈 운동: 점 따라가기
ACTIVITIES = (ACTIVITY_REST, ACTIVITY_EXERCISE)


@dataclass(frozen=True)
class HistoryEvent:
    ts: datetime
    type: str
    exercise: str | None = None
    duration_seconds: int | None = None
    activity: str | None = None  # 건너뜀·미룸이 휴식인지 운동인지. 완료 이벤트는 exercise로 알 수 있어 저장하지 않는다


def activity_of(event: HistoryEvent) -> str | None:
    """이벤트가 휴식(rest)인지 운동(exercise)인지. 옛 건너뜀·미룸처럼 알 수 없으면 None.

    완료는 깜빡임이면 휴식, 그 밖의 운동(점 따라가기 등)은 운동이다.
    """
    if event.type == EVENT_COMPLETED:
        return ACTIVITY_REST if event.exercise == EXERCISE_BLINK else ACTIVITY_EXERCISE
    return event.activity


@dataclass(frozen=True)
class DailySummary:
    date: date
    completed: int = 0
    skipped: int = 0
    snoozed: int = 0
    exercise_seconds: int = 0


def summarize_by_day(events: Iterable[HistoryEvent], tz: tzinfo | None = None) -> dict[date, DailySummary]:
    """로컬 날짜 기준으로 일별 집계를 만든다. `tz`가 None이면 시스템 로컬 시간대를 쓴다."""
    result: dict[date, DailySummary] = {}
    for e in events:
        day = e.ts.astimezone(tz).date()
        s = result.get(day, DailySummary(date=day))
        if e.type == EVENT_COMPLETED:
            s = DailySummary(
                day, s.completed + 1, s.skipped, s.snoozed, s.exercise_seconds + (e.duration_seconds or 0)
            )
        elif e.type == EVENT_SKIPPED:
            s = DailySummary(day, s.completed, s.skipped + 1, s.snoozed, s.exercise_seconds)
        elif e.type == EVENT_SNOOZED:
            s = DailySummary(day, s.completed, s.skipped, s.snoozed + 1, s.exercise_seconds)
        result[day] = s
    return result


class History:
    def __init__(
        self,
        events: Iterable[HistoryEvent] = (),
        save: Callable[[list[HistoryEvent]], None] | None = None,
    ) -> None:
        self._events = list(events)
        self._save = save

    @property
    def events(self) -> tuple[HistoryEvent, ...]:
        """집계와 화면에 쓰는 기록. 휴식인지 운동인지 알 수 없는 옛 건너뜀·미룸은 뺀다."""
        return tuple(e for e in self._events if e.type == EVENT_COMPLETED or e.activity is not None)

    def record_completed(self, ts: datetime, exercise: str, duration_seconds: int) -> None:
        self._append(HistoryEvent(ts, EVENT_COMPLETED, exercise, max(0, duration_seconds)))

    def record_snoozed(self, ts: datetime, activity: str = ACTIVITY_REST) -> None:
        self._append(HistoryEvent(ts, EVENT_SNOOZED, activity=_valid_activity(activity)))

    def record_skipped(self, ts: datetime, activity: str = ACTIVITY_REST) -> None:
        self._append(HistoryEvent(ts, EVENT_SKIPPED, activity=_valid_activity(activity)))

    def summarize(self, tz: tzinfo | None = None) -> dict[date, DailySummary]:
        return summarize_by_day(self.events, tz)

    def _append(self, event: HistoryEvent) -> None:
        self._events.append(event)
        if self._save is None:
            return
        try:
            self._save(list(self._events))
        except OSError:
            # 기록 저장에 실패해도 알림 동작은 계속한다. 메모리의 기록은 유지된다.
            log.warning("기록 저장에 실패했습니다.", exc_info=True)


def _valid_activity(activity: str) -> str:
    if activity not in ACTIVITIES:
        raise ValueError(f"알 수 없는 활동: {activity}")
    return activity


def history_to_dict(events: Iterable[HistoryEvent]) -> dict:
    items = []
    for e in events:
        item: dict[str, Any] = {"ts": e.ts.isoformat(timespec="seconds"), "type": e.type}
        if e.exercise is not None:
            item["exercise"] = e.exercise
        if e.duration_seconds is not None:
            item["duration_seconds"] = e.duration_seconds
        if e.activity is not None:
            item["activity"] = e.activity
        items.append(item)
    return {"version": HISTORY_VERSION, "events": items}


def _event_from_dict(raw: Any) -> HistoryEvent | None:
    """잘못된 이벤트는 None. 한 건이 깨졌다고 전체 기록을 버리지 않는다."""
    if not isinstance(raw, dict) or raw.get("type") not in EVENT_TYPES:
        return None
    try:
        ts = datetime.fromisoformat(raw["ts"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        local = ts.astimezone()
    except (OSError, OverflowError, ValueError):
        return None  # 윈도우가 로컬 시각으로 바꿀 수 있는 범위(대략 1970~3000년대)를 벗어난다
    if ts.tzinfo is None:
        ts = local  # 시간대가 없으면 로컬 시각으로 본다
    exercise = raw.get("exercise")
    if not isinstance(exercise, str):
        exercise = None
    duration = raw.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        duration = None
    activity = raw.get("activity")
    if activity not in ACTIVITIES:
        activity = None
    return HistoryEvent(ts, raw["type"], exercise, duration, activity)


def history_from_dict(data: Any) -> list[HistoryEvent]:
    raw_events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(raw_events, list):
        return []
    return [e for e in map(_event_from_dict, raw_events) if e is not None]
