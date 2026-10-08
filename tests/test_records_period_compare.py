import re
from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import Period
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui.records_tab import Mode, RecordsTab, arrow_line

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일. 이번 주 월~수 3일이 지났고, 지난 주는 9/28~10/4


def at(month, day, hour=12):
    return datetime(2026, month, day, hour, 0, tzinfo=KST)


def last_week(d):
    """지난 주(9/28 월요일 시작)의 d번째 날의 (월, 일)."""
    day = date(2026, 9, 28) + timedelta(days=d)
    return day.month, day.day


def done(ts, seconds=66):
    return HistoryEvent(ts, "completed", "blink", seconds)


def usage_of(entries):
    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(at(month, day, hour), seconds)
    return usage


def make_tab(qapp, events=(), entries=()):
    state = {"events": list(events), "usage": usage_of(entries)}
    tab = RecordsTab(lambda: state["events"], now=lambda: NOW, tz=KST, usage_provider=lambda: state["usage"])
    tab.set_period(Period.WEEK)  # 앱의 처음 화면은 일 보기이지만 이 테스트는 주 보기 기준이다
    tab.resize(1000, 900)
    tab.show()
    qapp.processEvents()
    return tab, state


def label(tab, name, index=0):
    return [lbl for lbl in tab.findChildren(QLabel) if lbl.objectName() == name][index]


def compare_texts(tab):
    return label(tab, "compareLine").text(), label(tab, "compareLineSub").text()


def click_bar(tab, index):
    chart = tab._chart
    rect = chart.bar_rect(index)
    y = rect.center().y() if rect.height() > 0 else chart._plot().bottom() - 4
    QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=QPoint(int(rect.center().x()), int(y)))


# 이번 주 월~수 6회(하루 평균 2.0), 지난 주 7회(하루 평균 1.0)
WEEK_EVENTS = (
    [done(at(10, 5, h)) for h in (9, 10)] + [done(at(10, 6, 9))] + [done(at(10, 7, h)) for h in (9, 10, 11)] + [done(at(*last_week(d), 9)) for d in range(7)]
)


# ---- 화살표 ----


def test_화살표는_추세에_따라_붙고_비교할_수_없으면_붙지_않는다():
    assert arrow_line("up", "어제보다 2회 많아요") == "▲ 어제보다 2회 많아요"
    assert arrow_line("down", "어제보다 2회 적어요") == "▼ 어제보다 2회 적어요"
    assert arrow_line("same", "어제와 같아요") == "– 어제와 같아요"
    assert arrow_line("same", "지난 주 기록이 없어요") == "지난 주 기록이 없어요"


# ---- 운동 ----


def test_주_보기는_큰_숫자_아래에_지난_주와의_하루_평균_비교가_보인다(qapp):
    tab, _ = make_tab(qapp, WEEK_EVENTS)
    assert compare_texts(tab) == ("▲ 지난 주보다 하루 평균 1.0회 많아요", "")
    assert not label(tab, "compareLine").isHidden() and label(tab, "compareLineSub").isHidden()  # 휴식 시간 비교는 없다


def test_일_보기는_어제와_합계로_비교한다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))])
    tab.set_period(Period.DAY)
    assert compare_texts(tab) == ("▲ 어제보다 1회 많아요", "")


def test_월_보기는_지난_달과_하루_평균으로_비교한다(qapp):
    events = [done(at(10, d, h)) for d in range(1, 8) for h in (9, 10)] + [done(at(9, d, 9)) for d in range(1, 31)]
    tab, _ = make_tab(qapp, events)
    tab.set_period(Period.MONTH)
    assert compare_texts(tab)[0] == "▲ 지난 달보다 하루 평균 1.0회 많아요"


def test_이전_기간으로_가면_그_기간의_앞_기간과_비교한다(qapp):
    events = [done(at(9, 29, 9)), done(at(9, 29, 10)), done(at(9, 22, 9))]
    tab, _ = make_tab(qapp, events)
    tab.go(-1)  # 지난 주(9/28~10/4)
    assert compare_texts(tab)[0] == "▲ 전주보다 하루 평균 0.1회 많아요"
    tab.set_period(Period.DAY)
    tab.go(-1)  # 어제
    assert compare_texts(tab)[0] == "전날 기록이 없어요"  # 어제를 보는 중이면 앞 기간은 '전날'이고 그날(10/5) 기록은 없다


