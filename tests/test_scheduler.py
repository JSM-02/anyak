import dataclasses

import pytest
from fakes import FakeClock, FakeIdle

from eyeexercise.core.scheduler import InvalidTransition, ReminderDue, ReminderScheduler, State
from eyeexercise.core.settings import Settings

# 기본 설정: 알림 20분(1200초), 미루기 5분(300초), 유휴 누적 정지 1분(60초), 리셋 5분(300초)


class Env:
    """1초 단위로 시간을 흘려보내며 스케줄러를 검증하는 도우미."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.clock = FakeClock()
        self.idle = FakeIdle()
        self.sched = ReminderScheduler(settings or Settings(), self.clock, self.idle)
        self.events: list = []

    def active(self, seconds: int) -> None:
        """사용자가 계속 입력하는 상태로 시간을 보낸다."""
        for _ in range(seconds):
            self.clock.advance(1)
            self.idle.value = 0
            self.events += self.sched.tick()

    def away(self, seconds: int) -> None:
        """입력을 멈춘다. 유휴 시간이 1초씩 늘어난다."""
        for _ in range(seconds):
            self.clock.advance(1)
            self.idle.value += 1
            self.events += self.sched.tick()

    def due_count(self) -> int:
        return sum(isinstance(e, ReminderDue) for e in self.events)


@pytest.fixture
def env() -> Env:
    return Env()


# ---- 기본 알림 ----


def test_처음에는_RUNNING이고_남은_시간은_interval(env):
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 1200


def test_20분이_되면_DUE가_되고_이벤트가_한_번_나온다(env):
    env.active(1199)
    assert env.sched.state is State.RUNNING
    assert env.due_count() == 0

    env.active(1)
    assert env.sched.state is State.DUE
    assert env.due_count() == 1


def test_DUE_중에는_이벤트가_반복되지_않고_상태가_유지된다(env):
    env.active(1200)
    env.active(600)
    assert env.sched.state is State.DUE
    assert env.due_count() == 1
    assert env.sched.remaining_seconds is None


# ---- 미루기 / 건너뛰기 / 운동 ----


def test_미루기_후_5분이_지나면_다시_DUE(env):
    env.active(1200)
    env.sched.snooze()
    assert env.sched.state is State.SNOOZED
    assert env.sched.remaining_seconds == 300

    env.active(299)
    assert env.sched.state is State.SNOOZED
    env.active(1)
    assert env.sched.state is State.DUE
    assert env.due_count() == 2


def test_건너뛰기는_타이머를_처음부터_다시_센다(env):
    env.active(1200)
    env.sched.skip()
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 1200

    env.active(1200)
    assert env.due_count() == 2


def test_운동_시작과_종료(env):
    env.active(1200)
    env.sched.start_exercise()
    assert env.sched.state is State.EXERCISING

    env.active(600)  # 운동 중에는 시간이 흘러도 이벤트가 없다
    assert env.sched.state is State.EXERCISING
    assert env.due_count() == 1

    env.sched.finish_exercise()
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 1200


def test_알림_없이도_지금_운동을_시작할_수_있다(env):
    env.active(100)
    env.sched.start_exercise()
    assert env.sched.state is State.EXERCISING


# ---- 일시정지 ----


def test_일시정지_중에는_진행하지_않고_재개하면_이어서_센다(env):
    env.active(600)
    env.sched.pause()
    assert env.sched.state is State.PAUSED

    env.active(2000)
    assert env.sched.state is State.PAUSED
    assert env.due_count() == 0

    env.sched.resume()
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 600
    env.active(600)
    assert env.sched.state is State.DUE


def test_미루기_대기_중_일시정지하고_재개하면_SNOOZED로_돌아온다(env):
    env.active(1200)
    env.sched.snooze()
    env.active(100)
    env.sched.pause()
    assert env.sched.remaining_seconds == 200
    env.sched.resume()
    assert env.sched.state is State.SNOOZED
    assert env.sched.remaining_seconds == 200


def test_일시정지_중에는_유휴시간이_길어도_영향이_없다(env):
    env.active(600)
    env.sched.pause()
    env.away(400)
    assert env.sched.state is State.PAUSED
    assert env.sched.elapsed_seconds == 600


# ---- 유휴 시간 규칙 ----


def test_유휴_59초는_정상_누적된다(env):
    env.active(100)
    env.away(59)
    assert env.sched.elapsed_seconds == 159


def test_유휴_1분이_되면_누적이_멈추고_유휴_구간은_제외된다(env):
    env.active(100)
    env.away(60)
    assert env.sched.elapsed_seconds == 100  # 유휴였던 60초는 빠진다

    env.away(120)
    assert env.sched.elapsed_seconds == 100  # 계속 멈춰 있다
    assert env.sched.state is State.RUNNING


def test_유휴에서_복귀하면_멈춘_지점부터_이어서_센다(env):
    env.active(100)
    env.away(240)
    env.active(10)
    # 복귀한 첫 tick은 마지막 입력 이후 0초이므로 세지 않는다
    assert env.sched.elapsed_seconds == 109


def test_유휴_4분59초는_리셋하지_않는다(env):
    env.active(100)
    env.away(299)
    assert env.sched.elapsed_seconds == 100
    assert env.sched.state is State.RUNNING


def test_유휴_5분이면_리셋한다(env):
    env.active(100)
    env.away(300)
    assert env.sched.elapsed_seconds == 0
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 1200


def test_리셋_후_복귀하면_처음부터_센다(env):
    env.active(100)
    env.away(400)
    env.active(10)
    assert env.sched.elapsed_seconds == 9


def test_미루기_대기_중_유휴_1분이면_대기_시간도_멈춘다(env):
    env.active(1200)
    env.sched.snooze()
    env.active(100)
    env.away(120)
    assert env.sched.state is State.SNOOZED
    assert env.sched.elapsed_seconds == 100


def test_미루기_대기_중_유휴_5분이면_미루기를_취소하고_RUNNING으로_리셋한다(env):
    env.active(1200)
    env.sched.snooze()
    env.active(100)
    env.away(300)
    assert env.sched.state is State.RUNNING
    assert env.sched.remaining_seconds == 1200
    assert env.due_count() == 1  # 다시 알리지 않는다


def test_DUE_중에는_유휴가_길어도_팝업을_유지한다(env):
    env.active(1200)
    env.away(1000)
    assert env.sched.state is State.DUE
    assert env.due_count() == 1


# ---- 절전 등으로 tick이 끊긴 경우 ----


def test_절전으로_길게_끊기면_리셋한다(env):
    env.active(100)
    env.clock.advance(3600)  # tick 없이 1시간이 흐름
    env.idle.value = 0  # 키를 눌러 깨움
    env.events += env.sched.tick()
    assert env.sched.state is State.RUNNING
    assert env.sched.elapsed_seconds == 0


def test_짧게_끊긴_구간은_사용_시간으로_세지_않는다(env):
    env.active(100)
    env.clock.advance(30)  # 10초 초과, 유휴 기준(60초) 미만
    env.events += env.sched.tick()
    assert env.sched.elapsed_seconds == 100
    env.active(5)
    assert env.sched.elapsed_seconds == 105


def test_끊긴_구간이_1분을_넘으면_누적_정지로_처리한다(env):
    env.active(100)
    env.clock.advance(100)
    env.events += env.sched.tick()
    assert env.sched.elapsed_seconds == 100
    assert env.sched.state is State.RUNNING


def test_DUE_중에_절전해도_DUE를_유지한다(env):
    env.active(1200)
    env.clock.advance(3600)
    env.events += env.sched.tick()
    assert env.sched.state is State.DUE
    assert env.due_count() == 1


# ---- 설정 변경 ----


def test_interval을_줄이면_누적된_시간_기준으로_바로_반영된다(env):
    env.active(700)
    env.sched.apply_settings(dataclasses.replace(Settings(), interval_minutes=10))
    assert env.sched.remaining_seconds == 0
    env.active(1)
    assert env.sched.state is State.DUE


def test_interval을_늘리면_남은_시간이_늘어난다(env):
    env.active(600)
    env.sched.apply_settings(dataclasses.replace(Settings(), interval_minutes=30))
    assert env.sched.remaining_seconds == 1200


def test_유휴_기준_변경이_반영된다(env):
    env.sched.apply_settings(
        dataclasses.replace(Settings(), idle_pause_minutes=2, idle_reset_minutes=3)
    )
    env.active(100)
    env.away(119)
    assert env.sched.elapsed_seconds == 219  # 2분 전까지는 정상 누적
    env.away(1)
    assert env.sched.elapsed_seconds == 100  # 2분이 되면 정지
    env.away(60)
    assert env.sched.elapsed_seconds == 0  # 3분이면 리셋


# ---- 잘못된 요청 ----


@pytest.mark.parametrize(
    "action",
    ["snooze", "skip", "finish_exercise", "resume"],
)
def test_RUNNING_상태에서_할_수_없는_동작은_예외(env, action):
    with pytest.raises(InvalidTransition):
        getattr(env.sched, action)()


def test_DUE_상태에서는_일시정지할_수_없다(env):
    env.active(1200)
    with pytest.raises(InvalidTransition):
        env.sched.pause()


def test_일시정지_중에는_운동을_시작할_수_없다(env):
    env.sched.pause()
    with pytest.raises(InvalidTransition):
        env.sched.start_exercise()
