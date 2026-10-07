from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import Period
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui.records_tab import Mode, RecordsTab

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일. 이번 주 월~수 3일이 지났고, 지난 주는 9/28~10/4


def at(month, day, hour=12):
    return datetime(2026, month, day, hour, 0, tzinfo=KST)


def last_week(d):
    day = date(2026, 9, 28) + timedelta(days=d)
    return day.month, day.day


def done(ts, seconds=66):
    return HistoryEvent(ts, "completed", "blink", seconds)


def skipped(ts):
    return HistoryEvent(ts, "skipped", activity="rest")


def make_tab(qapp, events=(), entries=()):
    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(at(month, day, hour), seconds)
    events = list(events)
    tab = RecordsTab(lambda: events, now=lambda: NOW, tz=KST, usage_provider=lambda: usage)
    tab.resize(1000, 900)
    tab.show()
    qapp.processEvents()
    return tab


def labels(tab, name):
    return [lbl for lbl in tab.findChildren(QLabel) if lbl.objectName() == name]


def card_texts(tab, name):
    return [lbl.text() for lbl in labels(tab, name)]


def click_bar(tab, index):
    chart = tab._chart
    rect = chart.bar_rect(index)
    y = rect.center().y() if rect.height() > 0 else chart._plot().bottom() - 4
    QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=QPoint(int(rect.center().x()), int(y)))


# 이번 주 월~수: 완료 6회(66초씩), 건너뜀 3회. 지난 주: 완료 7회(하루 1회), 건너뜀 2회
EVENTS = (
    [done(at(10, 5, 9)), done(at(10, 5, 10)), done(at(10, 6, 9)), done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 11))]
    + [skipped(at(10, 5, 12)), skipped(at(10, 7, 12)), skipped(at(10, 7, 13))]
    + [done(at(*last_week(d), 9)) for d in range(7)]
    + [skipped(at(*last_week(0), 12)), skipped(at(*last_week(3), 12))]
)
# 이번 주 하루 평균 80분(최고 화요일 2시간), 지난 주 하루 평균 30분(최고 30분)
USAGE = [(10, 5, 9, 3600), (10, 6, 9, 3600), (10, 6, 10, 3600), (10, 7, 9, 3600)] + [(*last_week(d), 9, 1800) for d in range(7)]


def test_주_운동_카드마다_앞_기간과의_비교가_보인다(qapp):
    tab = make_tab(qapp, EVENTS)
    assert card_texts(tab, "cardLabel") == ["하루 평균", "건너뜀", "미룸"]  # 휴식 시간은 보여 주지 않는다
    assert card_texts(tab, "cardValue") == ["2.0회", "3회", "0회"]
    assert card_texts(tab, "cardCompare") == [
        "▲ 지난 주보다 1.0회 많아요",
        "▲ 지난 주보다 하루 평균 0.7회 많아요",
        "– 지난 주와 같아요",
    ]
    assert all(not lbl.isHidden() for lbl in labels(tab, "cardCompare"))


def test_일_운동_카드는_어제와_합계로_비교한다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), skipped(at(10, 7, 11)), done(at(10, 6, 9)), skipped(at(10, 6, 10)), skipped(at(10, 6, 11))]
    tab = make_tab(qapp, events)
    tab.set_period(Period.DAY)
    assert card_texts(tab, "cardLabel") == ["건너뜀", "미룸", "쉰 시간대"]
    assert card_texts(tab, "cardValue") == ["1회", "0회", "2개"]  # 오늘은 9시와 10시에 쉬었다
    assert card_texts(tab, "cardCompare") == ["▼ 어제보다 1회 적어요", "– 어제와 같아요", "▲ 어제보다 1개 많아요"]


def test_월_운동_카드도_비교한다(qapp):
    events = [done(at(10, d, h)) for d in range(1, 8) for h in (9, 10)] + [done(at(9, d, 9)) for d in range(1, 31)]
    tab = make_tab(qapp, events)
    tab.set_period(Period.MONTH)
    assert card_texts(tab, "cardCompare")[0] == "▲ 지난 달보다 1.0회 많아요"


def test_지난_기간을_보면_전주로_비교한다(qapp):
    tab = make_tab(qapp, [done(at(*last_week(0), 9)), done(at(*last_week(1), 9)), done(at(9, 21, 9))])
    tab.go(-1)
    assert card_texts(tab, "cardCompare")[0] == "▲ 전주보다 0.1회 많아요"


