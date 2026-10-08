from datetime import date, datetime, timedelta, timezone

import pytest
from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.scheduler import ReminderScheduler
from eyeexercise.core.settings import Settings
from eyeexercise.core.stats import Period
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.records_tab import RECENT_COLLAPSED, RECENT_EXPANDED, BarChart, Mode, RecordsTab

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일. 이번 주는 10/5(월) ~ 10/11(일)


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def done(ts, exercise="blink", seconds=66):
    return HistoryEvent(ts, "completed", exercise, seconds)


class Source:
    """기록 목록을 돌려주는 가짜. 호출 횟수를 센다."""

    def __init__(self, events=()):
        self.events = list(events)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.events


def make_tab(qapp, events=()):
    source = Source(events)
    tab = RecordsTab(source, now=lambda: NOW, tz=KST)
    tab.set_period(Period.WEEK)  # 앱의 처음 화면은 일 보기이지만 이 테스트는 주 보기 기준이다
    tab.resize(520, 900)
    tab.show()
    qapp.processEvents()
    return tab, source


def number_text(tab):
    return tab._number.text()


def count_in_header(tab):
    # 큰 숫자는 "<span ...>14</span><span ...> 회</span>" 형태다
    import re

    return int(re.search(r">(\d+)</span>", number_text(tab)).group(1))


def day_marks(tab):
    """타임라인의 날짜 줄마다 (제목, 점 설명 목록). 기록 없는 날도 한 줄이다."""
    return [(d.title, [m.tip for m in d.marks]) for d in tab._timeline._days]


def marked_days(tab):
    return [(title, tips) for title, tips in day_marks(tab) if tips]


def clocks(tab):
    """점의 시각을 최신순으로 모은다. 예: ["14:00", "09:00", "12:00"]"""
    return [tip[:5] for d in tab._timeline._days for tip in reversed([m.tip for m in d.marks])]


def click_bar(tab, index):
    chart = tab._chart
    rect = chart.bar_rect(index)
    y = rect.center().y() if rect.height() > 0 else chart._plot().bottom() - 4
    QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=QPoint(int(rect.center().x()), int(y)))


# ---- 처음 상태 ----


def test_기록이_없어도_정상적으로_보인다(qapp):
    tab, _ = make_tab(qapp)
    assert tab.period is Period.WEEK
    assert count_in_header(tab) == 0
    assert tab._nav_title.text() == "이번 주"
    assert tab._caption.text() == "10월 5일 – 10월 11일"
    assert tab._chart.axis_max == 4
    assert tab._timeline._empty_text == "아직 기록이 없어요" and all(d.is_empty for d in tab._timeline._days)
    assert [v.text() for v in tab._highlight_values] == ["–", "0회", "0.0개"]


def test_이번_주가_기본이고_일_주_월_버튼이_있다(qapp):
    tab, _ = make_tab(qapp)
    assert [b.text() for b in tab._segment_buttons.values()] == ["일", "주", "월"]
    assert tab._segment_buttons[Period.WEEK].isChecked()
    assert not tab._next.isEnabled()  # 이번 주보다 앞으로는 못 간다
    assert tab._prev.isEnabled()


# ---- 요약 ----


def test_큰_숫자와_하이라이트가_기록을_반영한다(qapp):
    events = [done(at(10, 5)), done(at(10, 6), "blink", 60), done(at(10, 7, 9)), HistoryEvent(at(10, 7, 10), "skipped", activity="rest")]
    tab, _ = make_tab(qapp, events)
    assert count_in_header(tab) == 3
    labels = [lbl.text() for lbl in tab._highlight_labels]
    values = [v.text() for v in tab._highlight_values]
    assert labels == ["휴식 달성률", "건너뜀", "휴식 시간대"]
    assert values == ["–", "1회", "1.0개"]  # 사용 기록이 없어 달성률은 없다. 휴식 시간대 3개 ÷ 월~수 3일


def test_기간을_바꾸면_막대_수와_제목이_바뀐다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 7, 14))])
    tab.set_period(Period.DAY)
    assert tab._nav_title.text() == "오늘"
    assert len(tab._chart._buckets) == 24
    assert tab._caption.text() == "2026년 10월 7일 수요일"
    assert count_in_header(tab) == 2
    assert [lbl.text() for lbl in tab._highlight_labels] == ["휴식 달성률", "건너뜀", "휴식 시간대"]
    tab.set_period(Period.MONTH)
    assert tab._nav_title.text() == "이번 달"
    assert len(tab._chart._buckets) == 31
    assert tab._caption.text() == "2026년 10월"
    assert tab._segment_buttons[Period.MONTH].isChecked()


