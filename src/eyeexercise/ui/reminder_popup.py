"""화면 구석에 뜨는 작은 알림 팝업. 사용자가 버튼을 누를 때까지 유지된다.

홈 화면에서 알림이 떠 있을 때 물이 가득 찬 것과 같은 모습이다. 팝업 전체가 깊은 초록 물이고 맨 위의 얇은 띠에만 수면과
파도가 보인다. 글자와 버튼은 모두 물 속에 있어서 모래색이다.
"""

import time
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.tide import WAVE_WEAK, wave_margin
from eyeexercise.platform.win_motion import animations_enabled
from eyeexercise.ui import theme
from eyeexercise.ui.water import water_paths

_MARGIN = 16
_SLIDE_PX = 14  # 아래에서 이만큼 올라오며 나타난다
_FADE_MS = 180
_RADIUS = 18
_WIDTH = 340
_TOP_MARGIN = 30  # 위쪽 얇은 띠(수면이 지나는 곳). 파도의 가장 낮은 곳보다 커야 글자가 수면에 걸치지 않는다
SURFACE_Y = 16  # 수면이 위에서 이만큼(px) 아래에 놓인다. 팝업 높이가 달라져도 위쪽 띠의 두께는 같다
_FRAME_MS = 33  # 물결을 다시 그리는 간격(초당 약 30번)

_STYLE = """
#popup QLabel { background: transparent; }
#title { color: $sand; font-size: 18px; font-weight: 900; }
#message { color: $sand; font-size: $fs_small; font-weight: 600; }
#popup QPushButton {
    color: $sand; background: transparent; border: 2px solid $sand;
    border-radius: 8px; padding: 6px 10px; font-size: $fs_small; font-weight: 900;
}
#popup QPushButton:hover { background: rgba(242, 227, 179, 40); }
#popup QPushButton#primary { color: $ink; background: $sand; }
#popup QPushButton#primary:hover { background: #ffffff; border-color: #ffffff; }
#popup QPushButton#offer { border-style: dashed; }
"""


class ReminderPopup(QWidget):
    start_clicked = Signal()
    snooze_clicked = Signal()
    skip_clicked = Signal()
    exercise_clicked = Signal()  # '운동도 할래요?'

    _alert = None  # 팝업이 뜰 때 울리는 알림음. 소리를 끄면 None

    def __init__(
        self,
        snooze_minutes: int,
        animations: Callable[[], bool] = animations_enabled,
        motion_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("popup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 모서리를 둥글게 자르려고 직접 그린다
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # 작업 중인 창의 포커스를 뺏지 않는다
        self.setFixedWidth(_WIDTH)
        theme.bind(self, _STYLE)
        theme.on_changed(self._on_theme_changed)
        self._animations = animations
        self._motion_clock = motion_clock
        self._t0 = motion_clock()
        self._wave_t = 0.0

        title = QLabel("눈 쉬는 시간이에요")
        title.setObjectName("title")
        body = QLabel("잠깐 화면에서 눈을 떼고\n눈을 쉬게 해 볼까요?")
        body.setObjectName("message")

        start = QPushButton("시작")
        start.setObjectName("primary")
        snooze = QPushButton()
        self._snooze_button = snooze
        self.set_snooze_minutes(snooze_minutes)
        skip = QPushButton("건너뛰기")
        for button in (start, snooze, skip):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        start.clicked.connect(self.start_clicked)
        snooze.clicked.connect(self.snooze_clicked)
        skip.clicked.connect(self.skip_clicked)
        self._exercise_button = QPushButton()
        self._exercise_button.setObjectName("offer")
        self._exercise_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exercise_button.clicked.connect(self.exercise_clicked)
        self._exercise_button.hide()

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(start, stretch=3)
        buttons.addWidget(snooze, stretch=4)
        buttons.addWidget(skip, stretch=3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, _TOP_MARGIN, 20, 18)  # 위는 수면이 지나는 띠만큼 비워 둔다
        layout.setSpacing(2)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addSpacing(0)
        layout.addWidget(self._exercise_button)

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

        # 보이는 동안에만 물결을 다시 그린다. Windows의 '애니메이션 효과'를 끄면 물결은 멈춰 있다
        self._frame = QTimer(self)
        self._frame.setInterval(_FRAME_MS)
        self._frame.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame.timeout.connect(self._on_frame)

    def set_exercise_offer(self, done: int | None, goal: int) -> None:
        """'운동도 할래요? (오늘 1/2)' 버튼을 보이거나 숨긴다. done이 None이면 숨긴다 (목표를 채웠거나 운동이 꺼져 있을 때)."""
        if done is None:
            self._exercise_button.hide()
            return
        self._exercise_button.setText(f"운동도 할래요? (오늘 {done}/{goal})")
        self._exercise_button.show()

    def set_alert(self, alert) -> None:
        """팝업이 뜰 때 울릴 알림음(`play()`가 있는 것)을 정한다. None이면 조용히 뜬다."""
        self._alert = alert

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
        if self._alert is not None:
            self._alert.play()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._animations():
            self._frame.start()

    def hideEvent(self, event) -> None:
        self._frame.stop()
        self._appear.stop()  # 나타나는 도중에 닫혀도 다음에 깨끗하게 시작한다
        self.setWindowOpacity(1.0)
        super().hideEvent(event)

    # ---- 그리기 ----

    def _on_frame(self) -> None:
        self._wave_t = self._motion_clock() - self._t0 if self._animations() else 0.0
        self.update()

    def _on_theme_changed(self) -> None:
        self.update()

    def water_level(self) -> float:
        """수면이 위에서 SURFACE_Y 아래에 놓이도록 하는 물의 높이 비율(0~1)."""
        margin = wave_margin(WAVE_WEAK)
        return 1 - (SURFACE_Y + margin) / (self.height() + 2 * margin)

    def water_paths(self) -> tuple[QPainterPath, QPainterPath, QPainterPath]:
        """(앞쪽 물, 뒤쪽 옅은 물결, 수면의 선)."""
        return water_paths(self.width(), self.height(), self.water_level(), self._wave_t, WAVE_WEAK)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS, _RADIUS)
        painter.setClipPath(outline)  # 둥근 모서리 밖은 그리지 않아 투명하게 남는다
        painter.fillRect(self.rect(), theme.color("paper"))
        front, back, line = self.water_paths()
        water = theme.color("hero")
        soft = QColor(water)
        soft.setAlpha(66)
        painter.fillPath(back, soft)
        painter.fillPath(front, water)
        foam = theme.color("sand")
        foam.setAlpha(WAVE_WEAK.foam_alpha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(foam, WAVE_WEAK.foam_width))
        painter.drawPath(line)
        painter.setClipping(False)
        painter.setPen(QPen(theme.color("sidebar"), 1))
        painter.drawPath(outline)
        painter.end()
