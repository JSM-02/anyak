import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fakes import FakeClock, FakeIdle

from eyeexercise.core.usage import (
    HOURS,
    MAX_TICK_GAP_SECONDS,
    UsageLog,
    UsageTracker,
    usage_from_dict,
    usage_to_dict,
)
from eyeexercise.storage import json_store, paths

KST = timezone(timedelta(hours=9))
THRESHOLD = 60.0


def kst(*args):
    return datetime(*args, tzinfo=KST)


class Env:
    """FakeClock은 2026-10-06 09:00(KST)에서 시작한다. 1초씩 흘리며 사용 시간을 센다."""

    def __init__(self, save=None, flush_interval=60.0) -> None:
        self.clock = FakeClock()
        self.idle = FakeIdle()
        self.log = UsageLog()
        self.saved = []
        self.tracker = UsageTracker(
            self.log,
            self.clock,
            self.idle,
            lambda: THRESHOLD,
            save=save if save is not None else (lambda u: self.saved.append(u.days)),
            tz=KST,
            flush_interval=flush_interval,
        )
        self.tracker.tick()  # 첫 tick은 기준 시각만 잡는다

    def active(self, seconds):
        for _ in range(seconds):
            self.clock.advance(1)
            self.idle.value = 0
            self.tracker.tick()

    def away(self, seconds):
        for _ in range(seconds):
            self.clock.advance(1)
            self.idle.value += 1
            self.tracker.tick()


DAY = date(2026, 10, 6)


# ---- UsageLog ----


def test_시간대별로_더한다():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 5), 30)
    log.add(kst(2026, 10, 6, 9, 50), 45)
    log.add(kst(2026, 10, 6, 14, 0), 10)
    hourly = log.hourly(DAY)
    assert len(hourly) == HOURS and hourly[9] == 75 and hourly[14] == 10 and sum(hourly) == 85
    assert log.total(DAY) == 85


def test_기록이_없는_날은_모두_0():
    assert UsageLog().hourly(DAY) == [0.0] * 24
    assert UsageLog().total(DAY) == 0


def test_날짜별로_따로_쌓는다():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 23, 59), 20)
    log.add(kst(2026, 10, 7, 0, 1), 30)
    assert log.hourly(date(2026, 10, 6))[23] == 20 and log.hourly(date(2026, 10, 7))[0] == 30


def test_한_시간대는_3600초를_넘지_않는다():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 0), 3000)
    log.add(kst(2026, 10, 6, 9, 30), 3000)
    assert log.hourly(DAY)[9] == 3600


def test_0이하는_더하지_않는다():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 0), 0)
    log.add(kst(2026, 10, 6, 9, 0), -5)
    assert log.days == {}


def test_hourly가_돌려준_목록을_고쳐도_원본은_그대로():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 0), 10)
    log.hourly(DAY)[9] = 999
    log.days[DAY][9] = 999
    assert log.hourly(DAY)[9] == 10


# ---- 측정 ----


def test_입력이_있으면_사용_시간으로_센다():
    env = Env()
    env.active(30)
    assert env.log.total(DAY) == 30
    assert env.log.hourly(DAY)[9] == 30


def test_첫_tick은_세지_않는다():
    env = Env()
    assert env.log.total(DAY) == 0


def test_마지막_입력_뒤_59초까지는_사용_중이고_60초부터는_아니다():
    env = Env()
    env.active(10)
    env.away(59)  # idle 1~59초: 모두 사용 중
    assert env.log.total(DAY) == 10 + 59
    env.away(1)  # idle 60초
    assert env.log.total(DAY) == 10 + 59


def test_경계는_정확히_임계값_미만():
    env = Env()
    env.idle.value = THRESHOLD - 1
    env.clock.advance(1)
    env.tracker.tick()
    assert env.log.total(DAY) == 1  # idle 59초: 사용 중
    env.idle.value = THRESHOLD
    env.clock.advance(1)
    env.tracker.tick()
    assert env.log.total(DAY) == 1  # idle 60초: 사용 아님


