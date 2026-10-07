import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.scheduler import ReminderScheduler
from eyeexercise.core.settings import Settings
from eyeexercise.core.stats import Period, format_usage_axis
from eyeexercise.core.usage import UsageLog, UsageTracker
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.records_tab import Mode, RecordsTab

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일. 이번 주는 10/5(월) ~ 10/11(일)


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def done(ts):
    return HistoryEvent(ts, "completed", "blink", 66)


def usage_of(entries):
    """(월, 일, 시, 초) 목록으로 사용 기록을 만든다. 한 시간대는 최대 3600초다."""
    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(at(month, day, hour, 0), seconds)
    return usage


class Source:
    """운동 기록을 돌려주는 가짜. 호출 횟수를 센다."""

    def __init__(self, events=()):
        self.events = list(events)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.events


def make_tab(qapp, events=(), entries=()):
    source = Source(events)
    usage = usage_of(entries)
    tab = RecordsTab(source, now=lambda: NOW, tz=KST, usage_provider=lambda: usage)
    tab.resize(520, 900)
    tab.show()
    qapp.processEvents()
    return tab, source, usage


def big_text(tab):
    """큰 숫자의 글자만 꺼낸다. 예: "2 시간 30 분"."""
    text = re.sub(r"<[^>]+>", "", tab._number.text()).replace("&nbsp;", " ")
    return " ".join(text.split())


def exercise_count(tab):
    return int(re.search(r">(\d+)</span>", tab._number.text()).group(1))


def click_bar(tab, index):
    chart = tab._chart
    rect = chart.bar_rect(index)
    y = rect.center().y() if rect.height() > 0 else chart._plot().bottom() - 4
    QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=QPoint(int(rect.center().x()), int(y)))


def timeline_days_of(tab):
    return tab._timeline._days



# ---- 전환 ----


def test_전환_버튼이_있고_처음에는_눈_휴식이다(qapp):
    tab, _, _ = make_tab(qapp)
    assert [b.text() for b in tab._mode_buttons.values()] == ["눈 휴식", "스크린 타임"]  # 눈 운동은 전환이 아니라 오늘 요약과 하루 흐름에 횟수로만 나온다
    assert tab.mode is Mode.REST and tab._mode_buttons[Mode.REST].isChecked()


def test_버튼을_누르면_모드가_바뀐다(qapp):
    tab, _, _ = make_tab(qapp)
    tab._mode_buttons[Mode.SCREEN_TIME].click()
    assert tab.mode is Mode.SCREEN_TIME and tab._kicker.text() == "스크린 타임"
    tab._mode_buttons[Mode.REST].click()
    assert tab.mode is Mode.REST and tab._kicker.text() == "눈 휴식"


def test_스크린_타임으로_바꾸면_사용_시간을_큰_숫자로_보여_준다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 5, 9, 3600), (10, 7, 9, 1800), (10, 7, 10, 1800)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert tab._kicker.text() == "스크린 타임"
    assert big_text(tab) == "2 시간"  # 월 1시간 + 수 30분 + 30분
    assert tab._caption.text() == "10월 5일 – 10월 11일"


def test_기록이_없으면_0분이고_가운데_안내를_위한_눈금이_있다(qapp):
    tab, _, _ = make_tab(qapp)
    tab.set_mode(Mode.SCREEN_TIME)
    assert big_text(tab) == "0 분"
    assert tab._chart.axis_max == 20 * 60
    assert [v.text() for v in tab._highlight_values] == ["0분", "–", "–"]  # 사용이 없으면 달성률도 계산하지 않는다


def test_운동으로_돌아오면_운동_화면이_그대로다(qapp):
    tab, _, _ = make_tab(qapp, [done(at(10, 5)), done(at(10, 6))], entries=[(10, 5, 9, 3600)])
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_mode(Mode.REST)
    assert tab._kicker.text() == "눈 휴식" and exercise_count(tab) == 2
    assert tab._section.text() == "하루 흐름"
    assert tab._chart.axis_max == 4
    marked = [(d.title, [m.minute for m in d.marks]) for d in timeline_days_of(tab) if d.marks]
    assert marked == [("어제", [720]), ("10월 5일 (월)", [720])]


def test_모드를_바꿔도_기간과_위치는_유지되고_선택만_풀린다(qapp):
    tab, _, _ = make_tab(qapp, [done(at(10, 5))], entries=[(10, 5, 9, 600)])
    tab.set_period(Period.MONTH)
    tab.go(-1)
    anchor = tab.anchor
    click_bar(tab, 0)
    assert tab._chart._selected == 0
    tab.set_mode(Mode.SCREEN_TIME)
    assert tab.period is Period.MONTH and tab.anchor == anchor
    assert tab._chart._selected == -1
    assert tab._nav_title.text() == "2026년 9월"


