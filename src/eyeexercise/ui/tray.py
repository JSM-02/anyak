"""트레이 아이콘과 메뉴."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from eyeexercise.core.formatting import format_remaining
from eyeexercise.core.scheduler import State
from eyeexercise.ui.controller import Controller

_APP_NAME = "EyeExercise"


class TrayIcon(QObject):
    quit_requested = Signal()

    def __init__(self, controller: Controller, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._tray = QSystemTrayIcon(icon, self)

        self._menu = QMenu()  # 부모 없는 메뉴는 참조를 들고 있어야 사라지지 않는다
        self._act_now = self._menu.addAction("지금 운동")
        self._act_pause = self._menu.addAction("일시정지")
        self._menu.addSeparator()
        self._act_quit = self._menu.addAction("종료")
        self._tray.setContextMenu(self._menu)

        self._act_now.triggered.connect(controller.start_exercise)
        self._act_pause.triggered.connect(self._toggle_pause)
        self._act_quit.triggered.connect(self.quit_requested)

        controller.ticked.connect(self.refresh)
        controller.state_changed.connect(self.refresh)
        self.refresh()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def show_message(self, text: str) -> None:
        self._tray.showMessage(_APP_NAME, text, QSystemTrayIcon.MessageIcon.Information, 4000)

    def refresh(self) -> None:
        state = self._controller.state
        self._act_now.setEnabled(state in (State.RUNNING, State.SNOOZED, State.DUE))
        self._act_pause.setText("재개" if state is State.PAUSED else "일시정지")
        self._act_pause.setEnabled(state in (State.RUNNING, State.SNOOZED, State.PAUSED))
        self._tray.setToolTip(f"{_APP_NAME} — {self._status_text(state)}")

    def _status_text(self, state: State) -> str:
        if state is State.DUE:
            return "눈 운동할 시간이에요"
        if state is State.EXERCISING:
            return "운동 중"
        remaining = self._controller.remaining_seconds
        text = f"다음 알림까지 {format_remaining(remaining)}" if remaining is not None else ""
        if state is State.PAUSED:
            return f"일시정지됨 ({text})"
        if state is State.SNOOZED:
            return f"미루는 중 ({text})"
        return text

    def _toggle_pause(self) -> None:
        if self._controller.state is State.PAUSED:
            self._controller.resume()
        else:
            self._controller.pause()
