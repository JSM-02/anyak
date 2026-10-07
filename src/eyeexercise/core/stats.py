"""기록 탭에 보여 줄 요약 (GUI 없음). 일·주·월 단위로 막대 차트, 하이라이트, 최근 기록을 만든다.

날짜는 모두 로컬 시간대 기준이다. `tz`가 None이면 시스템 로컬 시간대를 쓰고, 테스트에서는 고정 시간대를 넘긴다.
"""

import calendar
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from enum import Enum

from eyeexercise.core.exercises import EXERCISE_BLINK, EXERCISE_DOT_FOLLOW
from eyeexercise.core.history import EVENT_COMPLETED, EVENT_SKIPPED, EVENT_SNOOZED, HistoryEvent
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


@dataclass(frozen=True)
class Highlight:
    label: str
    value: str  # 큰 글씨 값 (예: "8시간 5분")
    detail: str = ""  # 값 아래 작은 보조 설명 (예: "화요일"). 없으면 빈 문자열
    compare: str = ""  # 앞 기간과의 비교 한 줄 (예: "지난 주보다 하루 평균 0.3회 많아요"). 화살표는 화면이 붙인다
    trend: str = "same"  # compare의 추세: up / down / same


@dataclass(frozen=True)
class RecentRow:
    """최근 기록 표의 한 줄."""

    clock: str  # "14:32"
    name: str  # 운동 이름. 건너뜀·미룸은 빈 문자열
    kind: str  # completed / skipped / snoozed
    result: str  # "완료", "건너뜀", "미룸"
    length: str  # 완료한 운동 시간 ("1분 6초"). 그 외는 빈 문자열
    exercise: str = ""  # 완료한 운동의 종류 키 ("blink", "dot_follow"). 그 외는 빈 문자열


@dataclass(frozen=True)
class RecentGroup:
    """같은 날의 기록 묶음. 제목은 "오늘", "어제", "10월 3일 (토)"."""

    title: str
    rows: list[RecentRow]


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
    )


def highlights(period: Period, summary: RangeSummary) -> list[Highlight]:
    """하이라이트 카드 세 개. 하루 보기에는 평균이 의미 없어서 미룸을 보여 준다."""
    time_card = Highlight("운동 시간", format_duration(summary.exercise_seconds))
    skipped = Highlight("건너뜀", f"{summary.skipped}회")
    if period is Period.DAY:
        return [time_card, skipped, Highlight("미룸", f"{summary.snoozed}회")]
    return [Highlight("하루 평균", f"{summary.average_per_day:.1f}회"), time_card, skipped]


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


def recent_groups(
    events: Iterable[HistoryEvent], now: datetime, limit: int = 10, tz: tzinfo | None = None
) -> list[RecentGroup]:
    """가장 최근 기록부터 limit줄을 날짜별로 묶는다. 같은 날은 최신순이고 날짜도 최신순이다."""
    today = now.astimezone(tz).date()
    groups: list[RecentGroup] = []
    for e in sorted(events, key=lambda e: e.ts, reverse=True)[:limit]:
        local = e.ts.astimezone(tz)
        if e.type == EVENT_COMPLETED:
            name = EXERCISE_NAMES.get(e.exercise or "", e.exercise or "운동")
            length = format_duration(e.duration_seconds) if e.duration_seconds else ""
            row = RecentRow(f"{local:%H:%M}", name, EVENT_COMPLETED, "완료", length, e.exercise or "")
        elif e.type == EVENT_SKIPPED:
            row = RecentRow(f"{local:%H:%M}", "", EVENT_SKIPPED, "건너뜀", "")
        elif e.type == EVENT_SNOOZED:
            row = RecentRow(f"{local:%H:%M}", "", EVENT_SNOOZED, "미룸", "")
        else:
            continue
        title = range_title(Period.DAY, local.date(), today)
        if groups and groups[-1].title == title:
            groups[-1].rows.append(row)
        else:
            groups.append(RecentGroup(title, [row]))
    return groups


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


