"""눈 휴식·눈 운동 창. 타임라인(core/exercises)이 계산한 값을 그리기만 한다. 깜빡임이 켜진 휴식(깜빡임 + 먼 곳 바라보기)과 운동(점 따라가기)을 띄운다.

홈 화면·알림 팝업과 같은 물의 언어로 그린다. 창 맨 아래의 물이 진행에 따라 차오르고(먼 곳 바라보기 동안에는 줄어든다),
점 따라가기의 점은 물방울이다. 점이 움직이는 영역은 따로 상자로 두르지 않는다. 점 따라가기는 끝나면 바로 닫힌다(먼 곳 바라보기는 이어지지 않는다).

매 프레임 다시 그리는 곳은 점 둘레와 아래쪽 물뿐이다. 프레임 간격은 모니터 주사율에 맞춘다(60Hz면 16ms, 144Hz면 7ms).
"""

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QCursor, QGuiApplication, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.exercises import (
    DOT_PATTERNS,
    EXERCISE_BLINK,
    EXERCISE_DOT_FOLLOW,
    BlinkTimeline,
    DotFollowTimeline,
    ExerciseStep,
    LookAwayTimeline,
    Phase,
)
from eyeexercise.core.tide import WAVE_WEAK, wave_margin
from eyeexercise.platform.win_motion import animations_enabled
from eyeexercise.ui import theme
from eyeexercise.ui.speech import Speaker
from eyeexercise.ui.water import water_paths

# 깜빡임은 눈을 감고 소리로도 안내하므로 작게, 점 따라가기는 점이 움직일 영역이 필요해서 크게 띄운다.
WINDOW_SIZES = {EXERCISE_BLINK: (480, 320), EXERCISE_DOT_FOLLOW: (640, 440)}
WINDOW_SIZE = WINDOW_SIZES[EXERCISE_BLINK]
DOT_WINDOW_WIDTH_RATIO = 0.7  # 점 따라가기 창이 차지하는 화면 너비 비율. 눈동자가 크게 움직이도록 크게 띄운다
DOT_WINDOW_HEIGHT_RATIO = 0.88  # 세로는 안내 문구·버튼이 자리를 차지해서 점이 움직일 영역이 좁아지므로 더 크게 잡는다
_SCREEN_MARGIN = 40  # 화면 가장자리에서 띄우는 최소 여백
_RADIUS = 20
BAND_MIN, BAND_MAX = 12, 48  # 아래쪽 물의 높이(px). 시작할 때는 BAND_MIN(파도가 출렁여도 바닥이 늘 덮이는 높이), 끝날 때는 BAND_MAX


def window_size(exercise: str, area: QRect) -> tuple[int, int]:
    """운동 창의 크기. 깜빡임은 고정 크기, 점 따라가기는 화면 너비의 70%·높이의 88%(최소 크기 이상, 화면 안에서)."""
    if exercise != EXERCISE_DOT_FOLLOW:
        return WINDOW_SIZES[exercise]
    min_w, min_h = WINDOW_SIZES[EXERCISE_DOT_FOLLOW]
    width = max(min_w, round(area.width() * DOT_WINDOW_WIDTH_RATIO))  # int()는 1400*0.7=979.99…를 979로 자른다
    height = max(min_h, round(area.height() * DOT_WINDOW_HEIGHT_RATIO))
    return min(width, area.width() - _SCREEN_MARGIN), min(height, area.height() - _SCREEN_MARGIN)


_FRAME_MS = 16  # 주사율을 알 수 없을 때의 프레임 간격(약 60fps). 정밀 타이머를 함께 써야 Windows에서 간격이 고르다 (거친 타이머는 33ms가 실제 약 21fps)
_MIN_FRAME_MS = 4  # 아무리 빠른 모니터여도 이보다 잘게 나누지 않는다(약 240fps)


def frame_interval_ms(refresh_hz: float | None) -> int:
    """모니터 주사율에 맞는 프레임 간격(ms). 주사율보다 자주 그려도 보이지 않으므로 한 번에 한 프레임씩만 맞춘다.

    60Hz → 16, 120Hz → 8, 144Hz → 7, 240Hz → 4. 모르거나 60Hz 이하면 16ms다."""
    if not refresh_hz or refresh_hz <= 60:
        return _FRAME_MS
    return max(_MIN_FRAME_MS, min(_FRAME_MS, round(1000 / refresh_hz)))


