import re
from datetime import date, datetime, timedelta, timezone

import pytest

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import (
    Period,
    build_buckets,
    can_go_forward,
    format_duration,
    rest_highlights,
    rest_stats,
    range_bounds,
    range_caption,
    range_title,
    timeline_days,
    shift_anchor,
    summarize_range,
    week_start,
)

KST = timezone(timedelta(hours=9))
# 2026-10-07은 수요일이다. 이번 주는 10/5(월) ~ 10/11(일).
TODAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def done(ts, exercise="blink", seconds=66):
    return HistoryEvent(ts, "completed", exercise, seconds)


def skipped(ts):
    return HistoryEvent(ts, "skipped", activity="rest")


def snoozed(ts):
    return HistoryEvent(ts, "snoozed", activity="rest")


# ---- 기간 계산 ----


def test_주는_월요일에_시작한다():
    assert week_start(date(2026, 10, 7)) == date(2026, 10, 5)  # 수 → 월
    assert week_start(date(2026, 10, 5)) == date(2026, 10, 5)  # 월
    assert week_start(date(2026, 10, 11)) == date(2026, 10, 5)  # 일


def test_기간_범위():
    assert range_bounds(Period.DAY, TODAY) == (TODAY, TODAY)
    assert range_bounds(Period.WEEK, TODAY) == (date(2026, 10, 5), date(2026, 10, 11))
    assert range_bounds(Period.MONTH, TODAY) == (date(2026, 10, 1), date(2026, 10, 31))
    assert range_bounds(Period.MONTH, date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert range_bounds(Period.MONTH, date(2028, 2, 10))[1] == date(2028, 2, 29)  # 윤년


def test_기간_이동():
    assert shift_anchor(Period.DAY, TODAY, -1) == date(2026, 10, 6)
    assert shift_anchor(Period.WEEK, TODAY, -1) == date(2026, 9, 30)
    assert shift_anchor(Period.MONTH, TODAY, -1) == date(2026, 9, 1)
    assert shift_anchor(Period.MONTH, TODAY, 1) == date(2026, 11, 1)


def test_월_이동은_해를_넘어간다():
    assert shift_anchor(Period.MONTH, date(2026, 1, 15), -1) == date(2025, 12, 1)
    assert shift_anchor(Period.MONTH, date(2026, 12, 15), 1) == date(2027, 1, 1)
    assert shift_anchor(Period.MONTH, date(2026, 3, 31), -1) == date(2026, 2, 1)  # 31일에서도 안전하다


def test_미래로는_갈_수_없다():
    assert not can_go_forward(Period.DAY, TODAY, TODAY)
    assert can_go_forward(Period.DAY, date(2026, 10, 6), TODAY)
    assert not can_go_forward(Period.WEEK, TODAY, TODAY)  # 이번 주에는 오늘이 있다
    assert can_go_forward(Period.WEEK, date(2026, 9, 30), TODAY)
    assert not can_go_forward(Period.MONTH, TODAY, TODAY)
    assert can_go_forward(Period.MONTH, date(2026, 9, 1), TODAY)


def test_제목():
    assert range_title(Period.DAY, TODAY, TODAY) == "오늘"
    assert range_title(Period.DAY, date(2026, 10, 6), TODAY) == "어제"
    assert range_title(Period.DAY, date(2026, 10, 3), TODAY) == "10월 3일 (토)"
    assert range_title(Period.WEEK, TODAY, TODAY) == "이번 주"
    assert range_title(Period.WEEK, date(2026, 9, 30), TODAY) == "지난 주"
    assert range_title(Period.WEEK, date(2026, 9, 20), TODAY) == "9월 14일 주"
    assert range_title(Period.MONTH, TODAY, TODAY) == "이번 달"
    assert range_title(Period.MONTH, date(2026, 9, 1), TODAY) == "2026년 9월"


def test_날짜_범위_문구():
    assert range_caption(Period.DAY, TODAY) == "2026년 10월 7일 수요일"
    assert range_caption(Period.WEEK, TODAY) == "10월 5일 – 10월 11일"
    assert range_caption(Period.MONTH, TODAY) == "2026년 10월"


# ---- 막대 ----


def test_주_보기는_항상_7개_막대이고_빈_날은_0():
    buckets = build_buckets(Period.WEEK, TODAY, [], NOW, KST)
    assert [b.label for b in buckets] == list("월화수목금토일")
    assert all(b.completed == b.skipped == b.snoozed == b.exercise_seconds == 0 for b in buckets)


def test_주_보기_집계():
    events = [
        done(at(10, 5), seconds=66),
        done(at(10, 7, 9), "dot_follow", 60),
        done(at(10, 7, 14), seconds=66),
        skipped(at(10, 7, 15)),
        snoozed(at(10, 6)),
    ]
    b = build_buckets(Period.WEEK, TODAY, events, NOW, KST)
    assert (b[0].completed, b[0].exercise_seconds) == (1, 66)  # 월
    assert b[1].snoozed == 1  # 화
    assert (b[2].completed, b[2].skipped, b[2].exercise_seconds) == (2, 1, 126)  # 수


def test_다른_주의_기록은_섞이지_않는다():
    events = [done(at(10, 4)), done(at(10, 12)), done(at(10, 7))]  # 일요일(지난 주), 다음 주 월요일, 이번 주 수요일
    b = build_buckets(Period.WEEK, TODAY, events, NOW, KST)
    assert sum(x.completed for x in b) == 1 and b[2].completed == 1


def test_월_보기는_그_달_날짜_수만큼_막대():
    assert len(build_buckets(Period.MONTH, TODAY, [], NOW, KST)) == 31
    assert len(build_buckets(Period.MONTH, date(2026, 2, 3), [], NOW, KST)) == 28
    assert len(build_buckets(Period.MONTH, date(2028, 2, 3), [], NOW, KST)) == 29


def test_월_보기_축_글자는_7일_간격():
    b = build_buckets(Period.MONTH, TODAY, [], NOW, KST)
    assert [x.label for x in b if x.show_label] == ["1", "8", "15", "22", "29"]
    assert b[6].title == "10월 7일 (수)"


def test_월_보기_집계():
    events = [done(at(10, 1)), done(at(10, 31)), done(at(9, 30)), done(at(11, 1))]
    b = build_buckets(Period.MONTH, TODAY, events, NOW, KST)
    assert b[0].completed == 1 and b[30].completed == 1 and sum(x.completed for x in b) == 2


def test_하루_보기는_24개_시간_막대():
    events = [done(at(10, 7, 9, 5)), done(at(10, 7, 9, 50), "dot_follow", 60), skipped(at(10, 7, 14))]
    b = build_buckets(Period.DAY, TODAY, events, NOW, KST)
    assert len(b) == 24
    assert b[9].completed == 2 and b[9].exercise_seconds == 126
    assert b[14].skipped == 1
    assert [x.label for x in b if x.show_label] == ["0시", "6시", "12시", "18시"]
    assert b[9].title == "9시"


def test_자정_경계는_로컬_날짜로_나눈다():
    events = [done(datetime(2026, 10, 6, 23, 59, tzinfo=KST)), done(datetime(2026, 10, 7, 0, 1, tzinfo=KST))]
    b = build_buckets(Period.WEEK, TODAY, events, NOW, KST)
    assert (b[1].completed, b[2].completed) == (1, 1)
    day = build_buckets(Period.DAY, TODAY, events, NOW, KST)
    assert day[0].completed == 1 and day[23].completed == 0


def test_다른_시간대로_저장된_기록도_로컬_기준으로_센다():
    utc = HistoryEvent(datetime(2026, 10, 6, 15, 30, tzinfo=timezone.utc), "completed", "blink", 66)  # KST 10/7 00:30
    b = build_buckets(Period.DAY, TODAY, [utc], NOW, KST)
    assert b[0].completed == 1


def test_현재_막대와_미래_막대_표시():
    week = build_buckets(Period.WEEK, TODAY, [], NOW, KST)
    assert [b.is_current for b in week] == [False, False, True, False, False, False, False]
    assert [b.is_future for b in week] == [False, False, False, True, True, True, True]
    day = build_buckets(Period.DAY, TODAY, [], NOW, KST)
    assert day[14].is_current and not day[13].is_current
    assert all(b.is_future for b in day[15:]) and not any(b.is_future for b in day[:15])
    past = build_buckets(Period.WEEK, date(2026, 9, 30), [], NOW, KST)
    assert not any(b.is_current or b.is_future for b in past)
    future = build_buckets(Period.DAY, date(2026, 10, 9), [], NOW, KST)
    assert all(b.is_future for b in future)


# ---- 요약 ----


def test_요약_합계와_하루_평균은_지나간_날만_센다():
    events = [done(at(10, 5)), done(at(10, 5, 18)), done(at(10, 6)), done(at(10, 7)), skipped(at(10, 7)), snoozed(at(10, 6))]
    buckets = build_buckets(Period.WEEK, TODAY, events, NOW, KST)
    s = summarize_range(Period.WEEK, TODAY, buckets, NOW, KST)
    assert (s.completed, s.skipped, s.snoozed, s.exercise_seconds) == (4, 1, 1, 264)
    assert s.average_per_day == pytest.approx(4 / 3)  # 월·화·수 3일 (목~일은 아직 안 왔다)


def test_지난_주는_7일로_평균을_낸다():
    events = [done(at(9, 30)), done(at(9, 30)), done(at(10, 4))]
    anchor = date(2026, 9, 30)
    buckets = build_buckets(Period.WEEK, anchor, events, NOW, KST)
    assert summarize_range(Period.WEEK, anchor, buckets, NOW, KST).average_per_day == pytest.approx(3 / 7)


def test_월_평균은_이번_달에는_오늘까지_일수로_나눈다():
    buckets = build_buckets(Period.MONTH, TODAY, [done(at(10, 1))] * 1 + [done(at(10, 2))] * 6, NOW, KST)
    assert summarize_range(Period.MONTH, TODAY, buckets, NOW, KST).average_per_day == pytest.approx(7 / 7)


def test_미래_기간의_평균은_0():
    anchor = date(2026, 10, 14)
    buckets = build_buckets(Period.WEEK, anchor, [], NOW, KST)
    s = summarize_range(Period.WEEK, anchor, buckets, NOW, KST)
    assert s.average_per_day == 0.0 and s.completed == 0


def test_기록이_없으면_모두_0():
    buckets = build_buckets(Period.WEEK, TODAY, [], NOW, KST)
    s = summarize_range(Period.WEEK, TODAY, buckets, NOW, KST)
    assert (s.completed, s.skipped, s.snoozed, s.exercise_seconds, s.average_per_day) == (0, 0, 0, 0, 0.0)


# ---- 하이라이트 ----


def _rest(period, anchor, events, usage=None):
    from eyeexercise.core.usage import UsageLog

    return rest_stats(period, anchor, usage or UsageLog(), events, NOW, KST)


def test_눈_휴식_카드는_달성률_건너뜀_휴식_시간대():
    events = [done(at(10, 5), seconds=1260), skipped(at(10, 6)), snoozed(at(10, 6, 13))]
    s = summarize_range(Period.WEEK, TODAY, build_buckets(Period.WEEK, TODAY, events, NOW, KST), NOW, KST)
    for period in (Period.WEEK, Period.MONTH):
        cards = rest_highlights(period, s, _rest(period, TODAY, events), 1)
        assert [c.label for c in cards] == ["휴식 달성률", "건너뜀", "휴식 시간대"]  # 휴식 시간은 보여 주지 않는다
    cards = rest_highlights(Period.WEEK, s, _rest(Period.WEEK, TODAY, events), 1)
    assert [c.value for c in cards] == ["–", "1회", "0.3개"]  # 사용 기록이 없으니 달성률은 없다. 시간대 1개 ÷ 월~수 3일
    assert cards[2].detail == "하루 평균"


def test_둘째_카드는_건너뜀_대신_미룸을_보여_줄_수_있다():
    events = [skipped(at(10, 6)), snoozed(at(10, 6, 13)), snoozed(at(10, 7, 9))]
    s = summarize_range(Period.WEEK, TODAY, build_buckets(Period.WEEK, TODAY, events, NOW, KST), NOW, KST)
    rest = _rest(Period.WEEK, TODAY, events)
    assert [(c.label, c.value) for c in rest_highlights(Period.WEEK, s, rest, 0)][1] == ("건너뜀", "1회")
    assert [(c.label, c.value) for c in rest_highlights(Period.WEEK, s, rest, 0, "snoozed")][1] == ("미룸", "2회")


def test_하루_눈_휴식_카드는_쉰_시간대_수를_센다():
    from eyeexercise.core.stats import rest_slot_count

    events = [done(at(10, 7, 9, 5)), done(at(10, 7, 9, 40)), done(at(10, 7, 10)), snoozed(at(10, 7, 13))]
    s = summarize_range(Period.DAY, TODAY, build_buckets(Period.DAY, TODAY, events, NOW, KST), NOW, KST)
    slots = rest_slot_count(Period.DAY, TODAY, events, KST)
    assert slots == 2  # 9시에 두 번 쉬어도 한 시간대로 센다
    cards = rest_highlights(Period.DAY, s, _rest(Period.DAY, TODAY, events), slots)
    assert [(c.label, c.value) for c in cards][1:] == [("건너뜀", "0회"), ("휴식 시간대", "2개")]


def test_휴식_시간대는_날짜가_다르면_따로_센다():
    from eyeexercise.core.stats import rest_slot_count

    events = [done(at(10, 5, 9)), done(at(10, 6, 9)), done(at(10, 6, 9, 30)), skipped(at(10, 7, 9)), done(at(10, 14, 9))]
    assert rest_slot_count(Period.WEEK, TODAY, events, KST) == 2  # 건너뜀과 다른 주는 세지 않는다


# ---- 표시 형식 ----


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0초"),
        (45, "45초"),
        (60, "1분"),
        (66, "1분 6초"),
        (599, "9분 59초"),
        (600, "10분"),
        (1259, "20분"),  # 10분 이상은 초를 생략한다
        (3599, "59분"),
        (3600, "1시간"),
        (3900, "1시간 5분"),
        (-5, "0초"),
    ],
)
def test_시간_표시(seconds, text):
    assert format_duration(seconds) == text