def test_버튼을_누르면_기간이_바뀐다(qapp):
    tab, _ = make_tab(qapp)
    tab._segment_buttons[Period.DAY].click()
    assert tab.period is Period.DAY and tab._nav_title.text() == "오늘"
    tab._segment_buttons[Period.MONTH].click()
    assert tab.period is Period.MONTH


# ---- 이전 / 다음 ----


def test_이전_주로_가면_그_주_기록을_보여_준다(qapp):
    events = [done(at(10, 7)), done(at(9, 30)), done(at(9, 30, 15)), done(at(10, 4))]
    tab, _ = make_tab(qapp, events)
    assert count_in_header(tab) == 1
    tab.go(-1)
    assert tab._nav_title.text() == "지난 주"
    assert tab._caption.text() == "9월 28일 – 10월 4일"
    assert count_in_header(tab) == 3
    assert tab._next.isEnabled()
    assert [v.text() for v in tab._highlight_values][2] == "0.4개"  # 휴식 시간대 3개 ÷ 7일
    tab.go(1)
    assert tab._nav_title.text() == "이번 주" and count_in_header(tab) == 1


def test_이번_기간보다_앞으로는_갈_수_없다(qapp):
    tab, _ = make_tab(qapp)
    anchor = tab.anchor
    tab.go(1)
    assert tab.anchor == anchor and tab._nav_title.text() == "이번 주"
    for period in (Period.DAY, Period.MONTH):
        tab.set_period(period)
        before = tab.anchor
        tab.go(1)
        assert tab.anchor == before and not tab._next.isEnabled()


def test_기간을_바꾸면_오늘로_돌아온다(qapp):
    tab, _ = make_tab(qapp)
    tab.go(-1)
    tab.go(-1)
    tab.set_period(Period.MONTH)
    assert tab.anchor == date(2026, 10, 7) and tab._nav_title.text() == "이번 달"


def test_월_이동은_해를_넘어간다(qapp):
    tab, _ = make_tab(qapp)
    tab.set_period(Period.MONTH)
    for _ in range(10):
        tab.go(-1)
    assert tab._nav_title.text() == "2025년 12월"


# ---- 막대 선택 ----


def test_막대를_누르면_그_막대의_값을_크게_보여_준다(qapp):
    events = [done(at(10, 5)), done(at(10, 5, 15), "blink", 60), done(at(10, 7))]
    tab, _ = make_tab(qapp, events)
    click_bar(tab, 0)  # 월요일
    assert tab._kicker.text() == "10월 5일 (월)"
    assert count_in_header(tab) == 2
    assert tab._caption.text() == ""  # 건너뜀·미룸이 없으면 보조 문구도 없다
    assert tab._chart._selected == 0


def test_같은_막대를_다시_누르면_선택이_풀린다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 0)
    click_bar(tab, 0)
    assert tab._chart._selected == -1
    assert tab._kicker.text() == "눈 휴식" and tab._caption.text() == "10월 5일 – 10월 11일"


def test_다른_막대를_누르면_선택이_옮겨간다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5)), done(at(10, 6)), done(at(10, 6, 14))])
    click_bar(tab, 0)
    click_bar(tab, 1)
    assert tab._chart._selected == 1 and count_in_header(tab) == 2


def test_기록이_없는_막대도_선택할_수_있다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 1)  # 화요일: 기록 없음
    assert tab._chart._selected == 1
    assert count_in_header(tab) == 0 and tab._caption.text() == "휴식 기록 없음"


def test_아직_오지_않은_날은_선택할_수_없다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 5)  # 토요일(미래)
    assert tab._chart._selected == -1


def test_기간을_옮기면_선택이_풀린다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 0)
    tab.go(-1)
    assert tab._chart._selected == -1
    tab.go(1)
    click_bar(tab, 0)
    tab.set_period(Period.DAY)
    assert tab._chart._selected == -1


# ---- 차트 ----