_STYLE = """
#exercise QLabel { color: $text; background: transparent; }
#message { font-size: $fs_title; font-weight: 900; }
#exercise QLabel#tag { background: $hero; color: $sand; border-radius: 12px; padding: 5px 14px; font-size: $fs_caption; font-weight: 800; }
#hint { color: $text_secondary; font-size: $fs_caption; }
#exercise QPushButton {
    color: $sand; background: $hero; border: none; border-radius: 10px; padding: 8px 26px; font-size: $fs_body; font-weight: 900;
}
#exercise QPushButton:hover { background: #1B6B64; }
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
    _LOWER_LID = 0.8  # 아래 눈꺼풀이 위 눈꺼풀의 몇 배만큼 움직이는지 (1이면 위아래 대칭)
    _CURVE_PEAK = 0.75  # 3차 곡선의 가운데 높이는 조절점 높이의 3/4이다

    @staticmethod
    def _sag(eased: float) -> float:
        return 9.0 * (1 - eased)  # 감을수록 눈꼬리 선이 아래로 처진다

    def iris_center(self) -> QPointF:
        """홍채·동공의 위치. 눈꺼풀 사이로 열린 부분의 한가운데에 둔다 (눈꼬리 선이 아니라).

        위 눈꺼풀과 아래 눈꺼풀이 움직이는 양이 달라서, 눈꼬리 선에 그리면 눈이 아래를 보는 것처럼 보인다.
        """
        e = _ease(self._openness)
        cy = self.height() / 2
        reach = min(self.height() * 0.4, 58.0) * 1.35
        top = -reach * e  # 위 눈꺼풀이 올라간 만큼 (눈꼬리 선 기준)
        bottom = reach * e * self._LOWER_LID
        return QPointF(self.width() / 2, cy + self._sag(e) * self._CURVE_PEAK + (top + bottom) / 2 * self._CURVE_PEAK)

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
        sag = self._sag(e)
        up = cy + sag - reach * e
        down = cy + sag + reach * e * self._LOWER_LID  # 아래 눈꺼풀은 덜 움직인다
        path = QPainterPath()
        path.moveTo(cx - half_w, cy)
        path.cubicTo(cx - half_w * 0.45, up, cx + half_w * 0.45, up, cx + half_w, cy)
        path.cubicTo(cx + half_w * 0.45, down, cx - half_w * 0.45, down, cx - half_w, cy)
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        e = _ease(self._openness)
        center = self.iris_center()
        eye = self.lid_path()

        line = theme.color("accent")  # 윤곽선과 홍채는 포인트 초록, 눈 안쪽은 카드 바탕색
        outline = QPen(line, 5)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(outline)
        painter.setBrush(theme.color("surface"))
        painter.drawPath(eye)

        if e > 0.12:  # 거의 감겼을 때는 홍채를 그리지 않는다
            painter.setClipPath(eye)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(line)
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
    """점 따라가기 화면. 점의 위치는 0~1 정규화 좌표로 받아 영역 크기에 맞춰 그린다. None이면 점을 그리지 않는다.

    점은 물방울이다. 둘레로 물결이 퍼진다(움직임을 줄이면 사라진다). 움직이는 영역을 상자로 두르지 않고, 지나온 자리에 꼬리도 남기지 않는다.
    점이 움직일 때는 점 둘레(옛 자리와 새 자리)만 다시 그려서 프레임이 빠르게 나온다.
    """

    _MARGIN = 18  # 점이 영역 가장자리에 붙지 않게 하는 안쪽 여백
    _RIPPLE_MAX = 16 + 40  # 물결이 가장 크게 퍼졌을 때의 반지름

    def __init__(self) -> None:
        super().__init__()
        self._dot: tuple[float, float] | None = None
        self._time = 0.0
        self._animate = True
        self._dirty = QRect()  # 다음에 다시 그릴 곳(점의 옛 자리 포함)
        self.setMinimumSize(240, 140)

    @property
    def animated(self) -> bool:
        return self._animate

    def set_animate(self, on: bool) -> None:
        """물결을 그릴지. 끄면 점만 그린다."""
        self._animate = on
        self.update()

    def set_dot(self, dot: tuple[float, float] | None, t: float | None = None) -> None:
        """점의 위치를 정한다. t(초)를 함께 주면 그 시각을 기준으로 물결을 그린다."""
        old = self.dot_position()
        self._dot = dot
        if t is not None:
            self._time = t
        new = self.dot_position()
        region = QRect()
        for pos in (old, new):
            if pos is not None:
                region = region.united(self._box(pos))
        if region.isNull():
            self.update()  # 점이 없던 자리에서 없는 자리로: 달라진 것이 없어도 한 번 갱신한다
        else:
            self.update(region)

    def _box(self, pos: QPointF) -> QRect:
        r = int(self._RIPPLE_MAX + 6)
        return QRect(int(pos.x()) - r, int(pos.y()) - r, 2 * r, 2 * r)

    def _map(self, dot: tuple[float, float]) -> QPointF:
        m = self._MARGIN
        w, h = max(1, self.width() - 2 * m), max(1, self.height() - 2 * m)
        return QPointF(m + dot[0] * w, m + dot[1] * h)

    def dot_position(self) -> QPointF | None:
        """화면에 그려지는 점의 위치(위젯 좌표). 점이 없으면 None."""
        return None if self._dot is None else self._map(self._dot)

    def dot_color(self) -> QColor:
        """점의 색. 밝은 바탕에서는 깊은 초록(물), 어두운 바탕에서는 밝은 초록이라 어느 쪽에서도 또렷하다."""
        return theme.color("accent" if theme.is_dark() else "hero")

    def paintEvent(self, _event) -> None:
        pos = self.dot_position()
        if pos is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.dot_color()
        if self._animate:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for k in range(3):  # 물결: 점에서 번져 나가며 사라진다
                phase = (self._time * 0.8 + k / 3) % 1.0
                ring = QColor(color)
                ring.setAlphaF(0.35 * (1 - phase))
                painter.setPen(QPen(ring, 2.5))
                painter.drawEllipse(pos, 16 + 40 * phase, 16 + 40 * phase)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(pos, 14, 14)
        painter.setBrush(theme.color("sand"))
        painter.drawEllipse(pos, 4.5, 4.5)  # 시선을 모을 가운데 점
        painter.end()


class PatternRow(QWidget):
    """점이 그리는 여섯 가지 경로를 작은 그림으로 늘어놓고, 지금 따라가는 경로를 또렷하게 보여 준다."""

    _ICON_W, _ICON_H, _GAP = 44, 30, 8

    def __init__(self) -> None:
        super().__init__()
        self._current: int | None = None
        self.setFixedHeight(self._ICON_H + 6)

    @property
    def current(self) -> int | None:
        return self._current

    def set_current(self, index: int | None) -> None:
        if index != self._current:
            self._current = index
            self.update()

    def icon_path(self, index: int, rect: QRectF) -> QPainterPath:
        """경로 하나를 rect 안에 줄여 그린 선. 점이 움직이는 범위(0.1~0.9)가 rect를 채운다."""
        position = DOT_PATTERNS[index].position
        path = QPainterPath()
        for i in range(61):
            x, y = position(i / 60)
            point = QPointF(rect.left() + (x - 0.1) / 0.8 * rect.width(), rect.top() + (y - 0.1) / 0.8 * rect.height())
            path.moveTo(point) if i == 0 else path.lineTo(point)
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        count = len(DOT_PATTERNS)
        total = count * self._ICON_W + (count - 1) * self._GAP
        left = (self.width() - total) / 2
        for i in range(count):
            color = theme.color("text")
            color.setAlphaF(1.0 if i == self._current else 0.28)
            pen = QPen(color, 2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            rect = QRectF(left + i * (self._ICON_W + self._GAP) + 8, 6, self._ICON_W - 16, self._ICON_H - 8)
            painter.drawPath(self.icon_path(i, rect))
        painter.end()


class ExerciseWindow(QWidget):
    completed = Signal(str, int)  # 운동 이름, 총 시간(초)
    aborted = Signal()

    def __init__(self, speaker: Speaker | None = None, animations: Callable[[], bool] = animations_enabled) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("exercise")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 모서리를 둥글게 직접 그린다
        theme.bind(self, _STYLE)
        theme.on_changed(self._on_theme_changed)
        self.setMinimumSize(*WINDOW_SIZE)
        self.resize(*WINDOW_SIZE)

        self._speaker = speaker
        self._animations = animations
        self._last_phase: Phase | None = None
        self._timeline: BlinkTimeline | LookAwayTimeline | DotFollowTimeline | None = None
        self._running = False  # 중단할 수 있는 상태 (운동이 끝나기 전)
        self._progress = 0.0  # 아래쪽 물의 높이를 정하는 진행(0~1)
        self._wave_t = 0.0
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._on_frame)

        self._eye = EyeWidget()
        self._dots = DotCanvas()
        self._patterns = PatternRow()
        self._tag = QLabel()  # '눈 휴식' / '눈 운동'
        self._tag.setObjectName("tag")
        self._message = QLabel()
        self._message.setObjectName("message")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setMinimumHeight(40)  # 문구가 비는 쉬기 구간에도 눈 모양이 흔들리지 않게 높이를 고정한다
        self._button = QPushButton("중단")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_button)
        self._hint = QLabel()
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setObjectName("hint")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 12 + BAND_MAX)  # 아래는 물이 차오르는 자리만큼 비워 둔다
        layout.setSpacing(10)
        layout.addWidget(self._tag, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._eye, stretch=1)
        layout.addWidget(self._dots, stretch=1)
        layout.addWidget(self._patterns)
        layout.addWidget(self._message)
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

    @property
    def progress(self) -> float:
        """운동의 진행(0~1). 먼 곳 바라보기 동안에는 줄어든다. 아래쪽 물의 높이가 이 값을 따른다."""
        return self._progress

    def start(self, timeline: BlinkTimeline | LookAwayTimeline | DotFollowTimeline) -> None:
        """눈 휴식(깜빡임 + 먼 곳 바라보기) 또는 눈 운동(점 따라가기)을 시작한다. 마우스 커서가 있는 모니터의 가운데에 띄운다."""
        self._timeline = timeline
        is_blink = timeline.exercise == EXERCISE_BLINK
        self._tag.setText("눈 휴식" if is_blink else "눈 운동")
        self._eye.set_openness(1.0)
        self._eye.setVisible(is_blink)
        self._dots.setVisible(not is_blink)
        self._patterns.setVisible(not is_blink)
        self._dots.set_animate(self._animations())
        self._dots.set_dot(None)
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
        self._apply(self._timeline.step_at(0), 0.0)
        self.show()
        self.raise_()
        self.activateWindow()  # Esc 키를 받기 위해 포커스를 가져온다
        self._timer.setInterval(frame_interval_ms(self._refresh_hz()))  # 모니터 주사율에 맞춘다
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
        seconds = self._elapsed.elapsed() / 1000.0
        step = self._timeline.step_at(seconds)
        self._apply(step, seconds)
        if step.finished and self._running:
            # 운동을 마쳤다. 깜빡임 휴식은 먼 곳 바라보기 중에 닫아도 완료로 센다.
            self._running = False
            self._button.setText("닫기")
            self._hint.setText("Esc 키로 닫을 수 있어요")
            self.completed.emit(self._timeline.exercise, self._timeline.total_seconds)
        if step.done:
            self.close()  # 카운트다운이 끝나면 저절로 닫는다

    def _apply(self, step: ExerciseStep, seconds: float) -> None:
        if step.eye_openness is not None:
            self._eye.set_openness(step.eye_openness)
        self._dots.set_dot(step.dot, seconds)
        self._patterns.set_current(step.pattern)
        text = step.message
        if step.countdown:
            text = f"{text} · {step.countdown}"
        self._message.setText(text)
        self._progress = min(1.0, max(0.0, step.progress))
        self._wave_t = seconds if self._animations() else 0.0
        self.update(0, max(0, self.height() - BAND_MAX - 24), self.width(), BAND_MAX + 24)  # 아래쪽 물만 다시 그린다
        if step.phase is not self._last_phase:
            self._last_phase = step.phase
            if self._speaker is not None:
                self._speaker.cue(step.phase)

    def _on_theme_changed(self) -> None:
        self.update()

    def _refresh_hz(self) -> float | None:
        """창이 놓인 모니터의 주사율(Hz). 알 수 없으면 None."""
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        return screen.refreshRate() if screen else None

    def _screen_area(self) -> QRect:
        """마우스 커서가 있는 모니터에서 작업 표시줄을 뺀 영역."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    # ---- 그리기 ----

    def water_paths(self) -> tuple[QPainterPath, QPainterPath]:
        """(아래쪽 물, 수면의 선). 높이는 진행에 따라 BAND_MIN에서 BAND_MAX까지 차오른다."""
        band = BAND_MIN + (BAND_MAX - BAND_MIN) * self._progress
        margin, height = wave_margin(WAVE_WEAK), max(1, self.height())
        level = (band + margin) / (height + 2 * margin)  # 수면이 창 바닥에서 band(px) 위에 놓이도록 (water_paths의 높이 비율은 위아래 여백을 포함한다)
        return water_paths(self.width(), height, level, self._wave_t, WAVE_WEAK)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), _RADIUS, _RADIUS)
        painter.setClipPath(outline)  # 둥근 모서리 밖은 그리지 않아 투명하게 남는다
        painter.fillRect(self.rect(), theme.color("paper"))
        front, line = self.water_paths()
        painter.fillPath(front, theme.color("hero"))
        foam = theme.color("sand")
        foam.setAlpha(WAVE_WEAK.foam_alpha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(foam, WAVE_WEAK.foam_width))
        painter.drawPath(line)
        painter.end()