# ---- 하루 타임라인 (최근 기록) ----


def timeline(events=(), entries=(), days=7, now=NOW):
    return timeline_days(events, make_usage(entries), now, days, KST)


def test_타임라인은_오늘부터_거슬러_올라가는_날짜_줄이다():
    days = timeline()
    assert [d.title for d in days] == ["오늘", "어제", "10월 5일 (월)", "10월 4일 (일)", "10월 3일 (토)", "10월 2일 (금)", "10월 1일 (목)"]
    assert all(d.is_empty for d in days)  # 기록이 없는 날도 한 줄을 차지한다
    assert len(timeline(days=3)) == 3


def test_점은_시각_종류_설명을_가진다():
    events = [done(at(10, 7, 14, 32), "dot_follow", 60), done(at(10, 7, 14, 4), "blink", 66), skipped(at(10, 7, 13, 59)), snoozed(at(10, 7, 0, 0))]
    marks = timeline(events)[0].marks
    assert [m.minute for m in marks] == [0, 13 * 60 + 59, 14 * 60 + 4, 14 * 60 + 32]  # 시간순
    assert [m.kind for m in marks] == ["snoozed", "skipped", "completed", "completed"]
    assert [m.exercise for m in marks] == ["", "", "blink", "dot_follow"]
    assert [m.activity for m in marks] == ["rest", "rest", "rest", "exercise"]
    assert [m.tip for m in marks] == ["00:00 미룸", "13:59 건너뜀", "14:04 눈 휴식 · 1분 6초", "14:32 점 따라가기 · 1분"]


def test_날짜마다_휴식_운동_건너뜀_미룸을_따로_센다():
    events = [
        done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11), "dot_follow", 60),
        skipped(at(10, 7, 12)), skipped(at(10, 7, 13)), snoozed(at(10, 7, 14)),
        done(at(10, 6, 9)),
    ]
    days = timeline(events)
    assert (days[0].rests, days[0].exercises, days[0].skipped, days[0].snoozed) == (2, 1, 2, 1)
    assert (days[1].rests, days[1].exercises, days[1].skipped, days[1].snoozed) == (1, 0, 0, 0)
    assert len(days[0].marks) == 6


def test_칸의_숫자는_그_시간대에_마친_눈_운동만_센다():
    events = [done(at(10, 7, 14, 5)), done(at(10, 7, 14, 20), "dot_follow", 60), done(at(10, 7, 14, 40), "dot_follow", 60), skipped(at(10, 7, 14, 50))]
    today = timeline(events)[0]
    assert today.exercises_in_hour(14) == 2  # 휴식과 건너뜀은 세지 않는다
    assert today.exercises_in_hour(13) == 0


