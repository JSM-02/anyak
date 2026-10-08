"""홈 화면: 다음 눈 휴식까지 남은 시간, 오늘 휴식 달성률 게이지, 오늘 요약 타일, 오늘의 하루 흐름.

굵은 글씨와 두툼한 색 블록으로 구역을 나눈다. 계산은 core/home과 core/stats가 하고 이 모듈은 그리기만 한다.
"""

from collections.abc import Callable, Iterable
from datetime import datetime, tzinfo

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from eyeexercise.core.clock import SystemClock
from eyeexercise.core.formatting import home_timer
from eyeexercise.core.history import HistoryEvent
from eyeexercise.core.home import PROGRESS_CELLS, HomeSummary, filled_cells, home_summary, timer_progress
from eyeexercise.core.scheduler import State
from eyeexercise.core.settings import Settings
from eyeexercise.core.stats import format_usage, timeline_days
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui import theme
from eyeexercise.ui.page_column import centered_column
from eyeexercise.ui.gauge import RingGauge
from eyeexercise.ui.records_tab import TimelineChart

LIVE_REFRESH_MS = 30_000  # 보는 동안 스크린 타임·달성률이 따라가도록 새로 그리는 간격

_STYLE = """
#home, #homeContent { background: $bg; }
#home QLabel { background: transparent; }
#homeTitle { font-size: $fs_title; font-weight: 900; color: $text; }
#hero { background: $hero; border-radius: 18px; }
#heroKicker { font-size: $fs_heading; font-weight: 800; color: $sand; }
#heroClock { font-size: 64px; font-weight: 900; color: #ffffff; }
#heroSub { font-size: $fs_small; color: $sidebar_text; font-weight: 700; }
#heroRest { background: $sand; color: $ink; border: none; border-radius: 14px; padding: 11px 24px; font-size: $fs_body; font-weight: 800; }
#heroRest:hover { background: #ffffff; }
#heroRest:disabled { background: rgba(242, 227, 179, 70); color: rgba(255, 255, 255, 140); }
#heroSnooze { background: rgba(255, 255, 255, 36); color: #ffffff; border: none; border-radius: 14px; padding: 11px 22px; font-size: $fs_body; font-weight: 800; }
#heroSnooze:hover { background: rgba(255, 255, 255, 70); }
#heroSnooze:disabled { background: rgba(255, 255, 255, 14); color: $text_faint; }
#card { background: $surface; border: 1px solid $border; border-radius: 18px; }
#cardTitle { font-size: $fs_body; font-weight: 800; color: $text; }
#cardDetail { font-size: $fs_small; font-weight: 700; color: $text_secondary; }
#tileTitle { font-size: $fs_small; font-weight: 800; color: $text_secondary; }
#tileValue { font-size: $fs_stat; font-weight: 900; color: $text; }
#sectionTitle { font-size: $fs_heading; font-weight: 800; color: $text; }
"""


