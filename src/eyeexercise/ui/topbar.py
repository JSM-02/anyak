"""위쪽 메뉴 줄: 왼쪽에 앱 이름 글자, 오른쪽에 메뉴(선택한 메뉴는 아래 밑줄)와 사용 안내 "?", 메뉴 왼쪽에 눈 휴식 남은 시간(점 + 글자).

시안 E의 모양대로 상자 없이 굵은 글씨만 쓴다. 홈은 큰 타이머가 이미 있어서 남은 시간 표시를 숨긴다(`set_pill_visible`).
모두 직접 그려서 Windows 기본 모양에 의존하지 않고 테마(라이트·다크)가 바뀌면 같이 바뀐다.
"""

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QLabel, QWidget

from eyeexercise import APP_NAME
from eyeexercise.ui import theme

TOPBAR_HEIGHT = 68
PILL_WIDTH = 150


def _bold(pixel_size: int) -> QFont:
    font = QFont()
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.Weight.Black)
    return font


class NavButton(QAbstractButton):
    """메뉴 한 칸. 선택하면 글자가 또렷해지고 아래에 밑줄이 생긴다."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        self.setFixedHeight(40)
        self._keyboard_focus = False

    def focusInEvent(self, event) -> None:
        # 창이 처음 열리며 저절로 생긴 포커스에는 테두리를 그리지 않는다. Tab·Shift+Tab으로 옮겼을 때만 보인다.
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(event)

    def _text_width(self) -> int:
        return QFontMetrics(_bold(15)).horizontalAdvance(self.text())

    def sizeHint(self) -> QSize:
        return QSize(self._text_width() + 28, 40)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        checked = self.isChecked()
        foreground = theme.color("text") if checked or self.underMouse() else theme.color("text_secondary")
        painter.setFont(_bold(15))
        painter.setPen(foreground)
        painter.drawText(QRectF(0, 0, rect.width(), rect.height() - 6), Qt.AlignmentFlag.AlignCenter, self.text())
        if checked:  # 글자 아래 밑줄
            width = self._text_width()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(foreground)
            painter.drawRoundedRect(QRectF((rect.width() - width) / 2, rect.height() - 7, width, 3), 1.5, 1.5)
        if self.hasFocus() and self._keyboard_focus and not checked:  # 키보드로 옮겨 왔을 때 어디인지 보이게
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.color("text_secondary"), 1.5))
            painter.drawRoundedRect(rect.adjusted(1, 4, -1, -4), 8, 8)
        painter.end()


class HelpButton(QAbstractButton):
    """사용 안내를 여는 동그란 "?" 버튼. 테두리만 있는 원이라 메뉴 글자와 같은 결로 보인다."""

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("사용 안내")
        self.setToolTip("사용 안내")
        self.setFixedSize(36, 36)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        hovered = self.underMouse() or self.isDown()
        color = theme.color("text") if hovered else theme.color("text_secondary")
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("chip"))
            painter.drawEllipse(rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2))
        painter.drawEllipse(rect)
        painter.setFont(_bold(16))
        painter.setPen(color)
        painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()


class TimerPill(QWidget):
    """눈 휴식 남은 시간: ● 12:34 뒤 휴식. 상자 없이 점과 굵은 글자만 쓰고, 점 색으로 상태(보통·알림·정지·하는 중)를 알린다."""

    _DOT_COLORS = {"normal": "hero", "alert": "gauge_mid", "paused": "text_faint", "active": "gauge_good"}

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(PILL_WIDTH, 40)
        self._text = ""
        self._tone = "normal"

    @property
    def text(self) -> str:
        return self._text

    @property
    def tone(self) -> str:
        return self._tone

    def set_timer(self, text: str, tone: str = "normal") -> None:
        if (text, tone) == (self._text, self._tone):
            return
        self._text, self._tone = text, tone
        self.setToolTip(text)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.color(self._DOT_COLORS.get(self._tone, "hero")))
        painter.drawEllipse(QRectF(2, (rect.height() - 9) / 2, 9, 9))
        font = _bold(14)
        painter.setFont(font)
        painter.setPen(theme.color("text"))
        width = int(rect.width() - 22)
        elided = QFontMetrics(font).elidedText(self._text, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRectF(20, 0, width, rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        painter.end()


class TopBar(QWidget):
    current_changed = Signal(int)
    help_requested = Signal()  # "?"를 눌렀다

    def __init__(self, labels: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(TOPBAR_HEIGHT)
        self._labels = list(labels)
        self._group = QButtonGroup(self)
        self._buttons: list[NavButton] = []

        name = QLabel(APP_NAME)
        name.setFont(_bold(22))
        theme.bind(name, "QLabel { color: $text; background: transparent; }")

        self.timer_pill = TimerPill()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(36, 0, 36, 0)
        layout.setSpacing(6)
        layout.addWidget(name)
        layout.addStretch()
        layout.addWidget(self.timer_pill)
        layout.addSpacing(24)
        for index, label in enumerate(labels):
            button = NavButton(label)
            button.clicked.connect(lambda _=False, i=index: self.set_current(i))
            self._group.addButton(button)
            self._buttons.append(button)
            layout.addWidget(button)
        layout.addSpacing(10)
        self.help_button = HelpButton()
        self.help_button.clicked.connect(self.help_requested)
        layout.addWidget(self.help_button)
        self._buttons[0].setChecked(True)
        self._current = 0
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.update()
        for button in self._buttons:
            button.update()
        self.timer_pill.update()
        self.help_button.update()

    def count(self) -> int:
        return len(self._buttons)

    def label(self, index: int) -> str:
        return self._labels[index]

    def current(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if not 0 <= index < len(self._buttons):
            return
        self._buttons[index].setChecked(True)
        if index != self._current:
            self._current = index
            self.current_changed.emit(index)

    def set_timer(self, text: str, tone: str = "normal") -> None:
        self.timer_pill.set_timer(text, tone)

    def set_pill_visible(self, visible: bool) -> None:
        self.timer_pill.setVisible(visible)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color("paper"))
        painter.end()
