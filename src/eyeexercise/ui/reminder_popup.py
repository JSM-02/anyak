"""화면 구석에 뜨는 작은 알림 팝업. 알림은 사용자가 버튼을 누를 때까지 유지된다.

홈 화면에서 알림이 떠 있을 때 물이 가득 찬 것과 같은 모습이다. 팝업 전체가 깊은 초록 물이고 맨 위의 얇은 띠에만 수면과
파도가 보인다. 글자와 버튼은 모두 물 속에 있어서 모래색이다.

[시작]을 누르면같은 팝업이 20초 카운트다운으로 바뀐다. 먼 곳을 바라보는 20초 동안 물이 서서히 빠지고,
20초가 지나야 휴식을 마친 것으로 센다. 창이 따로 뜨지 않는다.
"""

import time
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QElapsedTimer, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.exercises import LOOK_AWAY_SECONDS, ExerciseStep, LookAwayTimeline, Phase
from eyeexercise.core.tide import WAVE_WEAK, wave_margin
from eyeexercise.platform.win_motion import animations_enabled
from eyeexercise.ui import theme
from eyeexercise.ui.speech import Speaker
from eyeexercise.ui.water import water_paths

_MARGIN = 16
_SLIDE_PX = 14  # 아래에서 이만큼 올라오며 나타난다
_FADE_MS = 180
_RADIUS = 20
_WIDTH = 340
_TOP_MARGIN = 30  # 위쪽 얇은 띠(수면이 지나는 곳). 파도의 가장 낮은 곳보다 커야 글자가 수면에 걸치지 않는다
SURFACE_Y = 16  # 수면이 위에서 이만큼(px) 아래에 놓인다. 팝업 높이가 달라져도 위쪽 띠의 두께는 같다
COUNT_HEIGHT = 160  # 카운트다운 모양의 높이. 숫자와 [중단]이 들어갈 만큼이다
_FRAME_MS = 33  # 물결을 다시 그리는 간격(초당 약 30번)
_QWIDGETSIZE_MAX = 16777215

_STYLE = """
#popup QLabel { background: transparent; }
#title { color: $sand; font-size: 18px; font-weight: 900; }
#message { color: $sand; font-size: $fs_small; font-weight: 600; }
#popup QPushButton {
    color: $sand; background: rgba(242, 227, 179, 46); border: none;
    border-radius: 10px; padding: 8px 12px; font-size: $fs_small; font-weight: 900;
}
#popup QPushButton:hover { background: rgba(242, 227, 179, 80); }
#popup QPushButton#primary { color: $ink; background: $sand; }
#popup QPushButton#primary:hover { background: #ffffff; }
#popup QPushButton#offer { background: rgba(242, 227, 179, 28); }
#popup QPushButton#offer:hover { background: rgba(242, 227, 179, 60); }
#popup QPushButton#abort { color: $ink; background: #ffffff; padding: 8px 18px; }
#popup QPushButton#abort:hover { background: $sand; }
"""


