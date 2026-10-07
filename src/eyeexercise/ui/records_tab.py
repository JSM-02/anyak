"""기록 탭. 기간 전환, 큰 숫자 요약, 막대 차트, 하이라이트 카드, 날짜별 표를 넓은 데스크톱 화면에 배치한다.

위쪽 전환으로 '눈 휴식'(마친 횟수)과 '스크린 타임'(PC 사용 시간)을 오간다. 둘은 같은 화면 구조를 쓴다. 눈 운동은 오늘 요약 카드와 하루 흐름에 횟수로만 나온다.
계산은 모두 core/stats가 한다. 이 모듈은 그 결과를 그리기만 한다.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QToolTip,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.history import ACTIVITY_EXERCISE, ACTIVITY_REST, HistoryEvent
from eyeexercise.core.stats import (
    TREND_SYMBOLS,
    Period,
    PeriodCompare,
    build_buckets,
    build_usage_buckets,
    can_go_forward,
    compare_exercise_period,
    compare_today,
    events_of,
    compare_usage_period,
    format_duration,
    format_usage,
    format_usage_axis,
    rest_stats,
    highlights_with_compare,
    nice_axis_max,
    nice_usage_axis,
    previous_label,
    range_caption,
    range_title,
    shift_anchor,
    summarize_range,
    summarize_usage,
    timeline_days,
    usage_highlights_with_compare,
    usage_parts,
)
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui import theme

_PERIOD_LABELS = ((Period.DAY, "일"), (Period.WEEK, "주"), (Period.MONTH, "월"))
RECENT_COLLAPSED = 7  # 처음에 보여 주는 하루 타임라인 일수
RECENT_EXPANDED = 30  # '더 보기'를 눌렀을 때
LIVE_REFRESH_MS = 30_000  # 스크린 타임을 보는 동안 숫자가 따라가도록 새로 그리는 간격


class Mode(Enum):
    REST = "rest"
    SCREEN_TIME = "screen_time"


_MODE_LABELS = ((Mode.REST, "눈 휴식"), (Mode.SCREEN_TIME, "스크린 타임"))

_STYLE = """
#records, #recordsContent { background: $bg; }
#records QLabel { background: transparent; }
#pageTitle { font-size: $fs_title; font-weight: bold; }
#segment { background: $hover; border-radius: 7px; }
#segment QPushButton {
    background: transparent; border: none; border-radius: 5px; padding: 5px 18px; color: $text_body;
}
#segment QPushButton:checked { background: $surface; color: $text; font-weight: bold; }
#nav QPushButton { background: transparent; border: none; font-size: $fs_icon; color: $accent; padding: 0 10px; }
#nav QPushButton:disabled { color: $disabled; }
#navTitle { font-size: $fs_body; font-weight: bold; min-width: 80px; }
#card { background: $surface; border: 1px solid $border; border-radius: 8px; }
#kicker { font-size: $fs_small; color: $text_secondary; font-weight: bold; }
#caption { font-size: $fs_small; color: $text_secondary; }
#cardLabel { font-size: $fs_caption; color: $text_secondary; }
#cardValue { font-size: $fs_title; font-weight: bold; }
#cardDetail { font-size: $fs_caption; color: $text_secondary; }
#cardCompare { font-size: $fs_caption; color: $text_body; padding-top: 4px; }
#todayTitle { font-size: $fs_caption; color: $text_secondary; font-weight: bold; }
#todayValue { font-size: $fs_stat; font-weight: bold; }
#todayLine { font-size: $fs_small; color: $text_body; }
#todayLineSub { font-size: $fs_caption; color: $text_muted; }
#compareLine { font-size: $fs_small; color: $text_body; }
#compareLineSub { font-size: $fs_caption; color: $text_muted; }
#legendItem { font-size: $fs_caption; color: $text_secondary; padding: 0 6px; }
#sectionTitle { font-size: $fs_heading; font-weight: bold; }
#moreButton { background: transparent; border: none; color: $accent; padding: 2px 6px; }
#moreButton:hover { text-decoration: underline; }
"""


class BarChart(QWidget):
    """막대 차트. 막대를 누르면 그 막대를 선택하고, 한 번 더 누르면 해제한다.

    값과 세로축은 밖에서 정해 준다. 완료 횟수(`set_data`)와 사용 시간(`set_series`)에 같이 쓴다.
    """

    selection_changed = Signal(int)  # 선택한 막대 번호. 해제하면 -1

    _LEFT, _RIGHT, _TOP, _BOTTOM = 6, 56, 10, 24  # 안쪽 여백 (오른쪽은 세로축 글자 자리)

    def __init__(self) -> None:
        super().__init__()
        self._buckets: Sequence = []
        self._values: list[float] = []
        self._axis: float = 4
        self._format: Callable[[float], str] = lambda v: str(int(v))
        self._empty_text = "기록이 없어요"
        self._selected = -1
        self.setMinimumHeight(200)

    def set_series(
        self,
        buckets: Sequence,
        values: Sequence[float],
        axis_max: float,
        axis_format: Callable[[float], str],
        selected: int = -1,
        empty_text: str = "기록이 없어요",
    ) -> None:
        self._buckets = buckets
        self._values = list(values)
        self._axis = axis_max
        self._format = axis_format
        self._empty_text = empty_text
        self._selected = selected
        self.update()

    def set_data(self, buckets: Sequence, selected: int = -1) -> None:
        """완료 횟수 막대 (운동 기록)."""
        values = [b.completed for b in buckets]
        self.set_series(buckets, values, nice_axis_max(max(values, default=0)), lambda v: str(int(v)), selected)

    @property
    def axis_max(self) -> float:
        return self._axis

    def _plot(self) -> QRectF:
        return QRectF(
            self._LEFT, self._TOP, max(1, self.width() - self._LEFT - self._RIGHT), max(1, self.height() - self._TOP - self._BOTTOM)
        )

    def index_at(self, x: float) -> int:
        """가로 위치 x에 있는 막대 번호. 없으면 -1."""
        if not self._buckets:
            return -1
        plot = self._plot()
        i = int((x - plot.left()) // (plot.width() / len(self._buckets)))
        return i if 0 <= i < len(self._buckets) and plot.left() <= x <= plot.right() else -1

    def bar_rect(self, i: int) -> QRectF:
        """i번째 막대의 사각형. 높이는 값에 비례한다."""
        plot = self._plot()
        slot = plot.width() / len(self._buckets)
        width = min(slot * 0.62, 34.0)
        height = plot.height() * self._values[i] / self._axis
        return QRectF(plot.left() + slot * i + (slot - width) / 2, plot.bottom() - height, width, height)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        i = self.index_at(event.position().x())
        if i < 0 or self._buckets[i].is_future:
            return
        self._selected = -1 if self._selected == i else i
        self.selection_changed.emit(self._selected)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        axis = self._axis

        small = QFont(self.font())
        small.setPixelSize(11)  # 차트 눈금·라벨 전용 크기
        painter.setFont(small)
        grid = QPen(theme.color("grid"), 1)
        for value in (0, axis / 2, axis):
            y = plot.bottom() - plot.height() * value / axis
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(theme.color("text_muted"))
            painter.drawText(
                QRectF(plot.right() + 4, y - 8, self._RIGHT - 4, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._format(value),
            )

        if not self._buckets:
            painter.end()
            return
        if not any(self._values):
            painter.setPen(theme.color("text_muted"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)

        slot = plot.width() / len(self._buckets)
        dim = self._selected >= 0
        for i, b in enumerate(self._buckets):
            if b.show_label:
                font = QFont(small)
                font.setBold(b.is_current)
                painter.setFont(font)
                painter.setPen(theme.color("accent") if b.is_current else theme.color("text_muted"))
                painter.drawText(
                    QRectF(plot.left() + slot * i - 8, plot.bottom() + 4, slot + 16, 16),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    b.label,
                )
            if b.is_future or self._values[i] <= 0:
                continue
            color = theme.color("accent")
            if dim and i != self._selected:
                color.setAlpha(90)  # 선택하지 않은 막대는 흐리게
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(self.bar_rect(i), 4, 4)
        painter.end()


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def _segmented(labels: Iterable[str]) -> tuple[QFrame, list[QPushButton], QButtonGroup]:
    """분할 버튼 (선택한 것만 흰 바탕으로 보인다)."""
    frame = QFrame()
    frame.setObjectName("segment")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(3, 3, 3, 3)
    layout.setSpacing(0)
    group = QButtonGroup(frame)
    buttons = []
    for text in labels:
        button = QPushButton(text)
        button.setCheckable(True)
        group.addButton(button)
        layout.addWidget(button)
        buttons.append(button)
    return frame, buttons, group


def arrow_line(trend: str, line: str) -> str:
    """비교 문구 앞에 ▲▼– 를 붙인다. "기록이 없어요"처럼 비교할 수 없을 때는 붙이지 않는다."""
    return line if "기록이 없어요" in line else f"{TREND_SYMBOLS[trend]} {line}"


def _bucket_caption(bucket) -> str:
    """막대를 눌렀을 때 큰 숫자 아래 문구: 그 막대의 건너뜀·미룸. 아무 기록이 없으면 안내."""
    parts = []
    if bucket.skipped:
        parts.append(f"건너뜀 {bucket.skipped}회")
    if bucket.snoozed:
        parts.append(f"미룸 {bucket.snoozed}회")
    if parts:
        return " · ".join(parts)
    return "" if bucket.completed else "휴식 기록 없음"


def activity_summary(day) -> str:
    """하루 줄 오른쪽 둘째 줄: "휴식 18회 · 운동 2회 · 건너뜀 3회". 건너뜀·미룸은 있을 때만."""
    parts = [f"휴식 {day.rests}회", f"운동 {day.exercises}회"]
    if day.skipped:
        parts.append(f"건너뜀 {day.skipped}회")
    if day.snoozed:
        parts.append(f"미룸 {day.snoozed}회")
    return " · ".join(parts)


class TimelineChart(QWidget):
    """하루 흐름. 날짜마다 한 줄, 시간대(1시간)마다 한 칸인 격자다.

    칸의 초록이 진할수록 그 시간대에 스크린 타임이 길고, 칸 안의 숫자는 그 시간대에 마친 눈 운동 횟수다.
    눈 휴식은 20분마다라 칸에 쓰면 너무 많아지므로 줄 오른쪽 요약에만 센다. 칸에 마우스를 올리면 자세한 내용이 뜬다.
    """

    _LABEL_W = 92  # 왼쪽 날짜 칸
    _INFO_W = 220  # 오른쪽 요약 칸
    _HEAD_H = 24  # 위쪽 시간 글자
    _ROW_H = 36
    _CELL_H = 26
    _GAP = 14  # 칸 사이 간격
    _CELL_GAP = 2  # 격자 칸 사이 틈
    _DEFAULT_START = 6  # 가로축은 보통 6시부터 자정까지. 더 이른 기록이 있으면 그 시각부터
    _TICK_HOURS = 3  # 시각 글자는 3시간마다

    def __init__(self) -> None:
        super().__init__()
        self._days: list = []
        self._start_hour = self._DEFAULT_START
        self._empty_text = "아직 기록이 없어요"
        self.setMouseTracking(True)
        self.setMinimumWidth(400)
        self._fit_height()

    def set_days(self, days: Sequence) -> None:
        self._days = list(days)
        self._start_hour = self._axis_start()
        self._fit_height()
        self.update()

    def _axis_start(self) -> int:
        """가로축이 시작하는 시(時). 낮 시간을 넓게 보이려고 기본 6시부터이고, 더 이른 기록이 있으면 그 시각부터 보인다."""
        earliest = self._DEFAULT_START
        for day in self._days:
            used = [h for h, seconds in enumerate(day.hours) if seconds > 0]
            if used:
                earliest = min(earliest, used[0])
            if day.marks:
                earliest = min(earliest, int(day.marks[0].minute // 60))
        return earliest - earliest % self._TICK_HOURS  # 시각 글자와 맞게 3의 배수로 내린다

    def _fit_height(self) -> None:
        self.setFixedHeight(self._HEAD_H + max(1, len(self._days)) * self._ROW_H + 4)

    def grid_rect(self) -> QRectF:
        """격자 전체(날짜 줄들이 공통으로 쓰는 가로 범위)."""
        left = self._LABEL_W + self._GAP
        right = self.width() - self._INFO_W - self._GAP
        return QRectF(left, self._HEAD_H, max(1.0, right - left), self._ROW_H * max(1, len(self._days)))

    def cell_rect(self, row: int, hour: int) -> QRectF:
        """row 줄의 hour시 칸. 축 밖의 시각이면 가장자리 밖으로 나간 칸을 돌려준다."""
        grid = self.grid_rect()
        width = grid.width() / (24 - self._start_hour)
        left = grid.left() + width * (hour - self._start_hour)
        top = grid.top() + row * self._ROW_H + (self._ROW_H - self._CELL_H) / 2
        half = self._CELL_GAP / 2
        return QRectF(left + half, top, width - self._CELL_GAP, self._CELL_H)

    def cell_at(self, pos: QPointF) -> tuple[int, int] | None:
        """pos(위젯 좌표)가 놓인 (줄, 시). 칸이 아니면 None."""
        grid = self.grid_rect()
        row = int((pos.y() - grid.top()) // self._ROW_H)
        if not (0 <= row < len(self._days) and grid.left() <= pos.x() < grid.right()):
            return None
        hour = self._start_hour + int((pos.x() - grid.left()) / grid.width() * (24 - self._start_hour))
        return row, min(23, hour)

    def tip_at(self, pos: QPointF) -> str:
        """pos에 보여 줄 설명. 칸에 스크린 타임이나 기록이 있으면 여러 줄(스크린 타임, 그 시간대의 기록들)로, 없으면 빈 문자열."""
        cell = self.cell_at(pos)
        if cell is None:
            return ""
        row, hour = cell
        day = self._days[row]
        lines = []
        if day.hours[hour] > 0:
            lines.append(f"스크린 타임 {format_usage(day.hours[hour])}")
        lines.extend(m.tip for m in day.hour_marks(hour))
        return "\n".join(lines)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        tip = self.tip_at(event.position())
        if tip:
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = QFont(self.font())
        small.setPixelSize(theme.FONT_SIZES["fs_caption"])
        painter.setFont(small)
        if not self._days or all(d.is_empty for d in self._days):
            painter.setPen(theme.color("text_muted"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text)
            painter.end()
            return

        # 위쪽 시각 글자: 3시간마다, 그 시간대 칸 위에
        painter.setPen(theme.color("text_muted"))
        for hour in range(self._start_hour, 24, self._TICK_HOURS):
            cell = self.cell_rect(0, hour)
            painter.drawText(QRectF(cell.left() - 12, 0, cell.width() + 24, self._HEAD_H - 4), Qt.AlignmentFlag.AlignCenter, f"{hour}시")

        bold = QFont(small)
        bold.setBold(True)
        for row, day in enumerate(self._days):
            top = self._HEAD_H + row * self._ROW_H
            painter.setFont(small)
            painter.setPen(theme.color("text") if row == 0 else theme.color("text_body"))
            painter.drawText(
                QRectF(0, top, self._LABEL_W, self._ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                day.title,
            )
            for hour in range(self._start_hour, 24):
                rect = self.cell_rect(row, hour)
                seconds = day.hours[hour]
                marks = day.hour_marks(hour)
                painter.setPen(Qt.PenStyle.NoPen)
                if seconds > 0:
                    fill = theme.color("accent")
                    strength = min(1.0, seconds / 3600)
                    fill.setAlpha(int(55 + 200 * strength))
                else:
                    fill, strength = theme.color("chip"), 0.0
                painter.setBrush(fill)
                painter.drawRoundedRect(rect, 4, 4)
                done = day.exercises_in_hour(hour)
                if done:  # 마친 눈 운동 횟수. 진한 칸에서는 흰 글자가 읽힌다
                    painter.setFont(bold)
                    painter.setPen(theme.color("on_accent") if strength > 0.55 else theme.color("text"))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(done))
                    painter.setFont(small)
            # 오른쪽 요약
            info = QRectF(self.width() - self._INFO_W, top, self._INFO_W, self._ROW_H)
            if day.is_empty:
                painter.setPen(theme.color("text_faint"))
                painter.drawText(info, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "기록 없음")
                continue
            has_usage = day.total_seconds >= 60
            first = f"{day.span} · {format_usage(day.total_seconds)}" if has_usage else "스크린 타임 기록 없음"
            painter.setPen(theme.color("text_body") if has_usage else theme.color("text_faint"))
            painter.drawText(
                QRectF(info.left(), top + 2, info.width(), 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, first
            )
            painter.setPen(theme.color("text_muted"))
            painter.drawText(
                QRectF(info.left(), top + 18, info.width(), 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                activity_summary(day),
            )
        painter.end()


class RecordsTab(QWidget):
    def __init__(
        self,
        events_provider: Callable[[], Iterable[HistoryEvent]],
        now: Callable[[], datetime] = SystemClock().now,
        tz: tzinfo | None = None,
        usage_provider: Callable[[], UsageLog] | None = None,
        interval_minutes: Callable[[], int] = lambda: 20,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._events = events_provider
        self._interval_minutes = interval_minutes  # 휴식 주기(분). 휴식 달성률의 권장 횟수를 구한다
        self._usage = usage_provider or UsageLog
        self._now = now
        self._tz = tz
        self._mode = Mode.REST
        self._period = Period.WEEK
        self._anchor = self._today()
        self._selected = -1
        self._expanded = False  # 최근 기록을 펼쳤는지

        self.setObjectName("records")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        theme.bind(self, _STYLE)
        theme.on_changed(self.refresh)  # 숫자 글자색처럼 문장에 박힌 색도 새 테마로 다시 만든다

        # 보는 것 (눈 휴식 / 눈 운동 / 스크린 타임)
        mode_frame, mode_buttons, self._mode_group = _segmented(text for _, text in _MODE_LABELS)
        self._mode_buttons: dict[Mode, QPushButton] = {}
        for (mode, _), button in zip(_MODE_LABELS, mode_buttons, strict=True):
            button.setChecked(mode is self._mode)
            button.clicked.connect(lambda _checked=False, m=mode: self.set_mode(m))
            self._mode_buttons[mode] = button

        # 기간 (일 / 주 / 월)
        segment, period_buttons, self._group = _segmented(text for _, text in _PERIOD_LABELS)
        self._segment_buttons: dict[Period, QPushButton] = {}
        for (period, _), button in zip(_PERIOD_LABELS, period_buttons, strict=True):
            button.setChecked(period is self._period)
            button.clicked.connect(lambda _checked=False, p=period: self.set_period(p))
            self._segment_buttons[period] = button

        # 이전 / 다음
        nav = QFrame()
        nav.setObjectName("nav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        self._prev = QPushButton("‹")
        self._next = QPushButton("›")
        self._prev.clicked.connect(lambda: self.go(-1))
        self._next.clicked.connect(lambda: self.go(1))
        self._nav_title = QLabel()
        self._nav_title.setObjectName("navTitle")
        self._nav_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self._prev)
        nav_layout.addWidget(self._nav_title)
        nav_layout.addWidget(self._next)

        # 큰 숫자 요약 + 차트 (왼쪽 큰 카드)
        self._kicker = QLabel()
        self._kicker.setObjectName("kicker")
        self._number = QLabel()
        self._number.setTextFormat(Qt.TextFormat.RichText)
        self._caption = QLabel()
        self._caption.setObjectName("caption")
        self._compare = QLabel()  # 앞 기간(전날·전주·전달)과의 비교
        self._compare.setObjectName("compareLine")
        self._compare_sub = QLabel()
        self._compare_sub.setObjectName("compareLineSub")
        self._chart = BarChart()
        self._chart.setMinimumHeight(230)
        self._chart.selection_changed.connect(self._on_selection)
        chart_card = _card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(20, 16, 16, 12)
        chart_layout.setSpacing(2)
        for widget in (self._kicker, self._number, self._caption, self._compare, self._compare_sub):
            chart_layout.addWidget(widget)
        chart_layout.addSpacing(8)
        chart_layout.addWidget(self._chart, stretch=1)

        # 하이라이트 카드 세 개 (오른쪽에 세로로)
        side = QVBoxLayout()
        side.setSpacing(12)
        self._highlight_labels: list[QLabel] = []
        self._highlight_values: list[QLabel] = []
        self._highlight_details: list[QLabel] = []
        self._highlight_compares: list[QLabel] = []
        for _ in range(3):
            card = _card()
            card.setMinimumWidth(210)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 14, 18, 14)
            layout.setSpacing(4)
            label, value, detail, compare = QLabel(), QLabel(), QLabel(), QLabel()
            label.setObjectName("cardLabel")
            value.setObjectName("cardValue")
            detail.setObjectName("cardDetail")
            compare.setObjectName("cardCompare")  # 앞 기간과의 비교
            compare.setWordWrap(True)
            layout.addWidget(label)
            layout.addWidget(value)
            layout.addWidget(detail)
            layout.addWidget(compare)
            layout.addStretch()
            side.addWidget(card, stretch=1)
            self._highlight_labels.append(label)
            self._highlight_values.append(value)
            self._highlight_details.append(detail)
            self._highlight_compares.append(compare)

        # 오늘 요약: 어제 하루와 비교해서 보여 준다 (보는 기간과 상관없이 항상 보인다)
        today_widget = QWidget()  # 창이 커져도 가장 큰 카드의 높이까지만 차지하고, 세 카드는 같은 높이로 맞춘다
        today_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        today_row = QHBoxLayout(today_widget)
        today_row.setContentsMargins(0, 0, 0, 0)
        today_row.setSpacing(12)
        self._today_cards: dict[str, list[QLabel]] = {}
        for key, title_text in (("rest", "오늘 눈 휴식"), ("exercise", "오늘 눈 운동"), ("screen", "오늘 스크린 타임")):
            card = _card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 12, 18, 12)
            layout.setSpacing(2)
            title_label, value_label, line = QLabel(title_text), QLabel(), QLabel()
            title_label.setObjectName("todayTitle")
            value_label.setObjectName("todayValue")
            line.setObjectName("todayLine")
            line.setWordWrap(True)  # 좁은 창에서 카드가 줄어들 수 있게 한다 (가로 스크롤이 생기지 않게)
            for widget in (title_label, value_label, line):
                layout.addWidget(widget)
            layout.addStretch()
            today_row.addWidget(card, stretch=1)
            self._today_cards[key] = [value_label, line]

        # 하루 타임라인 (운동·스크린 타임 두 모드 공통)
        self._section = QLabel()
        self._section.setObjectName("sectionTitle")
        self._legend = QWidget()
        self._legend_items: list[QLabel] = []
        legend_layout = QHBoxLayout(self._legend)
        legend_layout.setContentsMargins(8, 0, 0, 0)
        legend_layout.setSpacing(0)
        for html in self._legend_html():
            item = QLabel(html)
            item.setObjectName("legendItem")
            item.setTextFormat(Qt.TextFormat.RichText)
            legend_layout.addWidget(item)
            self._legend_items.append(item)
        self._more = QPushButton("더 보기")
        self._more.setObjectName("moreButton")
        self._more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more.clicked.connect(self._toggle_expanded)
        self._timeline = TimelineChart()
        table_card = _card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(20, 8, 20, 12)
        table_layout.addWidget(self._timeline)

        content = QWidget()
        content.setObjectName("recordsContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 22, 28, 24)
        body.setSpacing(14)
        # 내용이 창보다 길면 눌리지 않고 스크롤되게 한다 (이 설정이 없으면 스크롤 영역이 내용을 창 높이에 맞춰 찌그러뜨린다)
        body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        title = QLabel("기록")
        title.setObjectName("pageTitle")
        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(mode_frame)
        body.addLayout(top)
        body.addWidget(today_widget)

        controls = QHBoxLayout()
        controls.addWidget(segment)
        controls.addStretch()
        controls.addWidget(nav)
        body.addLayout(controls)

        main = QHBoxLayout()
        main.setSpacing(12)
        main.addWidget(chart_card, stretch=3)
        main.addLayout(side, stretch=1)
        body.addLayout(main)

        body.addSpacing(6)
        section_row = QHBoxLayout()
        section_row.addWidget(self._section)
        section_row.addWidget(self._legend)
        section_row.addStretch()
        section_row.addWidget(self._more)
        body.addLayout(section_row)
        body.addWidget(table_card)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # 스크린 타임은 계속 늘어나므로 보고 있는 동안 주기적으로 새로 그린다
        self._live = QTimer(self)
        self._live.setInterval(LIVE_REFRESH_MS)
        self._live.timeout.connect(self._on_live_tick)

        self.refresh()

    @staticmethod
    def _legend_html() -> list[str]:
        """하루 흐름 범례: 칸 색(스크린 타임)과 칸 안의 숫자(눈 운동 횟수). 휴식·건너뜀·미룸은 줄 오른쪽에 적혀 있다."""
        accent = theme.palette().accent
        return [
            f'<span style="color:{accent};">▬</span> 스크린 타임 (진할수록 오래)',
            "<b>2</b> 마친 눈 운동 횟수",
        ]

    # ---- 상태 ----

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def period(self) -> Period:
        return self._period

    @property
    def anchor(self):
        return self._anchor

    def _today(self):
        return self._now().astimezone(self._tz).date()

    def set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self._mode_buttons[mode].setChecked(True)
        self._selected = -1  # 막대 번호는 보는 것이 바뀌면 의미가 달라진다. 기간은 그대로 둔다.
        self.refresh()

    def set_period(self, period: Period) -> None:
        self._period = period
        self._segment_buttons[period].setChecked(True)
        self._anchor = self._today()  # 기간을 바꾸면 오늘 기준으로 돌아간다
        self._selected = -1
        self.refresh()

    def go(self, steps: int) -> None:
        if steps > 0 and not can_go_forward(self._period, self._anchor, self._today()):
            return
        self._anchor = shift_anchor(self._period, self._anchor, steps)
        self._selected = -1
        self.refresh()

    def _on_selection(self, index: int) -> None:
        self._selected = index
        self.refresh()

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self.refresh()

    def _on_live_tick(self) -> None:
        if self._mode is Mode.SCREEN_TIME and self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._live.start()
        self.refresh()  # 창이 숨겨진 동안 쌓인 기록을 보여 준다

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._live.stop()

    # ---- 그리기 ----

    def refresh(self) -> None:
        now = self._now()
        today = self._today()
        events = list(self._events())
        rest_events = events_of(events, ACTIVITY_REST)
        exercise_events = events_of(events, ACTIVITY_EXERCISE)
        usage = self._usage()
        # 눈 휴식 화면의 기록은 휴식만. 눈 운동은 오늘 요약 카드와 하루 흐름에서 횟수로만 보여 준다
        scoped = rest_events
        noun = "휴식"
        buckets = build_buckets(self._period, self._anchor, scoped, now, self._tz)
        summary = summarize_range(self._period, self._anchor, buckets, now, self._tz)

        self._draw_today(compare_today(rest_events, usage, now, self._tz), compare_today(exercise_events, usage, now, self._tz))
        self._nav_title.setText(range_title(self._period, self._anchor, today))
        self._next.setEnabled(can_go_forward(self._period, self._anchor, today))

        # 하이라이트 카드를 앞 기간과 비교하려고 앞 기간도 같은 방식으로 요약한다
        previous_anchor = shift_anchor(self._period, self._anchor, -1)
        previous = summarize_range(self._period, previous_anchor, build_buckets(self._period, previous_anchor, scoped, now, self._tz), now, self._tz)
        label = previous_label(self._period, self._anchor, today)
        if self._mode is Mode.SCREEN_TIME:
            self._draw_screen_time(buckets, usage, now, today, previous_anchor, label, events, rest_events)
        else:
            self._draw_activity(noun, buckets, summary, scoped, now, previous, label, events)

    def _draw_today(self, rest, exercise) -> None:
        for key, c in (("rest", rest), ("exercise", exercise)):
            value, line = self._today_cards[key]
            value.setText(f"{c.exercise_count}회")
            line.setText(arrow_line(c.exercise_trend, c.exercise_lines[0]))
        value, line = self._today_cards["screen"]
        value.setText(format_usage(rest.screen_seconds))
        line.setText(arrow_line(rest.screen_trend, rest.screen_line))

    def _set_compare(self, compare: PeriodCompare | None) -> None:
        """큰 숫자 아래의 앞 기간 비교. None이면(막대를 선택해 그 막대의 값을 보는 중) 숨긴다."""
        if compare is None:
            self._compare.setText("")
            self._compare_sub.setText("")
        else:
            self._compare.setText(arrow_line(compare.trend, compare.lines[0]))
            self._compare_sub.setText(compare.lines[1] if len(compare.lines) > 1 else "")
        self._compare.setVisible(compare is not None)
        self._compare_sub.setVisible(compare is not None and len(compare.lines) > 1)

    def _valid_selection(self, buckets: Sequence) -> int:
        if not 0 <= self._selected < len(buckets) or buckets[self._selected].is_future:
            self._selected = -1
        return self._selected

    def _draw_activity(self, noun, buckets, summary, scoped, now, previous, label, all_events) -> None:
        """눈 휴식 화면. noun은 문구에 들어가는 이름("휴식")."""
        selected = self._valid_selection(buckets)
        if selected >= 0:
            b = buckets[selected]
            self._kicker.setText(b.title)
            self._set_number(b.completed)
            self._caption.setText(_bucket_caption(b))
        else:
            self._kicker.setText(f"눈 {noun}")
            self._set_number(summary.completed)
            self._caption.setText(range_caption(self._period, self._anchor))
        self._chart.set_data(buckets, selected)
        self._set_compare(None if selected >= 0 else compare_exercise_period(self._period, self._anchor, scoped, now, self._tz))
        self._set_highlights(highlights_with_compare(self._period, summary, previous, label))

        self._draw_timeline(all_events, self._usage(), now)

    def _draw_timeline(self, events, usage: UsageLog, now) -> None:
        """눈 휴식·스크린 타임 두 화면이 같은 하루 타임라인을 보여 준다."""
        self._section.setText("하루 흐름")
        for item, html in zip(self._legend_items, self._legend_html(), strict=True):
            item.setText(html)  # 테마가 바뀌면 색도 따라간다
        self._more.setVisible(True)
        self._more.setText("접기" if self._expanded else "더 보기")
        self._legend.setVisible(True)
        self._timeline.set_days(timeline_days(events, usage, now, RECENT_EXPANDED if self._expanded else RECENT_COLLAPSED, self._tz))

    def _draw_screen_time(self, rest_buckets, usage: UsageLog, now, today, previous_anchor, label, all_events, rest_events) -> None:
        usage_buckets = build_usage_buckets(self._period, self._anchor, usage, now, self._tz)
        usage_summary = summarize_usage(self._period, self._anchor, usage_buckets, now, self._tz)
        selected = self._valid_selection(usage_buckets)
        if selected >= 0:
            b = usage_buckets[selected]
            self._kicker.setText(b.title)
            self._set_number_parts(usage_parts(b.seconds))
            self._caption.setText(f"눈 휴식 {rest_buckets[selected].completed}회")
        else:
            self._kicker.setText("스크린 타임")
            self._set_number_parts(usage_parts(usage_summary.total_seconds))
            self._caption.setText(range_caption(self._period, self._anchor))
        seconds = [b.seconds for b in usage_buckets]
        self._chart.set_series(
            usage_buckets, seconds, nice_usage_axis(max(seconds, default=0)), format_usage_axis, selected, "사용 기록이 없어요"
        )
        self._set_compare(None if selected >= 0 else compare_usage_period(self._period, self._anchor, usage, now, self._tz))
        previous_usage = summarize_usage(
            self._period, previous_anchor, build_usage_buckets(self._period, previous_anchor, usage, now, self._tz), now, self._tz
        )
        interval = self._interval_minutes()
        stats = rest_stats(self._period, self._anchor, usage, rest_events, now, self._tz, interval)
        previous_stats = rest_stats(self._period, previous_anchor, usage, rest_events, now, self._tz, interval)
        self._set_highlights(usage_highlights_with_compare(self._period, usage_summary, stats, previous_usage, previous_stats, label))

        self._draw_timeline(all_events, usage, now)

    def _set_highlights(self, cards) -> None:
        for label, value, detail, compare, card in zip(
            self._highlight_labels, self._highlight_values, self._highlight_details, self._highlight_compares, cards, strict=True
        ):
            label.setText(card.label)
            value.setText(card.value)
            detail.setText(card.detail)
            detail.setVisible(bool(card.detail))
            compare.setText(arrow_line(card.trend, card.compare) if card.compare else "")
            compare.setVisible(bool(card.compare))

    def _set_number(self, count: int) -> None:
        self._set_number_parts([(str(count), "회")])

    def _set_number_parts(self, parts: Sequence[tuple[str, str]]) -> None:
        """큰 숫자 + 작은 단위. 예: (5, 시간) (12, 분) → "5시간 12분"."""
        self._number.setText(
            "".join(
                f'<span style="font-size:{theme.FONT_SIZES["fs_display"]}px; font-weight:600; color:{theme.palette().text};">{number}</span>'
                f'<span style="font-size:{theme.FONT_SIZES["fs_heading"]}px; color:{theme.palette().text_secondary};"> {unit}&nbsp;</span>'
                for number, unit in parts
            )
        )
