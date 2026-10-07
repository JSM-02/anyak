import re
from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import Period
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui.records_tab import Mode, RecordsTab

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def rest(ts, seconds=66):
    return HistoryEvent(ts, "completed", "blink", seconds)  # 깜빡임 = 눈 휴식


def exercise(ts, seconds=60):
    return HistoryEvent(ts, "completed", "dot_follow", seconds)  # 점 따라가기 = 눈 운동


def usage_of(entries):
    usage = UsageLog()
    for month, day, hour, seconds in entries:
        usage.add(at(month, day, hour, 0), seconds)
    return usage


def make_tab(qapp, events=(), entries=()):
    state = {"events": list(events), "usage": usage_of(entries)}
    tab = RecordsTab(lambda: state["events"], now=lambda: NOW, tz=KST, usage_provider=lambda: state["usage"])
    tab.resize(1000, 900)
    tab.show()
    qapp.processEvents()
    return tab, state


def texts(tab, name):
    return [lbl.text() for lbl in tab.findChildren(QLabel) if lbl.objectName() == name]


def visible_texts(tab, name):
    return [lbl.text() for lbl in tab.findChildren(QLabel) if lbl.objectName() == name and not lbl.isHidden()]


def plain(html):
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


# 오늘 요약은 카드 세 장이다: 0 = 눈 휴식, 1 = 눈 운동, 2 = 스크린 타임
REST, EXERCISE, SCREEN = 0, 1, 2

# ---- 오늘 요약: 어제 하루와 비교 ----


def test_오늘_요약은_눈_휴식_눈_운동_스크린_타임_세_장이다(qapp):
    tab, _ = make_tab(qapp)
    assert texts(tab, "todayTitle") == ["오늘 눈 휴식", "오늘 눈 운동", "오늘 스크린 타임"]


def test_오늘_눈_휴식과_어제와의_비교가_보인다(qapp):
    events = [rest(at(10, 7, 9)), rest(at(10, 7, 10)), rest(at(10, 7, 14)), rest(at(10, 6, 9))]  # 오늘 3회, 어제 1회
    tab, _ = make_tab(qapp, events)
    assert texts(tab, "todayValue")[REST] == "3회"
    assert texts(tab, "todayLine")[REST] == "▲ 어제보다 2회 많아요"


def test_오늘_눈_운동은_휴식과_따로_센다(qapp):
    events = [rest(at(10, 7, 9)), rest(at(10, 7, 10)), exercise(at(10, 7, 11)), exercise(at(10, 6, 11)), rest(at(10, 6, 9))]
    tab, _ = make_tab(qapp, events)
    assert texts(tab, "todayValue")[REST] == "2회" and texts(tab, "todayValue")[EXERCISE] == "1회"
    assert texts(tab, "todayLine")[REST] == "▲ 어제보다 1회 많아요"
    assert texts(tab, "todayLine")[EXERCISE] == "– 어제와 같아요"
    assert texts(tab, "todayLineSub") == []  # 시간 비교 줄은 없다 (휴식 시간·운동 시간은 보여 주지 않는다)


def test_오늘이_어제보다_적으면_아래_화살표와_적다는_문구(qapp):
    tab, _ = make_tab(qapp, [rest(at(10, 7, 9)), rest(at(10, 6, 9)), rest(at(10, 6, 10)), rest(at(10, 6, 20))])
    assert texts(tab, "todayLine")[REST] == "▼ 어제보다 2회 적어요"


def test_같으면_같다고_보인다(qapp):
    tab, _ = make_tab(qapp, [rest(at(10, 7, 9)), rest(at(10, 6, 9))])
    assert texts(tab, "todayLine")[REST] == "– 어제와 같아요"


def test_어제_기록이_없으면_화살표_없이_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, [rest(at(10, 7, 9))])
    assert texts(tab, "todayLine")[REST] == "어제 기록이 없어요"
    assert texts(tab, "todayLine")[EXERCISE] == "어제 기록이 없어요"


