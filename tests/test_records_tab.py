from datetime import date, datetime, timedelta, timezone

import pytest
from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.scheduler import ReminderScheduler
from eyeexercise.core.settings import Settings
from eyeexercise.core.stats import Period
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.records_tab import RECENT_COLLAPSED, RECENT_EXPANDED, BarChart, RecordsTab

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


def table_rows(tab):
    """표의 데이터 줄(머리·날짜 제목 제외)을 칸 순서대로 돌려준다. 예: [["14:32", "점 따라가기", "완료", "1분"], ...]"""
    grid = tab._table._grid
    rows: dict[int, dict[int, str]] = {}
    for i in range(grid.count()):
        widget = grid.itemAt(i).widget()
        if isinstance(widget, QLabel) and widget.objectName() == "cell":
            row, column, _, _ = grid.getItemPosition(i)
            rows.setdefault(row, {})[column] = widget.text()
    return [[cells[c] for c in sorted(cells)] for _, cells in sorted(rows.items())]


def table_cells(tab, column):
    return [row[column] for row in table_rows(tab)]


def group_titles(tab):
    return [lbl.text() for lbl in tab.findChildren(QLabel) if lbl.objectName() == "groupTitle"]


def table_headers(tab):
    return [lbl.text() for lbl in tab.findChildren(QLabel) if lbl.objectName() == "tableHead"]


def muted_flags(tab):
    """데이터 줄마다 연한 회색 줄인지."""
    grid = tab._table._grid
    flags: dict[int, bool] = {}
    for i in range(grid.count()):
        widget = grid.itemAt(i).widget()
        if isinstance(widget, QLabel) and widget.objectName() == "cell":
            flags[grid.getItemPosition(i)[0]] = bool(widget.property("muted"))
    return [flags[r] for r in sorted(flags)]


def row_times(tab):
    return table_cells(tab, 0)


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
    assert [lbl.text() for lbl in tab.findChildren(QLabel) if lbl.objectName() == "empty"] == ["아직 기록이 없어요"]
    assert [v.text() for v in tab._highlight_values] == ["0.0회", "0초", "0회"]


def test_이번_주가_기본이고_일_주_월_버튼이_있다(qapp):
    tab, _ = make_tab(qapp)
    assert [b.text() for b in tab._segment_buttons.values()] == ["일", "주", "월"]
    assert tab._segment_buttons[Period.WEEK].isChecked()
    assert not tab._next.isEnabled()  # 이번 주보다 앞으로는 못 간다
    assert tab._prev.isEnabled()


# ---- 요약 ----


def test_큰_숫자와_하이라이트가_기록을_반영한다(qapp):
    events = [done(at(10, 5)), done(at(10, 6), "dot_follow", 60), done(at(10, 7, 9)), HistoryEvent(at(10, 7, 10), "skipped")]
    tab, _ = make_tab(qapp, events)
    assert count_in_header(tab) == 3
    labels = [lbl.text() for lbl in tab._highlight_labels]
    values = [v.text() for v in tab._highlight_values]
    assert labels == ["하루 평균", "운동 시간", "건너뜀"]
    assert values == ["1.0회", "3분 12초", "1회"]


def test_기간을_바꾸면_막대_수와_제목이_바뀐다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 7, 14))])
    tab.set_period(Period.DAY)
    assert tab._nav_title.text() == "오늘"
    assert len(tab._chart._buckets) == 24
    assert tab._caption.text() == "2026년 10월 7일 수요일"
    assert count_in_header(tab) == 2
    assert [lbl.text() for lbl in tab._highlight_labels] == ["운동 시간", "건너뜀", "미룸"]
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
    assert [v.text() for v in tab._highlight_values][0] == "0.4회"  # 7일로 나눈 평균 (3/7)
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
    events = [done(at(10, 5)), done(at(10, 5, 15), "dot_follow", 60), done(at(10, 7))]
    tab, _ = make_tab(qapp, events)
    click_bar(tab, 0)  # 월요일
    assert tab._kicker.text() == "10월 5일 (월)"
    assert count_in_header(tab) == 2
    assert tab._caption.text() == "운동 시간 2분 6초"
    assert tab._chart._selected == 0


def test_같은_막대를_다시_누르면_선택이_풀린다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 0)
    click_bar(tab, 0)
    assert tab._chart._selected == -1
    assert tab._kicker.text() == "완료한 운동" and tab._caption.text() == "10월 5일 – 10월 11일"


def test_다른_막대를_누르면_선택이_옮겨간다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5)), done(at(10, 6)), done(at(10, 6, 14))])
    click_bar(tab, 0)
    click_bar(tab, 1)
    assert tab._chart._selected == 1 and count_in_header(tab) == 2


def test_기록이_없는_막대도_선택할_수_있다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 5))])
    click_bar(tab, 1)  # 화요일: 기록 없음
    assert tab._chart._selected == 1
    assert count_in_header(tab) == 0 and tab._caption.text() == "완료한 운동 없음"


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


# ---- 최근 기록 ----


def test_최근_기록은_최신순으로_보인다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 14)), HistoryEvent(at(10, 6, 12), "skipped")]
    tab, _ = make_tab(qapp, events)
    assert row_times(tab) == ["14:00", "09:00", "12:00"]
    assert group_titles(tab) == ["오늘", "어제"]


