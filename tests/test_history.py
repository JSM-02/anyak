import logging
from datetime import date, datetime, timedelta, timezone

from fakes import FakeClock, FakeIdle

from eyeexercise.core.history import (
    History,
    HistoryEvent,
    history_from_dict,
    history_to_dict,
    summarize_by_day,
)
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.storage import json_store

KST = timezone(timedelta(hours=9))


def kst(*args) -> datetime:
    return datetime(*args, tzinfo=KST)


def test_이벤트_추가와_종류별_기록():
    h = History()
    h.record_completed(kst(2026, 10, 6, 14, 20), "blink", 30)
    h.record_snoozed(kst(2026, 10, 6, 14, 40))
    h.record_skipped(kst(2026, 10, 6, 14, 45))
    assert [e.type for e in h.events] == ["completed", "snoozed", "skipped"]
    assert h.events[0].exercise == "blink" and h.events[0].duration_seconds == 30


def test_일별_집계():
    h = History()
    h.record_completed(kst(2026, 10, 6, 10, 0), "blink", 30)
    h.record_completed(kst(2026, 10, 6, 11, 0), "dot_follow", 60)
    h.record_skipped(kst(2026, 10, 6, 12, 0))
    h.record_snoozed(kst(2026, 10, 6, 13, 0))
    h.record_snoozed(kst(2026, 10, 7, 9, 0))
    days = h.summarize(KST)
    assert days[date(2026, 10, 6)].completed == 2
    assert days[date(2026, 10, 6)].exercise_seconds == 90
    assert days[date(2026, 10, 6)].skipped == 1
    assert days[date(2026, 10, 6)].snoozed == 1
    assert days[date(2026, 10, 7)].snoozed == 1
    assert days[date(2026, 10, 7)].completed == 0


def test_자정_경계는_로컬_날짜로_나눈다():
    events = [
        HistoryEvent(kst(2026, 10, 6, 23, 59), "skipped"),
        HistoryEvent(kst(2026, 10, 7, 0, 1), "skipped"),
    ]
    days = summarize_by_day(events, KST)
    assert days[date(2026, 10, 6)].skipped == 1
    assert days[date(2026, 10, 7)].skipped == 1


def test_다른_시간대로_저장된_이벤트도_로컬_날짜로_센다():
    # UTC 15:30은 KST로 다음 날 00:30
    utc_event = HistoryEvent(datetime(2026, 10, 6, 15, 30, tzinfo=timezone.utc), "skipped")
    assert date(2026, 10, 7) in summarize_by_day([utc_event], KST)


def test_빈_기록의_집계는_빈_dict():
    assert History().summarize(KST) == {}


def test_저장_콜백이_추가할_때마다_호출된다():
    saved = []
    h = History(save=lambda events: saved.append(list(events)))
    h.record_skipped(kst(2026, 10, 6, 9, 0))
    h.record_snoozed(kst(2026, 10, 6, 9, 5))
    assert [len(s) for s in saved] == [1, 2]


def test_저장이_실패해도_예외를_내지_않고_메모리에는_남는다(caplog):
    def fail(_events):
        raise OSError("디스크 오류")

    h = History(save=fail)
    with caplog.at_level(logging.WARNING):
        h.record_skipped(kst(2026, 10, 6, 9, 0))
    assert len(h.events) == 1
    assert "기록 저장에 실패" in caplog.text


def test_dict_변환_왕복():
    events = [
        HistoryEvent(kst(2026, 10, 6, 14, 20, 5), "completed", "blink", 30),
        HistoryEvent(kst(2026, 10, 6, 14, 40, 10), "snoozed"),
    ]
    data = history_to_dict(events)
    assert data["version"] == 1
    assert data["events"][0]["ts"] == "2026-10-06T14:20:05+09:00"
    assert "exercise" not in data["events"][1]
    assert history_from_dict(data) == events