class CellBar(QWidget):
    """남은 시간의 진행 바. 20칸이 왼쪽부터 모래색으로 차오른다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filled = 0
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.update()

    @property
    def filled(self) -> int:
        return self._filled

    def set_filled(self, count: int) -> None:
        count = min(PROGRESS_CELLS, max(0, count))
        if count != self._filled:
            self._filled = count
            self.update()

    def cell_rect(self, index: int) -> QRectF:
        gap = 4.0
        width = (self.width() - gap * (PROGRESS_CELLS - 1)) / PROGRESS_CELLS
        return QRectF(index * (width + gap), 0, width, self.height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        empty = QColor(255, 255, 255, 40)
        for i in range(PROGRESS_CELLS):
            painter.setBrush(theme.color("sand") if i < self._filled else empty)
            painter.drawRoundedRect(self.cell_rect(i), 3, 3)
        painter.end()


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


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
    ) -> None:
        super().__init__(parent)
        self._events = events_provider
        self._now = now
        self._usage = usage_provider or UsageLog
        self._settings = settings_provider
        self._tz = tz
        self.setObjectName("home")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        theme.bind(self, _STYLE)

        # 타이머 카드
        self._kicker = QLabel()
        self._kicker.setObjectName("heroKicker")
        self._clock = QLabel()
        self._clock.setObjectName("heroClock")
        self._sub = QLabel()
        self._sub.setObjectName("heroSub")
        self._bar = CellBar()
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
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self._rest_button)
        buttons.addWidget(self._exercise_button)
        buttons.addWidget(self._pause_button)
        buttons.addWidget(self._snooze_button)
        buttons.addStretch()
        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.setSpacing(2)
        for widget in (self._kicker, self._clock, self._sub):
            hero_layout.addWidget(widget)
        hero_layout.addSpacing(10)
        hero_layout.addWidget(self._bar)
        hero_layout.addSpacing(16)
        hero_layout.addLayout(buttons)

        # 달성률 카드
        self.gauge = RingGauge()
        self._gauge_detail = QLabel()
        self._gauge_detail.setObjectName("cardDetail")
        self._gauge_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gauge_title = QLabel("오늘 휴식 달성률")
        gauge_title.setObjectName("cardTitle")
        gauge_card = _card()
        gauge_layout = QVBoxLayout(gauge_card)
        gauge_layout.setContentsMargins(22, 18, 22, 18)
        gauge_layout.addWidget(gauge_title)
        gauge_layout.addWidget(self.gauge, stretch=1)
        gauge_layout.addWidget(self._gauge_detail)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(hero, stretch=3)
        top.addWidget(gauge_card, stretch=2)

        # 오늘 요약 타일 세 개
        self._tiles: dict[str, QLabel] = {}
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        for key, title in (("screen", "오늘 스크린 타임"), ("longest", "최장 연속 사용"), ("exercise", "오늘 눈 운동")):
            card = _card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(2)
            title_label, value = QLabel(title), QLabel()
            title_label.setObjectName("tileTitle")
            value.setObjectName("tileValue")
            layout.addWidget(title_label)
            layout.addWidget(value)
            tiles.addWidget(card, stretch=1)
            self._tiles[key] = value

        # 오늘의 하루 흐름 한 줄
        flow_title = QLabel("오늘의 하루 흐름")
        flow_title.setObjectName("sectionTitle")
        self._timeline = TimelineChart()
        flow_card = _card()
        flow_layout = QVBoxLayout(flow_card)
        flow_layout.setContentsMargins(20, 8, 20, 12)
        flow_layout.addWidget(self._timeline)

        content = QWidget()
        content.setObjectName("homeContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 22, 28, 24)
        body.setSpacing(14)
        title = QLabel("홈")
        title.setObjectName("homeTitle")
        body.addWidget(title)
        body.addLayout(top)
        body.addLayout(tiles)
        body.addWidget(flow_title)
        body.addWidget(flow_card)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(centered_column(content))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._live = QTimer(self)
        self._live.setInterval(LIVE_REFRESH_MS)
        self._live.timeout.connect(self._on_live_tick)

        self.set_timer(State.RUNNING, None, None, None)
        self.refresh()

    # ---- 타이머 카드 ----

    def set_timer(self, state: State, remaining: float | None, target: float | None, activity: str | None) -> None:
        """컨트롤러가 1초마다 알려 주는 상태·남은 시간으로 타이머 카드를 그린다."""
        kicker, clock = home_timer(state, remaining, activity)
        self._kicker.setText(kicker)
        self._clock.setText(clock)
        self._sub.setText(f"{self._settings().interval_minutes}분마다 눈을 쉬어 줘요")
        self._bar.set_filled(PROGRESS_CELLS if state is State.DUE else filled_cells(timer_progress(remaining, target)))
        startable = state in (State.RUNNING, State.SNOOZED, State.DUE)
        self._rest_button.setEnabled(startable)
        self._exercise_button.setEnabled(startable)
        self._pause_button.setText("재개" if state is State.PAUSED else "일시정지")
        self._pause_button.setEnabled(state in (State.RUNNING, State.SNOOZED, State.PAUSED))
        self._snooze_button.setText(f"{self._settings().snooze_minutes}분 미루기")
        self._snooze_button.setVisible(state is State.DUE)  # 미루기는 알림이 떠 있을 때만 할 수 있다

    # ---- 오늘 요약 ----

    def _on_live_tick(self) -> None:
        if self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._live.start()
        self.refresh()  # 숨겨진 동안 쌓인 기록을 보여 준다

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._live.stop()

    def refresh(self) -> None:
        settings = self._settings()
        now = self._now()
        events = list(self._events())
        usage = self._usage()
        summary = home_summary(events, usage, now, settings.interval_minutes, settings.exercises.daily_goal, self._tz)
        self._draw_summary(summary)
        self._timeline.set_days(timeline_days(events, usage, now, 1, self._tz))

    def _draw_summary(self, s: HomeSummary) -> None:
        self.gauge.set_rate(s.rate)
        self._gauge_detail.setText(f"{s.rests}회 / 권장 {s.recommended}회" if s.rate is not None else "사용 시간이 짧아요")
        self._tiles["screen"].setText(format_usage(s.screen_seconds))
        self._tiles["longest"].setText(format_usage(s.longest_seconds) if s.longest_seconds > 0 else "–")
        self._tiles["exercise"].setText(f"{s.exercises}/{s.exercise_goal}회" if s.exercise_goal > 0 else f"{s.exercises}회")
