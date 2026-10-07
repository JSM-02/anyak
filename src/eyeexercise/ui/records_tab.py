"""기록 탭. 기간 전환, 큰 숫자 요약, 막대 차트, 하이라이트 카드, 날짜별 표를 넓은 데스크톱 화면에 배치한다.

위쪽 전환으로 '운동'(완료 횟수)과 '스크린 타임'(PC 사용 시간)을 오간다. 둘은 같은 화면 구조를 쓴다.
계산은 모두 core/stats가 한다. 이 모듈은 그 결과를 그리기만 한다.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.stats import (
    TREND_SYMBOLS,
    Period,
    PeriodCompare,
    build_buckets,
    build_usage_buckets,
    can_go_forward,
    compare_exercise_period,
    compare_today,
    compare_usage_period,
    format_duration,
    format_usage,
    format_usage_axis,
    highlights_with_compare,
    nice_axis_max,
    nice_usage_axis,
    previous_label,
    range_caption,
    range_title,
    recent_groups,
    shift_anchor,
    summarize_range,
    summarize_usage,
    usage_daily_rows,
    usage_highlights_with_compare,
    usage_parts,
)
from eyeexercise.core.usage import UsageLog

_BLUE = QColor("#1a73e8")
_GRAY = QColor("#9aa0a6")
_ORANGE = QColor("#f9ab00")
_PURPLE = QColor("#8e5bd8")
# 최근 기록의 색 원: 완료는 운동 종류별, 건너뜀·미룸은 결과별
_EXERCISE_COLORS = {"blink": _BLUE, "dot_follow": _PURPLE}
_RESULT_COLORS = {"skipped": _GRAY, "snoozed": _ORANGE}
_LEGEND = (("깜빡임", _BLUE), ("점 따라가기", _PURPLE), ("건너뜀", _GRAY), ("미룸", _ORANGE))


def marker_color(kind: str, exercise: str) -> QColor:
    """기록 한 줄 앞에 붙이는 색 원의 색. 모르는 운동은 파랑으로 둔다."""
    if kind == "completed":
        return _EXERCISE_COLORS.get(exercise, _BLUE)
    return _RESULT_COLORS.get(kind, _GRAY)


_PERIOD_LABELS = ((Period.DAY, "일"), (Period.WEEK, "주"), (Period.MONTH, "월"))
RECENT_COLLAPSED = 10  # 처음에 보여 주는 최근 기록 줄 수
RECENT_EXPANDED = 100  # '더 보기'를 눌렀을 때
LIVE_REFRESH_MS = 30_000  # 스크린 타임을 보는 동안 숫자가 따라가도록 새로 그리는 간격


class Mode(Enum):
    EXERCISE = "exercise"
    SCREEN_TIME = "screen_time"


_MODE_LABELS = ((Mode.EXERCISE, "운동"), (Mode.SCREEN_TIME, "스크린 타임"))

_STYLE = """
#records, #recordsContent { background: #f5f5f7; }
#records QLabel { background: transparent; }
#pageTitle { font-size: 24px; font-weight: bold; }
#segment { background: #e6e6ea; border-radius: 7px; }
#segment QPushButton {
    background: transparent; border: none; border-radius: 5px; padding: 5px 18px; color: #3c4043;
}
#segment QPushButton:checked { background: #ffffff; color: #202124; font-weight: bold; }
#nav QPushButton { background: transparent; border: none; font-size: 20px; color: #1a73e8; padding: 0 10px; }
#nav QPushButton:disabled { color: #c4c7cc; }
#navTitle { font-size: 14px; font-weight: bold; min-width: 80px; }
#card { background: #ffffff; border: 1px solid #e4e4e8; border-radius: 8px; }
#kicker { font-size: 13px; color: #5f6368; font-weight: bold; }
#caption { font-size: 13px; color: #5f6368; }
#cardLabel { font-size: 12px; color: #5f6368; }
#cardValue { font-size: 22px; font-weight: bold; }
#cardDetail { font-size: 12px; color: #5f6368; }
#cardCompare { font-size: 12px; color: #3c4043; padding-top: 4px; }
#todayTitle { font-size: 12px; color: #5f6368; font-weight: bold; }
#todayValue { font-size: 26px; font-weight: bold; }
#todayLine { font-size: 13px; color: #3c4043; }
#todayLineSub { font-size: 12px; color: #80868b; }
#compareLine { font-size: 13px; color: #3c4043; }
#compareLineSub { font-size: 12px; color: #80868b; }
#legendItem { font-size: 12px; color: #5f6368; padding: 0 6px; }
#sectionTitle { font-size: 16px; font-weight: bold; }
#moreButton { background: transparent; border: none; color: #1a73e8; padding: 2px 6px; }
#moreButton:hover { text-decoration: underline; }
#tableHead { font-size: 12px; color: #80868b; padding: 6px 0; }
#groupTitle { font-size: 13px; font-weight: bold; color: #202124; padding: 12px 0 4px 0; }
#cell { font-size: 14px; padding: 7px 0; }
#cell[muted="true"] { color: #9aa0a6; }
#empty { color: #80868b; font-size: 13px; }
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
        small.setPixelSize(11)
        painter.setFont(small)
        grid = QPen(QColor("#e0e0e5"), 1)
        for value in (0, axis / 2, axis):
            y = plot.bottom() - plot.height() * value / axis
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#80868b"))
            painter.drawText(
                QRectF(plot.right() + 4, y - 8, self._RIGHT - 4, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._format(value),
            )

        if not self._buckets:
            painter.end()
            return
        if not any(self._values):
            painter.setPen(QColor("#80868b"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)

        slot = plot.width() / len(self._buckets)
        dim = self._selected >= 0
        for i, b in enumerate(self._buckets):
            if b.show_label:
                font = QFont(small)
                font.setBold(b.is_current)
                painter.setFont(font)
                painter.setPen(_BLUE if b.is_current else QColor("#80868b"))
                painter.drawText(
                    QRectF(plot.left() + slot * i - 8, plot.bottom() + 4, slot + 16, 16),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    b.label,
                )
            if b.is_future or self._values[i] <= 0:
                continue
            color = QColor(_BLUE)
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


@dataclass(frozen=True)
class _TableRow:
    cells: Sequence[str]
    muted: bool = False  # 건너뜀·미룸처럼 덜 중요한 줄은 연한 회색으로 보인다
    marker: QColor | None = None  # 줄 앞의 색 원. 표 전체가 색 원 칸을 가질 때만 쓴다


def arrow_line(trend: str, line: str) -> str:
    """비교 문구 앞에 ▲▼– 를 붙인다. "기록이 없어요"처럼 비교할 수 없을 때는 붙이지 않는다."""
    return line if "기록이 없어요" in line else f"{TREND_SYMBOLS[trend]} {line}"


class _Table(QWidget):
    """날짜별로 묶을 수 있는 표. 모든 줄이 한 격자를 써서 칸이 줄마다 가지런하다."""

    def __init__(self) -> None:
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(0)
        self._columns = 0

    def clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()  # deleteLater만으로는 이벤트 루프가 돌 때까지 화면에 남아 새 줄과 겹쳐 보인다
                widget.setParent(None)
                widget.deleteLater()
        for column in range(self._columns):
            self._grid.setColumnStretch(column, 0)
            self._grid.setColumnMinimumWidth(column, 0)

    def set_content(
        self,
        headers: Sequence[str],
        stretches: Sequence[int],
        groups: Sequence[tuple[str | None, Sequence[_TableRow]]],
        markers: bool = False,
    ) -> None:
        """markers가 True면 맨 앞에 색 원 칸을 하나 더 둔다. 머리글은 비워 두고 칸 너비는 원에 맞춘다."""
        self.clear()
        offset = 1 if markers else 0
        self._columns = len(headers) + offset
        if markers:
            self._grid.setColumnMinimumWidth(0, 18)
        for column, (header, stretch) in enumerate(zip(headers, stretches, strict=True), start=offset):
            self._grid.setColumnStretch(column, stretch)
            label = QLabel(header)
            label.setObjectName("tableHead")
            self._grid.addWidget(label, 0, column)
        row = 1
        self._add_line(row)
        row += 1
        for title, rows in groups:
            if title is not None:
                label = QLabel(title)
                label.setObjectName("groupTitle")
                self._grid.addWidget(label, row, 0, 1, self._columns)
                row += 1
            for index, table_row in enumerate(rows):
                if index or title is None and row > 2:
                    self._add_line(row, light=True)
                    row += 1
                if markers and table_row.marker is not None:
                    dot = QLabel("●")
                    dot.setObjectName("dot")
                    dot.setProperty("marker", table_row.marker.name())
                    dot.setStyleSheet(f"color: {table_row.marker.name()}; font-size: 12px;")
                    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._grid.addWidget(dot, row, 0)
                for column, text in enumerate(table_row.cells, start=offset):
                    cell = QLabel(text)
                    cell.setObjectName("cell")
                    cell.setProperty("muted", table_row.muted)
                    self._grid.addWidget(cell, row, column)
                row += 1

    def _add_line(self, row: int, light: bool = False) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #f0f0f3;" if light else "background: #e4e4e8;")
        self._grid.addWidget(line, row, 0, 1, max(1, self._columns))


class RecordsTab(QWidget):
    def __init__(
        self,
        events_provider: Callable[[], Iterable[HistoryEvent]],
        now: Callable[[], datetime] = SystemClock().now,
        tz: tzinfo | None = None,
        usage_provider: Callable[[], UsageLog] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._events = events_provider
        self._usage = usage_provider or UsageLog
        self._now = now
        self._tz = tz
        self._mode = Mode.EXERCISE
        self._period = Period.WEEK
        self._anchor = self._today()
        self._selected = -1
        self._expanded = False  # 최근 기록을 펼쳤는지

        self.setObjectName("records")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(_STYLE)

        # 보는 것 (운동 / 스크린 타임)
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
        today_row = QHBoxLayout()
        today_row.setSpacing(12)
        self._today_cards: dict[str, list[QLabel]] = {}
        for key, title_text in (("exercise", "오늘 운동 완료"), ("screen", "오늘 스크린 타임")):
            card = _card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 12, 18, 12)
            layout.setSpacing(2)
            title_label, value_label, line, sub = QLabel(title_text), QLabel(), QLabel(), QLabel()
            title_label.setObjectName("todayTitle")
            value_label.setObjectName("todayValue")
            line.setObjectName("todayLine")
            sub.setObjectName("todayLineSub")
            for widget in (title_label, value_label, line, sub):
                layout.addWidget(widget)
            layout.addStretch()  # 두 칸의 줄 수가 달라도 글이 위에서부터 같은 높이에 놓이게 한다
            today_row.addWidget(card, stretch=1)
            self._today_cards[key] = [value_label, line, sub]

        # 표 (운동: 최근 기록 / 스크린 타임: 최근 7일)
        self._section = QLabel()
        self._section.setObjectName("sectionTitle")
        self._legend = QWidget()
        legend_layout = QHBoxLayout(self._legend)
        legend_layout.setContentsMargins(8, 0, 0, 0)
        legend_layout.setSpacing(0)
        for text, color in _LEGEND:
            item = QLabel(f'<span style="color:{color.name()};">●</span> {text}')
            item.setObjectName("legendItem")
            item.setTextFormat(Qt.TextFormat.RichText)
            legend_layout.addWidget(item)
        self._more = QPushButton("더 보기")
        self._more.setObjectName("moreButton")
        self._more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more.clicked.connect(self._toggle_expanded)
        self._table = _Table()
        table_card = _card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(20, 8, 20, 12)
        table_layout.addWidget(self._table)

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
        body.addLayout(today_row)

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
        usage = self._usage()
        buckets = build_buckets(self._period, self._anchor, events, now, self._tz)
        summary = summarize_range(self._period, self._anchor, buckets, now, self._tz)

        self._draw_today(compare_today(events, usage, now, self._tz))
        self._nav_title.setText(range_title(self._period, self._anchor, today))
        self._next.setEnabled(can_go_forward(self._period, self._anchor, today))

        # 하이라이트 카드를 앞 기간과 비교하려고 앞 기간도 같은 방식으로 요약한다
        previous_anchor = shift_anchor(self._period, self._anchor, -1)
        previous = summarize_range(self._period, previous_anchor, build_buckets(self._period, previous_anchor, events, now, self._tz), now, self._tz)
        label = previous_label(self._period, self._anchor, today)
        if self._mode is Mode.EXERCISE:
            self._draw_exercise(buckets, summary, events, now, previous, label)
        else:
            self._draw_screen_time(buckets, summary, usage, now, today, previous, previous_anchor, label)

    def _draw_today(self, c) -> None:
        value, line, sub = self._today_cards["exercise"]
        value.setText(f"{c.exercise_count}회")
        first, *rest = c.exercise_lines
        line.setText(arrow_line(c.exercise_trend, first))
        sub.setText(rest[0] if rest else "")
        sub.setVisible(bool(rest))
        value, line, sub = self._today_cards["screen"]
        value.setText(format_usage(c.screen_seconds))
        line.setText(arrow_line(c.screen_trend, c.screen_line))
        sub.setText("")
        sub.setVisible(False)

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

    def _draw_exercise(self, buckets, summary, events, now, previous, label) -> None:
        selected = self._valid_selection(buckets)
        if selected >= 0:
            b = buckets[selected]
            self._kicker.setText(b.title)
            self._set_number(b.completed)
            self._caption.setText(f"운동 시간 {format_duration(b.exercise_seconds)}" if b.completed else "완료한 운동 없음")
        else:
            self._kicker.setText("완료한 운동")
            self._set_number(summary.completed)
            self._caption.setText(range_caption(self._period, self._anchor))
        self._chart.set_data(buckets, selected)
        self._set_compare(None if selected >= 0 else compare_exercise_period(self._period, self._anchor, events, now, self._tz))
        self._set_highlights(highlights_with_compare(self._period, summary, previous, label))

        self._section.setText("최근 기록")
        has_more = len(events) > RECENT_COLLAPSED
        self._more.setVisible(has_more)
        self._more.setText("접기" if self._expanded else "더 보기")
        groups = []
        for group in recent_groups(events, now, RECENT_EXPANDED if self._expanded else RECENT_COLLAPSED, self._tz):
            rows = [
                _TableRow((r.clock, r.name, r.result, r.length), muted=r.kind != "completed", marker=marker_color(r.kind, r.exercise))
                for r in group.rows
            ]
            groups.append((group.title, rows))
        self._legend.setVisible(True)
        self._fill_table(("시간", "운동", "결과", "길이"), (1, 3, 2, 2), groups, "아직 기록이 없어요", markers=True)

    def _draw_screen_time(self, exercise_buckets, exercise_summary, usage: UsageLog, now, today, previous_exercise, previous_anchor, label) -> None:
        usage_buckets = build_usage_buckets(self._period, self._anchor, usage, now, self._tz)
        usage_summary = summarize_usage(self._period, self._anchor, usage_buckets, now, self._tz)
        selected = self._valid_selection(usage_buckets)
        if selected >= 0:
            b = usage_buckets[selected]
            self._kicker.setText(b.title)
            self._set_number_parts(usage_parts(b.seconds))
            self._caption.setText(f"운동 완료 {exercise_buckets[selected].completed}회")
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
        self._set_highlights(
            usage_highlights_with_compare(self._period, usage_summary, exercise_summary, previous_usage, previous_exercise, label)
        )

        self._section.setText("최근 7일")
        self._more.setVisible(False)
        self._legend.setVisible(False)
        rows = [_TableRow((name, format_usage(secs))) for name, secs in usage_daily_rows(usage, today)]
        self._fill_table(("날짜", "사용 시간"), (3, 2), [(None, rows)], "아직 기록이 없어요")

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
                f'<span style="font-size:42px; font-weight:600; color:#202124;">{number}</span>'
                f'<span style="font-size:17px; color:#5f6368;"> {unit}&nbsp;</span>'
                for number, unit in parts
            )
        )

    def _fill_table(self, headers, stretches, groups, empty_text: str, markers: bool = False) -> None:
        if any(rows for _, rows in groups):
            self._table.set_content(headers, stretches, groups, markers)
            return
        self._table.clear()
        empty = QLabel(empty_text)
        empty.setObjectName("empty")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setContentsMargins(0, 24, 0, 24)
        self._table._grid.addWidget(empty, 0, 0)  # noqa: SLF001 표 안에 안내 문구를 직접 놓는다