def test_휴식인지_운동인지_모르는_건너뜀과_미룸은_그리지_않는다():
    events = [HistoryEvent(at(10, 7, 9), "skipped"), HistoryEvent(at(10, 7, 10), "snoozed"), done(at(10, 7, 11))]
    today = timeline(events)[0]
    assert [m.kind for m in today.marks] == ["completed"] and today.skipped == today.snoozed == 0


def test_하루_줄의_요약_문구는_휴식_운동_횟수만_보여_준다():
    from eyeexercise.ui.records_tab import activity_summary

    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11), "dot_follow", 60), skipped(at(10, 7, 12)), snoozed(at(10, 7, 13)), done(at(10, 6, 9))]
    days = timeline(events)
    assert activity_summary(days[0]) == "휴식 2회 · 운동 1회"  # 건너뜀·미룸 횟수는 적지 않는다(마우스를 올리면 칸의 설명에 나온다)
    assert activity_summary(days[1]) == "휴식 1회 · 운동 0회"
    assert (days[0].skipped, days[0].snoozed) == (1, 1)  # 값은 그대로 계산해 둔다


def test_자정을_기준으로_오늘과_어제가_나뉜다():
    events = [done(datetime(2026, 10, 7, 0, 1, tzinfo=KST)), done(datetime(2026, 10, 6, 23, 59, tzinfo=KST))]
    days = timeline(events)
    assert [len(d.marks) for d in days[:2]] == [1, 1]
    assert days[1].marks[0].minute == pytest.approx(23 * 60 + 59)


def test_보여_주는_기간_밖의_기록은_빠진다():
    events = [done(at(10, 1, 9)), done(at(9, 30, 9))]
    days = timeline(events, days=7)
    assert sum(len(d.marks) for d in days) == 1  # 10월 1일은 7일 안, 9월 30일은 밖


def test_모르는_운동_이름은_그대로_보여_준다():
    assert timeline([done(at(10, 7), "jumping", 10)])[0].marks[0].tip == "12:00 jumping · 10초"


def test_완료_시간이_없으면_길이는_설명에_없다():
    events = [HistoryEvent(at(10, 7), "completed", "blink", None)]
    assert timeline(events)[0].marks[0].tip == "12:00 눈 휴식"


def test_모르는_종류의_이벤트는_건너뛴다():
    days = timeline([HistoryEvent(at(10, 7), "unknown"), done(at(10, 7, 9))])
    assert len(days[0].marks) == 1


def test_스크린_타임은_시간대별_초와_합계와_범위를_담는다():
    days = timeline(entries=[(10, 7, 9, 3600), (10, 7, 10, 1800), (10, 7, 18, 120), (10, 6, 9, 1800)])
    today = days[0]
    assert today.hours[9] == 3600 and today.hours[10] == 1800 and today.hours[18] == 120
    assert today.total_seconds == 5520
    assert not today.is_empty


def test_스크린_타임만_있어도_빈_날이_아니다():
    assert not timeline(entries=[(10, 7, 9, 600)])[0].is_empty


# ---- 차트 눈금 ----


@pytest.mark.parametrize(
    ("value", "axis"),
    [(0, 4), (1, 4), (4, 4), (5, 6), (6, 6), (7, 8), (9, 10), (11, 12), (13, 16), (21, 24), (31, 40), (100, 100), (101, 200), (250, 300)],
)
def test_세로축_최댓값(value, axis):
    from eyeexercise.core.stats import nice_axis_max

    assert nice_axis_max(value) == axis
    assert nice_axis_max(value) >= value


# ---- 스크린 타임 ----


def make_usage(entries):
    """(월, 일, 시, 초) 목록으로 사용 기록을 만든다."""
    from eyeexercise.core.usage import UsageLog

    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(datetime(2026, month, day, hour, 0, tzinfo=KST), seconds)
    return usage


def test_스크린_타임_주_보기는_7개_막대이고_하루_합계를_쓴다():
    from eyeexercise.core.stats import build_usage_buckets

    usage = make_usage([(10, 5, 9, 1800), (10, 5, 15, 600), (10, 7, 10, 3000)])
    b = build_usage_buckets(Period.WEEK, TODAY, usage, NOW, KST)
    assert [x.label for x in b] == list("월화수목금토일")
    assert [x.seconds for x in b] == [2400, 0, 3000, 0, 0, 0, 0]
    assert b[2].is_current and b[3].is_future


def test_스크린_타임_하루_보기는_24개_시간대():
    from eyeexercise.core.stats import build_usage_buckets

    usage = make_usage([(10, 7, 9, 1800), (10, 7, 14, 900), (10, 6, 9, 500)])
    b = build_usage_buckets(Period.DAY, TODAY, usage, NOW, KST)
    assert len(b) == 24 and b[9].seconds == 1800 and b[14].seconds == 900 and sum(x.seconds for x in b) == 2700
    assert b[14].is_current and b[15].is_future
    assert [x.label for x in b if x.show_label] == ["0시", "6시", "12시", "18시"]


def test_스크린_타임_월_보기는_그_달_날짜_수만큼():
    from eyeexercise.core.stats import build_usage_buckets

    usage = make_usage([(10, 1, 9, 100), (10, 31, 9, 200), (9, 30, 9, 999), (11, 1, 9, 999)])
    b = build_usage_buckets(Period.MONTH, TODAY, usage, NOW, KST)
    assert len(b) == 31 and b[0].seconds == 100 and b[30].seconds == 200 and sum(x.seconds for x in b) == 300


def test_스크린_타임_기록이_없으면_모두_0():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage
    from eyeexercise.core.usage import UsageLog

    b = build_usage_buckets(Period.WEEK, TODAY, UsageLog(), NOW, KST)
    s = summarize_usage(Period.WEEK, TODAY, b, NOW, KST)
    assert (s.total_seconds, s.average_per_day, s.peak_label, s.peak_seconds, s.active_buckets) == (0, 0, "", 0, 0)


def test_스크린_타임_요약은_합계_하루_평균_가장_많은_날():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage

    usage = make_usage([(10, 5, 9, 3600), (10, 6, 9, 1800), (10, 7, 9, 7200 - 3600), (10, 7, 10, 1800)])
    b = build_usage_buckets(Period.WEEK, TODAY, usage, NOW, KST)
    s = summarize_usage(Period.WEEK, TODAY, b, NOW, KST)
    assert s.total_seconds == 3600 + 1800 + 3600 + 1800
    assert s.average_per_day == pytest.approx(10800 / 3)  # 월·화·수 3일
    assert (s.peak_label, s.peak_seconds) == ("수요일", 5400)  # 수요일 3600 + 1800
    assert s.active_buckets == 3


def test_스크린_타임_가장_많은_막대_이름은_기간마다_다르다():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage

    usage = make_usage([(10, 7, 14, 3000)])
    for period, name in [(Period.DAY, "14시"), (Period.WEEK, "수요일"), (Period.MONTH, "7일")]:
        s = summarize_usage(period, TODAY, build_usage_buckets(period, TODAY, usage, NOW, KST), NOW, KST)
        assert s.peak_label == name


def test_스크린_타임_지난_주_평균은_7일로_나눈다():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage

    usage = make_usage([(9, 30, 9, 3600), (10, 4, 9, 3600)])
    anchor = date(2026, 9, 30)
    s = summarize_usage(Period.WEEK, anchor, build_usage_buckets(Period.WEEK, anchor, usage, NOW, KST), NOW, KST)
    assert s.average_per_day == pytest.approx(7200 / 7)


def test_스크린_타임_하이라이트_주_월():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage, usage_highlights

    usage = make_usage([(10, 5, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 3600)])  # 월 1시간, 수 2시간 (한 시간대는 최대 3600초)
    s = summarize_usage(Period.WEEK, TODAY, build_usage_buckets(Period.WEEK, TODAY, usage, NOW, KST), NOW, KST)
    rest = rs(Period.WEEK, usage, [done(at(10, 5, 9)), done(at(10, 7, 9, 30))])
    cards = usage_highlights(Period.WEEK, s, rest)
    assert [c.label for c in cards] == ["하루 평균", "최장 연속 사용 시간"]
    assert cards[0].value == "1시간"  # 3시간 / 월·화·수 3일
    assert cards[1].value.endswith("분") or cards[1].value.endswith("시간")
    assert [c.label for c in usage_highlights(Period.MONTH, s, rest)] == ["하루 평균", "최장 연속 사용 시간"]


