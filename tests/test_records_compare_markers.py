import re
from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import Period
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui.records_tab import Mode, RecordsTab, marker_color

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)  # 수요일


def at(month, day, hour=12, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def done(ts, exercise="blink", seconds=66):
    return HistoryEvent(ts, "completed", exercise, seconds)


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


def dots(tab):
    """타임라인의 점 색을 날짜 줄 순서(오늘 먼저), 같은 날은 시간순으로 돌려준다."""
    return [marker_color(m.kind, m.exercise).name() for d in tab._timeline._days for m in d.marks]


def plain(html):
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


# ---- 오늘 요약: 어제 하루와 비교 ----


def test_오늘_운동_완료와_어제와의_비교가_보인다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 7, 14)), done(at(10, 6, 9))]  # 오늘 3회, 어제 1회
    tab, _ = make_tab(qapp, events)
    assert texts(tab, "todayTitle") == ["오늘 운동 완료", "오늘 스크린 타임"]
    assert texts(tab, "todayValue")[0] == "3회"
    assert texts(tab, "todayLine")[0] == "▲ 어제보다 2회 많아요"
    assert texts(tab, "todayLineSub")[0] == "운동 시간은 2분 12초 많아요"


def test_오늘이_어제보다_적으면_아래_화살표와_적다는_문구(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 6, 9)), done(at(10, 6, 10)), done(at(10, 6, 20))])
    assert texts(tab, "todayLine")[0] == "▼ 어제보다 2회 적어요"
    assert texts(tab, "todayLineSub")[0] == "운동 시간은 2분 12초 적어요"


def test_같으면_같다고_보인다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 6, 9))])
    assert texts(tab, "todayLine")[0] == "– 어제와 같아요"
    assert texts(tab, "todayLineSub")[0] == "운동 시간도 같아요"


def test_어제_기록이_없으면_화살표_없이_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 9))])
    assert texts(tab, "todayLine")[0] == "어제 기록이 없어요"
    assert visible_texts(tab, "todayLineSub") == []  # 두 번째 줄(운동 시간 비교)은 숨긴다


def test_오늘_스크린_타임과_어제와의_비교가_보인다(qapp):
    # 어제 하루 1시간, 오늘 지금까지 3600 + 3600 + 900 = 8100초 = 2시간 15분
    entries = [(10, 6, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 3600), (10, 7, 11, 900)]
    tab, _ = make_tab(qapp, entries=entries)
    assert texts(tab, "todayValue")[1] == "2시간 15분"
    assert texts(tab, "todayLine")[1] == "▲ 어제보다 1시간 15분 많아요"


def test_스크린_타임_값과_비교_문구(qapp):
    entries = [(10, 6, 9, 3600), (10, 7, 9, 3600), (10, 7, 10, 1800)]  # 어제 1시간, 오늘 1시간 30분
    tab, _ = make_tab(qapp, entries=entries)
    assert texts(tab, "todayValue")[1] == "1시간 30분"
    assert texts(tab, "todayLine")[1] == "▲ 어제보다 30분 많아요"


def test_스크린_타임이_적으면_아래_화살표(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 6, 9, 3600), (10, 6, 10, 3600), (10, 7, 9, 1800)])
    assert texts(tab, "todayLine")[1] == "▼ 어제보다 1시간 30분 적어요"


def test_스크린_타임이_비슷하면_비슷하다고_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 6, 9, 1800), (10, 7, 9, 1810)])
    assert texts(tab, "todayLine")[1] == "– 어제와 비슷해요"


def test_어제_스크린_타임_기록이_없으면_안내만_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 7, 9, 1800)])
    assert texts(tab, "todayValue")[1] == "30분"
    assert texts(tab, "todayLine")[1] == "어제 기록이 없어요"