def test_최근_기록은_처음에_10줄만_보인다(qapp):
    events = [done(at(10, 7, 0, m)) for m in range(0, 59)] + [done(at(10, 6, 12, m)) for m in range(40)]
    tab, _ = make_tab(qapp, events)
    assert len(row_times(tab)) == RECENT_COLLAPSED == 10
    assert row_times(tab)[0] == "00:58"  # 가장 최근 기록부터


def test_더_보기를_누르면_펼쳐지고_접기로_다시_접는다(qapp):
    events = [done(at(10, 7, 0, m)) for m in range(0, 59)] + [done(at(10, 6, 12, m)) for m in range(40)]
    tab, _ = make_tab(qapp, events)
    assert not tab._more.isHidden() and tab._more.text() == "더 보기"
    tab._more.click()
    assert tab._more.text() == "접기" and len(row_times(tab)) == 99  # 최대 RECENT_EXPANDED(100)줄
    assert group_titles(tab) == ["오늘", "어제"]
    tab._more.click()
    assert tab._more.text() == "더 보기" and len(row_times(tab)) == RECENT_COLLAPSED


def test_펼친_줄_수에도_상한이_있다(qapp):
    events = [done(at(10, 7, h, m)) for h in range(24) for m in range(0, 60, 10)]  # 144건
    tab, _ = make_tab(qapp, events)
    tab._more.click()
    assert len(row_times(tab)) == RECENT_EXPANDED


def test_기록이_10개_이하면_더_보기_버튼이_없다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, h)) for h in range(10)])
    assert tab._more.isHidden()
    tab, _ = make_tab(qapp, [done(at(10, 7, h)) for h in range(11)])
    assert not tab._more.isHidden()


def test_표_머리와_칸은_시간_운동_결과_길이다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 14, 32), "dot_follow", 60), done(at(10, 7, 14, 4), "blink", 66)])
    assert table_headers(tab) == ["시간", "운동", "결과", "길이"]
    assert table_rows(tab) == [["14:32", "점 따라가기", "완료", "1분"], ["14:04", "깜빡임", "완료", "1분 6초"]]


def test_건너뜀과_미룸은_연한_회색_줄이고_완료는_또렷하다(qapp):
    events = [done(at(10, 7, 14)), HistoryEvent(at(10, 7, 13), "skipped"), HistoryEvent(at(10, 7, 12), "snoozed")]
    tab, _ = make_tab(qapp, events)
    assert table_rows(tab) == [["14:00", "깜빡임", "완료", "1분 6초"], ["13:00", "", "건너뜀", ""], ["12:00", "", "미룸", ""]]
    assert muted_flags(tab) == [False, True, True]


def test_기간과_상관없이_최근_기록은_그대로다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(9, 1, 9))])
    before = row_times(tab)
    tab.set_period(Period.DAY)
    tab.go(-1)
    assert row_times(tab) == before == ["09:00", "09:00"]
    assert group_titles(tab) == ["오늘", "9월 1일 (화)"]


# ---- 새로 그리기 ----


def test_새_기록이_생기면_refresh로_반영된다(qapp):
    tab, source = make_tab(qapp)
    assert count_in_header(tab) == 0
    source.events.append(done(at(10, 7, 14)))
    tab.refresh()
    assert count_in_header(tab) == 1 and row_times(tab) == ["14:00"]
    assert group_titles(tab) == ["오늘"]
    source.events.append(done(at(10, 7, 15)))
    tab.refresh()
    assert count_in_header(tab) == 2 and row_times(tab) == ["15:00", "14:00"]


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
    assert window._nav.item(0).text() == "기록"
    assert window._stack.widget(0) is window.records_tab


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


def test_왼쪽_메뉴에_기록_설정_시력_기록이_있다(qapp):
    window = MainWindow()
    assert [window._nav.item(i).text() for i in range(window._nav.count())] == ["기록", "설정", "시력 기록"]
    assert window._nav.currentRow() == 0 and window._stack.currentWidget() is window.records_tab


def test_메뉴를_고르면_본문이_바뀐다(qapp):
    window = MainWindow()
    window._nav.setCurrentRow(1)
    assert window._stack.currentIndex() == 1 and window._stack.currentWidget() is not window.records_tab
    window._nav.setCurrentRow(2)
    assert window._stack.currentIndex() == 2
    window._nav.setCurrentRow(0)
    assert window._stack.currentWidget() is window.records_tab


def test_아직_없는_화면은_안내_문구를_보여_준다(qapp):
    window = MainWindow()
    texts = [window._stack.widget(i).text() for i in (1, 2)]
    assert all("다음 단계" in t for t in texts)


def test_메인_창은_넓은_데스크톱_크기로_뜨고_더_작아지지_않는다(qapp):
    window = MainWindow()
    assert (window.width(), window.height()) == (1000, 700)
    assert (window.minimumWidth(), window.minimumHeight()) == (860, 560)


def test_하이라이트_카드는_보조_설명이_있을_때만_보여_준다(qapp):
    tab, _ = make_tab(qapp)
    assert all(d.isHidden() for d in tab._highlight_details)  # 운동 카드에는 보조 설명이 없다
