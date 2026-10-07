"""설정 화면. 값을 바꾸는 즉시 저장하고 실행 중인 앱에 반영한다.

처음에는 꼭 필요한 것만 보여 주고(알림 주기, 운동 켜기/끄기, 운동 길이, 소리, 시작 방식),
세부 값은 접어 둔 '고급 설정'에 둔다. 값은 사람이 세는 말로 보여 준다 (66초 대신 깜빡임 10회, 짧게/보통/길게).

값의 보정·저장·알림은 core의 SettingsManager가 한다. 이 모듈은 입력 컨트롤을 그리고, 바뀐 값을 넘기고,
돌려받은 (보정된) 설정으로 컨트롤을 다시 채우기만 한다.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from eyeexercise.core.exercises import (
    LENGTH_PRESETS,
    blink_cycles_for_seconds,
    blink_seconds_for_cycles,
    blink_timeline,
    current_preset,
    dot_follow_timeline,
    preset_changes,
)
from eyeexercise.core.settings import (
    BLINK_SECONDS_RANGE,
    DOT_FOLLOW_SECONDS_RANGE,
    IDLE_PAUSE_MINUTES_RANGE,
    IDLE_RESET_MINUTES_RANGE,
    INTERVAL_MINUTES_RANGE,
    SNOOZE_MINUTES_RANGE,
    SPEEDS,
    Settings,
)
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.stats import format_duration
from eyeexercise.ui.controls import CONTROLS_STYLE, LabeledSlider, Segmented, Switch

SPEED_LABELS = {"slow": "느리게", "normal": "보통", "fast": "빠르게"}
SAVE_FAILED_MESSAGE = "설정을 파일에 저장하지 못했어요. 이번 실행에서만 적용돼요."
BOTH_OFF_MESSAGE = "두 운동을 모두 끄면 알림이 와도 운동이 시작되지 않아요."
CUSTOM_LENGTH_MESSAGE = "고급 설정에서 운동마다 따로 정한 길이를 쓰고 있어요."
ADVANCED_CLOSED = "▸  고급 설정"
ADVANCED_OPEN = "▾  고급 설정"
DOT_STEP_SECONDS = 10  # 점 따라가기 시간 슬라이더의 한 칸

_STYLE = """
#settingsPage, #settingsContent { background: #f5f5f7; }
#settingsPage QLabel { background: transparent; }
#pageTitle { font-size: 24px; font-weight: bold; }
#sectionTitle { font-size: 16px; font-weight: bold; padding-top: 6px; }
#card { background: #ffffff; border: 1px solid #e4e4e8; border-radius: 8px; }
#rowTitle { font-size: 14px; }
#rowHint { font-size: 12px; color: #5f6368; }
#warning { font-size: 13px; color: #b06000; }
#saveStatus { font-size: 13px; color: #c5221f; }
#sliderValue { font-size: 14px; font-weight: bold; }
#advancedToggle { background: transparent; border: none; text-align: left; font-size: 15px; font-weight: bold; color: #1a73e8; padding: 8px 0; }
#advancedToggle:hover { color: #1765cc; }
""" + CONTROLS_STYLE


def _card(rows: list[QWidget]) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 4, 20, 4)
    layout.setSpacing(0)
    for i, row in enumerate(rows):
        if i:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet("background: #f0f0f3;")
            layout.addWidget(line)
        layout.addWidget(row)
    return frame


class SettingsPage(QWidget):
    def __init__(self, manager: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._loading = False  # 값을 채우는 중에는 바뀐 값으로 보고하지 않는다
        self._controls: dict[str, QWidget] = {}
        self._to_ui: dict[str, Callable[[int], int]] = {}  # 설정 값 → 화면 값 (예: 초 → 회)
        self._hints: dict[str, QLabel] = {}
        self._preset: Segmented | None = None

        self.setObjectName("settingsPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(_STYLE)

        title = QLabel("설정")
        title.setObjectName("pageTitle")
        self._status = QLabel()
        self._status.setObjectName("saveStatus")
        self._status.setWordWrap(True)
        self._status.hide()
        self._warning = QLabel(BOTH_OFF_MESSAGE)
        self._warning.setObjectName("warning")
        self._warning.setWordWrap(True)
        self._warning.hide()

        content = QWidget()
        content.setObjectName("settingsContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 22, 28, 24)
        body.setSpacing(10)
        body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)  # 창이 작아지면 눌리지 않고 스크롤된다
        body.addWidget(title)
        body.addWidget(self._status)

        # ---- 기본 설정: 꼭 필요한 것만 ----
        self._add_section(
            body,
            "알림",
            [self._slider("interval_minutes", "알림 주기", "이 시간마다 눈 운동을 알려요.", INTERVAL_MINUTES_RANGE, " 분", 5)],
        )
        self._add_section(
            body,
            "눈 운동",
            [
                self._switch("exercises.blink.enabled", "깜빡임 운동", "눈을 천천히 감았다 뜨는 운동이에요."),
                self._switch("exercises.dot_follow.enabled", "점 따라가기", "화면의 점을 눈으로 따라가는 운동이에요."),
                self._length_row(),
            ],
        )
        body.addWidget(self._warning)
        self._add_section(
            body,
            "소리와 시작",
            [
                self._switch("sound.enabled", "소리 안내", "운동 중 효과음으로 단계를 알려요. 눈을 감고도 따라 할 수 있어요."),
                self._switch("show_main_window_on_start", "시작할 때 창 보이기", "끄면 트레이에서만 조용히 시작해요."),
            ],
        )

        # ---- 고급 설정: 접어 둔다 ----
        self._advanced_toggle = QPushButton(ADVANCED_CLOSED)
        self._advanced_toggle.setObjectName("advancedToggle")
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.setFlat(True)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        body.addWidget(self._advanced_toggle)
        self._advanced = QWidget()
        advanced_layout = QVBoxLayout(self._advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(10)
        self._add_section(
            advanced_layout,
            "운동 세부",
            [
                self._slider(
                    "exercises.blink.duration_seconds",
                    "깜빡임 운동 횟수",
                    "",
                    (1, blink_cycles_for_seconds(BLINK_SECONDS_RANGE[1])),
                    "회",
                    5,
                    hint_key="blink_hint",
                    to_ui=blink_cycles_for_seconds,
                    to_setting=blink_seconds_for_cycles,
                ),
                self._slider(
                    "exercises.dot_follow.duration_seconds",
                    "점 따라가기 시간",
                    "",
                    (DOT_FOLLOW_SECONDS_RANGE[0] // DOT_STEP_SECONDS, DOT_FOLLOW_SECONDS_RANGE[1] // DOT_STEP_SECONDS),
                    "",
                    3,
                    hint_key="dot_hint",
                    to_ui=lambda seconds: max(1, (seconds + DOT_STEP_SECONDS // 2) // DOT_STEP_SECONDS),  # 65초 → 7칸(70초). 파이썬 round()는 6.5를 6으로 내린다
                    to_setting=lambda value: value * DOT_STEP_SECONDS,
                    formatter=lambda value: format_duration(value * DOT_STEP_SECONDS),
                ),
                self._segmented("exercises.dot_follow.speed", "점 따라가기 속도", ""),
            ],
        )
        self._add_section(
            advanced_layout,
            "알림 세부",
            [self._slider("snooze_minutes", "미루기 시간", "미루면 이 시간 뒤에 다시 알려요.", SNOOZE_MINUTES_RANGE, " 분", 5)],
        )
        self._add_section(
            advanced_layout,
            "자리 비움",
            [
                self._slider(
                    "idle_pause_minutes",
                    "알림 시간 멈춤",
                    "이 시간 입력이 없으면 알림 시간을 세지 않아요.",
                    IDLE_PAUSE_MINUTES_RANGE,
                    " 분",
                    5,
                ),
                self._slider(
                    "idle_reset_minutes",
                    "알림 시간 처음부터",
                    "이 시간 자리를 비우면 처음부터 다시 세요.",
                    IDLE_RESET_MINUTES_RANGE,
                    " 분",
                    5,
                ),
            ],
        )
        self._advanced.hide()  # 부모에 붙기 전에는 setVisible(True)를 부르지 않는다. 숨길 때만 hide()
        body.addWidget(self._advanced)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._load(manager.settings)
        manager.subscribe(lambda new, old: self._load(new))  # 다른 곳에서 설정이 바뀌어도 화면이 따라간다

    # ---- 만들기 ----

    def _add_section(self, body: QVBoxLayout, title: str, rows: list[QWidget]) -> None:
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        body.addWidget(label)
        body.addWidget(_card(rows))

    def _row(self, title: str, hint: str, control: QWidget, hint_key: str | None = None) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("rowTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("rowHint")
        hint_label.setWordWrap(True)
        if not hint:
            hint_label.hide()  # setVisible(True)는 부모가 없을 때 독립된 작은 창을 띄우므로, 숨길 때만 부른다
        texts.addWidget(title_label)
        texts.addWidget(hint_label)
        layout.addLayout(texts, stretch=1)
        layout.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
        if hint_key:
            self._hints[hint_key] = hint_label
        return row

    def _slider(
        self,
        path: str,
        title: str,
        hint: str,
        bounds: tuple[int, int],
        suffix: str,
        page_step: int,
        hint_key: str | None = None,
        to_ui: Callable[[int], int] | None = None,
        to_setting: Callable[[int], int] | None = None,
        formatter: Callable[[int], str] | None = None,
    ) -> QWidget:
        slider = LabeledSlider(bounds[0], bounds[1], suffix, page_step, formatter)
        convert = to_setting or (lambda value: value)
        slider.value_committed.connect(lambda value, p=path, c=convert: self._changed({p: c(value)}))
        self._controls[path] = slider
        self._to_ui[path] = to_ui or (lambda value: value)
        return self._row(title, hint, slider, hint_key)

    def _switch(self, path: str, title: str, hint: str) -> QWidget:
        switch = Switch()
        switch.setAccessibleName(title)
        switch.toggled.connect(lambda checked, p=path: self._changed({p: checked}))
        self._controls[path] = switch
        return self._row(title, hint, switch)

    def _segmented(self, path: str, title: str, hint: str) -> QWidget:
        segmented = Segmented([(SPEED_LABELS[speed], speed) for speed in SPEEDS])
        segmented.changed.connect(lambda value, p=path: self._changed({p: value}))
        self._controls[path] = segmented
        return self._row(title, hint, segmented)

    def _length_row(self) -> QWidget:
        """운동 길이: 짧게 / 보통 / 길게. 두 운동의 길이가 함께 바뀐다."""
        preset = Segmented([(p.label, p.key) for p in LENGTH_PRESETS])
        preset.changed.connect(lambda key: self._changed(preset_changes(key)))
        self._preset = preset
        return self._row("운동 길이", "", preset, hint_key="preset_hint")

    def _toggle_advanced(self) -> None:
        opened = self._advanced.isHidden()
        self._advanced.setVisible(opened)  # 이미 부모에 붙은 뒤라 안전하다
        self._advanced_toggle.setText(ADVANCED_OPEN if opened else ADVANCED_CLOSED)

    # ---- 값 주고받기 ----

    def _changed(self, changes: dict[str, Any]) -> None:
        if self._loading:
            return
        result = self._manager.update(changes)
        self._load(result.settings)  # 보정된 값으로 컨트롤을 되돌린다 (예: 멈춤 기준이 초기화 기준 이상이면 낮춰진다)
        self._show_save_result(result.saved)

    def _show_save_result(self, saved: bool) -> None:
        self._status.setText("" if saved else SAVE_FAILED_MESSAGE)
        self._status.setVisible(not saved)

    def _load(self, settings: Settings) -> None:
        """컨트롤을 설정 값으로 채운다. 값을 채우는 동안에는 변경으로 보고하지 않는다."""
        self._loading = True
        try:
            for path, value in self._values(settings).items():
                widget = self._controls[path]
                if isinstance(widget, LabeledSlider):
                    widget.setValue(self._to_ui[path](value))
                elif isinstance(widget, Switch):
                    widget.setChecked(value)
                elif isinstance(widget, Segmented):
                    widget.setCurrentData(value)
            blink_on = settings.exercises.blink.enabled
            dot_on = settings.exercises.dot_follow.enabled
            self._controls["exercises.blink.duration_seconds"].setEnabled(blink_on)
            self._controls["exercises.dot_follow.duration_seconds"].setEnabled(dot_on)
            self._controls["exercises.dot_follow.speed"].setEnabled(dot_on)
            self._preset.setEnabled(blink_on or dot_on)
            self._warning.setVisible(not blink_on and not dot_on)
            self._preset.setCurrentData(current_preset(settings.exercises))  # 고급에서 따로 정했으면 아무것도 고르지 않은 상태
            self._update_hints(settings)
        finally:
            self._loading = False

    @staticmethod
    def _values(settings: Settings) -> dict[str, Any]:
        ex = settings.exercises
        return {
            "interval_minutes": settings.interval_minutes,
            "snooze_minutes": settings.snooze_minutes,
            "idle_pause_minutes": settings.idle_pause_minutes,
            "idle_reset_minutes": settings.idle_reset_minutes,
            "exercises.blink.enabled": ex.blink.enabled,
            "exercises.blink.duration_seconds": ex.blink.duration_seconds,
            "exercises.dot_follow.enabled": ex.dot_follow.enabled,
            "exercises.dot_follow.duration_seconds": ex.dot_follow.duration_seconds,
            "exercises.dot_follow.speed": ex.dot_follow.speed,
            "sound.enabled": settings.sound.enabled,
            "show_main_window_on_start": settings.show_main_window_on_start,
        }

    def _update_hints(self, settings: Settings) -> None:
        ex = settings.exercises
        blink = blink_timeline(ex.blink.duration_seconds)
        dot = dot_follow_timeline(ex.dot_follow.duration_seconds, ex.dot_follow.speed)
        key = current_preset(ex)
        if key is None:
            self._set_hint("preset_hint", CUSTOM_LENGTH_MESSAGE)
        else:
            preset = next(p for p in LENGTH_PRESETS if p.key == key)
            self._set_hint("preset_hint", f"깜빡임 {preset.blink_cycles}회 · 점 따라가기 {format_duration(preset.dot_seconds)}")
        self._set_hint("blink_hint", f"준비·마무리 포함 약 {format_duration(blink.total_seconds)}")
        self._set_hint("dot_hint", f"준비·마무리 포함 약 {format_duration(dot.total_seconds)}")

    def _set_hint(self, key: str, text: str) -> None:
        label = self._hints[key]
        label.setText(text)
        label.setVisible(True)  # 이미 부모에 붙은 뒤라 안전하다

    def control(self, path: str) -> QWidget:
        """경로(예: "interval_minutes")에 해당하는 컨트롤. 테스트와 다른 화면에서 쓴다."""
        return self._controls[path]

    @property
    def preset_control(self) -> Segmented:
        return self._preset

    @property
    def advanced_open(self) -> bool:
        return not self._advanced.isHidden()

    @property
    def paths(self) -> list[str]:
        return list(self._controls)
