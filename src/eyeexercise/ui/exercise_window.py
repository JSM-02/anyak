"""눈 휴식·눈 운동 창. 타임라인(core/exercises)이 계산한 값을 그리기만 한다. 휴식(깜빡임 + 먼 곳 바라보기)과 운동(점 따라가기)을 모두 띄운다."""

from PySide6.QtCore import QElapsedTimer, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QCursor, QGuiApplication, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.exercises import (
    EXERCISE_BLINK,
    EXERCISE_DOT_FOLLOW,
    BlinkTimeline,
    DotFollowTimeline,
    ExerciseStep,
    LookAwayTimeline,
    Phase,
)
from eyeexercise.ui import theme
from eyeexercise.ui.speech import Speaker

# 깜빡임은 눈을 감고 소리로도 안내하므로 작게, 점 따라가기는 점이 움직일 영역이 필요해서 크게 띄운다.
WINDOW_SIZES = {EXERCISE_BLINK: (480, 320), EXERCISE_DOT_FOLLOW: (640, 440)}
WINDOW_SIZE = WINDOW_SIZES[EXERCISE_BLINK]
DOT_WINDOW_SCREEN_RATIO = 0.7  # 점 따라가기 창이 차지하는 화면 비율. 눈동자가 크게 움직이도록 크게 띄운다
_SCREEN_MARGIN = 40  # 화면 가장자리에서 띄우는 최소 여백


def window_size(exercise: str, area: QRect) -> tuple[int, int]:
    """운동 창의 크기. 깜빡임은 고정 크기, 점 따라가기는 화면의 70%(최소 크기 이상, 화면 안에서)."""
    if exercise != EXERCISE_DOT_FOLLOW:
        return WINDOW_SIZES[exercise]
    min_w, min_h = WINDOW_SIZES[EXERCISE_DOT_FOLLOW]
    width = max(min_w, round(area.width() * DOT_WINDOW_SCREEN_RATIO))  # int()는 1400*0.7=979.99…를 979로 자른다
    height = max(min_h, round(area.height() * DOT_WINDOW_SCREEN_RATIO))
    return min(width, area.width() - _SCREEN_MARGIN), min(height, area.height() - _SCREEN_MARGIN)
_FRAME_MS = 16  # 약 60fps. 정밀 타이머를 함께 써야 Windows에서 간격이 고르다 (거친 타이머는 33ms가 실제 약 21fps)

_STYLE = """
#exercise { background: $surface; border: 1px solid $border_strong; border-radius: 10px; }
#exercise QLabel { color: $text; }
#message { font-size: $fs_title; font-weight: bold; }
#tag { background: $chip; color: $text_body; border-radius: 10px; padding: 4px 12px; font-size: $fs_caption; font-weight: bold; }
#hint { color: $text_secondary; font-size: $fs_caption; }
#exercise QProgressBar {
    background: $hover; border: none; border-radius: 4px; max-height: 8px; min-height: 8px;
}
#exercise QProgressBar::chunk { background: $accent; border-radius: 4px; }
#exercise QPushButton {
    color: $text; background: $chip; border: 1px solid $border_strong;
    border-radius: 4px; padding: 6px 16px;
}
#exercise QPushButton:hover { background: $hover; }
"""


def _ease(openness: float) -> float:
    """눈꺼풀이 움직이는 속도 곡선. 감기·뜨기의 시작과 끝은 천천히, 가운데는 빠르게 해서 실제 눈처럼 부드럽게 보인다."""
    return openness * openness * (3 - 2 * openness)