class ReminderPopup(QWidget):
    start_clicked = Signal()
    snooze_clicked = Signal()
    skip_clicked = Signal()
    exercise_clicked = Signal()  # '운동도 할래요?'
    completed = Signal(str, int)  # 팝업 안의 20초를 마쳤다: 운동 이름, 시간(초)
    aborted = Signal()  # 20초를 마치기 전에 멈췄다

    _alert = None  # 팝업이 뜰 때 울리는 알림음. 소리를 끄면 None
    _speaker: Speaker | None = None

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

        # 카운트다운(먼 곳 바라보기) 상태
        self._counting = False
        self._timeline: LookAwayTimeline | None = None
        self._elapsed = QElapsedTimer()
        self._count_text = str(LOOK_AWAY_SECONDS)
        self._count_progress = 0.0  # 0(시작) ~ 1(끝). 물이 빠진 정도다

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

        # 알림 모양: 제목·안내·버튼
        self._alert_box = QWidget()
        alert_layout = QVBoxLayout(self._alert_box)
        alert_layout.setContentsMargins(0, 0, 0, 0)
        alert_layout.setSpacing(2)
        alert_layout.addWidget(title)
        alert_layout.addWidget(body)
        alert_layout.addSpacing(10)
        alert_layout.addLayout(buttons)
        alert_layout.addWidget(self._exercise_button)

        # 카운트다운 모양: 글자는 물과 함께 직접 그리고, 여기에는 [중단] 버튼만 둔다
        self._abort_button = QPushButton("중단")
        self._abort_button.setObjectName("abort")
        self._abort_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._abort_button.clicked.connect(self.hide)  # 숨겨지면서 중단으로 알린다(hideEvent)
        self._count_box = QWidget()
        count_layout = QVBoxLayout(self._count_box)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_row = QHBoxLayout()
        count_row.addStretch()
        count_row.addWidget(self._abort_button)
        count_layout.addStretch()
        count_layout.addLayout(count_row)
        self._count_box.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, _TOP_MARGIN, 20, 18)  # 위는 수면이 지나는 띠만큼 비워 둔다
        layout.addWidget(self._alert_box)
        layout.addWidget(self._count_box)

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

        # 보이는 동안에만 물결을 다시 그린다. Windows의 '애니메이션 효과'를 끄면 물결은 멈춰 있다(카운트다운은 계속 센다)
        self._frame = QTimer(self)
        self._frame.setInterval(_FRAME_MS)
        self._frame.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame.timeout.connect(self._on_frame)

    # ---- 설정 ----

    @property
    def counting(self) -> bool:
        """20초 카운트다운 중인지."""
        return self._counting

    @property
    def countdown_text(self) -> str:
        return self._count_text

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

    def set_speaker(self, speaker: Speaker | None) -> None:
        """카운트다운의 시작·끝 소리 안내를 정한다. None이면 조용하다."""
        self._speaker = speaker

    def set_snooze_minutes(self, minutes: int) -> None:
        """설정에서 미루기 시간을 바꾸면 버튼 글자도 바꾼다."""
        self._snooze_button.setText(f"{minutes}분 미루기")

    # ---- 보이기 ----

    def show_at_corner(self) -> None:
        """알림 모양으로, 주 모니터의 오른쪽 아래(작업 표시줄 위)에 띄운다."""
        self._leave_count_mode()
        self.adjustSize()
        self._appear_at_corner()
        if self._alert is not None:
            self._alert.play()

    def start_countdown(self, timeline: LookAwayTimeline) -> None:
        """20초 먼 곳 바라보기를 시작한다. 알림이 떠 있으면 그 자리에서 바뀌고(깜빡이지 않는다), 아니면 구석에 새로 뜬다."""
        was_visible = self.isVisible()
        bottom = self.geometry().bottom()
        self._timeline = timeline
        self._enter_count_mode()
        self._counting = True
        self._elapsed.start()
        self._apply_step(timeline.step_at(0))
        if was_visible:
            self.move(self.x(), bottom - self.height() + 1)  # 줄어들어도 화면 구석의 아래 위치를 지킨다
        else:
            self._appear_at_corner()
        self._frame.start()  # 애니메이션을 꺼도 카운트다운은 센다
        if self._speaker is not None:
            self._speaker.cue(Phase.LOOK_AWAY)

    def _appear_at_corner(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        target = QPoint(screen.right() - self.width() - _MARGIN, screen.bottom() - self.height() - _MARGIN)
        self._appear.stop()
        self.move(target)
        self.setWindowOpacity(0.0)
        self._slide.setStartValue(target + QPoint(0, _SLIDE_PX))
        self._slide.setEndValue(target)
        self.show()
        self._appear.start()

    def _enter_count_mode(self) -> None:
        self._alert_box.hide()
        self._count_box.show()
        self.setFixedHeight(COUNT_HEIGHT)
        self._count_progress = 0.0
        self._count_text = str(LOOK_AWAY_SECONDS)

    def _leave_count_mode(self) -> None:
        self._counting = False  # 카운트다운 도중에 알림이 새로 뜨는 일은 없지만, 남아 있는 상태는 정리한다
        self._count_box.hide()
        self._alert_box.show()
        self.setMinimumHeight(0)
        self.setMaximumHeight(_QWIDGETSIZE_MAX)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._animations() or self._counting:
            self._frame.start()

    def hideEvent(self, event) -> None:
        self._frame.stop()
        self._appear.stop()  # 나타나는 도중에 닫혀도 다음에 깨끗하게 시작한다
        self.setWindowOpacity(1.0)
        if self._counting:  # 20초를 마치기 전에 닫혔다
            self._counting = False
            if self._speaker is not None:
                self._speaker.stop()
            self.aborted.emit()
        super().hideEvent(event)

    # ---- 카운트다운 ----

    def _apply_step(self, step: ExerciseStep) -> None:
        self._count_text = str(step.countdown if step.countdown else (0 if step.done else LOOK_AWAY_SECONDS))
        self._count_progress = min(1.0, max(0.0, 1.0 - step.progress))

    def _finish_countdown(self) -> None:
        assert self._timeline is not None
        self._counting = False
        self.completed.emit(self._timeline.exercise, int(self._timeline.total_seconds + LOOK_AWAY_SECONDS))
        if self._speaker is not None:
            self._speaker.cue(Phase.FINISH)  # 눈을 돌려도 되도록 알려 준다
        self.hide()

    # ---- 그리기 ----

    def _on_frame(self) -> None:
        self._wave_t = self._motion_clock() - self._t0 if self._animations() else 0.0
        if self._counting and self._timeline is not None:
            step = self._timeline.step_at(self._elapsed.elapsed() / 1000.0)
            self._apply_step(step)
            if step.done:
                self._finish_countdown()
        self.update()

    def _on_theme_changed(self) -> None:
        self.update()

    def water_level(self) -> float:
        """물의 높이 비율(0~1). 알림 모양에서는 수면이 위에서 SURFACE_Y 아래에 놓이고, 카운트다운에서는 그 자리에서 바닥까지 내려간다."""
        margin, height = wave_margin(WAVE_WEAK), self.height()
        surface = SURFACE_Y
        if self._counting:
            surface += (height + margin - SURFACE_Y) * self._count_progress
        return 1 - (surface + margin) / (height + 2 * margin)

    def water_paths(self) -> tuple[QPainterPath, QPainterPath]:
        """(물, 수면의 선)."""
        return water_paths(self.width(), self.height(), self.water_level(), self._wave_t, WAVE_WEAK)

    def _font(self, px: float, weight: QFont.Weight) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(1, round(px)))
        font.setWeight(weight)
        return font

    def _paint_count_content(self, painter: QPainter, color: QColor) -> None:
        """카운트다운의 글자(안내·남은 초)를 color로 그린다. 물 밖(짙은색)과 물 안(모래색)에서 한 번씩 부른다."""
        painter.setPen(color)
        painter.setFont(self._font(18, QFont.Weight.Black))
        painter.drawText(
            QRectF(20, _TOP_MARGIN - 4, self.width() - 40, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "먼 곳을 바라보세요"
        )
        number_font = self._font(78, QFont.Weight.Black)
        baseline = self.height() - 22
        painter.setFont(number_font)
        painter.drawText(QPointF(20, baseline), self._count_text)
        width = QFontMetricsF(number_font).horizontalAdvance(self._count_text) or 60.0
        painter.setFont(self._font(18, QFont.Weight.Bold))
        painter.drawText(QPointF(20 + width + 8, baseline), "초")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), _RADIUS, _RADIUS)
        painter.setClipPath(outline)  # 둥근 모서리 밖은 그리지 않아 투명하게 남는다. 테두리 선도 그림자도 쓰지 않는다
        painter.fillRect(self.rect(), theme.color("paper"))
        front, line = self.water_paths()
        water = theme.color("hero")
        if self._counting:
            self._paint_count_content(painter, theme.color("text"))  # 물 밖의 글자. 아래의 물이 이 글자를 덮는다
        painter.fillPath(front, water)
        if self._counting:
            painter.save()
            painter.setClipPath(front, Qt.ClipOperation.IntersectClip)
            self._paint_count_content(painter, theme.color("sand"))  # 물에 잠긴 글자
            painter.restore()
        foam = theme.color("sand")
        foam.setAlpha(WAVE_WEAK.foam_alpha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(foam, WAVE_WEAK.foam_width))
        painter.drawPath(line)
        painter.end()