# ---- 차트 ----


def test_막대_높이는_사용_시간에_비례하고_눈금은_시간_단위다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 5, 9, 1800), (10, 6, 9, 3600), (10, 6, 10, 3600), (10, 6, 11, 3600)])
    tab.set_mode(Mode.SCREEN_TIME)
    chart = tab._chart
    assert chart.axis_max == 3 * 3600  # 가장 큰 화요일 3시간
    mon, tue = chart.bar_rect(0), chart.bar_rect(1)
    assert tue.height() == pytest.approx(mon.height() * 6)
    assert chart._format(chart.axis_max) == format_usage_axis(3 * 3600) == "3시간"
    assert chart._format(chart.axis_max / 2) == "1시간 30분"


def test_하루_보기는_24시간_막대와_시간대_하이라이트(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 7, 9, 1800), (10, 7, 14, 2700)])
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert len(tab._chart._buckets) == 24
    assert big_text(tab) == "1 시간 15 분"
    assert tab._chart.axis_max == 3600
    assert [lbl.text() for lbl in tab._highlight_labels] == ["가장 많이 쓴 시간", "쉬지 않고 쓴 가장 긴 시간", "휴식 달성률"]
    assert [v.text() for v in tab._highlight_values] == ["45분", "45분", "0%"]
    assert [d.text() for d in tab._highlight_details] == ["14시", "", "0회 / 권장 3회"]  # 75분 사용 → 20분마다 3회


def test_이전_기간으로_가면_그_기간_사용_시간이다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 7, 9, 600), (9, 30, 9, 3600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert big_text(tab) == "10 분"
    tab.go(-1)
    assert tab._nav_title.text() == "지난 주" and big_text(tab) == "1 시간"


def test_막대를_누르면_그_막대의_사용_시간과_운동_횟수를_보여_준다(qapp):
    events = [done(at(10, 5)), done(at(10, 5, 18)), done(at(10, 6))]
    tab, _, _ = make_tab(qapp, events, entries=[(10, 5, 9, 3600), (10, 5, 10, 1800)])
    tab.set_mode(Mode.SCREEN_TIME)
    click_bar(tab, 0)  # 월요일
    assert tab._kicker.text() == "10월 5일 (월)"
    assert big_text(tab) == "1 시간 30 분"
    assert tab._caption.text() == "눈 휴식 2회"
    click_bar(tab, 0)
    assert tab._kicker.text() == "스크린 타임" and big_text(tab) == "1 시간 30 분"  # 전체 합계로 돌아온다


def test_사용_기록이_없는_날을_눌러도_된다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 5, 9, 600)])
    tab.set_mode(Mode.SCREEN_TIME)
    click_bar(tab, 1)  # 화요일
    assert tab._chart._selected == 1 and big_text(tab) == "0 분" and tab._caption.text() == "눈 휴식 0회"


# ---- 하이라이트와 목록 ----


