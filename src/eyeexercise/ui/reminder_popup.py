"""화면 구석에 뜨는 작은 알림 팝업. 사용자가 버튼을 누를 때까지 유지된다."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_MARGIN = 16

_STYLE = """
#popup { background: #ffffff; border: 1px solid #c8ccd0; border-radius: 8px; }
#popup QLabel { color: #202124; }
#title { font-size: 15px; font-weight: bold; }
#popup QPushButton {
    color: #202124; background: #f1f3f4; border: 1px solid #dadce0;
    border-radius: 4px; padding: 6px 12px;
}
#popup QPushButton:hover { background: #e8eaed; }
#popup QPushButton#primary { color: #ffffff; background: #1a73e8; border: 1px solid #1a73e8; }
#popup QPushButton#primary:hover { background: #1765cc; }
"""


class ReminderPopup(QWidget):
    start_clicked = Signal()
    snooze_clicked = Signal()
    skip_clicked = Signal()

    def __init__(self, snooze_minutes: int) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("popup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # 작업 중인 창의 포커스를 뺏지 않는다
        self.setStyleSheet(_STYLE)

        title = QLabel("눈 운동 시간이에요")
        title.setObjectName("title")
        body = QLabel("잠깐 화면에서 눈을 떼고\n운동해 볼까요?")

        start = QPushButton("시작")
        start.setObjectName("primary")
        snooze = QPushButton(f"{snooze_minutes}분 미루기")
        skip = QPushButton("건너뛰기")
        start.clicked.connect(self.start_clicked)
        snooze.clicked.connect(self.snooze_clicked)
        skip.clicked.connect(self.skip_clicked)

        buttons = QHBoxLayout()
        buttons.addWidget(start)
        buttons.addWidget(snooze)
        buttons.addWidget(skip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addLayout(buttons)

    def show_at_corner(self) -> None:
        """주 모니터의 오른쪽 아래(작업 표시줄 위)에 띄운다."""
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - _MARGIN, screen.bottom() - self.height() - _MARGIN)
        self.show()