def test_잘못된_이벤트는_건너뛰고_나머지는_살린다():
    data = {
        "events": [
            {"ts": "2026-10-06T14:20:05+09:00", "type": "skipped"},
            {"ts": "날짜아님", "type": "skipped"},
            {"ts": "2026-10-06T14:20:05+09:00", "type": "모르는종류"},
            "문자열",
            {"type": "skipped"},
            {"ts": "2026-10-06T15:00:00+09:00", "type": "completed", "exercise": 5, "duration_seconds": -3},
        ]
    }
    events = history_from_dict(data)
    assert [e.type for e in events] == ["skipped", "completed"]
    assert events[1].exercise is None and events[1].duration_seconds is None


def test_events가_없거나_잘못된_구조면_빈_목록():
    assert history_from_dict(None) == []
    assert history_from_dict({}) == []
    assert history_from_dict({"events": "x"}) == []


def test_시간대_없는_시각은_로컬로_해석한다():
    events = history_from_dict({"events": [{"ts": "2026-10-06T14:20:05", "type": "skipped"}]})
    assert events[0].ts.tzinfo is not None


# ---- 저장소 ----


def test_기록_저장_후_다시_읽기(tmp_path):
    path = tmp_path / "history.json"
    events = [HistoryEvent(kst(2026, 10, 6, 14, 20, 5), "completed", "blink", 30)]
    json_store.save_history(path, events)
    assert json_store.load_history(path) == events


def test_기록_파일이_없으면_빈_목록(tmp_path):
    assert json_store.load_history(tmp_path / "history.json") == []


def test_손상된_기록_파일은_백업하고_빈_목록으로_시작한다(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{깨진 json", encoding="utf-8")
    assert json_store.load_history(path, now=lambda: datetime(2026, 10, 6, 14, 20, 5)) == []
    assert (tmp_path / "history.corrupt-20261006-142005.json").exists()


# ---- 컨트롤러 연결 ----


def _due_controller(qapp, history):
    from eyeexercise.ui.controller import Controller

    clock, idle = FakeClock(), FakeIdle()
    sched = ReminderScheduler(Settings(), clock, idle)
    controller = Controller(sched, history, now=clock.now)
    for _ in range(1200):  # 1초씩 흘려 DUE로 만든다 (큰 점프는 절전으로 처리된다)
        clock.advance(1)
        controller._on_tick()
    assert controller.state is State.DUE
    return controller


def test_컨트롤러가_미루기를_기록한다(qapp):
    h = History()
    c = _due_controller(qapp, h)
    c.snooze()
    assert [e.type for e in h.events] == ["snoozed"]


def test_컨트롤러가_건너뛰기를_기록한다(qapp):
    h = History()
    c = _due_controller(qapp, h)
    c.skip()
    assert [e.type for e in h.events] == ["skipped"]


def test_불가능한_요청은_기록하지_않는다(qapp):
    h = History()
    c = _due_controller(qapp, h)
    c.skip()
    c.skip()  # 이미 RUNNING이라 무시된다
    assert len(h.events) == 1


# ---- 마지막으로 완료한 운동 (운동을 번갈아 고를 때 쓴다) ----


def test_완료한_운동이_없으면_None():
    assert History().last_completed_exercise() is None
    h = History()
    h.record_skipped(kst(2026, 10, 6, 9, 0))
    h.record_snoozed(kst(2026, 10, 6, 9, 5))
    assert h.last_completed_exercise() is None  # 건너뛰거나 미룬 것은 운동으로 치지 않는다


def test_가장_최근에_완료한_운동을_돌려준다():
    h = History()
    h.record_completed(kst(2026, 10, 6, 9, 0), "blink", 66)
    h.record_completed(kst(2026, 10, 6, 10, 0), "dot_follow", 60)
    h.record_skipped(kst(2026, 10, 6, 11, 0))
    assert h.last_completed_exercise() == "dot_follow"


def test_기록_순서가_아니라_시각이_가장_늦은_것을_기준으로_한다():
    h = History(
        [
            HistoryEvent(kst(2026, 10, 6, 12, 0), "completed", "dot_follow", 60),
            HistoryEvent(kst(2026, 10, 6, 9, 0), "completed", "blink", 66),
        ]
    )
    assert h.last_completed_exercise() == "dot_follow"
