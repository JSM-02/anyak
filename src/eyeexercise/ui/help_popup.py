"""메뉴 줄의 "?"를 누르면 그 아래에 뜨는 사용 안내.

알림 팝업과 같은 깊은 초록 면에 모래색 제목과 밝은 본문을 쓴다. 바깥을 누르거나 Esc를 누르면 닫힌다.
문구는 `core/help_text.py`에 있다.
"""

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from eyeexercise.core.help_text import HELP_SECTIONS
from eyeexercise.ui import theme

_WIDTH = 440
_RADIUS = 22
_GAP = 8  # "?" 버튼과의 간격
_MARGIN = 12  # 화면 가장자리와 띄울 간격

# 초록 면 위의 글자는 두 테마에서 같은 색을 쓴다(면 색이 같아서). 밝은 본문색은 흰색에 가깝다.
_STYLE = """
QLabel { background: transparent; }
#helpTitle { color: $sand; font-size: $fs_body; font-weight: 900; }
#helpBody { color: #EAF3EF; font-size: $fs_small; }
"""


class HelpPopup(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("helpPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 모서리를 둥글게 직접 그린다
        self.setFixedWidth(_WIDTH)
        theme.bind(self, _STYLE)
        theme.on_changed(self._on_theme_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 24)
        layout.setSpacing(16)
        self.titles: list[QLabel] = []
        self.bodies: list[QLabel] = []
        for title, body in HELP_SECTIONS:
            block = QVBoxLayout()
            block.setSpacing(4)
            title_label = QLabel(title)
            title_label.setObjectName("helpTitle")
            body_label = QLabel(body)
            body_label.setObjectName("helpBody")
            body_label.setWordWrap(True)
            body_label.setTextFormat(Qt.TextFormat.PlainText)
            block.addWidget(title_label)
            block.addWidget(body_label)
            layout.addLayout(block)
            self.titles.append(title_label)
            self.bodies.append(body_label)

    def _on_theme_changed(self) -> None:
        self.update()

    def show_below(self, anchor: QWidget) -> None:
        """anchor(? 버튼) 아래, 오른쪽 끝을 맞춰 연다. 화면 밖으로 나가지 않게 당긴다."""
        self.adjustSize()
        spot = anchor.mapToGlobal(QPoint(anchor.width() - self.width(), anchor.height() + _GAP))
        screen = QGuiApplication.screenAt(anchor.mapToGlobal(anchor.rect().center())) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = min(max(spot.x(), area.left() + _MARGIN), area.right() - self.width() - _MARGIN)
            y = min(spot.y(), area.bottom() - self.height() - _MARGIN)
            spot = QPoint(x, y)
        self.move(spot)
        self.show()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.color("hero"))
        painter.drawRoundedRect(QRectF(self.rect()), _RADIUS, _RADIUS)
        painter.end()
