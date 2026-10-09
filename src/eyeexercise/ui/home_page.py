"""홈 화면: 20분 타이머를 차오르는 물로 보여 준다.

물은 시간이 갈수록 바닥에서 차오르고, 가득 차면 쉴 시간이다. 수면은 파도가 잔잔하게 일렁인다. 물 위의 글자는 짙은 색이고,
물에 잠긴 글자는 모래색이라 수면이 글자를 지나갈 때 색이 바뀐다(물 안과 밖을 두 번 그린다).
수위·파도·눈 아이콘 줄의 계산은 core/tide가 하고, 오늘의 요약은 core/home과 core/stats가 한다. 이 모듈은 그리기만 한다.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, tzinfo

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.formatting import home_timer
from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.home import HomeSummary, home_summary
from eyeexercise.core.scheduler import State
from eyeexercise.core.settings import Settings
from eyeexercise.core.stats import format_usage
from eyeexercise.core.tide import (
    WAVE_MID,
    EyeRow,
    WaveStyle,
    back_offset,
    display_level,
    eye_row,
    wave_margin,
    wave_offset,
    water_level,
)
from eyeexercise.core.usage import UsageLog
from eyeexercise.platform.win_motion import animations_enabled
from eyeexercise.ui import theme

LIVE_REFRESH_MS = 30_000  # 보는 동안 스크린 타임·달성률이 따라가도록 새로 그리는 간격
FRAME_MS = 33  # 물결을 다시 그리는 간격(초당 약 30번)
LEVEL_EASE = 0.12  # 수위가 목표로 다가가는 정도(프레임마다). 상태가 바뀌어도 물이 갑자기 뛰지 않는다
WAVE_STEP = 12  # 수면 곡선을 이 간격(px)마다 계산한다

MARGIN_X = 36
MARGIN_TOP = 28
MARGIN_BOTTOM = 26
BUTTON_ROW_HEIGHT = 44
ROW_GAP = 14
EYES_BLOCK_HEIGHT = 44  # 눈 아이콘 줄(이름 + 아이콘)의 높이
EYE_W, EYE_H, EYE_GAP = 26.0, 20.0, 5.0
MAX_EYES = 24
CLOCK_MAX_PX = 260
SIDE_RATIO = 0.07  # 넓은 창에서 좌우 여백이 창 너비의 이만큼 이상이다
CONTENT_MAX_WIDTH = 1180  # 글자가 모이는 영역의 최대 너비. 아주 넓은 창에서는 이 영역이 가운데에 놓이고 물만 창 전체를 채운다
MAX_SCALE = 1.25  # 큰 창에서 글자·아이콘을 키우는 최대 배율. 더 키우면 그저 확대한 것처럼 투박해 보인다

_STYLE = """
#heroRest { background: $sand; color: $ink; border: 2px solid $ink; border-radius: 8px; padding: 8px 20px; font-size: $fs_body; font-weight: 900; }
#heroRest:hover { background: #ffffff; }
#heroRest:disabled { background: rgba(242, 227, 179, 110); color: $text_faint; border-color: $text_faint; }
#heroSnooze { background: $surface; color: $text; border: 2px solid $text; border-radius: 8px; padding: 8px 18px; font-size: $fs_body; font-weight: 900; }
#heroSnooze:hover { background: $hover; }
#heroSnooze:disabled { background: $surface; color: $text_faint; border-color: $text_faint; }
"""

WIDEST_CLOCK = "00:00"  # 시계 글자 크기를 정할 때 쓰는 기준 글자(가장 넓은 모양). 지금 보이는 숫자가 바뀌어도 크기는 그대로다
WIDEST_STAT = "24시간 59분"

STAT_TITLES = (("screen", "오늘 스크린 타임"), ("longest", "최장 연속 사용"), ("exercise", "오늘 눈 운동"))


@dataclass(frozen=True)
class _Geometry:
    clock_px: float
    kicker: QRectF
    clock: QRectF
    sub: QRectF
    stats: list[QRectF]  # STAT_TITLES와 같은 순서. 이름과 값이 이 안에 두 줄로 들어간다
    eyes_label: QRectF
    eyes_top: float


class HomePage(QWidget):
    rest_requested = Signal()
    snooze_requested = Signal()
    exercise_requested = Signal()
    pause_toggled = Signal()  # 일시정지 중이면 재개, 아니면 일시정지

    def __init__(
        self,
        events_provider: Callable[[], Iterable[HistoryEvent]],
        now: Callable[[], datetime] = SystemClock().now,
        usage_provider: Callable[[], UsageLog] | None = None,
        settings_provider: Callable[[], Settings] = Settings,
        tz: tzinfo | None = None,
        parent: QWidget | None = None,
        animations: Callable[[], bool] = animations_enabled,
        motion_clock: Callable[[], float] = time.monotonic,
        wave: WaveStyle = WAVE_MID,
    ) -> None:
        super().__init__(parent)
        self._events = events_provider
        self._now = now
        self._usage = usage_provider or UsageLog
        self._settings = settings_provider
        self._tz = tz
        self._animations = animations
        self._motion_clock = motion_clock
        self._wave = wave
        self._motion = animations()
        self._t0 = motion_clock()
        self._wave_t = 0.0
        self.setObjectName("home")
        self.setMinimumSize(560, 440)
        theme.bind(self, _STYLE)
        theme.on_changed(self._on_theme_changed)

        # 그려지는 값
        self._kicker = ""
        self._clock = ""
        self._sub = ""
        self._stats: dict[str, str] = {key: "" for key, _title in STAT_TITLES}
        self._eye_label = ""
        self._eyes = EyeRow(0, 0, 0)
        self._target = 0.0
        self._level = 0.0

        # 버튼은 진짜 버튼이라 키보드로도 누를 수 있다. 물 위와 물 속 어디에서도 보이도록 바탕과 테두리를 가진다.
        self._rest_button = QPushButton("지금 휴식")
        self._rest_button.setObjectName("heroRest")
        self._exercise_button = QPushButton("지금 운동")
        self._exercise_button.setObjectName("heroSnooze")  # 보조 버튼 모양
        self._pause_button = QPushButton("일시정지")
        self._pause_button.setObjectName("heroSnooze")
        self._snooze_button = QPushButton()
        self._snooze_button.setObjectName("heroSnooze")
        for button in (self._rest_button, self._exercise_button, self._pause_button, self._snooze_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rest_button.clicked.connect(self.rest_requested)
        self._exercise_button.clicked.connect(self.exercise_requested)
        self._pause_button.clicked.connect(self.pause_toggled)
        self._snooze_button.clicked.connect(self.snooze_requested)
        self._buttons = (self._rest_button, self._exercise_button, self._pause_button, self._snooze_button)
        self._button_scale = 1.0
        buttons = self._button_row = QHBoxLayout()
        buttons.setSpacing(10)
        for button in self._buttons:
            buttons.addWidget(button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN_X, MARGIN_TOP, MARGIN_X, MARGIN_BOTTOM)
        layout.addStretch()
        layout.addLayout(buttons)

        self._live = QTimer(self)
        self._live.setInterval(LIVE_REFRESH_MS)
        self._live.timeout.connect(self._on_live_tick)
        self._frame = QTimer(self)
        self._frame.setInterval(FRAME_MS)
        self._frame.setTimerType(Qt.TimerType.PreciseTimer)  # 기본 타이머는 Windows에서 15ms 단위로 어긋나 물결이 끊겨 보인다
        self._frame.timeout.connect(self._on_frame)

        self.set_timer(State.RUNNING, None, None, None)
        self.refresh()

    # ---- 읽기 (테스트·접근성) ----

    @property
    def kicker_text(self) -> str:
        return self._kicker

    @property
    def clock_text(self) -> str:
        return self._clock

    @property
    def sub_text(self) -> str:
        return self._sub

    @property
    def eye_label(self) -> str:
        return self._eye_label

    @property
    def eyes(self) -> EyeRow:
        return self._eyes

    @property
    def water_target(self) -> float:
        """물이 차오르려는 목표 높이(0~1)."""
        return self._target

    @property
    def water_level(self) -> float:
        """지금 그려지는 물의 높이(0~1). 애니메이션이 켜져 있으면 목표로 서서히 다가간다."""
        return self._level

    def stat(self, key: str) -> str:
        return self._stats[key]

    def _scale(self) -> float:
        """창이 기본보다 크면 글자·아이콘·간격을 조금 키운다(최대 1.25배)."""
        return max(1.0, min(MAX_SCALE, min(self.width() / 880, self.height() / 620)))

    def _weight(self) -> QFont.Weight:
        """큰 숫자·요약 값의 굵기. 창이 클수록 한 단계씩 가늘어져서, 큰 창에서 글자가 둔해 보이지 않는다."""
        k = self._scale()
        return QFont.Weight.Black if k < 1.08 else QFont.Weight.ExtraBold if k < 1.18 else QFont.Weight.Bold

    def _fs(self, name: str) -> float:
        """테마 글자 크기(px)를 지금 배율로 키운 값."""
        return theme.FONT_SIZES[name] * self._scale()

    def _side(self) -> float:
        """글자와 버튼이 놓이는 좌우 여백. 창이 넓을수록 늘어나고, 글자 영역은 최대 너비를 넘지 않는다."""
        return max(float(MARGIN_X), self.width() * SIDE_RATIO, (self.width() - CONTENT_MAX_WIDTH) / 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        side, k = round(self._side()), self._scale()
        self.layout().setContentsMargins(side, round(MARGIN_TOP * k), side, round(MARGIN_BOTTOM * k))
        if k != self._button_scale:  # 버튼도 글자와 같은 비율로 키운다(색은 테마 스타일시트가, 크기는 이 스타일이 정한다)
            self._button_scale = k
            size = f"font-size: {round(self._fs('fs_body'))}px; padding: {round(8 * k)}px {round(20 * k)}px; border-radius: {round(8 * k)}px;"
            for button in self._buttons:
                button.setStyleSheet(size)
            self._button_row.setSpacing(round(10 * k))

    # ---- 타이머 ----

    def set_timer(self, state: State, remaining: float | None, target: float | None, activity: str | None) -> None:
        """컨트롤러가 1초마다 알려 주는 상태·남은 시간으로 타이머와 물의 높이를 정한다."""
        self._kicker, self._clock = home_timer(state, remaining, activity)
        self._sub = f"{self._settings().interval_minutes}분마다 눈을 쉬어 줘요"
        self._target = water_level(state, remaining, target)
        if not self._motion:
            self._level = self._target
        startable = state in (State.RUNNING, State.SNOOZED, State.DUE)
        self._rest_button.setEnabled(startable)
        self._exercise_button.setEnabled(startable)
        self._pause_button.setText("재개" if state is State.PAUSED else "일시정지")
        self._pause_button.setEnabled(state in (State.RUNNING, State.SNOOZED, State.PAUSED))
        self._snooze_button.setText(f"{self._settings().snooze_minutes}분 미루기")
        self._snooze_button.setVisible(state is State.DUE)  # 미루기는 알림이 떠 있을 때만 할 수 있다
        self._describe()
        self.update()

    # ---- 오늘 요약 ----

    def _on_live_tick(self) -> None:
        if self.isVisible():
            self._motion = self._animations()  # Windows의 애니메이션 설정이 바뀌었을 수 있다
            self._sync_frame_timer()
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._live.start()
        self._motion = self._animations()
        self._sync_frame_timer()
        self.refresh()  # 숨겨진 동안 쌓인 기록을 보여 준다

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._live.stop()
        self._frame.stop()  # 보이지 않는 동안에는 다시 그리지 않는다

    def _sync_frame_timer(self) -> None:
        if self._motion and self.isVisible():
            if not self._frame.isActive():
                self._frame.start()
        else:
            self._frame.stop()
            self._level = self._target
            self._wave_t = 0.0
            self.update()

    def refresh(self) -> None:
        settings = self._settings()
        summary = home_summary(
            list(self._events()), self._usage(), self._now(), settings.interval_minutes, settings.exercises.daily_goal, self._tz
        )
        self._draw_summary(summary)

    def _draw_summary(self, s: HomeSummary) -> None:
        self._stats["screen"] = format_usage(s.screen_seconds)
        self._stats["longest"] = format_usage(s.longest_seconds) if s.longest_seconds > 0 else "–"
        self._stats["exercise"] = f"{s.exercises}/{s.exercise_goal}회" if s.exercise_goal > 0 else f"{s.exercises}회"
        self._eyes = eye_row(s.rests, s.recommended, MAX_EYES)
        if s.recommended > 0:
            rate = f" · {round(s.rate * 100)}%" if s.rate is not None else ""
            self._eye_label = f"오늘 눈 휴식 {s.rests}회 / 권장 {s.recommended}회{rate}"
        else:
            self._eye_label = f"오늘 눈 휴식 {s.rests}회" if s.rests > 0 else "사용 시간이 짧아요"
        self._describe()
        self.update()

    def _describe(self) -> None:
        """그림으로 그린 글자는 화면 읽기 프로그램이 읽지 못하므로 같은 내용을 설명으로 달아 둔다."""
        stats = ", ".join(f"{title} {self._stats[key]}" for key, title in STAT_TITLES)
        self.setAccessibleName("홈")
        self.setAccessibleDescription(f"{self._kicker} {self._clock}. {self._eye_label}. {stats}")

    # ---- 애니메이션 ----

    def _on_frame(self) -> None:
        self._wave_t = self._motion_clock() - self._t0
        diff = self._target - self._level
        self._level = self._target if abs(diff) < 0.0005 else self._level + diff * LEVEL_EASE
        self.update()

    def _on_theme_changed(self) -> None:
        self.update()

    # ---- 수면 ----

    def water_paths(self) -> tuple[QPainterPath, QPainterPath, QPainterPath]:
        """(앞쪽 물, 뒤쪽 옅은 물결, 앞쪽 수면의 선). 수위 0%와 100%에서도 빈틈이 없도록 위아래로 여백을 둔다."""
        w, h = float(self.width()), float(self.height())
        margin = wave_margin(self._wave)
        base = -margin + (h + 2 * margin) * (1 - display_level(self._level))
        t = self._wave_t
        xs = [min(float(x), w) for x in range(0, int(w) + WAVE_STEP, WAVE_STEP)]
        line = QPainterPath(QPointF(xs[0], base + wave_offset(xs[0], t, w, self._wave)))
        back = QPainterPath(QPointF(xs[0], base + back_offset(xs[0], t, w, self._wave)))
        for x in xs[1:]:
            line.lineTo(x, base + wave_offset(x, t, w, self._wave))
            back.lineTo(x, base + back_offset(x, t, w, self._wave))
        front = QPainterPath(line)
        for path in (front, back):
            path.lineTo(w, h + margin)
            path.lineTo(0, h + margin)
            path.closeSubpath()
        return front, back, line

    # ---- 그리기 ----

    def _font(self, px: float, weight: QFont.Weight) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(1, round(px)))
        font.setWeight(weight)
        return font

    def _geometry(self) -> _Geometry:
        w, h = float(self.width()), float(self.height())
        k = self._scale()
        eyes_block = EYES_BLOCK_HEIGHT * k
        eyes_top = h - MARGIN_BOTTOM * k - BUTTON_ROW_HEIGHT * k - ROW_GAP * k - eyes_block
        mid_top, mid_bottom = MARGIN_TOP * k, eyes_top - ROW_GAP * k
        mid_h = max(1.0, mid_bottom - mid_top)
        side = self._side()
        right = w - side

        stat_value, stat_title = self._font(self._fs("fs_stat"), self._weight()), self._font(self._fs("fs_caption"), QFont.Weight.ExtraBold)
        value_metrics, title_metrics = QFontMetricsF(stat_value), QFontMetricsF(stat_title)
        # 요약 폭도 가장 넓은 값(예: 24시간 59분) 기준으로 잡아, 값이 바뀌어도 시계 크기와 글자 자리가 흔들리지 않는다
        stats_w = max(value_metrics.horizontalAdvance(WIDEST_STAT), *(title_metrics.horizontalAdvance(title) for _key, title in STAT_TITLES))
        stat_h = title_metrics.height() + value_metrics.height()
        gap = 14.0 * k
        stats_total = 3 * stat_h + 2 * gap
        stats = [
            QRectF(right - stats_w, mid_top + (mid_h - stats_total) / 2 + i * (stat_h + gap), stats_w, stat_h) for i in range(3)
        ]

        probe = QFontMetricsF(self._font(100, self._weight())).horizontalAdvance(WIDEST_CLOCK) or 300.0  # 가장 넓은 시계(00:00) 기준
        avail = max(60.0, right - side - stats_w - 28 * k)
        clock_px = max(24.0, min(CLOCK_MAX_PX * k, avail / probe * 100, mid_h * 0.62))
        small = QFontMetricsF(self._font(self._fs("fs_small"), QFont.Weight.Bold)).height()
        kicker_h = QFontMetricsF(self._font(self._fs("fs_heading"), QFont.Weight.ExtraBold)).height()
        # 큰 숫자는 글꼴 줄 높이가 아니라 숫자 모양 높이로 자리를 잡아, 위 글자와 아래 글자가 숫자에 가깝게 붙는다
        digit_h = QFontMetricsF(self._font(clock_px, self._weight())).tightBoundingRect("0").height() or clock_px * 0.72
        above, below = 8.0 * k, 12.0 * k
        total = kicker_h + above + digit_h + below + small
        top = mid_top + (mid_h - total) / 2
        left = side
        return _Geometry(
            clock_px,
            QRectF(left, top, avail, kicker_h),
            QRectF(left, top + kicker_h + above, avail, digit_h),  # 아래 변이 숫자가 놓이는 기준선
            QRectF(left, top + kicker_h + above + digit_h + below, avail, small),
            stats,
            QRectF(left, eyes_top, w - 2 * side, 20.0),
            eyes_top,
        )

    def _paint_content(self, painter: QPainter, color: QColor) -> None:
        """글자와 아이콘을 color로 그린다. 물 밖(짙은색)과 물 안(모래색)에서 한 번씩 부른다."""
        g = self._geometry()
        faded = QColor(color)
        faded.setAlphaF(0.78)

        painter.setPen(color)
        painter.setFont(self._font(self._fs("fs_heading"), QFont.Weight.ExtraBold))
        painter.drawText(g.kicker, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._kicker)
        if self._clock == "–":  # 시간을 세지 않는 동안의 자리 표시. 굵은 큰 글자로 그리면 막대처럼 보여서 작고 옅게 그린다
            painter.setPen(faded)
            painter.setFont(self._font(g.clock_px * 0.4, QFont.Weight.Bold))
        else:
            painter.setFont(self._font(g.clock_px, self._weight()))
        painter.drawText(QPointF(g.clock.left(), g.clock.bottom()), self._clock)  # 기준선에 맞춰 그린다
        painter.setPen(faded)
        painter.setFont(self._font(self._fs("fs_small"), QFont.Weight.Bold))
        painter.drawText(g.sub, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._sub)

        for (key, title), rect in zip(STAT_TITLES, g.stats, strict=True):
            title_h = QFontMetricsF(self._font(self._fs("fs_caption"), QFont.Weight.ExtraBold)).height()
            painter.setPen(faded)
            painter.setFont(self._font(self._fs("fs_caption"), QFont.Weight.ExtraBold))
            painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), title_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, title)
            painter.setPen(color)
            painter.setFont(self._font(self._fs("fs_stat"), self._weight()))
            painter.drawText(
                QRectF(rect.left(), rect.top() + title_h, rect.width(), rect.height() - title_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._stats[key],
            )

        painter.setPen(faded)
        painter.setFont(self._font(self._fs("fs_caption"), QFont.Weight.ExtraBold))
        painter.drawText(g.eyes_label, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._eye_label)
        self._paint_eyes(painter, color, g)

    def _paint_eyes(self, painter: QPainter, color: QColor, g: _Geometry) -> None:
        count = self._eyes.closed + self._eyes.open
        if count == 0 and self._eyes.hidden == 0:
            return
        side = self._side()
        room = self.width() - 2 * side - (36 if self._eyes.hidden else 0)
        k = self._scale()
        full_w, gap = EYE_W * k, EYE_GAP * k
        step = min(full_w + gap, room / max(1, count))
        scale = min(1.0, step / (full_w + gap))
        w, h = full_w * scale, EYE_H * k * scale
        y = g.eyes_top + EYES_BLOCK_HEIGHT * k - h - 2
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(count):
            self._draw_eye(painter, color, side + i * step, y, w, h, closed=i < self._eyes.closed)
        if self._eyes.hidden:
            painter.setPen(color)
            painter.setFont(self._font(self._fs("fs_caption"), QFont.Weight.ExtraBold))
            painter.drawText(QRectF(side + count * step + 4, y, 40, h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"+{self._eyes.hidden}")

    @staticmethod
    def _draw_eye(painter: QPainter, color: QColor, x: float, y: float, w: float, h: float, closed: bool) -> None:
        """26×20 칸에 그린 눈을 (w, h) 크기로 줄여 그린다. 감은 눈은 속눈썹이 있는 곡선, 뜬 눈은 눈동자가 있는 눈 모양이다."""
        sx, sy = w / EYE_W, h / EYE_H

        def p(px: float, py: float) -> QPointF:
            return QPointF(x + px * sx, y + py * sy)

        pen = QPen(color, 2.2 * min(sx, sy))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        if closed:
            path.moveTo(p(3, 7))
            path.quadTo(p(13, 17), p(23, 7))
            for x1, y1, x2, y2 in ((8, 13, 6, 17), (13, 15, 13, 19), (18, 13, 20, 17)):
                path.moveTo(p(x1, y1))
                path.lineTo(p(x2, y2))
            painter.drawPath(path)
        else:
            path.moveTo(p(2, 10))
            path.quadTo(p(13, 0), p(24, 10))
            path.quadTo(p(13, 20), p(2, 10))
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(p(13, 10), 2.6 * sx, 2.6 * sy)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), theme.color("paper"))
        front, back, line = self.water_paths()
        water = theme.color("hero")
        soft = QColor(water)
        soft.setAlpha(66)
        painter.fillPath(back, soft)  # 뒤쪽 옅은 물결은 글자 아래에 깔아서 짙은 글자가 흐려지지 않게 한다
        self._paint_content(painter, theme.color("text"))  # 물 밖의 글자. 아래의 물이 이 글자를 덮는다
        painter.fillPath(front, water)
        painter.save()
        painter.setClipPath(front)
        self._paint_content(painter, theme.color("sand"))  # 물에 잠긴 글자
        painter.restore()
        foam = theme.color("sand")
        foam.setAlpha(self._wave.foam_alpha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(foam, self._wave.foam_width))
        painter.drawPath(line)
        painter.end()
