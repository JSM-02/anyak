"""앱 조립 지점. 모든 모듈을 여기서 연결한다."""

import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.storage import json_store, paths
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.icons import app_icon
from eyeexercise.ui.reminder_popup import ReminderPopup
from eyeexercise.ui.tray import TrayIcon

log = logging.getLogger(__name__)


class _NoIdle:
    """임시 유휴 소스: 항상 방금 입력한 것으로 본다. 3b단계에서 Win32 구현으로 교체한다."""

    def idle_seconds(self) -> float:
        return 0.0


class TrayApp:
    def __init__(self, app: QApplication, settings: Settings) -> None:
        scheduler = ReminderScheduler(settings, SystemClock(), _NoIdle())
        self.controller = Controller(scheduler)
        self.popup = ReminderPopup(settings.snooze_minutes)
        self.tray = TrayIcon(self.controller, app_icon())

        self.controller.reminder_due.connect(self.popup.show_at_corner)
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.exercise_started.connect(self._on_exercise_started)

        self.popup.start_clicked.connect(self.controller.start_exercise)
        self.popup.snooze_clicked.connect(self.controller.snooze)
        self.popup.skip_clicked.connect(self.controller.skip)

        self.tray.quit_requested.connect(self.quit)
        self._app = app

    def start(self) -> None:
        self.tray.show()
        self.controller.start()

    def _on_state_changed(self, state: State) -> None:
        # 버튼이든 트레이 메뉴든, 알림 상태를 벗어나면 팝업을 닫는다.
        if state is not State.DUE:
            self.popup.hide()

    def _on_exercise_started(self) -> None:
        # 임시 동작: 운동 화면은 5단계에서 추가한다. 지금은 바로 끝난 것으로 처리한다.
        self.tray.show_message("눈 운동 화면은 아직 준비 중이에요. 타이머를 다시 시작합니다.")
        self.controller.finish_exercise()

    def quit(self) -> None:
        self.controller.stop()
        self.popup.hide()
        self.tray.hide()
        self._app.quit()


def _load_settings() -> Settings:
    path = paths.settings_path()
    settings = json_store.load_settings(path)
    if not path.exists():
        json_store.save_settings(path, settings)  # 직접 편집할 수 있도록 기본 파일을 만들어 둔다
    return settings


def _install_sigint_handler(tray_app: TrayApp) -> QTimer:
    """터미널의 Ctrl+C로 traceback 없이 정상 종료한다.

    Qt 이벤트 루프가 도는 동안에는 파이썬 시그널 핸들러가 실행되지 않으므로,
    빈 타이머로 주기적으로 인터프리터를 깨운다. 반환된 타이머는 참조를 유지해야 한다.
    """
    signal.signal(signal.SIGINT, lambda *_: tray_app.quit())
    wakeup = QTimer()
    wakeup.setInterval(200)
    wakeup.timeout.connect(lambda: None)
    wakeup.start()
    return wakeup


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("EyeExercise")
    app.setQuitOnLastWindowClosed(False)  # 트레이 상주 앱: 창이 없어도 종료하지 않는다
    app.setWindowIcon(app_icon())

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("시스템 트레이를 사용할 수 없어 종료합니다.")
        return 1

    tray_app = TrayApp(app, _load_settings())
    tray_app.start()
    sigint_wakeup = _install_sigint_handler(tray_app)  # noqa: F841 (참조 유지용)
    return app.exec()