def test_오래_비우면_그_시간은_세지_않는다():
    env = Env()
    env.active(20)
    env.away(300)
    env.active(10)
    assert env.log.total(DAY) == 20 + 59 + 10  # 비운 5분 중 1분 미만(59초)만 센다


def test_임계값이_바뀌면_바로_반영된다():
    threshold = [60.0]
    clock, idle = FakeClock(), FakeIdle()
    tracker = UsageTracker(UsageLog(), clock, idle, lambda: threshold[0], tz=KST)
    tracker.tick()
    idle.value = 90
    clock.advance(1)
    tracker.tick()
    assert tracker.usage.total(DAY) == 0
    threshold[0] = 120.0
    clock.advance(1)
    tracker.tick()
    assert tracker.usage.total(DAY) == 1


def test_절전처럼_오래_건너뛴_구간은_세지_않는다():
    env = Env()
    env.active(5)
    env.clock.advance(MAX_TICK_GAP_SECONDS + 1)  # tick이 한참 멈췄다가 재개
    env.idle.value = 0
    env.tracker.tick()
    assert env.log.total(DAY) == 5
    env.active(3)  # 이후에는 다시 센다
    assert env.log.total(DAY) == 8


def test_건너뛴_구간이_정확히_한계이면_센다():
    env = Env()
    env.clock.advance(MAX_TICK_GAP_SECONDS)
    env.idle.value = 0
    env.tracker.tick()
    assert env.log.total(DAY) == MAX_TICK_GAP_SECONDS


def test_시간대를_넘어가면_다음_시간대에_쌓인다():
    env = Env()
    env.clock.advance(3600 - 5)  # 09:59:55
    env.tracker.tick()  # 큰 점프라 세지 않는다
    env.active(10)  # 09:59:56 ~ 10:00:05
    hourly = env.log.hourly(DAY)
    assert hourly[9] == 4 and hourly[10] == 6  # 09:59:56~59 → 4초, 10:00:00~05 → 6초
    assert env.log.total(DAY) == 10


def test_자정을_넘어가면_다음_날에_쌓인다():
    env = Env()
    env.clock.advance(15 * 3600 - 3)  # 23:59:57
    env.tracker.tick()
    env.active(6)  # 구간은 끝나는 시각의 시간대에 쌓는다: :58, :59 → 첫날 2초, 00:00:00~:03 → 다음 날 4초
    assert env.log.hourly(DAY)[23] == 2
    assert env.log.hourly(date(2026, 10, 7))[0] == 4
    assert env.log.total(DAY) + env.log.total(date(2026, 10, 7)) == 6


# ---- 저장 ----


def test_일정_간격마다_저장한다():
    env = Env(flush_interval=10)
    env.active(9)
    assert env.saved == []
    env.active(1)
    assert len(env.saved) == 1
    env.active(5)
    assert len(env.saved) == 1  # 간격이 아직 안 됐다
    env.active(5)
    assert len(env.saved) == 2


def test_사용이_없으면_저장하지_않는다():
    env = Env(flush_interval=5)
    env.away(100)  # 입력이 없어서 새로 쌓인 것이 거의 없다 (처음 59초는 사용으로 센다)
    saved_during_away = len(env.saved)
    env.saved.clear()
    env.away(100)
    assert env.saved == [] and saved_during_away >= 1


def test_flush는_변경이_있을_때만_저장한다():
    env = Env()
    env.tracker.flush()
    assert env.saved == []
    env.active(3)
    env.tracker.flush()
    assert len(env.saved) == 1
    env.tracker.flush()
    assert len(env.saved) == 1  # 다시 바뀌기 전에는 저장하지 않는다


def test_저장이_실패해도_측정은_계속하고_다음에_다시_저장한다(caplog):
    fail = [True]
    calls = []

    def save(usage):
        calls.append(1)
        if fail[0]:
            raise OSError("디스크 오류")

    env = Env(save=save, flush_interval=1)
    with caplog.at_level(logging.WARNING):
        env.active(3)
    assert "스크린 타임 저장에 실패" in caplog.text
    assert env.log.total(DAY) == 3
    fail[0] = False
    n = len(calls)
    env.active(2)
    assert len(calls) > n and env.log.total(DAY) == 5
    env.saved.clear()
    env.tracker.flush()
    assert env.saved == []  # 성공했으니 더 저장할 것이 없다