def test_막대_높이는_완료_횟수에_비례한다(qapp):
    events = [done(at(10, 5))] + [done(at(10, 6, h)) for h in range(8, 13)]
    tab, _ = make_tab(qapp, events)
    chart = tab._chart
    assert chart.axis_max == 6  # 가장 큰 막대 5 → 보기 좋은 눈금 6
    one, five = chart.bar_rect(0), chart.bar_rect(1)
    assert five.height() == pytest.approx(one.height() * 5)
    assert chart.bar_rect(2).height() == 0  # 기록 없는 날


def test_세로축은_가장_큰_막대보다_높다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5, h)) for h in range(9, 14)])
    assert tab._chart.axis_max >= 5


def test_막대_위치로_번호를_찾는다(qapp):
    tab, _ = make_tab(qapp)
    chart = tab._chart
    centers = [chart.bar_rect(i).center().x() for i in range(7)]
    assert [chart.index_at(x) for x in centers] == list(range(7))
    assert chart.index_at(-50) == -1
    assert chart.index_at(chart.width() + 50) == -1
    assert BarChart().index_at(10) == -1  # 데이터가 없을 때


# ---- 하루 타임라인 (최근 기록) ----


def test_하루_흐름은_오늘부터_날짜별_한_줄이다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 14)), HistoryEvent(at(10, 6, 12), "skipped", activity="rest")]
    tab, _ = make_tab(qapp, events)
    assert tab._section.text() == "하루 흐름"
    titles = [t for t, _ in day_marks(tab)]
    assert len(titles) == RECENT_COLLAPSED == 7
    assert titles[:2] == ["오늘", "어제"]
    assert marked_days(tab) == [("오늘", ["09:00 눈 휴식 · 1분 6초", "14:00 눈 휴식 · 1분 6초"]), ("어제", ["12:00 건너뜀"])]
    assert clocks(tab) == ["14:00", "09:00", "12:00"]


def test_기록이_없는_날도_한_줄을_차지한다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    assert len(day_marks(tab)) == 7 and len(marked_days(tab)) == 1


def test_더_보기를_누르면_30일로_펼쳐지고_접기로_다시_접는다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    assert not tab._more.isHidden() and tab._more.text() == "더 보기"
    tab._more.click()
    assert tab._more.text() == "접기" and len(day_marks(tab)) == RECENT_EXPANDED == 30
    tab._more.click()
    assert tab._more.text() == "더 보기" and len(day_marks(tab)) == RECENT_COLLAPSED


def test_타임라인의_높이는_줄_수를_따라간다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    short = tab._timeline.height()
    tab._more.click()
    assert tab._timeline.height() > short


def test_칸은_시간대에_맞는_가로_위치에_있다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 14)), done(at(10, 6, 12, 0))])
    chart = tab._timeline
    grid = chart.grid_rect()
    assert chart._start_hour == 6  # 가로축은 6시부터 자정까지
    assert chart.cell_rect(0, 6).left() == pytest.approx(grid.left() + chart._CELL_GAP / 2)
    assert chart.cell_rect(0, 23).right() == pytest.approx(grid.right() - chart._CELL_GAP / 2)
    assert chart.cell_rect(0, 15).left() - chart.cell_rect(0, 14).left() == pytest.approx(grid.width() / 18)  # 칸 너비는 모두 같다
    assert chart.cell_rect(1, 12).left() == pytest.approx(chart.cell_rect(0, 12).left())  # 줄이 달라도 같은 시각은 같은 세로 줄
    assert chart.cell_rect(1, 12).top() > chart.cell_rect(0, 12).top()  # 어제는 오늘 아래 줄


def test_칸에_마우스를_올리면_그_시간대의_설명이_뜬다(qapp):
    events = [done(at(10, 7, 14, 32), "dot_follow", 60), done(at(10, 7, 14, 50), "blink", 66), HistoryEvent(at(10, 7, 9, 0), "skipped", activity="rest")]
    tab, _ = make_tab(qapp, events)
    chart = tab._timeline
    assert chart.tip_at(chart.cell_rect(0, 14).center()) == "14:32 점 따라가기 · 1분\n14:50 눈 휴식 · 1분 6초"
    assert chart.tip_at(chart.cell_rect(0, 9).center()) == "09:00 건너뜀"
    assert chart.tip_at(chart.cell_rect(0, 11).center()) == ""  # 아무것도 없는 시간대
    assert chart.tip_at(QPointF(5, 5)) == ""  # 격자 밖


