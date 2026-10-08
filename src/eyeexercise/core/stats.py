"""기록 탭에 보여 줄 요약 (GUI 없음). 일·주·월 단위로 막대 차트, 하이라이트, 하루 타임라인(최근 기록)을 만든다.

날짜는 모두 로컬 시간대 기준이다. `tz`가 None이면 시스템 로컬 시간대를 쓰고, 테스트에서는 고정 시간대를 넘긴다.
"""

import calendar
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from enum import Enum

from eyeexercise.core.exercises import EXERCISE_BLINK, EXERCISE_DOT_FOLLOW
from eyeexercise.core.history import (
    ACTIVITY_EXERCISE,
    ACTIVITY_REST,
    EVENT_COMPLETED,
    EVENT_SKIPPED,
    EVENT_SNOOZED,
    HistoryEvent,
    activity_of,
)
from eyeexercise.core.usage import UsageLog

WEEKDAYS = "월화수목금토일"  # date.weekday() 순서 (월요일 = 0). 주는 월요일에 시작한다.
EXERCISE_NAMES = {EXERCISE_BLINK: "깜빡임", EXERCISE_DOT_FOLLOW: "점 따라가기"}


class Period(Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class Bucket:
    """막대 하나. 하루 보기에서는 한 시간, 주·월 보기에서는 하루다."""

    label: str  # 축에 쓰는 짧은 글자
    title: str  # 선택했을 때 보여 주는 이름 (예: "10월 7일 (수)", "14시")
    show_label: bool  # 막대가 많을 때 축에는 일부만 글자를 쓴다
    completed: int = 0
    skipped: int = 0
    snoozed: int = 0
    exercise_seconds: int = 0
    is_current: bool = False  # 지금이 속한 막대
    is_future: bool = False  # 아직 오지 않은 막대


@dataclass(frozen=True)
class RangeSummary:
    completed: int
    skipped: int
    snoozed: int
    exercise_seconds: int
    average_per_day: float  # 지나간 날(오늘까지)만 센 하루 평균 완료 횟수
    days: int = 1  # 평균에 쓴 지나간 날 수 (아직 오지 않은 날은 뺀다)
    active_buckets: int = 0  # 완료가 한 번이라도 있었던 막대 수 (하루 보기에서는 쉰 시간대 수)


@dataclass(frozen=True)
class Highlight:
    label: str
    value: str  # 큰 글씨 값 (예: "8시간 5분")
    detail: str = ""  # 값 아래 작은 보조 설명 (예: "화요일"). 없으면 빈 문자열
    compare: str = ""  # 앞 기간과의 비교 한 줄 (예: "지난 주보다 하루 평균 0.3회 많아요"). 화살표는 화면이 붙인다
    trend: str = "same"  # compare의 추세: up / down / same


# ---- 기간 계산 ----


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def range_bounds(period: Period, anchor: date) -> tuple[date, date]:
    """anchor가 속한 기간의 첫날과 마지막 날(포함)."""
    if period is Period.DAY:
        return anchor, anchor
    if period is Period.WEEK:
        start = week_start(anchor)
        return start, start + timedelta(days=6)
    last = calendar.monthrange(anchor.year, anchor.month)[1]
    return anchor.replace(day=1), anchor.replace(day=last)


def shift_anchor(period: Period, anchor: date, steps: int) -> date:
    """기간을 steps만큼 이동한 기준일. 월은 그 달 1일로 맞춘다."""
    if period is Period.DAY:
        return anchor + timedelta(days=steps)
    if period is Period.WEEK:
        return anchor + timedelta(weeks=steps)
    index = anchor.year * 12 + (anchor.month - 1) + steps
    return date(index // 12, index % 12 + 1, 1)


def can_go_forward(period: Period, anchor: date, today: date) -> bool:
    """다음 기간이 미래만 있지 않을 때만 앞으로 갈 수 있다."""
    _, end = range_bounds(period, anchor)
    return end < today


def _weekday_text(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def range_title(period: Period, anchor: date, today: date) -> str:
    start, end = range_bounds(period, anchor)
    contains_today = start <= today <= end
    if period is Period.DAY:
        if anchor == today:
            return "오늘"
        if anchor == today - timedelta(days=1):
            return "어제"
        return f"{anchor.month}월 {anchor.day}일 ({_weekday_text(anchor)})"
    if period is Period.WEEK:
        this_week = week_start(today)
        if start == this_week:
            return "이번 주"
        if start == this_week - timedelta(weeks=1):
            return "지난 주"
        return f"{start.month}월 {start.day}일 주"
    return "이번 달" if contains_today else f"{anchor.year}년 {anchor.month}월"


def range_caption(period: Period, anchor: date) -> str:
    """제목 아래에 항상 보여 주는 날짜 범위."""
    start, end = range_bounds(period, anchor)
    if period is Period.DAY:
        return f"{anchor.year}년 {anchor.month}월 {anchor.day}일 {_weekday_text(anchor)}요일"
    if period is Period.WEEK:
        return f"{start.month}월 {start.day}일 – {end.month}월 {end.day}일"
    return f"{anchor.year}년 {anchor.month}월"


# ---- 막대 ----


def _empty_buckets(period: Period, anchor: date, now: datetime) -> list[Bucket]:
    today = now.date()
    start, end = range_bounds(period, anchor)
    if period is Period.DAY:
        buckets = []
        for hour in range(24):
            is_current = anchor == today and hour == now.hour
            is_future = anchor > today or (anchor == today and hour > now.hour)
            buckets.append(Bucket(f"{hour}시", f"{hour}시", hour % 6 == 0, is_current=is_current, is_future=is_future))
        return buckets
    buckets = []
    day = start
    while day <= end:
        if period is Period.WEEK:
            label, show = _weekday_text(day), True
        else:
            label, show = str(day.day), (day.day - 1) % 7 == 0
        title = f"{day.month}월 {day.day}일 ({_weekday_text(day)})"
        buckets.append(Bucket(label, title, show, is_current=day == today, is_future=day > today))
        day += timedelta(days=1)
    return buckets


def build_buckets(
    period: Period,
    anchor: date,
    events: Iterable[HistoryEvent],
    now: datetime,
    tz: tzinfo | None = None,
) -> list[Bucket]:
    """기간의 막대 목록. 이벤트가 없는 시간·날도 0으로 채워서 항상 같은 개수를 돌려준다."""
    local_now = now.astimezone(tz)
    buckets = _empty_buckets(period, anchor, local_now)
    start, end = range_bounds(period, anchor)
    counts = [[0, 0, 0, 0] for _ in buckets]  # completed, skipped, snoozed, seconds
    for e in events:
        local = e.ts.astimezone(tz)
        if not start <= local.date() <= end:
            continue
        index = local.hour if period is Period.DAY else (local.date() - start).days
        c = counts[index]
        if e.type == EVENT_COMPLETED:
            c[0] += 1
            c[3] += e.duration_seconds or 0
        elif e.type == EVENT_SKIPPED:
            c[1] += 1
        elif e.type == EVENT_SNOOZED:
            c[2] += 1
    return [
        Bucket(b.label, b.title, b.show_label, c[0], c[1], c[2], c[3], b.is_current, b.is_future)
        for b, c in zip(buckets, counts, strict=True)
    ]


def summarize_range(period: Period, anchor: date, buckets: Iterable[Bucket], now: datetime, tz: tzinfo | None = None) -> RangeSummary:
    buckets = list(buckets)
    completed = sum(b.completed for b in buckets)
    start, end = range_bounds(period, anchor)
    today = now.astimezone(tz).date()
    elapsed_days = max(0, (min(end, today) - start).days + 1)
    return RangeSummary(
        completed=completed,
        skipped=sum(b.skipped for b in buckets),
        snoozed=sum(b.snoozed for b in buckets),
        exercise_seconds=sum(b.exercise_seconds for b in buckets),
        average_per_day=completed / elapsed_days if elapsed_days else 0.0,
        days=elapsed_days,
        active_buckets=sum(1 for b in buckets if b.completed > 0 and not b.is_future),
    )


def rest_slot_count(period: Period, anchor: date, events: Iterable[HistoryEvent], tz: tzinfo | None = None) -> int:
    """기간 동안 눈 휴식을 마친 시간대(날짜 + 시)의 수. 같은 시간대에 여러 번 쉬어도 한 번으로 센다."""
    start, end = range_bounds(period, anchor)
    slots = set()
    for e in events:
        if e.type != EVENT_COMPLETED:
            continue
        local = e.ts.astimezone(tz)
        if start <= local.date() <= end:
            slots.add((local.date(), local.hour))
    return len(slots)


SKIP_KINDS = {EVENT_SKIPPED: "건너뜀", EVENT_SNOOZED: "미룸"}


def rest_highlights(period: Period, summary: RangeSummary, rest: "RestStats", slots: int, kind: str = EVENT_SKIPPED) -> list[Highlight]:
    """눈 휴식 하이라이트 카드 세 개: 휴식 달성률, 건너뜀(또는 미룸. kind로 고른다), 휴식 시간대.

    휴식 시간대는 하루 보기에서는 쉰 시간대 수, 주·월 보기에서는 지나간 날 기준 하루 평균이다."""
    if rest.rate is None:
        rate = Highlight("휴식 달성률", "–", "사용 시간이 짧아요")
    else:
        rate = Highlight("휴식 달성률", f"{round(rest.rate * 100)}%", f"{rest.rests}회 / 권장 {rest.recommended}회")
    count = summary.skipped if kind == EVENT_SKIPPED else summary.snoozed
    second = Highlight(SKIP_KINDS[kind], f"{count}회")
    if period is Period.DAY:
        third = Highlight("휴식 시간대", f"{slots}개")
    else:
        third = Highlight("휴식 시간대", f"{_per_day(slots, summary.days):.1f}개", "하루 평균")
    return [rate, second, third]


# ---- 표시 형식 ----


def format_duration(seconds: int) -> str:
    """"45초", "1분 6초", "21분", "1시간 5분". 10분 이상은 초를 생략한다."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}초"
    minutes, rest = divmod(seconds, 60)
    if minutes < 10:
        return f"{minutes}분 {rest}초" if rest else f"{minutes}분"
    if minutes < 60:
        return f"{minutes}분"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}시간 {minutes}분" if minutes else f"{hours}시간"


# ---- 하루 타임라인 (최근 기록) ----

MIN_ACTIVE_SECONDS = 60  # 한 시간대에 이만큼은 써야 '사용한 시간대'로 본다


@dataclass(frozen=True)
class TimelineMark:
    """하루 줄 위의 기록 하나 (휴식·운동 완료, 건너뜀, 미룸)."""

    minute: float  # 자정부터의 분 (0~1440)
    kind: str  # completed / skipped / snoozed
    activity: str  # rest(눈 휴식) / exercise(눈 운동)
    exercise: str  # 완료한 운동의 종류 키. 그 외는 빈 문자열
    tip: str  # 마우스를 올렸을 때 보여 줄 설명 ("14:32 점 따라가기 · 1분")


@dataclass(frozen=True)
class TimelineDay:
    title: str  # "오늘", "어제", "10월 3일 (토)"
    hours: list[float]  # 시간대별(0~23시) 스크린 타임(초)
    marks: list[TimelineMark]  # 시간순
    total_seconds: float
    rests: int  # 마친 눈 휴식 횟수
    exercises: int  # 마친 눈 운동 횟수
    skipped: int
    snoozed: int

    @property
    def is_empty(self) -> bool:
        return not self.marks and self.total_seconds <= 0

    def hour_marks(self, hour: int) -> list[TimelineMark]:
        """hour시(0~23)에 일어난 기록들. 시간순."""
        return [m for m in self.marks if int(m.minute // 60) == hour]

    def exercises_in_hour(self, hour: int) -> int:
        """hour시에 마친 눈 운동 횟수. 격자 칸의 숫자다 (휴식은 20분마다라 칸에 쓰면 너무 많아진다)."""
        return sum(1 for m in self.hour_marks(hour) if m.kind == EVENT_COMPLETED and m.activity == ACTIVITY_EXERCISE)


def _mark(e: HistoryEvent, local: datetime) -> TimelineMark | None:
    activity = activity_of(e)
    if activity is None:  # 휴식인지 운동인지 모르는 옛 건너뜀·미룸은 그리지 않는다
        return None
    minute = local.hour * 60 + local.minute + local.second / 60
    clock = f"{local:%H:%M}"
    if e.type == EVENT_COMPLETED:
        length = f" · {format_duration(e.duration_seconds)}" if e.duration_seconds else ""
        if activity == ACTIVITY_REST:
            return TimelineMark(minute, EVENT_COMPLETED, activity, e.exercise or "", f"{clock} 눈 휴식{length}")
        name = EXERCISE_NAMES.get(e.exercise or "", e.exercise or "운동")
        return TimelineMark(minute, EVENT_COMPLETED, activity, e.exercise or "", f"{clock} {name}{length}")
    if e.type == EVENT_SKIPPED:
        return TimelineMark(minute, EVENT_SKIPPED, activity, "", f"{clock} 건너뜀")
    if e.type == EVENT_SNOOZED:
        return TimelineMark(minute, EVENT_SNOOZED, activity, "", f"{clock} 미룸")
    return None


def timeline_days(
    events: Iterable[HistoryEvent], usage: UsageLog, now: datetime, days: int = 7, tz: tzinfo | None = None
) -> list[TimelineDay]:
    """오늘부터 거슬러 올라가는 days일의 하루 타임라인. 기록이 없는 날도 한 줄을 차지한다."""
    today = now.astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)
    marks: dict[date, list[TimelineMark]] = {}
    for e in sorted(events, key=lambda e: e.ts):
        local = e.ts.astimezone(tz)
        if not first_day <= local.date() <= today:
            continue
        mark = _mark(e, local)
        if mark is not None:
            marks.setdefault(local.date(), []).append(mark)
    result = []
    for i in range(days):
        day = today - timedelta(days=i)
        hours = usage.hourly(day)
        day_marks = marks.get(day, [])

        def count(kind: str, activity: str | None = None) -> int:
            return sum(1 for m in day_marks if m.kind == kind and (activity is None or m.activity == activity))

        result.append(
            TimelineDay(
                range_title(Period.DAY, day, today),
                hours,
                day_marks,
                sum(hours),
                count(EVENT_COMPLETED, ACTIVITY_REST),
                count(EVENT_COMPLETED, ACTIVITY_EXERCISE),
                count(EVENT_SKIPPED),
                count(EVENT_SNOOZED),
            )
        )
    return result


def events_of(events: Iterable[HistoryEvent], activity: str) -> list[HistoryEvent]:
    """휴식(rest) 또는 운동(exercise) 기록만. 구분할 수 없는 옛 건너뜀·미룸은 들어가지 않는다."""
    return [e for e in events if activity_of(e) == activity]


# ---- 차트 눈금 ----

_AXIS_STEPS = (4, 6, 8, 10, 12, 16, 20, 24, 30, 40, 50, 60, 80, 100)


def nice_axis_max(value: int) -> int:
    """막대 차트의 세로축 최댓값. 가장 큰 막대가 눈금 안에 들어오는 보기 좋은 값(4, 6, 8, 10…)으로 올린다."""
    for step in _AXIS_STEPS:
        if value <= step:
            return step
    return -(-value // 100) * 100  # 100보다 크면 100 단위로 올림


# ---- 스크린 타임 ----


@dataclass(frozen=True)
class UsageBucket:
    """스크린 타임 막대 하나. 하루 보기에서는 한 시간, 주·월 보기에서는 하루다."""

    label: str
    title: str
    show_label: bool
    seconds: float = 0.0
    is_current: bool = False
    is_future: bool = False


@dataclass(frozen=True)
class UsageSummary:
    total_seconds: float
    average_per_day: float  # 지나간 날만 센 하루 평균(초)
    peak_label: str  # 가장 많이 쓴 막대 이름 ("14시", "수요일", "7일"). 사용이 없으면 빈 문자열
    peak_seconds: float
    active_buckets: int  # 조금이라도 쓴 막대 수


def build_usage_buckets(period: Period, anchor: date, usage: UsageLog, now: datetime, tz: tzinfo | None = None) -> list[UsageBucket]:
    """기간의 스크린 타임 막대. 쓰지 않은 시간·날도 0으로 채워서 항상 같은 개수를 돌려준다."""
    skeleton = _empty_buckets(period, anchor, now.astimezone(tz))
    start, _ = range_bounds(period, anchor)
    if period is Period.DAY:
        seconds = usage.hourly(anchor)
    else:
        seconds = [usage.total(start + timedelta(days=i)) for i in range(len(skeleton))]
    return [UsageBucket(b.label, b.title, b.show_label, s, b.is_current, b.is_future) for b, s in zip(skeleton, seconds, strict=True)]


def summarize_usage(period: Period, anchor: date, buckets: Iterable[UsageBucket], now: datetime, tz: tzinfo | None = None) -> UsageSummary:
    buckets = list(buckets)
    total = sum(b.seconds for b in buckets)
    start, end = range_bounds(period, anchor)
    elapsed_days = max(0, (min(end, now.astimezone(tz).date()) - start).days + 1)
    peak = max(buckets, key=lambda b: b.seconds, default=None)
    suffix = {Period.DAY: "", Period.WEEK: "요일", Period.MONTH: "일"}[period]
    return UsageSummary(
        total_seconds=total,
        average_per_day=total / elapsed_days if elapsed_days else 0.0,
        peak_label=f"{peak.label}{suffix}" if peak is not None and peak.seconds > 0 else "",
        peak_seconds=peak.seconds if peak is not None and peak.seconds > 0 else 0.0,
        active_buckets=sum(1 for b in buckets if b.seconds > 0),
    )


@dataclass(frozen=True)
class RestStats:
    """스크린 타임과 눈 휴식을 함께 본 값. 이 앱만의 지표라서 다른 스크린 타임 서비스에는 없다."""

    rests: int  # 마친 눈 휴식 횟수
    recommended: int  # 사용 시간에 맞는 권장 횟수 (하루마다 사용 시간 ÷ 휴식 주기를 올림해서 더한다. 1분도 안 쓴 날은 0회)
    longest_seconds: float  # 최장 연속 사용 시간(초)
    longest_label: str  # 그 시간이 있던 날 이름. 하루 보기에서는 빈 문자열

    @property
    def rate(self) -> float | None:
        """휴식 달성률(0~1). 권장 횟수가 0이면(사용 시간이 1분도 안 되면) None. 권장보다 많이 쉬어도 1이 최대다."""
        if self.recommended <= 0:
            return None
        return min(1.0, self.rests / self.recommended)


def longest_unbroken_seconds(hours: Iterable[float], rest_minutes: Iterable[float]) -> float:
    """하루 중 쉬지 않고 쓴 가장 긴 시간(초).

    스크린 타임은 시간대(1시간) 단위로만 저장돼 있어서 한 시간대의 사용량이 그 시간에 고르게 퍼졌다고 본다.
    눈 휴식을 마친 시각(자정부터의 분)과, 사용이 1분도 안 되는 시간대(자리를 비운 시간)에서 끊어
    끊긴 구간마다 사용 시간을 더하고 그중 가장 긴 것을 돌려준다.
    """
    hours = list(hours)
    breaks = {int(m) for m in rest_minutes if 0 <= m < 1440}
    for hour, seconds in enumerate(hours):
        if seconds < MIN_ACTIVE_SECONDS:
            breaks.update(range(hour * 60, hour * 60 + 60))
    best = current = 0.0
    for minute in range(1440):
        if minute in breaks:
            best, current = max(best, current), 0.0
        else:
            current += hours[minute // 60] / 60
    return max(best, current)


def rest_stats(
    period: Period,
    anchor: date,
    usage: UsageLog,
    events: Iterable[HistoryEvent],
    now: datetime,
    tz: tzinfo | None = None,
    interval_minutes: int = 20,
) -> RestStats:
    """기간의 휴식 달성률과 쉬지 않고 쓴 가장 긴 시간. events는 눈 휴식 기록(완료만 센다)."""
    today = now.astimezone(tz).date()
    start, end = range_bounds(period, anchor)
    rest_minutes: dict[date, list[float]] = {}
    for e in events:
        if e.type != EVENT_COMPLETED or activity_of(e) != ACTIVITY_REST:
            continue
        local = e.ts.astimezone(tz)
        if start <= local.date() <= end:
            rest_minutes.setdefault(local.date(), []).append(local.hour * 60 + local.minute)
    rests = recommended = 0
    longest, longest_day = 0.0, None
    interval_seconds = max(1, interval_minutes) * 60
    for i in range((min(end, today) - start).days + 1):
        day = start + timedelta(days=i)
        hours = usage.hourly(day)
        day_rests = rest_minutes.get(day, [])
        rests += len(day_rests)
        used = sum(hours)
        if used >= MIN_ACTIVE_SECONDS:  # 1분도 안 쓴 날은 쉴 필요가 없다
            recommended += math.ceil(used / interval_seconds)
        seconds = longest_unbroken_seconds(hours, day_rests)
        if seconds > longest:
            longest, longest_day = seconds, day
    label = "" if period is Period.DAY or longest_day is None else range_title(Period.DAY, longest_day, today)
    return RestStats(rests, recommended, longest, label)


def usage_highlights(period: Period, summary: UsageSummary, rest: RestStats) -> list[Highlight]:
    """스크린 타임 하이라이트 카드 두 개: 사용량(하루 보기는 피크 타임, 주·월은 하루 평균)과 최장 연속 사용 시간."""
    peak_value = format_usage(summary.peak_seconds) if summary.peak_label else "–"
    if period is Period.DAY:
        first = Highlight("피크 타임", peak_value, summary.peak_label)
    else:
        first = Highlight("하루 평균", format_usage(summary.average_per_day))
    longest = Highlight("최장 연속 사용 시간", format_usage(rest.longest_seconds) if rest.longest_seconds > 0 else "–", rest.longest_label)
    return [first, longest]


def format_usage(seconds: float) -> str:
    """스크린 타임 표시. 분 단위로 반올림한다: "0분", "45분", "5시간 12분", "2시간"."""
    minutes = round(max(0.0, seconds) / 60)
    hours, minutes = divmod(minutes, 60)
    if hours == 0:
        return f"{minutes}분"
    return f"{hours}시간 {minutes}분" if minutes else f"{hours}시간"


def usage_parts(seconds: float) -> list[tuple[str, str]]:
    """큰 숫자로 보여 줄 (숫자, 단위) 조각. 예: [("5", "시간"), ("12", "분")]. 0이면 [("0", "분")]."""
    minutes = round(max(0.0, seconds) / 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append((str(hours), "시간"))
    if minutes or not hours:
        parts.append((str(minutes), "분"))
    return parts


# 세로축 눈금(분). 가운데 눈금도 깔끔한 값이 되도록 짝수 위주로 고른다.
_USAGE_AXIS_MINUTES = (20, 30, 60, 120, 180, 240, 360, 480, 720, 960, 1440)


def nice_usage_axis(max_seconds: float) -> int:
    """스크린 타임 막대 차트의 세로축 최댓값(초). 가장 큰 막대가 눈금 안에 들어오게 올린다."""
    for minutes in _USAGE_AXIS_MINUTES:
        if max_seconds <= minutes * 60:
            return minutes * 60
    return -(-int(max_seconds) // 86400) * 86400  # 하루(24시간)를 넘으면 24시간 단위로 올림


def format_usage_axis(seconds: float) -> str:
    """세로축 눈금 글자: 0, 30분, 1시간, 1시간 30분."""
    minutes = round(seconds / 60)
    if minutes == 0:
        return "0"
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return f"{rest}분"
    return f"{hours}시간 {rest}분" if rest else f"{hours}시간"


# ---- 어제와 비교 ----

TREND_SYMBOLS = {"up": "▲", "down": "▼", "same": "–"}
NO_YESTERDAY = "어제 기록이 없어요"


@dataclass(frozen=True)
class TodayCompare:
    """오늘 요약과 어제 하루 전체와의 비교. 오늘이 아직 진행 중이면 어제보다 적게 보일 수 있다."""

    exercise_count: int
    exercise_trend: str  # up / down / same
    exercise_lines: list[str]  # ["어제보다 2회 많아요"]
    screen_seconds: float
    screen_trend: str
    screen_line: str


def _trend(delta: float) -> str:
    return "up" if delta > 0 else "down" if delta < 0 else "same"


def _more_less(delta: float, amount: str) -> str:
    return f"{amount} 많아요" if delta > 0 else f"{amount} 적어요"


def compare_today(events: Iterable[HistoryEvent], usage: UsageLog, now: datetime, tz: tzinfo | None = None) -> TodayCompare:
    """오늘의 횟수와 스크린 타임을 어제 하루 전체와 비교한다."""
    today = now.astimezone(tz).date()
    yesterday = today - timedelta(days=1)

    count_today = count_yesterday = 0
    yesterday_events = 0
    for e in events:
        day = e.ts.astimezone(tz).date()
        if day == yesterday:
            yesterday_events += 1
        if e.type != EVENT_COMPLETED or day not in (today, yesterday):
            continue
        if day == today:
            count_today += 1
        else:
            count_yesterday += 1

    # 어제 기록이 하나도 없으면 앱이 꺼져 있었던 것이라 비교가 의미 없다
    if yesterday_events == 0:
        exercise_lines = [NO_YESTERDAY]
        exercise_trend = "same"
    else:
        delta = count_today - count_yesterday
        exercise_trend = _trend(delta)
        count_line = "어제와 같아요" if delta == 0 else f"어제보다 {_more_less(delta, f'{abs(delta)}회')}"
        exercise_lines = [count_line]

    screen_today, screen_yesterday = usage.total(today), usage.total(yesterday)
    if screen_yesterday == 0:
        screen_line, screen_trend = NO_YESTERDAY, "same"
    else:
        screen_delta = screen_today - screen_yesterday
        if round(abs(screen_delta) / 60) == 0:  # 분 단위로 보여 주므로 반올림해서 0분이면 "비슷해요" ("0분 많아요"가 나오지 않게)
            screen_line, screen_trend = "어제와 비슷해요", "same"
        else:
            screen_trend = _trend(screen_delta)
            screen_line = f"어제보다 {_more_less(screen_delta, format_usage(abs(screen_delta)))}"

    return TodayCompare(count_today, exercise_trend, exercise_lines, screen_today, screen_trend, screen_line)


# ---- 앞 기간과 비교 (전날 / 전주 / 전달) ----


@dataclass(frozen=True)
class PeriodCompare:
    """선택한 기간을 바로 앞 기간과 비교한 문구. 일은 합계끼리, 주·월은 하루 평균끼리 비교한다."""

    trend: str  # up / down / same
    lines: list[str]  # 첫 줄은 핵심 비교, 둘째 줄(있으면)은 보조 비교


def previous_label(period: Period, anchor: date, today: date) -> str:
    """앞 기간의 이름. 지금 기간이면 어제·지난 주·지난 달, 지난 기간을 보는 중이면 전날·전주·전달."""
    start, end = range_bounds(period, anchor)
    current = start <= today <= end
    return {
        Period.DAY: "어제" if current else "전날",
        Period.WEEK: "지난 주" if current else "전주",
        Period.MONTH: "지난 달" if current else "전달",
    }[period]


def _with_particle(word: str) -> str:
    """"어제와", "전날과"처럼 마지막 글자의 받침에 맞는 조사(와/과)를 붙인다."""
    code = ord(word[-1]) - 0xAC00
    return f"{word}{'과' if 0 <= code < 11172 and code % 28 else '와'}"


def _range_summary(period: Period, anchor: date, events: list[HistoryEvent], now: datetime, tz: tzinfo | None) -> RangeSummary:
    return summarize_range(period, anchor, build_buckets(period, anchor, events, now, tz), now, tz)


def compare_exercise_period(period: Period, anchor: date, events: Iterable[HistoryEvent], now: datetime, tz: tzinfo | None = None) -> PeriodCompare:
    """마친 횟수를 앞 기간과 비교한다. 앞 기간에 기록이 하나도 없으면 비교하지 않는다."""
    events = list(events)
    label = previous_label(period, anchor, now.astimezone(tz).date())
    cur = _range_summary(period, anchor, events, now, tz)
    prev = _range_summary(period, shift_anchor(period, anchor, -1), events, now, tz)
    if prev.completed + prev.skipped + prev.snoozed == 0:
        return PeriodCompare("same", [f"{label} 기록이 없어요"])

    if period is Period.DAY:
        delta = cur.completed - prev.completed
        count_line = f"{_with_particle(label)} 같아요" if delta == 0 else f"{label}보다 {_more_less(delta, f'{abs(delta)}회')}"
        return PeriodCompare(_trend(delta), [count_line])

    # 주·월: 진행 중인 기간을 앞 기간 전체와 합계로 비교하면 항상 적게 나오므로, 지나간 날 기준 하루 평균끼리 비교한다
    avg_delta = cur.average_per_day - prev.average_per_day  # 반올림은 차이를 구한 뒤에 한다 (먼저 하면 0.14가 0.2로 보인다)
    if round(abs(avg_delta), 1) == 0:  # 화면에 0.0회로 보이면 같다고 한다
        count_line = f"하루 평균이 {_with_particle(label)} 같아요"
    else:
        count_line = f"{label}보다 하루 평균 {_more_less(avg_delta, f'{abs(avg_delta):.1f}회')}"
    return PeriodCompare(_trend(avg_delta) if round(abs(avg_delta), 1) else "same", [count_line])


def compare_usage_period(period: Period, anchor: date, usage: UsageLog, now: datetime, tz: tzinfo | None = None) -> PeriodCompare:
    """스크린 타임을 앞 기간과 비교한다. 앞 기간에 기록이 없으면 비교하지 않는다."""
    label = previous_label(period, anchor, now.astimezone(tz).date())
    cur = summarize_usage(period, anchor, build_usage_buckets(period, anchor, usage, now, tz), now, tz)
    prev_anchor = shift_anchor(period, anchor, -1)
    prev = summarize_usage(period, prev_anchor, build_usage_buckets(period, prev_anchor, usage, now, tz), now, tz)
    if prev.total_seconds == 0:
        return PeriodCompare("same", [f"{label} 기록이 없어요"])
    if period is Period.DAY:
        delta, per_day = cur.total_seconds - prev.total_seconds, ""
    else:
        delta, per_day = cur.average_per_day - prev.average_per_day, "하루 평균 "
    if round(abs(delta) / 60) == 0:  # 분 단위로 보여 주므로 반올림해서 0분이면 비슷하다고 한다
        same = f"{_with_particle(label)} 비슷해요" if not per_day else f"하루 평균이 {_with_particle(label)} 비슷해요"
        return PeriodCompare("same", [same])
    return PeriodCompare(_trend(delta), [f"{label}보다 {per_day}{_more_less(delta, format_usage(abs(delta)))}"])


# ---- 하이라이트 카드의 앞 기간 비교 ----


def _card_compare(
    label: str,
    delta: float,
    amount: Callable[[float], str],
    *,
    similar: bool,
    per_day: bool = False,
    subject: str | None = None,
    same_word: str = "같아요",
) -> dict:
    """카드 하나의 비교 줄. subject는 비교 대상 이름(기본은 앞 기간, 최고 기록은 "지난 주 최고")이다."""
    target = subject or label
    if similar:
        return {"compare": f"{_with_particle(target)} {same_word}", "trend": "same"}
    prefix = "하루 평균 " if per_day else ""
    return {"compare": f"{target}보다 {prefix}{_more_less(delta, amount(abs(delta)))}", "trend": _trend(delta)}


def _count_card(label: str, cur: float, prev: float, *, per_day: bool, average: bool = False) -> dict:
    """횟수 카드. 하루 평균이거나 하루 평균끼리 비교할 때는 소수 첫째 자리까지, 합계끼리는 정수로 보여 준다."""
    delta = cur - prev
    if per_day or average:
        return _card_compare(label, delta, lambda v: f"{v:.1f}회", similar=round(abs(delta), 1) == 0, per_day=per_day)
    return _card_compare(label, delta, lambda v: f"{int(v)}회", similar=delta == 0)


def _seconds_card(label: str, cur: float, prev: float, *, per_day: bool) -> dict:
    delta = cur - prev
    return _card_compare(label, delta, lambda v: format_duration(round(v)), similar=round(delta) == 0, per_day=per_day)


def _usage_card(label: str, cur: float, prev: float, *, per_day: bool = False, subject: str | None = None) -> dict:
    delta = cur - prev
    return _card_compare(
        label, delta, format_usage, similar=round(abs(delta) / 60) == 0, per_day=per_day, subject=subject, same_word="비슷해요"
    )


def _per_day(value: float, days: int) -> float:
    return value / max(1, days)


def rest_highlights_with_compare(
    period: Period,
    summary: RangeSummary,
    previous: RangeSummary | None,
    label: str,
    rest: RestStats,
    slots: int,
    previous_slots: int,
    kind: str = EVENT_SKIPPED,
) -> list[Highlight]:
    """눈 휴식 하이라이트 카드에 앞 기간과의 비교를 더한다. 앞 기간에 기록이 하나도 없으면 비교하지 않는다. 휴식 달성률에는 비교를 붙이지 않는다."""
    cards = rest_highlights(period, summary, rest, slots, kind)
    if previous is None or previous.completed + previous.skipped + previous.snoozed == 0:
        return cards
    name = SKIP_KINDS[kind]
    cur, prev = (summary.skipped, previous.skipped) if kind == EVENT_SKIPPED else (summary.snoozed, previous.snoozed)
    if period is Period.DAY:
        fields = {
            name: _count_card(label, cur, prev, per_day=False),
            "휴식 시간대": _count_unit_card(label, slots, previous_slots, "개"),
        }
    else:  # 주·월은 지나간 날 기준 하루 평균끼리 비교한다
        delta = _per_day(slots, summary.days) - _per_day(previous_slots, previous.days)
        fields = {
            name: _count_card(label, _per_day(cur, summary.days), _per_day(prev, previous.days), per_day=True),
            "휴식 시간대": _card_compare(label, delta, lambda v: f"{v:.1f}개", similar=round(abs(delta), 1) == 0, per_day=True),
        }
    return [replace(card, **fields.get(card.label, {})) for card in cards]


def usage_highlights_with_compare(
    period: Period,
    summary: UsageSummary,
    rest: RestStats,
    previous: UsageSummary | None,
    previous_rest: RestStats | None,
    label: str,
) -> list[Highlight]:
    """스크린 타임 하이라이트 카드에 앞 기간과의 비교를 더한다. 앞 기간 스크린 타임이 없으면 비교하지 않는다."""
    cards = usage_highlights(period, summary, rest)
    fields: dict[str, dict] = {}
    if previous is not None and previous.total_seconds > 0:
        if period is Period.DAY:
            fields["피크 타임"] = _usage_card(label, summary.peak_seconds, previous.peak_seconds, subject=f"{label} 최고")
        else:
            fields["하루 평균"] = _usage_card(label, summary.average_per_day, previous.average_per_day)
        if previous_rest is not None and previous_rest.longest_seconds > 0 and rest.longest_seconds > 0:
            fields["최장 연속 사용 시간"] = _usage_card(label, rest.longest_seconds, previous_rest.longest_seconds)
    return [replace(card, **fields.get(card.label, {})) for card in cards]


def _count_unit_card(label: str, cur: int, prev: int, unit: str) -> dict:
    delta = cur - prev
    return _card_compare(label, delta, lambda v: f"{int(v)}{unit}", similar=delta == 0)