class EyeWidget(QWidget):
    """눈 모양. openness 1.0은 활짝 뜬 눈, 0.0은 감은 눈.

    아몬드 모양의 눈꺼풀이 위아래로 닫히고(위 눈꺼풀이 더 많이 움직인다), 완전히 감으면 아래로 처진 곡선이 된다.
    openness는 시간에 비례해 오므로 그리는 쪽에서 부드러운 곡선(_ease)을 입힌다.
    """

    _IRIS_R = 31.0
    _PUPIL_R = 13.0

    def __init__(self) -> None:
        super().__init__()
        self._openness = 1.0
        self.setMinimumSize(200, 110)

    def set_openness(self, value: float) -> None:
        self._openness = max(0.0, min(1.0, value))
        self.update()

    def lid_path(self) -> QPainterPath:
        """눈 윤곽(아몬드). 감을수록 납작해지고 아래로 처진다."""
        e = _ease(self._openness)
        cx, cy = self.width() / 2, self.height() / 2
        half_w = min(self.width() * 0.4, 110.0)
        reach = min(self.height() * 0.4, 58.0) * 1.35  # 3차 곡선 조절점 높이 (실제로 올라가는 높이는 약 3/4)
        sag = 9.0 * (1 - e)  # 감을수록 눈꼬리 선이 아래로 처진다
        up = cy + sag - reach * e
        down = cy + sag + reach * e * 0.55  # 아래 눈꺼풀은 덜 움직인다
        path = QPainterPath()
        path.moveTo(cx - half_w, cy)
        path.cubicTo(cx - half_w * 0.45, up, cx + half_w * 0.45, up, cx + half_w, cy)
        path.cubicTo(cx + half_w * 0.45, down, cx - half_w * 0.45, down, cx - half_w, cy)
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        e = _ease(self._openness)
        center = QPointF(self.width() / 2, self.height() / 2)
        eye = self.lid_path()

        outline = QPen(theme.color("accent"), 5)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(outline)
        painter.setBrush(theme.color("surface"))
        painter.drawPath(eye)

        if e > 0.12:  # 거의 감겼을 때는 홍채를 그리지 않는다
            painter.setClipPath(eye)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("accent"))
            painter.drawEllipse(center, self._IRIS_R, self._IRIS_R)
            painter.setBrush(QColor("#202124"))  # 동공은 어느 테마에서나 어둡게
            painter.drawEllipse(center, self._PUPIL_R, self._PUPIL_R)
            painter.setBrush(QColor(255, 255, 255, 235))  # 눈에 생기를 주는 작은 반짝임
            painter.drawEllipse(QPointF(center.x() - 9, center.y() - 9), 4.5, 4.5)
            painter.setClipping(False)
            painter.setPen(outline)  # 홍채가 덮은 윤곽선을 다시 그린다
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(eye)
        painter.end()


class DotCanvas(QWidget):
    """점 따라가기 화면. 점의 위치는 0~1 정규화 좌표로 받아 영역 크기에 맞춰 그린다. None이면 점을 그리지 않는다."""

    _MARGIN = 18  # 점이 영역 가장자리에 붙지 않게 하는 안쪽 여백

    def __init__(self) -> None:
        super().__init__()
        self._dot: tuple[float, float] | None = None
        self.setMinimumSize(240, 140)

    def set_dot(self, dot: tuple[float, float] | None) -> None:
        self._dot = dot
        self.update()

    def dot_position(self) -> QPointF | None:
        """화면에 그려지는 점의 위치(위젯 좌표). 점이 없으면 None."""
        if self._dot is None:
            return None
        m = self._MARGIN
        w, h = max(1, self.width() - 2 * m), max(1, self.height() - 2 * m)
        return QPointF(m + self._dot[0] * w, m + self._dot[1] * h)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.color("chip"))  # 점이 움직이는 영역을 은은하게 보여 준다
        painter.drawRoundedRect(self.rect(), 10, 10)
        pos = self.dot_position()
        if pos is not None:
            glow = theme.color("accent")
            glow.setAlpha(50)
            painter.setBrush(glow)
            painter.drawEllipse(pos, 20, 20)  # 은은한 번짐
            painter.setBrush(theme.color("accent"))
            painter.drawEllipse(pos, 11, 11)
            painter.setBrush(theme.color("on_accent"))
            painter.drawEllipse(pos, 3, 3)  # 시선을 모을 가운데 점
        painter.end()