def test_오늘_요약은_보는_기간과_모드에_상관없이_항상_같다(qapp):
    events = [done(at(10, 7, 9)), done(at(10, 7, 10)), done(at(10, 6, 9))]
    tab, _ = make_tab(qapp, events, entries=[(10, 6, 9, 3600), (10, 7, 9, 7200 // 2)])
    before = (texts(tab, "todayValue"), texts(tab, "todayLine"), texts(tab, "todayLineSub"))
    tab.set_period(Period.MONTH)
    tab.go(-1)
    tab.set_mode(Mode.SCREEN_TIME)
    tab.set_period(Period.DAY)
    assert (texts(tab, "todayValue"), texts(tab, "todayLine"), texts(tab, "todayLineSub")) == before


def test_새_기록이_생기면_오늘_요약도_바뀐다(qapp):
    tab, state = make_tab(qapp, [done(at(10, 7, 9)), done(at(10, 6, 9)), done(at(10, 6, 10))])
    assert texts(tab, "todayValue")[0] == "1회" and texts(tab, "todayLine")[0] == "▼ 어제보다 1회 적어요"
    state["events"].append(done(at(10, 7, 11)))
    tab.refresh()
    assert texts(tab, "todayValue")[0] == "2회" and texts(tab, "todayLine")[0] == "– 어제와 같아요"
    state["usage"].add(at(10, 7, 9, 0), 600)
    tab.refresh()
    assert texts(tab, "todayValue")[1] == "10분"


def test_기록이_하나도_없어도_오늘_요약이_보인다(qapp):
    tab, _ = make_tab(qapp)
    assert texts(tab, "todayValue") == ["0회", "0분"]
    assert texts(tab, "todayLine") == ["어제 기록이 없어요", "어제 기록이 없어요"]


# ---- 최근 기록의 색 원 ----


def test_색_원은_운동_종류와_결과에_따라_다르다():
    assert marker_color("completed", "blink").name() == "#1a73e8"
    assert marker_color("completed", "dot_follow").name() == "#8e5bd8"
    assert marker_color("skipped", "").name() == "#9aa0a6"
    assert marker_color("snoozed", "").name() == "#f9ab00"


def test_모르는_운동은_파랑_모르는_종류는_회색():
    assert marker_color("completed", "jumping").name() == "#1a73e8"
    assert marker_color("unknown", "").name() == "#9aa0a6"


def test_네_가지_색은_모두_다르다():
    colors = {
        marker_color("completed", "blink").name(),
        marker_color("completed", "dot_follow").name(),
        marker_color("skipped", "").name(),
        marker_color("snoozed", "").name(),
    }
    assert len(colors) == 4


def test_점의_색은_운동_종류와_결과에_맞다(qapp):
    events = [
        done(at(10, 7, 11), "dot_follow"),
        done(at(10, 7, 12), "blink"),
        HistoryEvent(at(10, 7, 13), "skipped"),
        HistoryEvent(at(10, 7, 14), "snoozed"),
    ]
    tab, _ = make_tab(qapp, events)
    assert dots(tab) == ["#8e5bd8", "#1a73e8", "#9aa0a6", "#f9ab00"]


def test_점_개수는_보이는_기간의_기록_수이고_펼치면_옛_기록도_보인다(qapp):
    events = [done(at(10, 7, h)) for h in range(0, 14)] + [done(at(9, 20, 9))]  # 9/20은 7일 밖
    tab, _ = make_tab(qapp, events)
    assert len(dots(tab)) == 14
    tab._more.click()
    assert len(dots(tab)) == 15


def test_범례는_칸_색과_숫자와_귀퉁이_점의_뜻을_보여_준다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 14))])
    assert [plain(t) for t in texts(tab, "legendItem")] == ["▬ 스크린 타임 (진할수록 오래)", "3 완료한 운동 횟수", "● 건너뜀", "● 미룸"]
    assert not tab._legend.isHidden()
    colors = re.findall(r"#[0-9a-f]{6}", " ".join(texts(tab, "legendItem")))
    assert colors == ["#188038", "#9aa0a6", "#f9ab00"]  # 칸 색은 포인트 색(초록), 건너뜀 회색, 미룸 주황


def test_범례의_점_색은_귀퉁이_점과_같다(qapp):
    tab, _ = make_tab(qapp, [done(at(10, 7, 14))])
    colors = re.findall(r"#[0-9a-f]{6}", " ".join(texts(tab, "legendItem")))
    assert colors[1:] == [marker_color("skipped", "").name(), marker_color("snoozed", "").name()]


def test_스크린_타임_모드에서도_범례가_보인다(qapp):
    tab, _ = make_tab(qapp, entries=[(10, 7, 9, 600)])
    tab.set_mode(Mode.SCREEN_TIME)
    assert not tab._legend.isHidden()
    tab.set_mode(Mode.EXERCISE)
    assert not tab._legend.isHidden()


def test_기록이_없으면_점이_없다(qapp):
    tab, _ = make_tab(qapp)
    assert dots(tab) == []
