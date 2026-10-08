"""메인 창(기록·설정·시력 기록 대시보드). 닫으면 종료하지 않고 트레이로 숨긴다.

Windows 데스크톱 앱처럼 왼쪽에 메뉴, 오른쪽에 넓은 본문을 둔다.
"""

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QRect, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from eyeexercise import APP_NAME
from eyeexercise.core.autostart import AutoStart
from eyeexercise.core.clock import SystemClock
from eyeexercise.core.formatting import timer_pill
from eyeexercise.core.history import History
from eyeexercise.core.scheduler import State
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.usage import UsageLog
from eyeexercise.core.vision import VisionLog
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.home_page import HomePage
from eyeexercise.ui.records_tab import RecordsTab
from eyeexercise.ui.settings_page import SettingsPage
from eyeexercise.ui.sidebar import Sidebar
from eyeexercise.ui.vision_page import VisionPage

WINDOW_SIZE = (1000, 700)
WINDOW_MIN_SIZE = (880, 560)
_SCREEN_MARGIN = 40  # 작업 표시줄과 창 테두리를 빼고 화면에 남기는 여유

_MENU = ("홈", "기록", "시력 기록", "설정")  # 같은 순서로 본문 화면을 쌓는다
_MENU_ICONS = ("home", "chart", "eye", "gear")


def fit_to_screen(area: QRect) -> tuple[tuple[int, int], tuple[int, int]]:
    """(기본 크기, 최소 크기). 배율이 높아 화면이 작게 쓰이면(예: 1080p 150% → 논리 높이 약 720px) 화면 안에 들어오게 줄인다."""
    max_w, max_h = max(1, area.width() - _SCREEN_MARGIN), max(1, area.height() - _SCREEN_MARGIN)
    size = (min(WINDOW_SIZE[0], max_w), min(WINDOW_SIZE[1], max_h))
    minimum = (min(WINDOW_MIN_SIZE[0], size[0]), min(WINDOW_MIN_SIZE[1], size[1]))
    return size, minimum


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(
        self,
        history: History | None = None,
        now: Callable[[], datetime] = SystemClock().now,
        usage: UsageLog | None = None,
        settings_manager: SettingsManager | None = None,
        vision_log: VisionLog | None = None,
        autostart: AutoStart | None = None,
    ) -> None:
        super().__init__()
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        screen = QGuiApplication.primaryScreen()
        size, minimum = fit_to_screen(screen.availableGeometry()) if screen else (WINDOW_SIZE, WINDOW_MIN_SIZE)
        self.resize(*size)
        self.setMinimumSize(*minimum)

        manager = settings_manager or SettingsManager(Settings())
        self.home_page = HomePage(
            lambda: history.events if history else (),
            now,
            usage_provider=lambda: usage or UsageLog(),
            settings_provider=lambda: manager.settings,
        )
        manager.subscribe(lambda _new, _old: self.home_page.refresh())  # 휴식 주기·운동 목표가 바뀌면 오늘 요약도 따라간다
        self.records_tab = RecordsTab(
            lambda: history.events if history else (),
            now,
            usage_provider=lambda: usage or UsageLog(),
            interval_minutes=lambda: manager.settings.interval_minutes,
        )
        self.settings_page = SettingsPage(manager, autostart=autostart)
        self.vision_page = VisionPage(vision_log, today=lambda: now().date())
        self._stack = QStackedWidget()
        for page in (self.home_page, self.records_tab, self.vision_page, self.settings_page):  # _MENU와 같은 순서
            self._stack.addWidget(page)

        self.sidebar = Sidebar(_MENU, _MENU_ICONS)
        self.sidebar.current_changed.connect(self._stack.setCurrentIndex)
        self._controller: Controller | None = None

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

    def attach_controller(self, controller: Controller) -> None:
        """사이드바의 눈 휴식 타이머와 홈 화면이 컨트롤러의 남은 시간·상태를 따라가게 한다."""
        self._controller = controller
        controller.ticked.connect(self._refresh_timer)
        controller.state_changed.connect(self._refresh_timer)
        controller.activity_started.connect(self._refresh_timer)  # 상태가 바뀐 직후에야 휴식인지 운동인지 정해지므로 한 번 더 그린다
        controller.history_changed.connect(self.home_page.refresh)
        self.home_page.rest_requested.connect(controller.start_rest)
        self.home_page.snooze_requested.connect(controller.snooze)
        self.home_page.exercise_requested.connect(controller.start_exercise)
        self.home_page.pause_toggled.connect(self._toggle_pause)
        self._refresh_timer()

    def _toggle_pause(self) -> None:
        if self._controller is None:
            return
        if self._controller.state is State.PAUSED:
            self._controller.resume()
        else:
            self._controller.pause()

    def _refresh_timer(self) -> None:
        if self._controller is None:
            return
        c = self._controller
        text, tone = timer_pill(c.state, c.remaining_seconds, c.activity)
        self.sidebar.set_timer(text, tone)
        self.home_page.set_timer(c.state, c.remaining_seconds, c.target_seconds, c.activity)

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def prepare_to_quit(self) -> None:
        """앱을 정말 종료할 때 호출한다. 이후의 닫기 요청은 숨기지 않고 받아들인다."""
        self._quitting = True

    def closeEvent(self, event: QCloseEvent) -> None:
        # 앱 종료 중이거나 Windows 로그오프·종료 중이면 막지 않는다 (막으면 종료가 지연된다).
        app = QGuiApplication.instance()
        if self._quitting or (app is not None and app.isSavingSession()):
            event.accept()
            return
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