def test_스크린_타임_하이라이트_하루():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage, usage_highlights

    usage = make_usage([(10, 7, 9, 1800), (10, 7, 14, 2700)])
    s = summarize_usage(Period.DAY, TODAY, build_usage_buckets(Period.DAY, TODAY, usage, NOW, KST), NOW, KST)
    cards = usage_highlights(Period.DAY, s, rs(Period.DAY, usage, []))
    # 피크 타임 14시(45분) · 최장 연속 사용 시간(휴식이 없으니 14시대의 45분)
    assert [(c.label, c.value, c.detail) for c in cards] == [("피크 타임", "45분", "14시"), ("최장 연속 사용 시간", "45분", "")]


def test_스크린_타임_사용이_없으면_카드는_대시이거나_0이다():
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage, usage_highlights
    from eyeexercise.core.usage import UsageLog

    s = summarize_usage(Period.WEEK, TODAY, build_usage_buckets(Period.WEEK, TODAY, UsageLog(), NOW, KST), NOW, KST)
    cards = usage_highlights(Period.WEEK, s, rs(Period.WEEK, UsageLog(), []))
    assert [c.value for c in cards] == ["0분", "–"]
    assert [c.detail for c in cards] == ["", ""]


@pytest.mark.parametrize(
    ("seconds", "text", "parts"),
    [
        (0, "0분", [("0", "분")]),
        (29, "0분", [("0", "분")]),
        (30, "0분", [("0", "분")]),  # 0.5분은 반올림 규칙상 0분(파이썬 round는 짝수로)
        (31, "1분", [("1", "분")]),
        (45 * 60, "45분", [("45", "분")]),
        (3599, "1시간", [("1", "시간")]),
        (3600, "1시간", [("1", "시간")]),
        (3600 + 12 * 60, "1시간 12분", [("1", "시간"), ("12", "분")]),
        (5 * 3600 + 12 * 60, "5시간 12분", [("5", "시간"), ("12", "분")]),
        (-100, "0분", [("0", "분")]),
    ],
)
def test_스크린_타임_표시_형식(seconds, text, parts):
    from eyeexercise.core.stats import format_usage, usage_parts

    assert format_usage(seconds) == text
    assert usage_parts(seconds) == parts


@pytest.mark.parametrize(
    ("max_seconds", "axis_minutes"),
    [(0, 20), (1200, 20), (1201, 30), (1800, 30), (1801, 60), (3600, 60), (3601, 120), (4 * 3600, 240), (5 * 3600, 360), (24 * 3600, 1440)],
)
def test_스크린_타임_세로축_최댓값(max_seconds, axis_minutes):
    from eyeexercise.core.stats import nice_usage_axis

    assert nice_usage_axis(max_seconds) == axis_minutes * 60


def test_스크린_타임_세로축은_하루를_넘으면_24시간_단위로_올린다():
    from eyeexercise.core.stats import nice_usage_axis

    assert nice_usage_axis(24 * 3600 + 1) == 48 * 3600


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0"), (600, "10분"), (1800, "30분"), (3600, "1시간"), (5400, "1시간 30분"), (7200, "2시간"), (12 * 3600, "12시간")]
)
def test_스크린_타임_세로축_눈금_글자(seconds, text):
    from eyeexercise.core.stats import format_usage_axis

    assert format_usage_axis(seconds) == text


def test_세로축_가운데_눈금도_깔끔하다():
    from eyeexercise.core.stats import format_usage_axis, nice_usage_axis

    for max_seconds in (100, 1500, 3000, 7000, 12000, 20000, 40000, 80000):
        axis = nice_usage_axis(max_seconds)
        assert axis % 60 == 0
        assert (axis // 2) % 300 == 0, axis  # 가운데 눈금이 5분 단위로 떨어진다 (15분, 30분, 1시간 30분…)
        assert format_usage_axis(axis // 2)


# ---- 어제와 비교 (어제 하루 전체와 비교한다) ----
# NOW는 수요일 14:30이다.


def compare(events=(), entries=(), now=NOW):
    from eyeexercise.core.stats import compare_today

    return compare_today(events, usage_of_hours(entries), now, KST)


def usage_of_hours(entries):
    """(월, 일, 시, 초) 목록으로 사용 기록을 만든다."""
    from eyeexercise.core.usage import UsageLog

    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(at(month, day, hour, 0), seconds)
    return usage


def test_오늘이_어제보다_많으면_많다고_알려_준다():
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 14)), done(at(10, 6, 9))]  # 오늘 3회(198초), 어제 1회(66초)
    c = compare(events)
    assert c.exercise_count == 3 and c.exercise_trend == "up"
    assert c.exercise_lines == ["어제보다 2회 많아요"]


def test_오늘이_적으면_적다고_알려_준다():
    events = [done(at(10, 7, 9)), done(at(10, 6, 9)), done(at(10, 6, 10)), done(at(10, 6, 11))]
    c = compare(events)
    assert c.exercise_trend == "down"
    assert c.exercise_lines == ["어제보다 2회 적어요"]


def test_같으면_같다고_알려_준다():
    c = compare([done(at(10, 7, 9)), done(at(10, 6, 9))])
    assert c.exercise_trend == "same"
    assert c.exercise_lines == ["어제와 같아요"]


def test_어제는_하루_전체를_센다_저녁_기록도_포함():
    events = [done(at(10, 7, 9)), done(at(10, 6, 9)), done(at(10, 6, 23, 59))]  # 어제는 오전과 밤 11시 59분
    assert compare(events).exercise_lines[0] == "어제보다 1회 적어요"


def test_비교는_지금_몇_시인지와_상관없다():
    events = [done(at(10, 7, 9)), done(at(10, 6, 9)), done(at(10, 6, 20))]
    morning = compare(events, now=datetime(2026, 10, 7, 9, 30, tzinfo=KST))
    night = compare(events, now=datetime(2026, 10, 7, 23, 0, tzinfo=KST))
    assert morning.exercise_lines == night.exercise_lines == ["어제보다 1회 적어요"]


def test_건너뜀과_미룸은_횟수에_세지_않는다():
    events = [done(at(10, 7, 9)), skipped(at(10, 7, 10)), snoozed(at(10, 7, 11)), done(at(10, 6, 9)), skipped(at(10, 6, 10)), skipped(at(10, 6, 11))]
    assert compare(events).exercise_count == 1
    assert compare(events).exercise_lines[0] == "어제와 같아요"


def test_어제_기록이_전혀_없으면_비교하지_않는다():
    c = compare([done(at(10, 7, 9)), done(at(10, 5, 9))])  # 그저께 기록은 어제가 아니다
    assert c.exercise_lines == ["어제 기록이 없어요"] and c.exercise_trend == "same"
    assert c.exercise_count == 1


def test_어제_건너뜀만_있어도_앱이_켜져_있었으니_비교한다():
    c = compare([done(at(10, 7, 9)), skipped(at(10, 6, 9))])
    assert c.exercise_lines[0] == "어제보다 1회 많아요"


def test_오늘_기록이_없으면_0회이고_어제보다_적다():
    c = compare([done(at(10, 6, 9)), done(at(10, 6, 10))])
    assert c.exercise_count == 0 and c.exercise_trend == "down"
    assert c.exercise_lines[0] == "어제보다 2회 적어요"


def test_다른_시간대로_저장된_기록도_로컬_날짜로_비교한다():
    utc = HistoryEvent(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc), "completed", "blink", 66)  # KST 어제 09:00
    assert compare([utc, done(at(10, 7, 9))]).exercise_lines[0] == "어제와 같아요"


def test_자정을_넘긴_기록은_날짜로_구분한다():
    now = datetime(2026, 10, 7, 0, 10, tzinfo=KST)
    events = [done(datetime(2026, 10, 7, 0, 5, tzinfo=KST)), done(datetime(2026, 10, 6, 0, 5, tzinfo=KST)), done(datetime(2026, 10, 6, 23, 59, tzinfo=KST))]
    c = compare(events, now=now)
    assert c.exercise_count == 1 and c.exercise_lines[0] == "어제보다 1회 적어요"