def test_같은_시간대의_운동은_한_칸에_모인다(qapp):
    events = [done(at(10, 7, 14, 5)), done(at(10, 7, 14, 25)), HistoryEvent(at(10, 7, 14, 45), "skipped", activity="rest"), done(at(10, 7, 15, 0))]
    tab, _ = make_tab(qapp, events)
    today = tab._timeline._days[0]
    assert [m.kind for m in today.hour_marks(14)] == ["completed", "completed", "skipped"]
    assert [m.kind for m in today.hour_marks(15)] == ["completed"]
    assert today.hour_marks(13) == []


def test_하루_흐름이_실제로_그려진다(qapp):
    """칸 색(스크린 타임)과 눈 운동 횟수 글자가 픽셀로 나타나고, 휴식·건너뜀·미룸은 칸에 그려지지 않는지 본다."""
    from eyeexercise.core.usage import UsageLog

    usage = UsageLog()
    usage.add(NOW.replace(hour=9, minute=30), 3000)
    events = [
        done(at(10, 7, 14, 0), "dot_follow", 60),
        done(at(10, 7, 16, 0), "blink"),
        HistoryEvent(at(10, 7, 11, 10), "skipped", activity="rest"),
        HistoryEvent(at(10, 7, 11, 20), "snoozed", activity="rest"),
    ]
    tab = RecordsTab(Source(events), now=lambda: NOW, tz=KST, usage_provider=lambda: usage)
    tab.set_period(Period.WEEK)  # 앱의 처음 화면은 일 보기이지만 이 테스트는 주 보기 기준이다
    tab.resize(900, 900)
    tab.show()
    qapp.processEvents()
    chart = tab._timeline
    image = chart.grab().toImage()

    used = chart.cell_rect(0, 9)
    color = image.pixelColor(int(used.left()) + 3, int(used.bottom()) - 3)
    assert color.green() > color.red() + 20  # 스크린 타임이 있는 칸은 초록 계열
    empty = chart.cell_rect(0, 7)
    assert image.pixelColor(int(empty.left()) + 3, int(empty.bottom()) - 3).name() == "#dfebe6"  # 쓰지 않은 시간은 빈 칸

    done_cell = chart.cell_rect(0, 14)  # 눈 운동 1회: 칸 가운데에 숫자 "1"이 그려진다
    dark = sum(
        1
        for x in range(int(done_cell.left()), int(done_cell.right()))
        for y in range(int(done_cell.top()), int(done_cell.bottom()))
        if image.pixelColor(x, y).lightness() < 110
    )
    assert dark > 5

    rest_cell = chart.cell_rect(0, 16)  # 눈 휴식은 칸에 숫자를 쓰지 않는다 (20분마다라 너무 많아진다)
    flat = {image.pixelColor(x, y).name() for x in range(int(rest_cell.left()) + 2, int(rest_cell.right()) - 2) for y in range(int(rest_cell.top()) + 2, int(rest_cell.bottom()) - 2)}
    assert flat == {"#dfebe6"}
    skipped_cell = chart.cell_rect(0, 11)  # 건너뜀·미룸도 칸 귀퉁이에 점을 그리지 않는다 (줄 오른쪽 요약과 마우스 설명으로만)
    corner = image.pixelColor(int(skipped_cell.right() - 4), int(skipped_cell.top() + 4))
    assert corner.name() == "#dfebe6"


def test_기간과_상관없이_하루_흐름은_그대로다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 6, 9))])
    before = day_marks(tab)
    tab.set_period(Period.DAY)
    tab.go(-1)
    assert day_marks(tab) == before


def test_기록이_하나도_없으면_안내_문구만_그린다(qapp):
    tab, _ = make_tab(qapp)
    assert all(d.is_empty for d in tab._timeline._days)
    tab._timeline.grab()  # 그리다가 죽지 않는다


def test_새_기록이_생기면_refresh로_반영된다(qapp):
    tab, source = make_tab(qapp)
    assert count_in_header(tab) == 0
    source.events.append(done(at(10, 7, 14)))
    tab.refresh()
    assert count_in_header(tab) == 1 and clocks(tab) == ["14:00"]
    assert [t for t, _ in marked_days(tab)] == ["오늘"]
    source.events.append(done(at(10, 7, 15)))
    tab.refresh()
    assert count_in_header(tab) == 2 and clocks(tab) == ["15:00", "14:00"]