class ExerciseWindow(QWidget):
    completed = Signal(str, int)  # 운동 이름, 총 시간(초)
    aborted = Signal()

    def __init__(self, speaker: Speaker | None = None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("exercise")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        theme.bind(self, _STYLE)
        self.setMinimumSize(*WINDOW_SIZE)
        self.resize(*WINDOW_SIZE)

        self._speaker = speaker
        self._last_phase: Phase | None = None
        self._timeline: BlinkTimeline | LookAwayTimeline | DotFollowTimeline | None = None
        self._running = False  # 중단할 수 있는 상태 (운동이 끝나기 전)
        self._look_away_layout = False  # 점 따라가기에서 먼 곳 보기 화면(깜빡임과 같은 모양)으로 바꿨는지
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._on_frame)

        self._eye = EyeWidget()
        self._dots = DotCanvas()
        self._tag = QLabel()  # '눈 휴식' / '눈 운동'
        self._tag.setObjectName("tag")
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
        self._hint.setObjectName("hint")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 16)
        layout.setSpacing(12)
        layout.addWidget(self._tag, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._eye, stretch=1)
        layout.addWidget(self._dots, stretch=1)
        layout.addWidget(self._message)
        layout.addWidget(self._progress)
        layout.addLayout(buttons)
        layout.addWidget(self._hint)

    def set_speaker(self, speaker: Speaker | None) -> None:
        """설정에서 소리를 켜거나 끄면 바꾼다. 진행 중인 운동이 있으면 그 소리는 멈추고 다음 단계부터 새 설정을 쓴다."""
        if self._speaker is not None:
            self._speaker.stop()
        self._speaker = speaker

    @property
    def running(self) -> bool:
        return self._running

    def start(self, timeline: BlinkTimeline | LookAwayTimeline | DotFollowTimeline) -> None:
        """눈 휴식(깜빡임 + 먼 곳 바라보기) 또는 눈 운동(점 따라가기)을 시작한다. 마우스 커서가 있는 모니터의 가운데에 띄운다."""
        self._timeline = timeline
        is_blink = timeline.exercise == EXERCISE_BLINK
        self._tag.setText("눈 휴식" if is_blink else "눈 운동")
        self._eye.set_openness(1.0)
        self._eye.setVisible(is_blink)
        self._dots.setVisible(not is_blink)
        self._look_away_layout = False
        area = self._screen_area()
        size = window_size(timeline.exercise, area)
        self.setMinimumSize(0, 0)  # 이전 운동의 최소 크기가 남아 작게 줄이지 못하는 일을 막는다
        self.setMinimumSize(*size)
        self.resize(*size)
        self.move(area.center().x() - size[0] // 2, area.center().y() - size[1] // 2)
        self._running = True
        self._last_phase = None
        self._button.setText("중단")
        self._hint.setText("Esc 키로도 중단할 수 있어요")
        self._elapsed.start()
        self._apply(self._timeline.step_at(0))
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
            # 운동을 마쳤다. 먼 곳 바라보기 중에 닫아도 완료로 센다.
            self._running = False
            self._button.setText("닫기")
            self._hint.setText("Esc 키로 닫을 수 있어요")
            self.completed.emit(self._timeline.exercise, self._timeline.total_seconds)
        if step.done:
            self.close()  # 카운트다운이 끝나면 저절로 닫는다

    def _apply(self, step: ExerciseStep) -> None:
        if step.phase is Phase.LOOK_AWAY and not self._look_away_layout and self._timeline.exercise != EXERCISE_BLINK:
            self._enter_look_away_layout()
        if step.eye_openness is not None:
            self._eye.set_openness(step.eye_openness)
        self._dots.set_dot(step.dot)
        text = step.message
        if step.countdown:
            text = f"{text} · {step.countdown}"
        self._message.setText(text)
        self._progress.setValue(round(step.progress * 1000))
        if step.phase is not self._last_phase:
            self._last_phase = step.phase
            if self._speaker is not None:
                self._speaker.cue(step.phase)

    def _enter_look_away_layout(self) -> None:
        """점 따라가기의 먼 곳 바라보기: 깜빡임 운동과 같은 모양(작은 창 + 눈 모양)으로 바꾼다. 창 가운데는 그대로 둔다."""
        self._look_away_layout = True
        center = self.geometry().center()
        self._dots.setVisible(False)
        self._eye.setVisible(True)
        self._eye.set_openness(1.0)
        width, height = WINDOW_SIZES[EXERCISE_BLINK]
        self.setMinimumSize(width, height)
        self.resize(width, height)
        self.move(center.x() - width // 2, center.y() - height // 2)

    def _screen_area(self) -> QRect:
        """마우스 커서가 있는 모니터에서 작업 표시줄을 뺀 영역."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()