def usage_highlights(period: Period, summary: UsageSummary, completed: int) -> list[Highlight]:
    """스크린 타임 하이라이트 카드 세 개. 운동 완료 횟수를 함께 보여 줘서 사용량과 비교할 수 있게 한다."""
    peak_value = format_usage(summary.peak_seconds) if summary.peak_label else "–"
    peak_label = summary.peak_label
    exercise = Highlight("운동 완료", f"{completed}회")
    if period is Period.DAY:
        return [Highlight("가장 많이 쓴 시간", peak_value, peak_label), Highlight("사용한 시간대", f"{summary.active_buckets}개"), exercise]
    return [Highlight("하루 평균", format_usage(summary.average_per_day)), Highlight("가장 많이 쓴 날", peak_value, peak_label), exercise]


def usage_daily_rows(usage: UsageLog, today: date, days: int = 7) -> list[tuple[str, float]]:
    """오늘부터 거슬러 올라가는 (날짜 이름, 사용 시간(초)) 목록."""
    rows = []
    for i in range(days):
        day = today - timedelta(days=i)
        rows.append((range_title(Period.DAY, day, today), usage.total(day)))
    return rows


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
    exercise_lines: list[str]  # ["어제보다 2회 많아요", "운동 시간은 2분 12초 많아요"]
    screen_seconds: float
    screen_trend: str
    screen_line: str


def _trend(delta: float) -> str:
    return "up" if delta > 0 else "down" if delta < 0 else "same"


def _more_less(delta: float, amount: str) -> str:
    return f"{amount} 많아요" if delta > 0 else f"{amount} 적어요"


def compare_today(events: Iterable[HistoryEvent], usage: UsageLog, now: datetime, tz: tzinfo | None = None) -> TodayCompare:
    """오늘의 운동 완료 횟수·운동 시간·스크린 타임을 어제 하루 전체와 비교한다."""
    today = now.astimezone(tz).date()
    yesterday = today - timedelta(days=1)

    count_today = count_yesterday = 0
    seconds_today = seconds_yesterday = 0
    yesterday_events = 0
    for e in events:
        day = e.ts.astimezone(tz).date()
        if day == yesterday:
            yesterday_events += 1
        if e.type != EVENT_COMPLETED or day not in (today, yesterday):
            continue
        if day == today:
            count_today += 1
            seconds_today += e.duration_seconds or 0
        else:
            count_yesterday += 1
            seconds_yesterday += e.duration_seconds or 0

    # 어제 기록이 하나도 없으면 앱이 꺼져 있었던 것이라 비교가 의미 없다
    if yesterday_events == 0:
        exercise_lines = [NO_YESTERDAY]
        exercise_trend = "same"
    else:
        delta = count_today - count_yesterday
        exercise_trend = _trend(delta)
        count_line = "어제와 같아요" if delta == 0 else f"어제보다 {_more_less(delta, f'{abs(delta)}회')}"
        time_delta = seconds_today - seconds_yesterday
        time_line = "운동 시간도 같아요" if time_delta == 0 else f"운동 시간은 {_more_less(time_delta, format_duration(abs(time_delta)))}"
        exercise_lines = [count_line, time_line]

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
    """운동 완료 횟수와 운동 시간을 앞 기간과 비교한다. 앞 기간에 기록이 하나도 없으면 비교하지 않는다."""
    events = list(events)
    label = previous_label(period, anchor, now.astimezone(tz).date())
    cur = _range_summary(period, anchor, events, now, tz)
    prev = _range_summary(period, shift_anchor(period, anchor, -1), events, now, tz)
    if prev.completed + prev.skipped + prev.snoozed == 0:
        return PeriodCompare("same", [f"{label} 기록이 없어요"])

    if period is Period.DAY:
        delta = cur.completed - prev.completed
        time_delta = cur.exercise_seconds - prev.exercise_seconds
        count_line = f"{_with_particle(label)} 같아요" if delta == 0 else f"{label}보다 {_more_less(delta, f'{abs(delta)}회')}"
        time_line = "운동 시간도 같아요" if time_delta == 0 else f"운동 시간은 {_more_less(time_delta, format_duration(abs(time_delta)))}"
        return PeriodCompare(_trend(delta), [count_line, time_line])

    # 주·월: 진행 중인 기간을 앞 기간 전체와 합계로 비교하면 항상 적게 나오므로, 지나간 날 기준 하루 평균끼리 비교한다
    avg_delta = cur.average_per_day - prev.average_per_day  # 반올림은 차이를 구한 뒤에 한다 (먼저 하면 0.14가 0.2로 보인다)
    cur_time, prev_time = cur.exercise_seconds / max(1, cur.days), prev.exercise_seconds / max(1, prev.days)
    time_delta = round(cur_time - prev_time)
    if round(abs(avg_delta), 1) == 0:  # 화면에 0.0회로 보이면 같다고 한다
        count_line = f"하루 평균이 {_with_particle(label)} 같아요"
    else:
        count_line = f"{label}보다 하루 평균 {_more_less(avg_delta, f'{abs(avg_delta):.1f}회')}"
    time_line = "운동 시간도 같아요" if time_delta == 0 else f"운동 시간은 하루 평균 {_more_less(time_delta, format_duration(abs(time_delta)))}"
    return PeriodCompare(_trend(avg_delta) if round(abs(avg_delta), 1) else "same", [count_line, time_line])


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