def test_창이_다시_보일_때_새로_그린다(qapp):
    tab, source = make_tab(qapp)
    tab.hide()
    source.events.append(done(at(10, 7, 14)))
    calls = source.calls
    tab.show()
    assert source.calls > calls and count_in_header(tab) == 1


def test_선택한_막대는_새로_그려도_유지된다(qapp):
    tab, source = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 0)
    source.events.append(done(at(10, 5, 18)))
    tab.refresh()
    assert tab._chart._selected == 0 and count_in_header(tab) == 2


# ---- 메인 창 ----


def test_메인_창에_기록_탭이_있다(qapp):
    window = MainWindow()
    assert window.sidebar.label(1) == "기록"
    assert window._stack.widget(1) is window.records_tab


def test_메인_창은_기록을_받아_보여_준다(qapp):
    history = History([done(NOW)])
    window = MainWindow(history, now=lambda: NOW)
    window.records_tab._tz = KST
    window.records_tab.refresh()
    assert count_in_header(window.records_tab) == 1


# ---- 컨트롤러: 기록이 바뀌면 알린다 ----


def _controller():
    clock = FakeClock()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now)
    emitted = []
    controller.history_changed.connect(lambda: emitted.append(1))
    return controller, clock, emitted


def _make_due(controller, clock):
    for _ in range(1200):
        clock.advance(1)
        controller._on_tick()


def test_미루기_건너뛰기_완료_때_기록이_바뀌었다고_알린다(qapp):
    controller, clock, emitted = _controller()
    _make_due(controller, clock)
    controller.snooze()
    assert emitted == [1]
    for _ in range(300):
        clock.advance(1)
        controller._on_tick()
    controller.skip()
    assert emitted == [1, 1]
    controller.start_exercise()
    controller.complete_exercise("blink", 66)
    assert emitted == [1, 1, 1]


def test_무시된_요청과_중단은_기록이_바뀌었다고_알리지_않는다(qapp):
    controller, clock, emitted = _controller()
    controller.skip()  # 알림 중이 아니라서 무시된다
    controller.start_exercise()
    controller.abort_exercise()
    assert emitted == []


# ---- 메인 창: 왼쪽 메뉴 + 넓은 본문 ----


def test_왼쪽_메뉴에_홈_기록_시력_기록_설정이_있다(qapp):
    window = MainWindow()
    assert [window.sidebar.label(i) for i in range(window.sidebar.count())] == ["홈", "기록", "시력 기록", "설정"]
    assert window.sidebar.current() == 0 and window._stack.currentWidget() is window.home_page


def test_메뉴를_고르면_본문이_바뀐다(qapp):
    window = MainWindow()
    window.sidebar.set_current(1)
    assert window._stack.currentIndex() == 1 and window._stack.currentWidget() is window.records_tab
    window.sidebar.set_current(3)
    assert window._stack.currentIndex() == 3
    window.sidebar.set_current(0)
    assert window._stack.currentWidget() is window.home_page


def test_설정과_시력_기록_메뉴는_각각_실제_화면이다(qapp):
    window = MainWindow()
    assert window._stack.widget(2) is window.vision_page
    assert window._stack.widget(3) is window.settings_page


def test_메인_창은_넓은_데스크톱_크기로_뜨고_더_작아지지_않는다(qapp):
    from PySide6.QtGui import QGuiApplication

    from eyeexercise.ui.main_window import fit_to_screen

    # 화면이 넉넉하면 1000×700(최소 860×560), 작은 화면이면 그 안에 들어오게 줄어든다 (테스트 화면은 작다)
    size, minimum = fit_to_screen(QGuiApplication.primaryScreen().availableGeometry())
    window = MainWindow()
    assert (window.width(), window.height()) == size
    assert (window.minimumWidth(), window.minimumHeight()) == minimum


def test_하이라이트_카드는_보조_설명이_있을_때만_보여_준다(qapp):
    tab, _ = make_tab(qapp)
    tab.set_period(Period.DAY)
    details = tab._highlight_details
    assert [d.isHidden() for d in details] == [False, True, True]  # 하루 보기에서는 달성률의 '사용 시간이 짧아요'만 있다
    tab.set_period(Period.WEEK)
    assert [d.text() for d in details] == ["사용 시간이 짧아요", "", "하루 평균"]  # 주·월 보기의 휴식 시간대는 하루 평균임을 알린다


