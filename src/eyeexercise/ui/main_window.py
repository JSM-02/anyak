"""메인 창(기록·설정·시력 기록 대시보드). 닫으면 종료하지 않고 트레이로 숨긴다.

Windows 데스크톱 앱처럼 왼쪽에 메뉴, 오른쪽에 넓은 본문을 둔다.
"""

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.history import History
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.usage import UsageLog
from eyeexercise.core.vision import VisionLog
from eyeexercise.ui import theme
from eyeexercise.ui.records_tab import RecordsTab
from eyeexercise.ui.settings_page import SettingsPage
from eyeexercise.ui.vision_page import VisionPage

WINDOW_SIZE = (1000, 700)
WINDOW_MIN_SIZE = (860, 560)
_SCREEN_MARGIN = 40  # 작업 표시줄과 창 테두리를 빼고 화면에 남기는 여유
SIDEBAR_WIDTH = 176

_STYLE = """
#sidebar { background: $sidebar; border-right: 1px solid $sidebar_border; }
#appName { font-size: $fs_heading; font-weight: bold; color: $text; padding: 4px 6px 12px 6px; }
#navList { background: transparent; border: none; outline: none; }
#navList::item { padding: 10px 12px; border-radius: 6px; margin: 1px 0; color: $text_body; }
#navList::item:hover { background: $hover; }
#navList::item:selected { background: $surface; color: $accent; font-weight: bold; }
"""

_MENU = ("기록", "설정", "시력 기록")


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
    ) -> None:
        super().__init__()
        self._quitting = False
        self.setWindowTitle("EyeExercise")
        screen = QGuiApplication.primaryScreen()
        size, minimum = fit_to_screen(screen.availableGeometry()) if screen else (WINDOW_SIZE, WINDOW_MIN_SIZE)
        self.resize(*size)
        self.setMinimumSize(*minimum)

        self.records_tab = RecordsTab(lambda: history.events if history else (), now, usage_provider=lambda: usage or UsageLog())
        self.settings_page = SettingsPage(settings_manager or SettingsManager(Settings()))
        self.vision_page = VisionPage(vision_log, today=lambda: now().date())
        self._stack = QStackedWidget()
        for page in (self.records_tab, self.settings_page, self.vision_page):  # _MENU와 같은 순서
            self._stack.addWidget(page)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._nav.addItems(_MENU)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        app_name = QLabel("EyeExercise")
        app_name.setObjectName("appName")
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 14, 10, 10)
        side_layout.addWidget(app_name)
        side_layout.addWidget(self._nav)

        central = QWidget()
        theme.bind(central, _STYLE)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

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