def test_앞_기간에_기록이_없으면_화살표_없이_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    assert compare_texts(tab)[0] == "지난 주 기록이 없어요"
    assert label(tab, "compareLineSub").isHidden()


def test_기록이_하나도_없어도_비교_줄이_깨지지_않는다(qapp):
    tab, _ = make_tab(qapp)
    assert compare_texts(tab)[0] == "지난 주 기록이 없어요"


def test_같으면_같다고_보인다(qapp):
    events = [done(at(10, 5, 9)), done(at(10, 6, 9)), done(at(10, 7, 9))] + [done(at(*last_week(d), 9)) for d in range(7)]
    tab, _ = make_tab(qapp, events)
    assert compare_texts(tab) == ("– 하루 평균이 지난 주와 같아요", "")


# ---- 막대를 선택하면 숨긴다 ----


def test_막대를_선택하면_비교_줄을_숨기고_해제하면_다시_보인다(qapp):
    tab, _ = make_tab(qapp, WEEK_EVENTS)
    click_bar(tab, 0)  # 월요일
    assert label(tab, "compareLine").isHidden() and label(tab, "compareLineSub").isHidden()
    assert label(tab, "compareLine").text() == ""
    click_bar(tab, 0)
    assert not label(tab, "compareLine").isHidden()
    assert compare_texts(tab)[0] == "▲ 지난 주보다 하루 평균 1.0회 많아요"


# ---- 스크린 타임 ----


def test_스크린_타임_주_보기는_지난_주와_하루_평균으로_비교한다(qapp):
    entries = [(10, d, 9, 3600) for d in (5, 6, 7)] + [(*last_week(d), 9, 1800) for d in range(7)]
    tab, _ = make_tab(qapp, entries=entries)
    tab.set_mode(Mode.SCREEN_TIME)
    assert compare_texts(tab)[0] == "▲ 지난 주보다 하루 평균 30분 많아요"
    assert label(tab, "compareLineSub").isHidden()  # 스크린 타임은 한 줄이다


def test_스크린_타임_일_보기는_어제_합계와_비교한다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 6, 9, 3600), (10, 7, 9, 1800)])
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert compare_texts(tab)[0] == "▼ 어제보다 30분 적어요"


def test_스크린_타임_앞_기간_기록이_없으면_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 7, 9, 600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert compare_texts(tab)[0] == "지난 주 기록이 없어요"


def test_스크린_타임에서도_막대를_선택하면_비교를_숨긴다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 5, 9, 600), (10, 7, 9, 600), (*last_week(0), 9, 600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert not label(tab, "compareLine").isHidden()
    click_bar(tab, 0)
    assert label(tab, "compareLine").isHidden()


def test_모드를_바꾸면_비교_내용도_바뀐다(qapp):
    entries = [(10, d, 9, 3600) for d in (5, 6, 7)] + [(*last_week(d), 9, 1800) for d in range(7)]
    tab, _ = make_tab(qapp, WEEK_EVENTS, entries)
    exercise = compare_texts(tab)[0]
    tab.set_mode(Mode.SCREEN_TIME)
    assert compare_texts(tab)[0] != exercise and "회" not in compare_texts(tab)[0]
    tab.set_mode(Mode.REST)
    assert compare_texts(tab)[0] == exercise


# ---- 오늘 요약과 일치 ----


def test_일_보기의_비교는_오늘_요약의_문구와_같다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))]
    entries = [(10, 6, 9, 3600), (10, 7, 9, 1800)]
    tab, _ = make_tab(qapp, events, entries)
    tab.set_period(Period.DAY)
    assert label(tab, "compareLine").text() == label(tab, "todayLine", 0).text()
    tab.set_mode(Mode.SCREEN_TIME)
    assert label(tab, "compareLine").text() == label(tab, "todayLine", 2).text()  # 오늘 요약의 셋째 칸이 스크린 타임


def test_새_기록이_생기면_비교도_바뀐다(qapp):
    tab, state = make_tab(qapp, WEEK_EVENTS)
    state["events"].extend(done(at(10, 7, h)) for h in (12, 13, 14))  # 이번 주 하루 평균 3.0
    tab.refresh()
    assert compare_texts(tab)[0] == "▲ 지난 주보다 하루 평균 2.0회 많아요"
    assert re.search(r"2\.0", compare_texts(tab)[0])
