"""설정 화면 등에 쓰는 컨트롤. Windows 기본 모양에 의존하지 않고 직접 그려서 흰 카드 위에서도 또렷하다.

(스타일시트로 일부만 꾸민 기본 입력칸·체크박스는 테두리가 사라져서 흰 배경에서 보이지 않았다.)
"""

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

BLUE = "#1a73e8"

# 슬라이더와 분할 버튼의 모양. 이 컨트롤을 쓰는 화면의 스타일시트에 이어 붙인다.
CONTROLS_STYLE = f"""
QSlider::groove:horizontal {{ height: 6px; background: #d5d8dc; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {BLUE}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -7px 0; border-radius: 10px;
    background: #ffffff; border: 2px solid {BLUE};
}}
QSlider::handle:horizontal:hover {{ background: #e8f0fe; }}
QSlider::sub-page:horizontal:disabled {{ background: #c4c7cc; }}
QSlider::handle:horizontal:disabled {{ border-color: #c4c7cc; background: #f1f3f4; }}
#segment {{ background: #e6e6ea; border: 1px solid #d5d8dc; border-radius: 7px; }}
#segment QPushButton {{
    background: transparent; border: none; border-radius: 5px; padding: 5px 16px; color: #3c4043;
}}
#segment QPushButton:checked {{ background: #ffffff; color: #202124; font-weight: bold; }}
#segment QPushButton:disabled {{ color: #9aa0a6; }}
"""


class Switch(QAbstractButton):
    """켜기/끄기 슬라이드 스위치. 누르면 동그라미가 밀려 켜짐(파랑)과 꺼짐(회색)이 바뀐다."""

    _SIZE = QSize(46, 26)

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self._SIZE)

    def sizeHint(self) -> QSize:
        return self._SIZE

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, enabled = self.isChecked(), self.isEnabled()
        if enabled:
            track = QColor(BLUE if on else "#9aa0a6")
        else:
            track = QColor("#a8c7fa" if on else "#dadce0")
        width, height = float(self.width()), float(self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 3, width, height - 6), (height - 6) / 2, (height - 6) / 2)
        knob = height - 10
        x = width - knob - 5 if on else 5.0
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.drawEllipse(QRectF(x, 5, knob, knob))
        if self.hasFocus():  # 키보드로 옮겨 왔을 때 어디에 있는지 보이게
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BLUE), 2))
            painter.drawRoundedRect(QRectF(1, 2, width - 2, height - 4), (height - 4) / 2, (height - 4) / 2)
        painter.end()


class _Slider(QSlider):
    """값을 바꾸려면 직접 끌거나 눌러야 한다. 페이지를 스크롤하다가 마우스 휠로 값이 바뀌는 사고를 막는다."""

    def __init__(self) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()  # 페이지 스크롤로 넘긴다


class _ValueBubble(QWidget):
    """슬라이더 손잡이 바로 위에 현재 값을 말풍선으로 보여 준다. 손잡이를 따라 움직인다."""

    _HEIGHT = 22

    def __init__(self, slider: QSlider, text: Callable[[], str]) -> None:
        super().__init__()
        self._slider = slider
        self._text = text
        self.setFixedHeight(self._HEIGHT)
        slider.valueChanged.connect(lambda _v: self.update())

    def handle_center_x(self) -> float:
        option = QStyleOptionSlider()
        self._slider.initStyleOption(option)
        handle = self._slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self._slider
        )
        return handle.center().x()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        text = self._text()
        width = painter.fontMetrics().horizontalAdvance(text) + 16
        left = min(max(self.handle_center_x() - width / 2, 0), max(0, self.width() - width))
        box = QRectF(left, 0, width, self._HEIGHT - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BLUE))
        painter.drawRoundedRect(box, 8, 8)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class LabeledSlider(QWidget):
    """슬라이더 + 현재 값("20 분"). 끄는 동안에는 값만 미리 보여 주고, 놓았을 때(또는 키·클릭으로 바꿨을 때) 확정한다."""

    value_committed = Signal(int)

    def __init__(
        self, low: int, high: int, suffix: str = "", page_step: int = 1, formatter: Callable[[int], str] | None = None
    ) -> None:
        super().__init__()
        self._suffix = suffix
        self._formatter = formatter  # 값을 "1분 30초"처럼 직접 꾸밀 때 쓴다. 없으면 숫자 + 단위
        self._slider = _Slider()
        self._slider.setRange(low, high)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(page_step)
        self._slider.setMinimumWidth(220)
        self._slider.setMinimumHeight(28)  # 손잡이(테두리 포함 약 20px)가 위아래로 잘리지 않게 한다
        self._label = QLabel()
        self._label.setObjectName("sliderValue")
        self._label.setMinimumWidth(72)
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        track = QVBoxLayout()
        track.setContentsMargins(0, 0, 0, 0)
        track.setSpacing(0)
        self._bubble = _ValueBubble(self._slider, lambda: self._format(self._slider.value()))
        track.addWidget(self._bubble)
        track.addWidget(self._slider)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(track, stretch=1)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignTop)
        self._slider.valueChanged.connect(self._on_value_changed)
        self._slider.sliderReleased.connect(lambda: self.value_committed.emit(self._slider.value()))
        self._on_value_changed(self._slider.value())

    def _format(self, value: int) -> str:
        return self._formatter(value) if self._formatter else f"{value}{self._suffix}"

    def _on_value_changed(self, value: int) -> None:
        self._label.setText(self._format(value))
        if not self._slider.isSliderDown():
            self.value_committed.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def setValue(self, value: int) -> None:
        self._slider.setValue(value)

    def minimum(self) -> int:
        return self._slider.minimum()

    def maximum(self) -> int:
        return self._slider.maximum()

    def suffix(self) -> str:
        return self._suffix

    @property
    def slider(self) -> QSlider:
        return self._slider

    @property
    def value_label(self) -> QLabel:
        return self._label

    @property
    def bubble(self) -> QWidget:
        return self._bubble



class Segmented(QFrame):
    """분할 버튼. 선택한 것만 흰 바탕으로 보인다. 사용자가 누르면 changed(값)을 낸다."""

    changed = Signal(object)

    def __init__(self, options: Sequence[tuple[str, Any]]) -> None:
        super().__init__()
        self.setObjectName("segment")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._buttons: list[QPushButton] = []
        self._data: list[Any] = []
        for text, data in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, d=data: self.changed.emit(d))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons.append(button)
            self._data.append(data)

    def buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def currentData(self) -> Any:
        for button, data in zip(self._buttons, self._data, strict=True):
            if button.isChecked():
                return data
        return None

    def setCurrentData(self, data: Any) -> None:
        """값을 고른 것으로 표시한다. 목록에 없는 값이면 아무것도 고르지 않은 상태가 된다.
        changed는 내지 않는다 (화면을 채울 때 쓰므로)."""
        self._group.setExclusive(False)  # 배타 그룹에서는 선택된 버튼을 프로그램으로도 끌 수 없다
        for button, value in zip(self._buttons, self._data, strict=True):
            button.setChecked(value == data)
        self._group.setExclusive(True)
