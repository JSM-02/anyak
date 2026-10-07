"""스케줄러와 UI를 잇는 컨트롤러. 1초마다 tick()을 부르고 결과를 Qt 시그널로 알린다."""

import logging
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.history import History
from eyeexercise.core.scheduler import InvalidTransition, ReminderDue, ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.core.usage import UsageTracker

log = logging.getLogger(__name__)

TICK_INTERVAL_MS = 1000


class Controller(QObject):
    state_changed = Signal(object)  # State
    reminder_due = Signal()
    exercise_started = Signal()
    ticked = Signal()
    history_changed = Signal()  # 기록이 추가됐다 (기록 화면을 새로 그린다)

    def __init__(
        self,
        scheduler: ReminderScheduler,
        history: History | None = None,
        now: Callable[[], datetime] = SystemClock().now,
        usage_tracker: UsageTracker | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scheduler = scheduler
        self._history = history
        self._usage = usage_tracker
        self._now = now
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    @property
    def state(self) -> State:
        return self._scheduler.state

    @property
    def remaining_seconds(self) -> float | None:
        return self._scheduler.remaining_seconds

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.flush_usage()

    def apply_settings(self, settings: Settings) -> None:
        """바뀐 설정을 스케줄러에 전달한다. 이미 센 시간은 유지하고 다음 알림부터 새 주기가 적용된다."""
        self._scheduler.apply_settings(settings)

    def flush_usage(self) -> None:
        """스크린 타임의 마지막 구간까지 저장한다. 앱을 끝낼 때 부른다."""
        if self._usage is not None:
            self._usage.flush()

    # ---- 사용자 동작 ----

    def snooze(self) -> None:
        if self._run(self._scheduler.snooze) and self._history:
            self._history.record_snoozed(self._now())
            self.history_changed.emit()

    def skip(self) -> None:
        if self._run(self._scheduler.skip) and self._history:
            self._history.record_skipped(self._now())
            self.history_changed.emit()

    def start_exercise(self) -> None:
        if self._run(self._scheduler.start_exercise):
            self.exercise_started.emit()

    def complete_exercise(self, exercise: str, duration_seconds: int) -> None:
        """운동을 끝까지 마쳤다. 기록을 남기고 타이머를 처음부터 다시 센다."""
        if self._run(self._scheduler.finish_exercise) and self._history:
            self._history.record_completed(self._now(), exercise, duration_seconds)
            self.history_changed.emit()

    def abort_exercise(self) -> None:
        """운동을 중단했다. 기록은 남기지 않고 타이머만 처음부터 다시 센다."""
        self._run(self._scheduler.finish_exercise)

    def pause(self) -> None:
        self._run(self._scheduler.pause)

    def resume(self) -> None:
        self._run(self._scheduler.resume)

    # ---- 내부 ----

    def _on_tick(self) -> None:
        if self._usage is not None:
            self._usage.tick()
        before = self._scheduler.state
        events = self._scheduler.tick()
        self._notify_state(before)
        for event in events:
            if isinstance(event, ReminderDue):
                self.reminder_due.emit()
        self.ticked.emit()

    def _run(self, action) -> bool:
        """스케줄러 동작을 실행한다. 현재 상태에서 불가능한 요청은 기록만 하고 무시한다."""
        before = self._scheduler.state
        try:
            action()
        except InvalidTransition as e:
            log.warning("무시한 요청: %s", e)
            return False
        self._notify_state(before)
        return True

    def _notify_state(self, before: State) -> None:
        after = self._scheduler.state
        if after is not before:
            self.state_changed.emit(after)