def test_저장_콜백이_없어도_동작한다():
    clock, idle = FakeClock(), FakeIdle()
    tracker = UsageTracker(UsageLog(), clock, idle, lambda: 60.0, save=None, tz=KST, flush_interval=1)
    tracker.tick()
    clock.advance(1)
    tracker.tick()
    tracker.flush()
    assert tracker.usage.total(DAY) == 1


# ---- dict 변환과 파일 ----


def test_dict_변환_왕복():
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 0), 125.46)
    log.add(kst(2026, 10, 7, 23, 0), 3600)
    data = usage_to_dict(log)
    assert data["version"] == 1 and list(data["days"]) == ["2026-10-06", "2026-10-07"]
    assert data["days"]["2026-10-06"][9] == 125.5
    restored = usage_from_dict(data)
    assert restored.hourly(date(2026, 10, 6))[9] == 125.5
    assert restored.hourly(date(2026, 10, 7))[23] == 3600


def test_깨진_날은_건너뛰고_나머지는_살린다():
    data = {
        "days": {
            "2026-10-06": [10] + [0] * 23,
            "날짜아님": [0] * 24,
            "2026-10-07": [0] * 5,  # 길이가 24가 아니다
            "2026-10-08": ["a"] + [0] * 23,
            "2026-10-09": [True] + [0] * 23,
            "2026-10-10": "문자열",
        }
    }
    assert list(usage_from_dict(data).days) == [date(2026, 10, 6)]


def test_범위를_벗어난_값은_보정한다():
    data = {"days": {"2026-10-06": [-5, 99999] + [0] * 22}}
    hourly = usage_from_dict(data).hourly(DAY)
    assert hourly[0] == 0 and hourly[1] == 3600


def test_아주_큰_수나_NaN_무한대도_보정한다():
    huge = 10**400
    data = {"days": {"2026-10-06": [huge, -huge, float("nan"), float("inf"), float("-inf")] + [0] * 19}}
    hourly = usage_from_dict(data).hourly(DAY)
    assert hourly[:5] == [3600, 0, 0, 3600, 0]
    usage_to_dict(usage_from_dict(data))  # 저장용 변환도 예외가 없다


def test_구조가_잘못되면_빈_기록():
    for bad in (None, {}, {"days": []}, [1, 2], "x"):
        assert usage_from_dict(bad).days == {}


def test_모르는_키는_무시한다():
    log = usage_from_dict({"version": 1, "extra": 1, "days": {"2026-10-06": [1] + [0] * 23, "x": 0}})
    assert log.total(DAY) == 1


def test_파일에_저장_후_다시_읽기(tmp_path):
    path = paths.usage_path(tmp_path)
    assert path.name == "usage.json"
    log = UsageLog()
    log.add(kst(2026, 10, 6, 9, 0), 100)
    json_store.save_usage(path, log)
    assert json_store.load_usage(path).hourly(DAY)[9] == 100


def test_파일이_없으면_빈_기록(tmp_path):
    assert json_store.load_usage(tmp_path / "usage.json").days == {}


def test_손상된_파일은_백업하고_빈_기록으로_시작한다(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("{깨진 json", encoding="utf-8")
    assert json_store.load_usage(path, now=lambda: datetime(2026, 10, 7, 12, 0, 0)).days == {}
    assert (tmp_path / "usage.corrupt-20261007-120000.json").exists()


def test_추적기와_파일_저장소_연결(tmp_path):
    path = tmp_path / "usage.json"
    clock, idle = FakeClock(), FakeIdle()
    tracker = UsageTracker(UsageLog(), clock, idle, lambda: 60.0, save=lambda u: json_store.save_usage(path, u), tz=KST)
    tracker.tick()
    for _ in range(5):
        clock.advance(1)
        tracker.tick()
    tracker.flush()
    assert json_store.load_usage(path).total(DAY) == pytest.approx(5)
