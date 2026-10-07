"""화면 구석에 뜨는 작은 알림 팝업. 사용자가 버튼을 누를 때까지 유지된다."""

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eyeexercise.ui import theme
from eyeexercise.ui.icons import render_icon

_MARGIN = 16
_SLIDE_PX = 14  # 아래에서 이만큼 올라오며 나타난다
_FADE_MS = 180
_ICON_PX = 36

_STYLE = """
#popup { background: $surface; border: 1px solid $border_strong; border-radius: 8px; }
#popup QLabel { color: $text; }
#title { font-size: $fs_heading; font-weight: bold; }
#message { color: $text_secondary; }
#popup QLabel#icon { background: transparent; }
#popup QPushButton {
    color: $text; background: $chip; border: 1px solid $border_strong;
    border-radius: 4px; padding: 6px 12px;
}
#popup QPushButton:hover { background: $hover; }
#popup QPushButton#primary { color: $on_accent; background: $accent; border: 1px solid $accent; }
#popup QPushButton#primary:hover { background: $accent_hover; border: 1px solid $accent_hover; }
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
        theme.bind(self, _STYLE)

        icon = QLabel()
        icon.setObjectName("icon")
        icon.setPixmap(QPixmap.fromImage(render_icon(_ICON_PX * 2)).scaled(
            _ICON_PX, _ICON_PX, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        icon.setFixedSize(_ICON_PX, _ICON_PX)
        title = QLabel("눈 운동 시간이에요")
        title.setObjectName("title")
        body = QLabel("잠깐 화면에서 눈을 떼고\n운동해 볼까요?")
        body.setObjectName("message")

        start = QPushButton("시작")
        start.setObjectName("primary")
        snooze = QPushButton()
        self._snooze_button = snooze
        self.set_snooze_minutes(snooze_minutes)
        skip = QPushButton("건너뛰기")
        start.clicked.connect(self.start_clicked)
        snooze.clicked.connect(self.snooze_clicked)
        skip.clicked.connect(self.skip_clicked)

        buttons = QHBoxLayout()
        buttons.addWidget(start)
        buttons.addWidget(snooze)
        buttons.addWidget(skip)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(body)
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        header.addLayout(texts, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addLayout(buttons)

        # 나타날 때: 투명에서 선명하게, 아래에서 살짝 위로. 갑자기 튀어나오지 않아 덜 거슬린다
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(_FADE_MS)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(_FADE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._appear = QParallelAnimationGroup(self)
        self._appear.addAnimation(self._fade)
        self._appear.addAnimation(self._slide)

    def set_snooze_minutes(self, minutes: int) -> None:
        """설정에서 미루기 시간을 바꾸면 버튼 글자도 바꾼다."""
        self._snooze_button.setText(f"{minutes}분 미루기")

    def show_at_corner(self) -> None:
        """주 모니터의 오른쪽 아래(작업 표시줄 위)에 띄운다."""
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        target = QPoint(screen.right() - self.width() - _MARGIN, screen.bottom() - self.height() - _MARGIN)
        self._appear.stop()
        self.move(target)
        self.setWindowOpacity(0.0)
        self._slide.setStartValue(target + QPoint(0, _SLIDE_PX))
        self._slide.setEndValue(target)
        self.show()
        self._appear.start()

    def hideEvent(self, event) -> None:
        self._appear.stop()  # 나타나는 도중에 닫혀도 다음에 깨끗하게 시작한다
        self.setWindowOpacity(1.0)
        super().hideEvent(event)