def test_하이라이트는_평균_쉬지_않고_쓴_시간_휴식_달성률(qapp):
    events = [done(at(10, 5)), done(at(10, 6)), done(at(10, 7))]
    tab, _, _ = make_tab(qapp, events, entries=[(10, 5, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 3600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert [lbl.text() for lbl in tab._highlight_labels] == ["하루 평균", "쉬지 않고 쓴 가장 긴 시간", "휴식 달성률"]
    assert [v.text() for v in tab._highlight_values] == ["1시간", "2시간", "33%"]  # 수요일 9~11시를 쉬지 않고 썼다, 권장 9회 중 3회
    assert [d.text() for d in tab._highlight_details] == ["", "오늘", "3회 / 권장 9회"]


def test_스크린_타임에서도_하루_흐름에_시간대별_사용이_보인다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 7, 9, 3600), (10, 7, 10, 1800), (10, 6, 9, 1800), (10, 1, 9, 600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert tab._section.text() == "하루 흐름"
    days = timeline_days_of(tab)
    assert [d.title for d in days][:3] == ["오늘", "어제", "10월 5일 (월)"] and len(days) == 7
    assert days[0].hours[9] == 3600 and days[0].hours[10] == 1800
    assert (days[0].span, days[1].span, days[2].span, days[6].span) == ("09:00~11:00", "09:00~10:00", "", "09:00~10:00")
    assert days[0].total_seconds == 5400
    assert not tab._more.isHidden() and not tab._legend.isHidden()


def test_하루_흐름의_마우스_설명에_사용_시간이_나온다(qapp):
    tab, _, _ = make_tab(qapp, entries=[(10, 7, 9, 2520)])
    chart = tab._timeline
    assert chart.tip_at(chart.cell_rect(0, 9).center()) == "스크린 타임 42분"
    assert chart.tip_at(chart.cell_rect(0, 7).center()) == ""


# ---- 주기 갱신 ----


def test_스크린_타임을_보는_동안에는_주기적으로_새로_그린다(qapp):
    tab, source, usage = make_tab(qapp, entries=[(10, 7, 9, 600)])
    assert tab._live.isActive()
    tab.set_mode(Mode.SCREEN_TIME)
    assert big_text(tab) == "10 분"
    usage.add(at(10, 7, 9, 0), 1200)  # 사용 시간이 늘었다
    calls = source.calls
    tab._live.timeout.emit()
    assert source.calls > calls and big_text(tab) == "30 분"


def test_운동_화면에서는_주기_갱신이_다시_그리지_않는다(qapp):
    tab, source, _ = make_tab(qapp)
    calls = source.calls
    tab._live.timeout.emit()
    assert source.calls == calls


def test_숨겨지면_주기_갱신을_멈추고_다시_보이면_시작한다(qapp):
    tab, _, _ = make_tab(qapp)
    tab.hide()
    assert not tab._live.isActive()
    tab.show()
    assert tab._live.isActive()


# ---- 연결 ----


def test_컨트롤러가_매초_사용_시간을_쌓고_종료할_때_저장한다(qapp):
    clock, idle = FakeClock(), FakeIdle()
    saved = []
    tracker = UsageTracker(UsageLog(), clock, idle, lambda: 60.0, save=lambda u: saved.append(u.total(date(2026, 10, 6))), tz=KST)
    controller = Controller(ReminderScheduler(Settings(), clock, idle), History(), now=clock.now, usage_tracker=tracker)
    controller._on_tick()  # 기준 시각
    for _ in range(5):
        clock.advance(1)
        controller._on_tick()
    assert tracker.usage.total(date(2026, 10, 6)) == 5
    assert saved == []  # 아직 저장 간격이 안 됐다
    controller.stop()
    assert saved == [5]  # 끝낼 때 마지막 구간까지 저장


def test_사용_추적기가_없어도_컨트롤러는_동작한다(qapp):
    clock, idle = FakeClock(), FakeIdle()
    controller = Controller(ReminderScheduler(Settings(), clock, idle), History(), now=clock.now)
    clock.advance(1)
    controller._on_tick()
    controller.stop()
    controller.flush_usage()


def test_메인_창이_사용_기록을_스크린_타임에_전달한다(qapp):
    usage = usage_of([(10, 7, 9, 1800)])
    window = MainWindow(History(), now=lambda: NOW, usage=usage)
    window.records_tab._tz = KST
    window.records_tab.set_mode(Mode.SCREEN_TIME)
    assert big_text(window.records_tab) == "30 분"


def test_메인_창에_사용_기록이_없어도_스크린_타임이_열린다(qapp):
    window = MainWindow(History())
    window.records_tab.set_mode(Mode.SCREEN_TIME)
    assert big_text(window.records_tab) == "0 분"


def test_휴식_주기를_바꾸면_휴식_달성률이_따라간다(qapp):
    from eyeexercise.core.history import HistoryEvent
    from eyeexercise.ui.records_tab import RecordsTab

    usage = usage_of([(10, 7, 9, 3600)])
    events = [HistoryEvent(at(10, 7, 9, 30), "completed", "blink", 36)]
    interval = {"minutes": 20}
    tab = RecordsTab(lambda: events, now=lambda: NOW, tz=KST, usage_provider=lambda: usage, interval_minutes=lambda: interval["minutes"])
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert [d.text() for d in tab._highlight_details][2] == "1회 / 권장 3회"
    interval["minutes"] = 60  # 60분마다 쉬는 설정이면 권장은 1회
    tab.refresh()
    assert [v.text() for v in tab._highlight_values][2] == "100%"
    assert [d.text() for d in tab._highlight_details][2] == "1회 / 권장 1회"


def test_눈_운동과_건너뜀은_휴식_달성률에_세지_않는다(qapp):
    from eyeexercise.core.history import HistoryEvent

    events = [
        HistoryEvent(at(10, 7, 9, 10), "completed", "dot_follow", 60),
        HistoryEvent(at(10, 7, 9, 20), "skipped", activity="rest"),
    ]
    tab, _, _ = make_tab(qapp, events, entries=[(10, 7, 9, 3600)])
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert [d.text() for d in tab._highlight_details][2] == "0회 / 권장 3회"
