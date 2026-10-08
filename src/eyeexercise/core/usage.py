"""스크린 타임(PC 사용 시간). 입력 여부만 보고 사용 중인 시간을 시간대별로 쌓는다 (파일 I/O와 GUI 없음).

마지막 입력 이후 `threshold`초가 지나지 않았으면 그 시간을 사용 중으로 센다. 입력 내용, 프로그램 이름,
창 제목은 보지도 저장하지도 않는다. 이 앱이 실행 중인 시간만 잴 수 있다.

저장은 주입받은 `save` 콜백이 맡는다. 사용자가 직접 입력한 데이터가 아니라서, 저장에 실패해도
경고만 남기고 측정은 계속한다.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, tzinfo
from typing import Any

from eyeexercise.core.clock import Clock
from eyeexercise.core.idle import IdleSource

log = logging.getLogger(__name__)

USAGE_VERSION = 1
HOURS = 24
HOUR_SECONDS = 3600.0
MAX_TICK_GAP_SECONDS = 10.0  # 이보다 오래 건너뛴 구간(절전 등)은 사용으로 세지 않는다
FLUSH_INTERVAL_SECONDS = 60.0


def _clamp_seconds(value: float) -> float:
    """한 시간대의 초를 0~3600으로 보정한다. NaN은 0으로 본다.

    파일에서 읽은 아주 큰 정수는 float로 바꾸면 OverflowError라서, 바꾸기 전에 범위부터 자른다.
    """
    if value != value:  # NaN
        return 0.0
    return float(max(0, min(HOUR_SECONDS, value)))


class UsageLog:
    """날짜별·시간대별 사용 시간(초)."""

    def __init__(self, days: Mapping[date, Sequence[float]] | None = None) -> None:
        self._days: dict[date, list[float]] = {}
        for day, hours in (days or {}).items():
            self._days[day] = [_clamp_seconds(v) for v in hours]

    @property
    def days(self) -> dict[date, list[float]]:
        return {day: list(hours) for day, hours in self._days.items()}

    def add(self, when: datetime, seconds: float) -> None:
        """when이 속한 시간대에 seconds를 더한다. 한 시간대는 3600초를 넘지 않는다."""
        if seconds <= 0:
            return
        hours = self._days.setdefault(when.date(), [0.0] * HOURS)
        hours[when.hour] = min(HOUR_SECONDS, hours[when.hour] + seconds)

    def hourly(self, day: date) -> list[float]:
        """그 날의 24개 시간대별 사용 시간. 기록이 없으면 모두 0."""
        return list(self._days.get(day, [0.0] * HOURS))

    def total(self, day: date) -> float:
        return sum(self._days.get(day, ()))


class UsageTracker:
    def __init__(
        self,
        usage: UsageLog,
        clock: Clock,
        idle_source: IdleSource,
        threshold_seconds: Callable[[], float],
        save: Callable[[UsageLog], None] | None = None,
        tz: tzinfo | None = None,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
    ) -> None:
        self._usage = usage
        self._clock = clock
        self._idle = idle_source
        self._threshold = threshold_seconds
        self._save = save
        self._tz = tz
        self._flush_interval = flush_interval
        self._last_tick: float | None = None
        self._last_flush = clock.monotonic()
        self._dirty = False

    @property
    def usage(self) -> UsageLog:
        return self._usage

    def tick(self) -> None:
        """1초마다 부른다. 지난 tick 이후 시간을, 사용 중이었다면 지금 시간대에 더한다."""
        now = self._clock.monotonic()
        previous, self._last_tick = self._last_tick, now
        if previous is not None:
            dt = now - previous
            if 0 < dt <= MAX_TICK_GAP_SECONDS and self._idle.idle_seconds() < self._threshold():
                self._usage.add(self._clock.now().astimezone(self._tz), dt)
                self._dirty = True
        if self._dirty and now - self._last_flush >= self._flush_interval:
            self.flush()

    def flush(self) -> None:
        """쌓인 기록을 저장한다. 앱을 끝낼 때도 불러서 마지막 구간을 잃지 않게 한다."""
        if not self._dirty or self._save is None:
            return
        self._last_flush = self._clock.monotonic()
        try:
            self._save(self._usage)
        except OSError:
            log.warning("스크린 타임 저장에 실패했습니다.", exc_info=True)
            return  # 다음 기회에 다시 저장한다
        self._dirty = False


def usage_to_dict(usage: UsageLog) -> dict:
    return {
        "version": USAGE_VERSION,
        "days": {day.isoformat(): [round(v, 1) for v in hours] for day, hours in sorted(usage.days.items())},
    }


def usage_from_dict(data: Any) -> UsageLog:
    """깨진 날은 건너뛰고 나머지는 살린다. 범위를 벗어난 값은 0~3600초로 보정한다."""
    raw_days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(raw_days, dict):
        return UsageLog()
    days: dict[date, list[float]] = {}
    for key, hours in raw_days.items():
        try:
            day = date.fromisoformat(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(hours, list) or len(hours) != HOURS:
            continue
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in hours):
            continue
        days[day] = hours
    return UsageLog(days)