def test_가로축은_이른_기록이_있으면_그_시각부터_보인다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 14))])
    assert tab._timeline._start_hour == 6
    tab, _ = make_tab(qapp, [done(at(10, 7, 14)), done(at(10, 6, 4, 30))])
    assert tab._timeline._start_hour == 3  # 4시 30분 기록이 보이도록 글자 단위(3시간)로 내린다
    tab, _ = make_tab(qapp, [done(at(10, 7, 0, 10))])
    chart = tab._timeline
    assert chart._start_hour == 0
    assert chart.cell_rect(0, 0).left() == pytest.approx(chart.grid_rect().left() + chart._CELL_GAP / 2)


# ---- 눈 휴식 / 눈 운동 / 스크린 타임 전환 (7.6c) ----


def test_구분이_없는_옛_건너뜀은_어느_화면에도_세지_않는다(qapp):
    events = [done(at(10, 7, 9)), HistoryEvent(at(10, 7, 10), "skipped"), HistoryEvent(at(10, 7, 11), "snoozed")]
    tab, _ = make_tab(qapp, events)
    skipped_card = tab._highlight_values[1].text()
    assert skipped_card == "0회"
    assert tab._timeline._days[0].skipped == 0 and tab._timeline._days[0].snoozed == 0


def test_하루_줄_오른쪽에_휴식_운동_횟수만_적힌다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11), "dot_follow", 60), HistoryEvent(at(10, 7, 12), "skipped", activity="rest")]
    tab, _ = make_tab(qapp, events)
    from eyeexercise.ui.records_tab import activity_summary

    assert activity_summary(tab._timeline._days[0]) == "휴식 2회 · 운동 1회"


def test_창이_커져도_오늘_요약_카드는_내용만큼만_차지한다(qapp):
    from PySide6.QtWidgets import QFrame

    tab, _ = make_tab(qapp)
    tab.resize(1000, 1700)
    qapp.processEvents()
    cards = [f for f in tab.findChildren(QFrame) if f.objectName() == "card"][:3]
    assert all(card.height() < 150 for card in cards)


def test_오늘_요약_세_카드는_높이가_같다(qapp):
    from PySide6.QtWidgets import QFrame

    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 6, 9))])
    tab.resize(1000, 1700)
    qapp.processEvents()
    cards = [f for f in tab.findChildren(QFrame) if f.objectName() == "card"][:3]
    assert len({card.height() for card in cards}) == 1


def test_눈_휴식_화면은_휴식만_세고_눈_운동은_전환이_없다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11), "dot_follow", 60), done(at(10, 6, 11), "dot_follow", 60)]
    tab, _ = make_tab(qapp, events)
    assert [m.value for m in Mode] == ["rest", "screen_time"]  # 눈 운동 화면은 없다
    assert tab.mode is Mode.REST and tab._kicker.text() == "눈 휴식" and count_in_header(tab) == 2  # 운동은 세지 않는다
    assert [lbl.text() for lbl in tab._highlight_labels] == ["휴식 달성률", "건너뜀", "휴식 시간대"]
    assert "운동 시간" not in " ".join(lbl.text() for lbl in tab._highlight_labels)  # 휴식 시간·운동 시간은 보여 주지 않는다


def test_눈_운동_횟수는_오늘_요약과_하루_흐름에서_볼_수_있다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 11), "dot_follow", 60), done(at(10, 7, 15), "dot_follow", 60)]
    tab, _ = make_tab(qapp, events)
    today = tab._today_cards["exercise"][0].text()
    assert today == "2회"
    day = tab._timeline._days[0]
    assert (day.exercises, day.exercises_in_hour(11), day.exercises_in_hour(15)) == (2, 1, 1)


def test_막대를_누르면_그_막대의_건너뜀과_미룸을_알려_준다(qapp):
    events = [
        done(at(10, 5)),
        HistoryEvent(at(10, 5, 11), "skipped", activity="rest"),
        HistoryEvent(at(10, 5, 12), "skipped", activity="rest"),
        HistoryEvent(at(10, 5, 13), "snoozed", activity="rest"),
        HistoryEvent(at(10, 7, 9), "skipped", activity="rest"),
        done(at(10, 7, 10)),
    ]
    tab, _ = make_tab(qapp, events)
    click_bar(tab, 0)  # 월요일
    assert tab._caption.text() == "건너뜀 2회 · 미룸 1회"
    click_bar(tab, 2)  # 수요일(오늘): 건너뜀만
    assert tab._caption.text() == "건너뜀 1회"
    click_bar(tab, 1)  # 화요일: 기록 없음
    assert tab._caption.text() == "휴식 기록 없음"