def test_스크린_타임은_어제_하루_전체와_비교한다():
    # 어제: 9시 1시간, 10시 1시간, 14시 50분, 15시 1시간 = 13800초. 오늘: 9시 1시간, 10시 30분 = 5400초
    entries = [(10, 6, 9, 3600), (10, 6, 10, 3600), (10, 6, 14, 3000), (10, 6, 15, 3600), (10, 7, 9, 3600), (10, 7, 10, 1800)]
    c = compare(entries=entries)
    assert c.screen_seconds == 5400
    assert c.screen_line == "어제보다 2시간 20분 적어요" and c.screen_trend == "down"  # 5400 - 13800 = -8400초


def test_스크린_타임이_더_많으면_많다고_알려_준다():
    entries = [(10, 6, 9, 600), (10, 7, 9, 3600), (10, 7, 10, 3600), (10, 7, 11, 600)]
    c = compare(entries=entries)
    assert c.screen_line == "어제보다 2시간 많아요" and c.screen_trend == "up"  # 7800 - 600 = 7200초


def test_스크린_타임_차이가_분으로_0분이면_비슷하다고_한다():
    for today_seconds in (1000, 1020, 1030, 980, 970):  # 어제 1000초 기준 0, +20, +30, -20, -30초
        c = compare(entries=[(10, 6, 9, 1000), (10, 7, 9, today_seconds)])
        assert c.screen_line == "어제와 비슷해요" and c.screen_trend == "same", today_seconds


def test_스크린_타임_차이가_1분_이상으로_보이면_비슷하다고_하지_않는다():
    c = compare(entries=[(10, 6, 9, 1000), (10, 7, 9, 1040)])  # +40초 → 1분
    assert c.screen_line == "어제보다 1분 많아요" and c.screen_trend == "up"
    c = compare(entries=[(10, 6, 9, 1000), (10, 7, 9, 960)])  # -40초 → 1분
    assert c.screen_line == "어제보다 1분 적어요" and c.screen_trend == "down"


def test_스크린_타임_5분_차이는_비슷하지_않다():
    c = compare(entries=[(10, 6, 9, 1000), (10, 7, 9, 1300)])
    assert c.screen_line == "어제보다 5분 많아요"


def test_스크린_타임_비교_문구에는_0분이_나오지_않는다():
    for today_seconds in range(0, 3600, 7):
        line = compare(entries=[(10, 6, 9, 1800), (10, 7, 9, today_seconds)]).screen_line
        assert not re.search(r"(?<!\d)0분", line), (today_seconds, line)  # "30분"의 0은 괜찮고, 단독 "0분"만 막는다


def test_어제_스크린_타임_기록이_없으면_비교하지_않는다():
    c = compare(entries=[(10, 7, 9, 3600)])
    assert c.screen_line == "어제 기록이 없어요" and c.screen_trend == "same" and c.screen_seconds == 3600


def test_운동과_스크린_타임_비교는_서로_독립이다():
    c = compare([done(at(10, 7, 9)), done(at(10, 6, 9))], entries=[(10, 7, 9, 3600)])
    assert c.exercise_lines[0] == "어제와 같아요" and c.screen_line == "어제 기록이 없어요"


def test_추세_기호():
    from eyeexercise.core.stats import TREND_SYMBOLS

    assert TREND_SYMBOLS == {"up": "▲", "down": "▼", "same": "–"}


# ---- 앞 기간과 비교 (전날 / 전주 / 전달) ----
# NOW는 수요일 14:30. 이번 주는 10/5(월)~10/11(일) 중 월·화·수 3일이 지났다. 지난 주는 9/28~10/4.


def pc_exercise(period, events, anchor=TODAY):
    from eyeexercise.core.stats import compare_exercise_period

    return compare_exercise_period(period, anchor, events, NOW, KST)


def pc_usage(period, entries, anchor=TODAY):
    from eyeexercise.core.stats import compare_usage_period

    return compare_usage_period(period, anchor, usage_of_hours(entries), NOW, KST)


def lw(d):
    """지난 주(9/28 월요일 시작)의 d번째 날의 (월, 일)."""
    day = date(2026, 9, 28) + timedelta(days=d)
    return day.month, day.day


def lw_at(d, hour):
    month, day = lw(d)
    return at(month, day, hour)


def test_앞_기간의_이름():
    from eyeexercise.core.stats import previous_label

    assert [previous_label(Period.DAY, TODAY, TODAY), previous_label(Period.WEEK, TODAY, TODAY), previous_label(Period.MONTH, TODAY, TODAY)] == ["어제", "지난 주", "지난 달"]
    past = date(2026, 9, 15)
    assert [previous_label(Period.DAY, past, TODAY), previous_label(Period.WEEK, past, TODAY), previous_label(Period.MONTH, past, TODAY)] == ["전날", "전주", "전달"]


def test_이번_기간이_아니면_전날_전주_전달이라고_부른다():
    from eyeexercise.core.stats import previous_label

    assert previous_label(Period.DAY, date(2026, 10, 6), TODAY) == "전날"  # 어제를 보는 중이면 그 앞은 '전날'
    assert previous_label(Period.WEEK, date(2026, 9, 30), TODAY) == "전주"  # 지난 주를 보는 중이면 그 앞은 '전주'


def test_조사는_마지막_글자의_받침에_맞춘다():
    from eyeexercise.core.stats import _with_particle

    assert [_with_particle(w) for w in ("어제", "전날", "지난 주", "전주", "지난 달", "전달")] == ["어제와", "전날과", "지난 주와", "전주와", "지난 달과", "전달과"]


# -- 일 --


def test_일_운동은_전날_합계와_비교한다():
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))]
    c = pc_exercise(Period.DAY, events)
    assert c.trend == "up" and c.lines == ["어제보다 1회 많아요"]


def test_지난_날을_보면_그_전날과_비교한다():
    events = [done(at(10, 6, 9)), done(at(10, 6, 10)), done(at(10, 5, 9))]
    c = pc_exercise(Period.DAY, events, anchor=date(2026, 10, 6))
    assert c.lines[0] == "전날보다 1회 많아요"
    same = pc_exercise(Period.DAY, [done(at(10, 6, 9)), done(at(10, 5, 9))], anchor=date(2026, 10, 6))
    assert same.trend == "same" and same.lines == ["전날과 같아요"]


def test_일_비교는_오늘_요약과_같은_결과다():
    from eyeexercise.core.stats import compare_today

    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9)), done(at(10, 6, 20), seconds=100), skipped(at(10, 6, 11))]
    usage = usage_of_hours([(10, 6, 9, 3600), (10, 7, 9, 1800)])
    today = compare_today(events, usage, NOW, KST)
    from eyeexercise.core.stats import compare_exercise_period, compare_usage_period

    ex = compare_exercise_period(Period.DAY, TODAY, events, NOW, KST)
    assert (ex.trend, ex.lines) == (today.exercise_trend, today.exercise_lines)
    us = compare_usage_period(Period.DAY, TODAY, usage, NOW, KST)
    assert (us.trend, us.lines) == (today.screen_trend, [today.screen_line])


def test_앞_기간에_기록이_없으면_비교하지_않는다():
    assert pc_exercise(Period.DAY, [done(at(10, 7, 9))]).lines == ["어제 기록이 없어요"]
    assert pc_exercise(Period.WEEK, [done(at(10, 7, 9))]).lines == ["지난 주 기록이 없어요"]
    assert pc_exercise(Period.MONTH, [done(at(10, 7, 9))]).lines == ["지난 달 기록이 없어요"]
    assert pc_exercise(Period.WEEK, [done(at(10, 7, 9))]).trend == "same"


def test_앞_기간에_건너뜀만_있어도_앱이_켜져_있었으니_비교한다():
    c = pc_exercise(Period.DAY, [done(at(10, 7, 9)), skipped(at(10, 6, 9))])
    assert c.lines[0] == "어제보다 1회 많아요"


# -- 주 --


def test_주는_하루_평균끼리_비교한다_진행_중인_주도_공정하게():
    # 이번 주(월~수 3일): 6회 → 하루 평균 2.0회. 지난 주(7일): 7회 → 하루 평균 1.0회. 합계는 이번 주가 적지만 평균은 높다.
    events = [done(at(10, 5, h)) for h in (9, 10)] + [done(at(10, 6, 9))] + [done(at(10, 7, h)) for h in (9, 10, 11)]
    events += [done(lw_at(d, 9)) for d in range(7)]
    c = pc_exercise(Period.WEEK, events)
    assert c.trend == "up"
    assert c.lines == ["지난 주보다 하루 평균 1.0회 많아요"]


