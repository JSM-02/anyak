"""메인 창(기록·설정 대시보드). 닫으면 종료하지 않고 트레이로 숨긴다."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._quitting = False
        self.setWindowTitle("EyeExercise")
        self.resize(640, 440)
        placeholder = QLabel("기록과 설정 화면은 7단계에서 추가됩니다.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

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