def highlights_with_compare(period: Period, summary: RangeSummary, previous: RangeSummary | None, label: str) -> list[Highlight]:
    """운동 하이라이트 카드에 앞 기간과의 비교를 더한다. 앞 기간에 기록이 하나도 없으면 비교하지 않는다."""
    cards = highlights(period, summary)
    if previous is None or previous.completed + previous.skipped + previous.snoozed == 0:
        return cards
    if period is Period.DAY:
        fields = {
            "운동 시간": _seconds_card(label, summary.exercise_seconds, previous.exercise_seconds, per_day=False),
            "건너뜀": _count_card(label, summary.skipped, previous.skipped, per_day=False),
            "미룸": _count_card(label, summary.snoozed, previous.snoozed, per_day=False),
        }
    else:  # 주·월은 지나간 날 기준 하루 평균끼리 비교한다
        fields = {
            "하루 평균": _count_card(label, summary.average_per_day, previous.average_per_day, per_day=False, average=True),
            "운동 시간": _seconds_card(
                label, _per_day(summary.exercise_seconds, summary.days), _per_day(previous.exercise_seconds, previous.days), per_day=True
            ),
            "건너뜀": _count_card(label, _per_day(summary.skipped, summary.days), _per_day(previous.skipped, previous.days), per_day=True),
        }
    return [replace(card, **fields.get(card.label, {})) for card in cards]


def usage_highlights_with_compare(
    period: Period,
    summary: UsageSummary,
    exercise: RangeSummary,
    previous: UsageSummary | None,
    previous_exercise: RangeSummary | None,
    label: str,
) -> list[Highlight]:
    """스크린 타임 하이라이트 카드에 앞 기간과의 비교를 더한다. 사용 시간 카드는 앞 기간 스크린 타임이, 운동 완료 카드는 앞 기간 운동 기록이 있을 때만 비교한다."""
    cards = usage_highlights(period, summary, exercise.completed)
    fields: dict[str, dict] = {}
    if previous is not None and previous.total_seconds > 0:
        peak = _usage_card(label, summary.peak_seconds, previous.peak_seconds, subject=f"{label} 최고")
        if period is Period.DAY:
            fields["가장 많이 쓴 시간"] = peak
            fields["사용한 시간대"] = _count_unit_card(label, summary.active_buckets, previous.active_buckets, "개")
        else:
            fields["하루 평균"] = _usage_card(label, summary.average_per_day, previous.average_per_day)
            fields["가장 많이 쓴 날"] = peak
    if previous_exercise is not None and previous_exercise.completed + previous_exercise.skipped + previous_exercise.snoozed > 0:
        if period is Period.DAY:
            fields["운동 완료"] = _count_card(label, exercise.completed, previous_exercise.completed, per_day=False)
        else:
            fields["운동 완료"] = _count_card(
                label, exercise.average_per_day, previous_exercise.average_per_day, per_day=True
            )
    return [replace(card, **fields.get(card.label, {})) for card in cards]


def _count_unit_card(label: str, cur: int, prev: int, unit: str) -> dict:
    delta = cur - prev
    return _card_compare(label, delta, lambda v: f"{int(v)}{unit}", similar=delta == 0)