def test_하루_보기의_쉰_시간대는_휴식이_있었던_시간대_수다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 7, 9, 40)), done(at(10, 7, 14))])
    tab.set_period(Period.DAY)
    assert tab._highlight_values[2].text() == "2개"  # 9시대와 14시대


def test_기록_탭은_처음에_일_보기로_열린다(qapp):
    tab = RecordsTab(Source(), now=lambda: NOW, tz=KST)
    assert tab.period is Period.DAY


# ---- 건너뜀 ‹ › 미룸 이동 (눈 휴식 하이라이트 둘째 카드) ----


def test_둘째_카드는_화살표로_건너뜀과_미룸을_오간다(qapp):
    events = [
        done(at(10, 7, 9)),
        HistoryEvent(at(10, 7, 10), "skipped", activity="rest"),
        HistoryEvent(at(10, 7, 11), "snoozed", activity="rest"),
        HistoryEvent(at(10, 7, 12), "snoozed", activity="rest"),
    ]
    tab, _ = make_tab(qapp, events)
    assert not tab._skip_prev.isHidden() and not tab._skip_next.isHidden()
    assert (tab._skip_prev.text(), tab._skip_next.text()) == ("‹", "›")
    assert tab._highlight_labels[1].text() == "건너뜀" and tab._highlight_values[1].text() == "1회"
    tab._skip_next.click()
    assert tab._highlight_labels[1].text() == "미룸" and tab._highlight_values[1].text() == "2회"
    tab.refresh()  # 새로 그려도 고른 것이 유지된다
    assert tab._highlight_values[1].text() == "2회"
    tab._skip_next.click()  # 둘뿐이라 한 바퀴 돌아 건너뜀으로 돌아온다
    assert tab._highlight_labels[1].text() == "건너뜀"
    tab._skip_prev.click()
    assert tab._highlight_labels[1].text() == "미룸"
    tab._skip_prev.click()
    assert tab._highlight_labels[1].text() == "건너뜀" and tab._highlight_values[1].text() == "1회"


def test_화살표는_눈_휴식_화면에만_있다(qapp):
    tab, _ = make_tab(qapp)
    tab.set_mode(Mode.SCREEN_TIME)
    assert tab._skip_prev.isHidden() and tab._skip_next.isHidden()
    tab.set_mode(Mode.REST)
    assert not tab._skip_prev.isHidden() and not tab._skip_next.isHidden()


def test_일_월로_바꿔도_고른_미룸이_유지된다(qapp):
    tab, _ = make_tab(qapp, [HistoryEvent(at(10, 7, 10), "snoozed", activity="rest")])
    tab._skip_next.click()
    for period in (Period.DAY, Period.MONTH, Period.WEEK):
        tab.set_period(period)
        assert tab._highlight_labels[1].text() == "미룸" and tab._highlight_values[1].text() == "1회"


def test_스크린_타임_카드는_두_개일_때_내용만큼만_차지한다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    tab.resize(1000, 1100)
    qapp.processEvents()
    chart_card = tab._chart.parentWidget()
    assert abs(sum(card.height() for card in tab._highlight_cards) - chart_card.height()) < 40  # 눈 휴식 화면의 세 카드는 차트 높이를 채운다
    tab.set_mode(Mode.SCREEN_TIME)
    qapp.processEvents()
    shown = [card for card in tab._highlight_cards if not card.isHidden()]
    assert len(shown) == 2 and tab._highlight_cards[2].isHidden()
    assert all(card.height() <= card.sizeHint().height() + 8 for card in shown)  # 늘어나지 않고 내용 높이를 쓴다
    assert sum(card.height() for card in shown) < chart_card.height() * 0.6  # 빈 공간이 줄었다
    tab.set_mode(Mode.REST)
    qapp.processEvents()
    assert abs(sum(card.height() for card in tab._highlight_cards) - chart_card.height()) < 40  # 돌아오면 다시 채운다
