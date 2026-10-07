"""깜빡임 운동 창. 타임라인(core/exercises)이 계산한 값을 그리기만 한다."""

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QCursor, QGuiApplication, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.exercises import EXERCISE_BLINK, BlinkStep, BlinkTimeline, Phase, blink_timeline
from eyeexercise.ui.speech import Speaker

WINDOW_SIZE = (480, 320)  # 소리로도 안내하므로 화면은 작게 둔다
_FRAME_MS = 33  # 약 30fps

_STYLE = """
#exercise { background: #ffffff; border: 1px solid #c8ccd0; border-radius: 10px; }
#exercise QLabel { color: #202124; }
#message { font-size: 24px; font-weight: bold; }
#exercise QProgressBar {
    background: #e8eaed; border: none; border-radius: 4px; max-height: 8px; min-height: 8px;
}
#exercise QProgressBar::chunk { background: #1a73e8; border-radius: 4px; }
#exercise QPushButton {
    color: #202124; background: #f1f3f4; border: 1px solid #dadce0;
    border-radius: 4px; padding: 6px 16px;
}
#exercise QPushButton:hover { background: #e8eaed; }
"""


class EyeWidget(QWidget):
    """눈 모양. openness 1.0은 활짝 뜬 눈, 0.0은 감은 눈."""

    def __init__(self) -> None:
        super().__init__()
        self._openness = 1.0
        self.setMinimumSize(200, 110)

    def set_openness(self, value: float) -> None:
        self._openness = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        half_w = min(self.width() * 0.4, 110.0)
        half_h = max(2.0, min(self.height() * 0.4, 58.0) * self._openness)  # 감아도 선은 남긴다
        eye = QRectF(center.x() - half_w, center.y() - half_h, half_w * 2, half_h * 2)

        painter.setPen(QPen(QColor("#1a73e8"), 5))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(eye)

        if self._openness > 0.15:  # 거의 감겼을 때는 홍채를 그리지 않는다
            clip = QPainterPath()
            clip.addEllipse(eye)
            painter.setClipPath(clip)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1a73e8"))
            painter.drawEllipse(center, 34, 34)
            painter.setBrush(QColor("#202124"))
            painter.drawEllipse(center, 15, 15)
            painter.setClipping(False)
            painter.setPen(QPen(QColor("#1a73e8"), 5))  # 홍채가 덮은 윤곽선을 다시 그린다
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(eye)
        painter.end()


class ExerciseWindow(QWidget):
    completed = Signal(str, int)  # 운동 이름, 총 시간(초)
    aborted = Signal()

    def __init__(self, speaker: Speaker | None = None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("exercise")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(_STYLE)
        self.setMinimumSize(*WINDOW_SIZE)
        self.resize(*WINDOW_SIZE)

        self._speaker = speaker
        self._last_phase: Phase | None = None
        self._timeline: BlinkTimeline | None = None
        self._running = False  # 중단할 수 있는 상태 (깜빡임 운동이 끝나기 전)
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._on_frame)

        self._eye = EyeWidget()
        self._message = QLabel()
        self._message.setObjectName("message")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setMinimumHeight(40)  # 문구가 비는 쉬기 구간에도 눈 모양이 흔들리지 않게 높이를 고정한다
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._button = QPushButton("중단")
        self._button.clicked.connect(self._on_button)
        self._hint = QLabel()
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet("color: #5f6368; font-size: 12px;")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 16)
        layout.setSpacing(12)
        layout.addWidget(self._eye, stretch=1)
        layout.addWidget(self._message)
        layout.addWidget(self._progress)
        layout.addLayout(buttons)
        layout.addWidget(self._hint)

    @property
    def running(self) -> bool:
        return self._running

    def start(self, duration_seconds: int) -> None:
        """운동을 시작한다. 마우스 커서가 있는 모니터의 가운데에 띄운다."""
        self._timeline = blink_timeline(duration_seconds)
        self._running = True
        self._last_phase = None
        self._button.setText("중단")
        self._hint.setText("Esc 키로도 중단할 수 있어요")
        self._elapsed.start()
        self._apply(self._timeline.step_at(0))
        self._center_on_cursor_screen()
        self.show()
        self.raise_()
        self.activateWindow()  # Esc 키를 받기 위해 포커스를 가져온다
        self._timer.start()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape or (not self._running and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        if self._speaker is not None:
            self._speaker.stop()
        if self._running:
            self._running = False
            self.aborted.emit()
        event.accept()

    # ---- 내부 ----

    def _on_button(self) -> None:
        self.close()  # 진행 중이면 중단, 끝난 뒤에는 닫기

    def _on_frame(self) -> None:
        assert self._timeline is not None
        step = self._timeline.step_at(self._elapsed.elapsed() / 1000.0)
        self._apply(step)
        if step.finished and self._running:
            # 깜빡임 운동을 마쳤다. 먼 곳 바라보기 중에 닫아도 완료로 센다.
            self._running = False
            self._button.setText("닫기")
            self._hint.setText("Esc 키로 닫을 수 있어요")
            self.completed.emit(EXERCISE_BLINK, self._timeline.total_seconds)
        if step.done:
            self.close()  # 카운트다운이 끝나면 저절로 닫는다

    def _apply(self, step: BlinkStep) -> None:
        self._eye.set_openness(step.eye_openness)
        text = step.message
        if step.countdown:
            text = f"{text} · {step.countdown}"
        self._message.setText(text)
        self._progress.setValue(round(step.progress * 1000))
        if step.phase is not self._last_phase:
            self._last_phase = step.phase
            if self._speaker is not None:
                self._speaker.cue(step.phase)

    def _center_on_cursor_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