def test_주_평균이_적으면_적다고_알려_준다():
    events = [done(at(10, 7, 9))] + [done(lw_at(d, h)) for d in range(7) for h in (9, 10)]  # 이번 주 하루 평균 0.3, 지난 주 2.0
    c = pc_exercise(Period.WEEK, events)
    assert c.trend == "down" and c.lines[0] == "지난 주보다 하루 평균 1.7회 적어요"


def test_주_평균이_같으면_같다고_알려_준다():
    events = [done(at(10, 5, 9)), done(at(10, 6, 9)), done(at(10, 7, 9))] + [done(lw_at(d, 9)) for d in range(7)]  # 둘 다 하루 평균 1.0
    c = pc_exercise(Period.WEEK, events)
    assert c.trend == "same" and c.lines == ["하루 평균이 지난 주와 같아요"]


def test_지난_주를_보면_전주와_하루_평균으로_비교한다():
    events = [done(at(9, 29, 9)), done(at(9, 29, 10)), done(at(9, 22, 9))]
    c = pc_exercise(Period.WEEK, events, anchor=date(2026, 9, 30))  # 9/28~10/4 vs 9/21~9/27, 둘 다 7일
    assert c.lines[0] == "전주보다 하루 평균 0.1회 많아요"  # 2/7 - 1/7 = 0.14 → 0.3 - 0.1


def test_하루_평균_차이는_실제_차이를_구한_뒤_반올림한다():
    # 이번 주 하루 평균 2/3(0.67), 지난 주 1/7(0.14): 실제 차이 0.52 → 0.5. 먼저 반올림하면 0.7 - 0.1 = 0.6이 된다.
    events = [done(at(10, 5, 9)), done(at(10, 5, 10))] + [done(lw_at(0, 9))]
    assert pc_exercise(Period.WEEK, events).lines[0] == "지난 주보다 하루 평균 0.5회 많아요"


def test_하루_평균_차이가_화면에서_0점0이면_같다고_한다():
    # 이번 주 3/3 = 1.0, 지난 주 7/7 = 1.0 → 같다. 차이가 0.04여도 0.0회로 보이니 같다고 한다.
    events = [done(at(10, 5, 9)), done(at(10, 6, 9)), done(at(10, 7, 9))] + [done(lw_at(d, 9)) for d in range(7)]
    assert pc_exercise(Period.WEEK, events).trend == "same"


# -- 월 --


def test_월은_전달과_하루_평균으로_비교한다():
    # 이번 달(10/1~10/7, 7일) 14회 → 2.0. 지난 달(30일) 30회 → 1.0
    events = [done(at(10, d, h)) for d in range(1, 8) for h in (9, 10)] + [done(at(9, d, 9)) for d in range(1, 31)]
    c = pc_exercise(Period.MONTH, events)
    assert c.trend == "up" and c.lines[0] == "지난 달보다 하루 평균 1.0회 많아요"


def test_월_평균이_같으면_조사는_과():
    events = [done(at(10, d, 9)) for d in range(1, 8)] + [done(at(9, d, 9)) for d in range(1, 31)]
    assert pc_exercise(Period.MONTH, events).lines[0] == "하루 평균이 지난 달과 같아요"


def test_지난_달을_보면_전달과_비교한다():
    events = [done(at(9, d, 9)) for d in range(1, 31)] + [done(at(8, d, 9)) for d in range(1, 16)]
    c = pc_exercise(Period.MONTH, events, anchor=date(2026, 9, 1))
    assert c.lines[0] == "전달보다 하루 평균 0.5회 많아요"  # 30/30 = 1.0 vs 15/31 = 0.48 → 0.5와 1.0의 차


# -- 스크린 타임 --


def test_일_스크린_타임은_전날_합계와_비교한다():
    c = pc_usage(Period.DAY, [(10, 6, 9, 1800), (10, 7, 9, 3600)])
    assert c.trend == "up" and c.lines == ["어제보다 30분 많아요"]


def test_주_스크린_타임은_하루_평균끼리_비교한다():
    # 이번 주 월~수 각 1시간(하루 평균 1시간), 지난 주 7일 각 30분(하루 평균 30분)
    entries = [(10, d, 9, 3600) for d in (5, 6, 7)] + [(*lw(d), 9, 1800) for d in range(7)]
    c = pc_usage(Period.WEEK, entries)
    assert c.trend == "up" and c.lines == ["지난 주보다 하루 평균 30분 많아요"]


def test_스크린_타임이_더_적으면_적다고_알려_준다():
    entries = [(10, 7, 9, 600)] + [(*lw(d), 9, 3600) for d in range(7)]  # 이번 주 하루 평균 200초(3분), 지난 주 1시간
    c = pc_usage(Period.WEEK, entries)
    assert c.trend == "down" and c.lines == ["지난 주보다 하루 평균 57분 적어요"]


def test_스크린_타임_평균이_분으로_같으면_비슷하다고_한다():
    entries = [(10, d, 9, 1800) for d in (5, 6, 7)] + [(*lw(d), 9, 1810) for d in range(7)]
    c = pc_usage(Period.WEEK, entries)
    assert c.trend == "same" and c.lines == ["하루 평균이 지난 주와 비슷해요"]
    day = pc_usage(Period.DAY, [(10, 6, 9, 1800), (10, 7, 9, 1810)])
    assert day.lines == ["어제와 비슷해요"]


def test_월_스크린_타임은_전달과_비교한다():
    entries = [(10, d, 9, 3600) for d in range(1, 8)] + [(9, d, 9, 1800) for d in range(1, 31)]
    c = pc_usage(Period.MONTH, entries)
    assert c.lines == ["지난 달보다 하루 평균 30분 많아요"]
    past = pc_usage(Period.MONTH, [(9, d, 9, 3600) for d in range(1, 31)] + [(8, d, 9, 1800) for d in range(1, 32)], anchor=date(2026, 9, 1))
    assert past.lines == ["전달보다 하루 평균 30분 많아요"]


def test_앞_기간_스크린_타임_기록이_없으면_비교하지_않는다():
    assert pc_usage(Period.DAY, [(10, 7, 9, 600)]).lines == ["어제 기록이 없어요"]
    assert pc_usage(Period.WEEK, [(10, 7, 9, 600)]).lines == ["지난 주 기록이 없어요"]
    assert pc_usage(Period.MONTH, [(10, 7, 9, 600)]).lines == ["지난 달 기록이 없어요"]


def test_스크린_타임_비교_문구에는_0분이_나오지_않는다():
    for seconds in range(0, 3600, 13):
        for period in (Period.DAY, Period.WEEK):
            entries = [(10, 6, 9, 1800), (9, 30, 9, 1800), (10, 7, 9, seconds)]
            line = pc_usage(period, entries).lines[0]
            assert not re.search(r"(?<!\d)0분", line), (period, seconds, line)


# ---- 하이라이트 카드의 앞 기간 비교 ----


def ex_summary(period, events, anchor=TODAY):
    return summarize_range(period, anchor, build_buckets(period, anchor, events, NOW, KST), NOW, KST)


def us_summary(period, usage, anchor=TODAY):
    from eyeexercise.core.stats import build_usage_buckets, summarize_usage

    return summarize_usage(period, anchor, build_usage_buckets(period, anchor, usage, NOW, KST), NOW, KST)


def rs(period, usage, events, anchor=TODAY, interval=20):
    from eyeexercise.core.stats import rest_stats

    return rest_stats(period, anchor, usage, events, NOW, KST, interval)


def card_map(cards):
    return {c.label: c for c in cards}


def exercise_cards(period, events, anchor=TODAY, label="지난 주", kind="skipped", usage=None):
    from eyeexercise.core.stats import rest_highlights_with_compare, rest_slot_count
    from eyeexercise.core.usage import UsageLog

    events = list(events)
    usage = usage or UsageLog()
    previous_anchor = shift_anchor(period, anchor, -1)
    return card_map(
        rest_highlights_with_compare(
            period,
            ex_summary(period, events, anchor),
            ex_summary(period, events, previous_anchor),
            label,
            rs(period, usage, events, anchor),
            rest_slot_count(period, anchor, events, KST),
            rest_slot_count(period, previous_anchor, events, KST),
            kind,
        )
    )