def test_앞_기간에_기록이_없으면_카드의_비교_줄은_숨긴다(qapp):
    tab = make_tab(qapp, [done(at(10, 7, 9))])
    assert all(lbl.isHidden() for lbl in labels(tab, "cardCompare"))
    assert card_texts(tab, "cardCompare") == ["", "", ""]


def test_기록이_하나도_없어도_카드가_깨지지_않는다(qapp):
    tab = make_tab(qapp)
    assert card_texts(tab, "cardValue") == ["0.0회", "0회", "0회"]
    assert all(lbl.isHidden() for lbl in labels(tab, "cardCompare"))


def test_카드_비교_줄은_긴_문구가_잘리지_않게_줄바꿈한다(qapp):
    tab = make_tab(qapp, EVENTS)
    assert all(lbl.wordWrap() for lbl in labels(tab, "cardCompare"))


def test_막대를_선택해도_카드는_기간_전체의_비교를_그대로_보여_준다(qapp):
    tab = make_tab(qapp, EVENTS)
    before = card_texts(tab, "cardCompare")
    click_bar(tab, 0)
    assert card_texts(tab, "cardCompare") == before


# ---- 스크린 타임 ----


def test_스크린_타임_주_카드_비교(qapp):
    tab = make_tab(qapp, EVENTS, USAGE)
    tab.set_mode(Mode.SCREEN_TIME)
    assert card_texts(tab, "cardLabel") == ["하루 평균", "쉬지 않고 쓴 가장 긴 시간", "휴식 달성률"]
    assert card_texts(tab, "cardValue") == ["1시간 20분", "1시간 59분", "50%"]
    assert card_texts(tab, "cardCompare") == ["▲ 지난 주보다 50분 많아요", "▲ 지난 주보다 1시간 30분 많아요", ""]  # 달성률은 비교하지 않는다
    assert card_texts(tab, "cardDetail")[1:] == ["어제", "6회 / 권장 12회"]  # 화요일(어제)에 가장 오래 쉬지 않았고, 권장 12회 중 6회 쉬었다


def test_스크린_타임_일_카드_비교(qapp):
    entries = [(10, 7, 9, 3600), (10, 7, 10, 1800), (10, 6, 9, 1800)]
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))]
    tab = make_tab(qapp, events, entries)
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert card_texts(tab, "cardLabel") == ["가장 많이 쓴 시간", "쉬지 않고 쓴 가장 긴 시간", "휴식 달성률"]
    assert card_texts(tab, "cardValue") == ["1시간", "59분", "50%"]
    assert card_texts(tab, "cardCompare") == ["▲ 어제 최고보다 30분 많아요", "▲ 어제보다 30분 많아요", ""]


def test_스크린_타임_앞_기간_기록이_없으면_비교를_숨긴다(qapp):
    tab = make_tab(qapp, EVENTS, [(10, 7, 9, 3600)])  # 지난 주 스크린 타임 기록 없음
    tab.set_mode(Mode.SCREEN_TIME)
    assert card_texts(tab, "cardCompare") == ["", "", ""]
    assert all(lbl.isHidden() for lbl in labels(tab, "cardCompare"))


def test_모드를_바꾸면_카드_비교도_바뀐다(qapp):
    tab = make_tab(qapp, EVENTS, USAGE)
    exercise = card_texts(tab, "cardCompare")
    tab.set_mode(Mode.SCREEN_TIME)
    assert card_texts(tab, "cardCompare") != exercise
    tab.set_mode(Mode.REST)
    assert card_texts(tab, "cardCompare") == exercise


def test_큰_숫자_아래_비교와_카드_비교가_함께_보인다(qapp):
    tab = make_tab(qapp, EVENTS)
    assert labels(tab, "compareLine")[0].text() == "▲ 지난 주보다 하루 평균 1.0회 많아요"
    assert card_texts(tab, "cardCompare")[0] == "▲ 지난 주보다 1.0회 많아요"


def test_새_기록이_생기면_카드_비교도_바뀐다(qapp):
    events = list(EVENTS)
    usage = UsageLog()
    tab = RecordsTab(lambda: events, now=lambda: NOW, tz=KST, usage_provider=lambda: usage)
    tab.show()
    assert card_texts(tab, "cardCompare")[1] == "▲ 지난 주보다 하루 평균 0.7회 많아요"
    events.extend([skipped(at(10, 7, 14)), skipped(at(10, 7, 15)), skipped(at(10, 6, 14))])  # 건너뜀이 6회가 되어 하루 평균 2.0
    tab.refresh()
    assert card_texts(tab, "cardCompare")[1] == "▲ 지난 주보다 하루 평균 1.7회 많아요"
