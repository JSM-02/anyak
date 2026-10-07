"""앱 조립 지점. 모든 모듈을 여기서 연결한다."""

import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.exercises import build_timeline, enabled_exercises, next_exercise
from eyeexercise.core.history import History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.usage import UsageTracker
from eyeexercise.core.vision import VisionLog
from eyeexercise.platform.win_idle import WinIdleSource
from eyeexercise.platform.win_window import allow_any_process_to_set_foreground, set_app_user_model_id
from eyeexercise.storage import json_store, paths
from eyeexercise.ui import theme
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.exercise_window import ExerciseWindow
from eyeexercise.ui.icons import app_icon
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.reminder_popup import ReminderPopup
from eyeexercise.ui.single_instance import SingleInstance
from eyeexercise.ui.speech import create_speaker
from eyeexercise.ui.tray import TrayIcon

log = logging.getLogger(__name__)


class TrayApp:
    def __init__(self, app: QApplication, settings: Settings) -> None:
        self._app = app
        self._settings = settings
        theme.set_mode(settings.appearance)  # 창을 만들기 전에 정해야 처음부터 맞는 색으로 뜬다
        self._hide_hint_shown = False

        clock, idle = SystemClock(), WinIdleSource()
        scheduler = ReminderScheduler(settings, clock, idle)
        history_file = paths.history_path()
        self.history = History(
            json_store.load_history(history_file),
            save=lambda events: json_store.save_history(history_file, events),
        )
        usage_file = paths.usage_path()
        self.usage = json_store.load_usage(usage_file)
        usage_tracker = UsageTracker(
            self.usage,
            clock,
            idle,
            lambda: self._settings.idle_pause_minutes * 60,  # 알림 타이머가 "자리 비움"으로 보는 기준과 같다. 설정이 바뀌면 바로 따라간다
            save=lambda usage: json_store.save_usage(usage_file, usage),
        )
        self.controller = Controller(scheduler, self.history, usage_tracker=usage_tracker)
        app.aboutToQuit.connect(self.controller.flush_usage)  # 로그오프·종료 때도 마지막 구간을 저장한다
        self.popup = ReminderPopup(settings.snooze_minutes)
        self.exercise_window = ExerciseWindow(create_speaker(settings.sound.enabled))
        settings_file = paths.settings_path()
        self.settings_manager = SettingsManager(settings, save=lambda s: json_store.save_settings(settings_file, s))
        self.settings_manager.subscribe(self._on_settings_changed)
        vision_file = paths.vision_path()
        self.vision_log = VisionLog(
            json_store.load_vision(vision_file),
            save=lambda records: json_store.save_vision(vision_file, records),
        )
        self.main_window = MainWindow(
            self.history, usage=self.usage, settings_manager=self.settings_manager, vision_log=self.vision_log
        )
        self.tray = TrayIcon(self.controller, app_icon())

        self.controller.reminder_due.connect(self.popup.show_at_corner)
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.history_changed.connect(self.main_window.records_tab.refresh)
        self.controller.exercise_started.connect(self._on_exercise_started)

        self.exercise_window.completed.connect(self.controller.complete_exercise)
        self.exercise_window.aborted.connect(self.controller.abort_exercise)

        self.popup.start_clicked.connect(self.controller.start_exercise)
        self.popup.snooze_clicked.connect(self.controller.snooze)
        self.popup.skip_clicked.connect(self.controller.skip)

        self.main_window.hidden_to_tray.connect(self._on_hidden_to_tray)
        self.tray.open_requested.connect(self.show_main_window)
        self.tray.quit_requested.connect(self.quit)

    def start(self) -> None:
        self.tray.show()
        self.controller.start()
        if self._settings.show_main_window_on_start:
            self.show_main_window()

    def show_main_window(self) -> None:
        self.main_window.show_and_raise()

    def quit(self) -> None:
        self.main_window.prepare_to_quit()
        self.controller.stop()
        self.popup.hide()
        self.exercise_window.hide()
        self.tray.hide()
        self._app.quit()

    def _on_settings_changed(self, new: Settings, old: Settings) -> None:
        """설정 화면에서 값을 바꾸면 실행 중인 부분에 바로 반영한다."""
        self._settings = new  # 운동 선택·시간, 스크린 타임 기준 등은 이 값을 그때그때 읽는다
        self.controller.apply_settings(new)
        if new.snooze_minutes != old.snooze_minutes:
            self.popup.set_snooze_minutes(new.snooze_minutes)
        if new.appearance != old.appearance:
            theme.set_mode(new.appearance)
        if new.sound.enabled != old.sound.enabled:
            self.exercise_window.set_speaker(create_speaker(new.sound.enabled))

    def _on_state_changed(self, state: State) -> None:
        # 버튼이든 트레이 메뉴든, 알림 상태를 벗어나면 팝업을 닫는다.
        if state is not State.DUE:
            self.popup.hide()

    def _on_exercise_started(self) -> None:
        # 켜진 운동을 번갈아 진행한다. 마지막으로 마친 운동의 다음 것을 고른다.
        exercises = self._settings.exercises
        choice = next_exercise(enabled_exercises(exercises), self.history.last_completed_exercise())
        if choice is None:
            self.tray.show_message("사용할 수 있는 운동이 없어요. 설정에서 운동을 하나 이상 켜 주세요.")
            self.controller.abort_exercise()
            return
        self.exercise_window.start(build_timeline(choice, exercises))

    def _on_hidden_to_tray(self) -> None:
        # 창이 사라져서 당황하지 않도록, 실행 중 처음 한 번만 알려준다.
        if not self._hide_hint_shown:
            self._hide_hint_shown = True
            self.tray.show_message("창을 닫아도 트레이에서 계속 실행돼요. 종료는 트레이 메뉴에서 할 수 있어요.")


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
    set_app_user_model_id("EyeExercise.EyeExercise")  # 작업 표시줄에 파이썬이 아닌 우리 아이콘이 보이게
    app = QApplication(sys.argv)
    theme.apply_app_font(app)
    theme.follow_system(app)  # Windows의 라이트/다크 설정을 따라가고, 바뀌면 바로 반영한다
    app.setApplicationName("EyeExercise")
    app.setQuitOnLastWindowClosed(False)  # 트레이 상주 앱: 창이 없어도 종료하지 않는다
    app.setWindowIcon(app_icon())

    instance = SingleInstance()
    if not instance.acquire():
        allow_any_process_to_set_foreground()
        if instance.notify_primary():
            log.info("이미 실행 중입니다. 실행 중인 창을 앞으로 가져옵니다.")
            return 0
        log.error("이미 실행 중인 인스턴스에 연결하지 못했습니다.")
        return 1

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.error("시스템 트레이를 사용할 수 없어 종료합니다.")
        return 1

    tray_app = TrayApp(app, _load_settings())
    instance.activated.connect(tray_app.show_main_window)
    tray_app.start()
    sigint_wakeup = _install_sigint_handler(tray_app)  # noqa: F841 (참조 유지용)
    code = app.exec()
    instance.release()
    return code