# 이번 주 월~수: 완료 6회(월2·화1·수3, 66초씩), 건너뜀 3회(월1·수2). 지난 주: 완료 7회(하루 1회), 건너뜀 2회
WEEK_CARD_EVENTS = (
    [done(at(10, 5, 9)), done(at(10, 5, 10)), done(at(10, 6, 9)), done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11))]
    + [skipped(at(10, 5, 12)), skipped(at(10, 7, 12)), skipped(at(10, 7, 13))]
    + [done(lw_at(d, 9)) for d in range(7)]
    + [skipped(lw_at(0, 12)), skipped(lw_at(3, 12))]
)


def test_주_카드는_하루_평균끼리_비교한다():
    cards = exercise_cards(Period.WEEK, WEEK_CARD_EVENTS)
    assert [cards[k].value for k in ("휴식 달성률", "건너뜀", "휴식 시간대")] == ["–", "3회", "2.0개"]  # 월·화·수 시간대 6개 ÷ 3일
    assert (cards["건너뜀"].compare, cards["건너뜀"].trend) == ("지난 주보다 하루 평균 0.7회 많아요", "up")  # 1.0 - 0.29
    assert (cards["휴식 시간대"].compare, cards["휴식 시간대"].trend) == ("지난 주보다 하루 평균 1.0개 많아요", "up")  # 6/3 - 7/7
    assert cards["휴식 달성률"].compare == ""  # 달성률은 앞 기간과 비교하지 않는다


def test_미룸을_고르면_미룸을_앞_기간과_비교한다():
    events = [snoozed(at(10, 7, 9)), snoozed(at(10, 7, 10)), snoozed(lw_at(0, 9)), done(at(10, 7, 11))]
    cards = exercise_cards(Period.WEEK, events, kind="snoozed")
    assert "건너뜀" not in cards and cards["미룸"].value == "2회"
    assert (cards["미룸"].compare, cards["미룸"].trend) == ("지난 주보다 하루 평균 0.5회 많아요", "up")  # 2/3 - 1/7


def test_월_카드도_하루_평균끼리_비교한다():
    events = [done(at(10, d, h)) for d in range(1, 8) for h in (9, 10)] + [done(at(9, d, 9)) for d in range(1, 31)]
    cards = exercise_cards(Period.MONTH, events, label="지난 달")
    assert cards["건너뜀"].compare == "지난 달과 같아요"  # 둘 다 0
    assert cards["휴식 시간대"].compare == "지난 달보다 하루 평균 1.0개 많아요"  # 14/7 - 1


def test_일_카드는_합계끼리_비교한다():
    events = (
        [done(at(10, 7, 9)), done(at(10, 7, 10)), skipped(at(10, 7, 11))]  # 오늘 완료 2회, 건너뜀 1, 미룸 0
        + [done(at(10, 6, 9)), skipped(at(10, 6, 10)), skipped(at(10, 6, 11)), snoozed(at(10, 6, 12))]  # 어제 완료 1회, 건너뜀 2, 미룸 1
    )
    cards = exercise_cards(Period.DAY, events, label="어제")
    assert [cards[k].value for k in ("건너뜀", "휴식 시간대")] == ["1회", "2개"]  # 9시와 10시에 쉬었다
    assert (cards["휴식 시간대"].compare, cards["휴식 시간대"].trend) == ("어제보다 1개 많아요", "up")
    assert (cards["건너뜀"].compare, cards["건너뜀"].trend) == ("어제보다 1회 적어요", "down")
    assert exercise_cards(Period.DAY, events, label="어제", kind="snoozed")["미룸"].compare == "어제보다 1회 적어요"


def test_같은_값이면_같다고_알려_준다():
    events = [done(at(10, 7, 9)), skipped(at(10, 7, 10)), done(at(10, 6, 9)), skipped(at(10, 6, 10))]
    cards = exercise_cards(Period.DAY, events, label="어제")
    assert all(cards[k].compare == "어제와 같아요" and cards[k].trend == "same" for k in ("휴식 시간대", "건너뜀"))


def test_카드_값은_비교를_더해도_그대로다():
    from eyeexercise.core.stats import rest_slot_count
    from eyeexercise.core.usage import UsageLog

    events = list(WEEK_CARD_EVENTS)
    plain_cards = rest_highlights(
        Period.WEEK, ex_summary(Period.WEEK, events), rs(Period.WEEK, UsageLog(), events), rest_slot_count(Period.WEEK, TODAY, events, KST)
    )
    with_compare = exercise_cards(Period.WEEK, events)
    assert [(c.label, c.value, c.detail) for c in plain_cards] == [(c.label, c.value, c.detail) for c in with_compare.values()]


def test_앞_기간에_기록이_없으면_카드에_비교를_붙이지_않는다():
    cards = exercise_cards(Period.WEEK, [done(at(10, 7, 9))])
    assert all(c.compare == "" and c.trend == "same" for c in cards.values())


def test_앞_기간_정보가_없으면_카드에_비교를_붙이지_않는다():
    from eyeexercise.core.stats import rest_highlights_with_compare
    from eyeexercise.core.usage import UsageLog

    cards = rest_highlights_with_compare(
        Period.WEEK, ex_summary(Period.WEEK, WEEK_CARD_EVENTS), None, "지난 주", rs(Period.WEEK, UsageLog(), []), 5, 0
    )
    assert all(c.compare == "" for c in cards)


def test_지난_기간을_보면_전주_이름으로_비교한다():
    events = [done(lw_at(0, 9)), done(lw_at(1, 9)), done(at(9, 21, 9)), skipped(lw_at(0, 12))]
    cards = exercise_cards(Period.WEEK, events, anchor=date(2026, 9, 30), label="전주")
    assert cards["건너뜀"].compare.startswith("전주보다 하루 평균")


def test_카드_비교_조사는_앞_기간_이름에_맞다():
    events = [done(at(10, 7, 9)), done(at(10, 6, 9))]
    assert exercise_cards(Period.DAY, events, label="어제")["건너뜀"].compare == "어제와 같아요"
    assert exercise_cards(Period.DAY, events, label="전날")["건너뜀"].compare == "전날과 같아요"
    month = exercise_cards(Period.MONTH, [done(at(10, 7, 9)), done(at(9, 1, 9))], label="지난 달")
    assert month["건너뜀"].compare == "지난 달과 같아요"


# -- 스크린 타임 카드 --


def usage_cards(period, entries, events=(), prev_entries=None, anchor=TODAY, label="지난 주"):
    from eyeexercise.core.stats import usage_highlights_with_compare

    usage = usage_of_hours(entries)
    events = list(events)
    prev_anchor = shift_anchor(period, anchor, -1)
    return card_map(
        usage_highlights_with_compare(
            period,
            us_summary(period, usage, anchor),
            rs(period, usage, events, anchor),
            us_summary(period, usage, prev_anchor),
            rs(period, usage, events, prev_anchor),
            label,
        )
    )


# 이번 주: 월 1시간, 화 2시간(9시·10시), 수 1시간 → 하루 평균 80분, 최고 화요일 2시간. 지난 주: 하루 30분씩 7일 → 하루 평균 30분, 최고 월요일 30분
WEEK_USAGE = [(10, 5, 9, 3600), (10, 6, 9, 3600), (10, 6, 10, 3600), (10, 7, 9, 3600)] + [(*lw(d), 9, 1800) for d in range(7)]


def test_스크린_타임_주_카드_비교():
    cards = usage_cards(Period.WEEK, WEEK_USAGE, WEEK_CARD_EVENTS)
    assert [cards[k].value for k in ("하루 평균", "최장 연속 사용 시간")] == ["1시간 20분", "1시간 59분"]
    assert (cards["하루 평균"].compare, cards["하루 평균"].trend) == ("지난 주보다 50분 많아요", "up")  # 80분 - 30분
    # 화요일 9~11시를 9시 휴식 한 번만 끼고 썼다 (9시 정각에 쉬었으니 그 뒤 119분), 지난 주는 30분씩 7일이라 가장 긴 게 29분
    assert cards["최장 연속 사용 시간"].detail == "어제"
    assert (cards["최장 연속 사용 시간"].compare, cards["최장 연속 사용 시간"].trend) == ("지난 주보다 1시간 30분 많아요", "up")


def test_스크린_타임_일_카드_비교():
    entries = [(10, 7, 9, 3600), (10, 7, 10, 1800), (10, 6, 9, 1800)]  # 오늘 9시 1시간·10시 30분, 어제 9시 30분
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))]
    cards = usage_cards(Period.DAY, entries, events, label="어제")
    assert [cards[k].value for k in ("피크 타임", "최장 연속 사용 시간")] == ["1시간", "59분"]
    assert cards["피크 타임"].compare == "어제 최고보다 30분 많아요"
    assert cards["최장 연속 사용 시간"].compare == "어제보다 30분 많아요"  # 9시 정각에 쉰 뒤 59분 vs 어제 30분