def test_오늘_스크린_타임과_어제와의_비교가_보인다(qapp):
    # 어제 하루 1시간, 오늘 지금까지 3600 + 3600 + 900 = 8100초 = 2시간 15분
    entries = [(10, 6, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 3600), (10, 7, 11, 900)]
    tab, _ = make_tab(qapp, entries=entries)
    assert texts(tab, "todayValue")[SCREEN] == "2시간 15분"
    assert texts(tab, "todayLine")[SCREEN] == "▲ 어제보다 1시간 15분 많아요"


def test_스크린_타임_값과_비교_문구(qapp):
    entries = [(10, 6, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 1800)]  # 어제 1시간, 오늘 1시간 30분
    tab, _ = make_tab(qapp, entries=entries)
    assert texts(tab, "todayValue")[SCREEN] == "1시간 30분"
    assert texts(tab, "todayLine")[SCREEN] == "▲ 어제보다 30분 많아요"


def test_스크린_타임이_적으면_아래_화살표(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 6, 9, 3600), (10, 6, 10, 3600), (10, 7, 9, 1800)])
    assert texts(tab, "todayLine")[SCREEN] == "▼ 어제보다 1시간 30분 적어요"


def test_스크린_타임이_비슷하면_비슷하다고_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 6, 9, 1800), (10, 7, 9, 1810)])
    assert texts(tab, "todayLine")[SCREEN] == "– 어제와 비슷해요"


def test_어제_스크린_타임_기록이_없으면_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 7, 9, 1800)])
    assert texts(tab, "todayValue")[SCREEN] == "30분"
    assert texts(tab, "todayLine")[SCREEN] == "어제 기록이 없어요"


def test_오늘_요약은_보는_기간과_모드에_상관없이_항상_같다(qapp):
    events = [rest(at(10, 7, 9)), rest(at(10, 7, 10)), exercise(at(10, 6, 9))]
    tab, _ = make_tab(qapp, events, entries=[(10, 6, 9, 3600), (10, 7, 9, 7200 // 2)])
    before = (texts(tab, "todayValue"), texts(tab, "todayLine"), texts(tab, "todayLineSub"))
    tab.set_period(Period.MONTH)
    tab.go(-1)
    for mode in (Mode.SCREEN_TIME, Mode.REST):
        tab.set_mode(mode)
        tab.set_period(Period.DAY)
        assert (texts(tab, "todayValue"), texts(tab, "todayLine"), texts(tab, "todayLineSub")) == before


def test_새_기록이_생기면_오늘_요약도_바뀐다(qapp):
    tab, state = make_tab(qapp, [rest(at(10, 7, 9)), rest(at(10, 6, 9)), rest(at(10, 6, 10))])
    assert texts(tab, "todayValue")[REST] == "1회" and texts(tab, "todayLine")[REST] == "▼ 어제보다 1회 적어요"
    state["events"].append(rest(at(10, 7, 11)))
    tab.refresh()
    assert texts(tab, "todayValue")[REST] == "2회" and texts(tab, "todayLine")[REST] == "– 어제와 같아요"
    state["usage"].add(at(10, 7, 9, 0), 600)
    tab.refresh()
    assert texts(tab, "todayValue")[SCREEN] == "10분"


def test_기록이_하나도_없어도_오늘_요약이_보인다(qapp):
    tab, _ = make_tab(qapp)
    assert texts(tab, "todayValue") == ["0회", "0회", "0분"]
    assert texts(tab, "todayLine") == ["어제 기록이 없어요"] * 3


# ---- 하루 흐름: 범례와 칸 안의 숫자 ----


def test_범례는_칸_색과_눈_운동_숫자의_뜻을_보여_준다(qapp):
    tab, _ = make_tab(qapp, [rest(at(10, 7, 14))])
    assert [plain(t) for t in texts(tab, "legendItem")] == ["▬ 스크린 타임 (진할수록 오래)", "2 마친 눈 운동 횟수"]
    assert not tab._legend.isHidden()
    assert re.findall(r"#[0-9a-f]{6}", " ".join(texts(tab, "legendItem"))) == ["#188038"]  # 칸 색은 포인트 색(초록)


def test_모든_모드에서_범례가_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 7, 9, 600)])
    for mode in (Mode.SCREEN_TIME, Mode.REST):
        tab.set_mode(mode)
        assert not tab._legend.isHidden()
