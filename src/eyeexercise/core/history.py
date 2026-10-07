"""운동 기록 모델. 이벤트 단위로 쌓고, 일별 집계는 여기서 계산한다 (파일 I/O 없음).

저장은 주입받은 `save` 콜백이 맡는다. core는 파일을 모르고, 저장 실패가 앱을 멈추게 하지도 않는다.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Any

log = logging.getLogger(__name__)

HISTORY_VERSION = 1
EVENT_COMPLETED = "completed"
EVENT_SNOOZED = "snoozed"
EVENT_SKIPPED = "skipped"
EVENT_TYPES = (EVENT_COMPLETED, EVENT_SNOOZED, EVENT_SKIPPED)


@dataclass(frozen=True)
class HistoryEvent:
    ts: datetime
    type: str
    exercise: str | None = None
    duration_seconds: int | None = None


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
        return tuple(self._events)

    def record_completed(self, ts: datetime, exercise: str, duration_seconds: int) -> None:
        self._append(HistoryEvent(ts, EVENT_COMPLETED, exercise, max(0, duration_seconds)))

    def record_snoozed(self, ts: datetime) -> None:
        self._append(HistoryEvent(ts, EVENT_SNOOZED))

    def record_skipped(self, ts: datetime) -> None:
        self._append(HistoryEvent(ts, EVENT_SKIPPED))

    def summarize(self, tz: tzinfo | None = None) -> dict[date, DailySummary]:
        return summarize_by_day(self._events, tz)

    def last_completed_exercise(self) -> str | None:
        """가장 최근에 끝까지 마친 운동의 이름. 운동을 번갈아 고를 때 쓴다."""
        done = [e for e in self._events if e.type == EVENT_COMPLETED and e.exercise]
        return max(done, key=lambda e: e.ts).exercise if done else None

    def _append(self, event: HistoryEvent) -> None:
        self._events.append(event)
        if self._save is None:
            return
        try:
            self._save(list(self._events))
        except OSError:
            # 기록 저장에 실패해도 알림 동작은 계속한다. 메모리의 기록은 유지된다.
            log.warning("기록 저장에 실패했습니다.", exc_info=True)


def history_to_dict(events: Iterable[HistoryEvent]) -> dict:
    items = []
    for e in events:
        item: dict[str, Any] = {"ts": e.ts.isoformat(timespec="seconds"), "type": e.type}
        if e.exercise is not None:
            item["exercise"] = e.exercise
        if e.duration_seconds is not None:
            item["duration_seconds"] = e.duration_seconds
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
    if ts.tzinfo is None:
        ts = ts.astimezone()  # 시간대가 없으면 로컬 시각으로 본다
    exercise = raw.get("exercise")
    if not isinstance(exercise, str):
        exercise = None
    duration = raw.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        duration = None
    return HistoryEvent(ts, raw["type"], exercise, duration)


def history_from_dict(data: Any) -> list[HistoryEvent]:
    raw_events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(raw_events, list):
        return []
    return [e for e in map(_event_from_dict, raw_events) if e is not None]