def test_스크린_타임이_적으면_적다고_알려_준다():
    entries = [(10, 7, 9, 600)] + [(*lw(d), 9, 3600) for d in range(7)]
    cards = usage_cards(Period.WEEK, entries, [done(at(10, 7, 9)), done(lw_at(0, 9))])
    assert cards["하루 평균"].trend == "down" and cards["하루 평균"].compare == "지난 주보다 57분 적어요"


def test_스크린_타임_평균이_분으로_같으면_비슷하다고_한다():
    entries = [(10, d, 9, 1800) for d in (5, 6, 7)] + [(*lw(d), 9, 1810) for d in range(7)]
    cards = usage_cards(Period.WEEK, entries, [done(at(10, 7, 9)), done(lw_at(0, 9))])
    assert cards["하루 평균"].compare == "지난 주와 비슷해요" and cards["하루 평균"].trend == "same"
    assert cards["최장 연속 사용 시간"].compare == "지난 주와 비슷해요"  # 둘 다 한 시간대 30분을 쉬지 않고 썼다


def test_앞_기간_스크린_타임이_없으면_비교를_붙이지_않는다():
    entries = [(10, 7, 9, 3600)]  # 지난 주 사용 기록 없음
    cards = usage_cards(Period.WEEK, entries, WEEK_CARD_EVENTS)
    assert cards["하루 평균"].compare == "" and cards["최장 연속 사용 시간"].compare == ""


def test_휴식_기록이_없어도_사용_카드는_앞_기간과_비교한다():
    cards = usage_cards(Period.WEEK, WEEK_USAGE, [done(at(10, 7, 9))])
    assert cards["하루 평균"].compare != "" and cards["최장 연속 사용 시간"].compare != ""


def test_스크린_타임_카드_값은_비교를_더해도_그대로다():
    from eyeexercise.core.stats import usage_highlights

    usage = usage_of_hours(WEEK_USAGE)
    plain_cards = usage_highlights(Period.WEEK, us_summary(Period.WEEK, usage), rs(Period.WEEK, usage, list(WEEK_CARD_EVENTS)))
    with_compare = usage_cards(Period.WEEK, WEEK_USAGE, WEEK_CARD_EVENTS)
    assert [(c.label, c.value, c.detail) for c in plain_cards] == [(c.label, c.value, c.detail) for c in with_compare.values()]


def test_비교_문구에는_0분과_0회가_단독으로_나오지_않는다():
    for seconds in range(0, 3600, 17):
        entries = [(10, 7, 9, seconds), (10, 6, 9, 1800)]
        cards = usage_cards(Period.DAY, entries, [done(at(10, 7, 9)), done(at(10, 6, 9))], label="어제")
        for card in cards.values():
            assert not re.search(r"(?<!\d)0(분|회|개)", card.compare), (seconds, card.label, card.compare)


# ---- 쉬지 않고 쓴 가장 긴 시간 / 휴식 달성률 ----


def test_쉬지_않고_쓴_가장_긴_시간은_사용_구간을_휴식과_빈_시간에서_끊는다():
    from eyeexercise.core.stats import longest_unbroken_seconds

    hours = [0.0] * 24
    hours[9] = hours[10] = hours[11] = 3600.0
    assert longest_unbroken_seconds(hours, []) == 3 * 3600  # 9~12시를 한 번도 안 쉬고 썼다
    # 10시 30분에 쉬면 둘로 갈린다. 쉰 그 1분은 빠진다: 9:00~10:29(90분) / 10:31~11:59(89분)
    assert longest_unbroken_seconds(hours, [10 * 60 + 30]) == 90 * 60
    # 사용이 없는 시간대(점심)는 자리를 비운 것이라 쉰 것으로 본다
    hours = [0.0] * 24
    for h in (9, 10, 12, 13, 14):
        hours[h] = 3600.0
    assert longest_unbroken_seconds(hours, []) == 3 * 3600  # 12~15시


def test_쉬지_않고_쓴_시간은_일부만_쓴_시간대는_쓴_만큼만_센다():
    from eyeexercise.core.stats import longest_unbroken_seconds

    hours = [0.0] * 24
    hours[9] = 1800.0
    assert longest_unbroken_seconds(hours, []) == 1800
    assert longest_unbroken_seconds([0.0] * 24, [600]) == 0
    assert longest_unbroken_seconds(hours, [-5, 2000]) == 1800  # 하루 밖의 시각은 무시한다


def test_하루_보기의_휴식_달성률():
    usage = make_usage([(10, 7, 9, 3600), (10, 7, 10, 3600), (10, 7, 11, 3600)])  # 3시간 → 20분마다 권장 9회
    events = [done(at(10, 7, 9, 30)), done(at(10, 7, 10, 0)), done(at(10, 7, 11, 30))]
    stats = rs(Period.DAY, usage, events)
    assert (stats.rests, stats.recommended) == (3, 9)
    assert stats.rate == pytest.approx(1 / 3)
    assert stats.longest_seconds == 89 * 60  # 10:01~11:29 (분 단위로 센 값)
    assert stats.longest_label == ""


def test_휴식을_더_많이_해도_달성률은_100퍼센트가_최대다():
    usage = make_usage([(10, 7, 9, 1500)])  # 25분 사용 → 권장 1회
    events = [done(at(10, 7, 9, m)) for m in (5, 10, 15)]
    assert rs(Period.DAY, usage, events).rate == 1.0


def test_사용_시간이_1분도_안_되면_달성률을_계산하지_않는다():
    stats = rs(Period.DAY, make_usage([(10, 7, 9, 59)]), [done(at(10, 7, 9, 5))])
    assert stats.recommended == 0 and stats.rate is None


def test_휴식_주기보다_짧게_써도_권장_횟수는_1회다():
    stats = rs(Period.DAY, make_usage([(10, 7, 9, 600)]), [done(at(10, 7, 9, 5))])
    assert (stats.recommended, stats.rate) == (1, 1.0)


def test_휴식_달성률은_눈_휴식_완료만_센다():
    usage = make_usage([(10, 7, 9, 3600)])
    events = [done(at(10, 7, 9, 5)), skipped(at(10, 7, 9, 10)), snoozed(at(10, 7, 9, 15)), done(at(10, 7, 9, 30), "dot_follow", 60)]
    assert rs(Period.DAY, usage, events).rests == 1  # 건너뜀·미룸·눈 운동은 휴식으로 세지 않는다


def test_권장_횟수는_하루마다_올림해서_더한다():
    # 하루 19분씩 3일이면 하루로 합친 57분(올림 3회)이 아니라 하루마다 1회씩 3회
    usage = make_usage([(10, 5, 9, 1140), (10, 6, 9, 1140), (10, 7, 9, 1140)])
    assert rs(Period.WEEK, usage, []).recommended == 3


def test_20분을_조금_넘기면_권장_횟수는_2회다():
    usage = make_usage([(10, 7, 9, 1201)])
    assert rs(Period.DAY, usage, []).recommended == 2
    assert rs(Period.DAY, make_usage([(10, 7, 9, 1200)]), []).recommended == 1  # 정확히 20분이면 1회


def test_휴식_주기를_바꾸면_권장_횟수가_따라간다():
    usage = make_usage([(10, 7, 9, 3600)])
    assert rs(Period.DAY, usage, [], interval=20).recommended == 3
    assert rs(Period.DAY, usage, [], interval=30).recommended == 2
    assert rs(Period.DAY, usage, [], interval=60).recommended == 1


def test_주_보기는_가장_길게_쉬지_않은_날의_이름을_알려_준다():
    usage = make_usage([(10, 5, 9, 3600), (10, 6, 9, 3600), (10, 6, 10, 3600), (10, 7, 9, 3600)])
    stats = rs(Period.WEEK, usage, [])
    assert stats.longest_seconds == 2 * 3600 and stats.longest_label == "어제"  # 화요일(오늘이 수요일)


def test_아직_오지_않은_날은_세지_않는다():
    usage = make_usage([(10, 7, 9, 3600)])
    stats = rs(Period.WEEK, usage, [])
    assert stats.recommended == 3  # 오늘까지만
