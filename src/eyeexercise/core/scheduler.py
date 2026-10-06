"""주기 알림 스케줄러. 스스로 타이머를 돌리지 않고, 호출자가 tick()을 주기적으로 부른다."""

from dataclasses import dataclass
from enum import Enum

from eyeexercise.core.clock import Clock
from eyeexercise.core.idle import IdleSource
from eyeexercise.core.settings import Settings

# tick 사이 간격이 이보다 크면 절전·최대 절전 등으로 끊긴 것으로 본다.
MAX_TICK_GAP_SECONDS = 10.0


class State(Enum):
    RUNNING = "running"  # 다음 알림까지 카운트다운 중
    DUE = "due"  # 알림 팝업이 떠 있음 (사용자가 응답할 때까지 유지)
    SNOOZED = "snoozed"  # 미루기 후 다시 알릴 때까지 카운트다운 중
    EXERCISING = "exercising"
    PAUSED = "paused"  # 사용자가 트레이에서 일시정지


_COUNTING = frozenset({State.RUNNING, State.SNOOZED})


@dataclass(frozen=True)
class ReminderDue:
    """알림을 띄울 때가 되었다."""


Event = ReminderDue


class InvalidTransition(RuntimeError):
    """현재 상태에서 할 수 없는 동작을 요청했다."""


class ReminderScheduler:
    def __init__(self, settings: Settings, clock: Clock, idle_source: IdleSource) -> None:
        self._settings = settings
        self._clock = clock
        self._idle = idle_source
        self._state = State.RUNNING
        self._paused_from: State | None = None
        self._elapsed = 0.0
        # 유휴로 누적이 멈춘(또는 리셋된) 상태인지. 복귀 직후 첫 tick 계산에 쓴다.
        self._idle_paused = False
        self._last_tick = clock.monotonic()

    # ---- 조회 ----

    @property
    def state(self) -> State:
        return self._state

    @property
    def elapsed_seconds(self) -> float:
        return self._elapsed

    @property
    def remaining_seconds(self) -> float | None:
        """다음 알림까지 남은 시간. 카운트다운 중이 아니면(알림·운동 중) None."""
        state = self._paused_from if self._state is State.PAUSED else self._state
        if state not in _COUNTING:
            return None
        return max(0.0, self._target_seconds(state) - self._elapsed)

    # ---- 시간 진행 ----

    def tick(self) -> list[Event]:
        now = self._clock.monotonic()
        dt = max(0.0, now - self._last_tick)
        self._last_tick = now

        if self._state not in _COUNTING:
            return []

        idle = self._idle.idle_seconds()
        gap = dt > MAX_TICK_GAP_SECONDS
        if gap:
            # 끊긴 구간 전체를 입력 없이 비운 시간으로 본다.
            idle = max(idle, dt)

        if idle >= self._settings.idle_reset_minutes * 60:
            self._state = State.RUNNING
            self._elapsed = 0.0
            self._idle_paused = True
            return []

        if idle >= self._settings.idle_pause_minutes * 60:
            if not self._idle_paused:
                self._idle_paused = True
                # 유휴 판정 전에 이미 누적된 유휴 구간은 되돌린다.
                self._elapsed = max(0.0, self._elapsed - max(0.0, idle - dt))
            return []

        if gap:
            counted = 0.0  # 끊긴 구간은 사용 시간이 아니다
        elif self._idle_paused:
            counted = min(dt, idle)  # 복귀 직후에는 마지막 입력 이후 시간만 센다
        else:
            counted = dt
        self._idle_paused = False
        self._elapsed += counted

        if self._elapsed >= self._target_seconds(self._state):
            self._state = State.DUE
            return [ReminderDue()]
        return []

    # ---- 사용자 동작 ----

    def snooze(self) -> None:
        self._require(State.DUE)
        self._state = State.SNOOZED
        self._elapsed = 0.0
        self._idle_paused = False

    def skip(self) -> None:
        self._require(State.DUE)
        self._restart()

    def start_exercise(self) -> None:
        self._require(State.DUE, State.RUNNING, State.SNOOZED)
        self._state = State.EXERCISING

    def finish_exercise(self) -> None:
        """운동을 끝냈거나 중단했다. 어느 쪽이든 타이머를 처음부터 다시 센다."""
        self._require(State.EXERCISING)
        self._restart()

    def pause(self) -> None:
        self._require(State.RUNNING, State.SNOOZED)
        self._paused_from = self._state
        self._state = State.PAUSED

    def resume(self) -> None:
        self._require(State.PAUSED)
        assert self._paused_from is not None
        self._state = self._paused_from
        self._paused_from = None
        self._idle_paused = False

    def apply_settings(self, settings: Settings) -> None:
        """설정 변경을 반영한다. 이미 누적된 시간은 유지한다."""
        self._settings = settings

    # ---- 내부 ----

    def _target_seconds(self, state: State) -> float:
        minutes = self._settings.snooze_minutes if state is State.SNOOZED else self._settings.interval_minutes
        return minutes * 60.0

    def _restart(self) -> None:
        self._state = State.RUNNING
        self._elapsed = 0.0
        self._idle_paused = False

    def _require(self, *allowed: State) -> None:
        if self._state not in allowed:
            names = "/".join(s.name for s in allowed)
            raise InvalidTransition(f"{self._state.name} 상태에서는 할 수 없다 (필요한 상태: {names})")
