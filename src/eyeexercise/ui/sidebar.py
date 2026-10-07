"""왼쪽 사이드바: 로고, 메뉴, 아래쪽의 눈 휴식 타이머 알약.

짙은 바탕에 굵은 글씨의 메뉴를 쓰고, 선택한 메뉴는 포인트 색 블록으로 보인다. 모두 직접 그려서
Windows 기본 모양에 의존하지 않고 테마(라이트·다크)가 바뀌면 같이 바뀐다.
"""

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from eyeexercise.ui import theme
from eyeexercise.ui.icons import render_icon

SIDEBAR_WIDTH = 212

# 메뉴 아이콘(24칸 격자의 선 그림). 이름은 Sidebar(icons=...)에서 고른다.
NAV_ICON_PATHS = {
    "home": "M3 11.5L12 4l9 7.5M6 10v9h12v-9",
    "chart": "M5 20V10M12 20V4M19 20v-7",
    "eye": "M2.5 12C5 7.5 8.5 5.5 12 5.5s7 2 9.5 6.5c-2.5 4.5-6 6.5-9.5 6.5S5 16.5 2.5 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
    "gear": "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM4 12h2M18 12h2M12 4v2M12 18v2",
}


def _icon_svg(path: str, color: str) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/></svg>'
    ).encode()


def _bold(pixel_size: int) -> QFont:
    font = QFont()
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.Weight.Black)
    return font


class NavButton(QAbstractButton):
    """사이드바 메뉴 한 칸. 선택하면 포인트 색 블록, 마우스를 올리면 은은한 밝은 블록."""

    def __init__(self, text: str, icon_name: str) -> None:
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        self.setFixedHeight(46)
        self._path = NAV_ICON_PATHS[icon_name]

    def sizeHint(self) -> QSize:
        return QSize(SIDEBAR_WIDTH - 32, 46)

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
        if self.isChecked():
            background, foreground = theme.color("accent"), QColor("#ffffff")
        elif self.underMouse():
            background, foreground = QColor(255, 255, 255, 22), QColor("#ffffff")
        else:
            background, foreground = QColor(0, 0, 0, 0), theme.color("sidebar_text")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 14, 14)
        if self.hasFocus() and not self.isChecked():  # 키보드로 옮겨 왔을 때 어디인지 보이게
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.color("sidebar_text"), 2))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 13, 13)
        QSvgRenderer(_icon_svg(self._path, foreground.name())).render(painter, QRectF(14, (rect.height() - 20) / 2, 20, 20))
        painter.setFont(_bold(15))
        painter.setPen(foreground)
        painter.drawText(QRectF(46, 0, rect.width() - 56, rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()


class TimerPill(QWidget):
    """눈 휴식 타이머 알약: ● 12:34 뒤 휴식. 점 색으로 상태(보통·알림·정지·하는 중)를 알린다."""

    _DOT_COLORS = {"normal": "sand", "alert": "gauge_mid", "paused": "text_faint", "active": "gauge_good"}

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(42)
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
        painter.setBrush(theme.color("sidebar_pill"))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setBrush(theme.color(self._DOT_COLORS.get(self._tone, "sand")))
        painter.drawEllipse(QRectF(16, (rect.height() - 9) / 2, 9, 9))
        font = _bold(13)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        width = int(rect.width() - 42 - 12)
        elided = QFontMetrics(font).elidedText(self._text, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRectF(34, 0, width, rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        painter.end()


class Sidebar(QWidget):
    current_changed = Signal(int)

    def __init__(self, labels: Sequence[str], icons: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._labels = list(labels)
        self._group = QButtonGroup(self)
        self._buttons: list[NavButton] = []

        logo = QLabel()
        logo.setPixmap(QPixmap.fromImage(render_icon(80)).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        name = QLabel("EyeExercise")
        name.setFont(_bold(17))
        name.setStyleSheet("color: #ffffff; background: transparent;")
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 0, 22)
        header.setSpacing(10)
        header.addWidget(logo)
        header.addWidget(name)
        header.addStretch()

        self.timer_pill = TimerPill()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 26, 16, 20)
        layout.setSpacing(6)
        layout.addLayout(header)
        for index, (label, icon) in enumerate(zip(labels, icons, strict=True)):
            button = NavButton(label, icon)
            button.clicked.connect(lambda _=False, i=index: self.set_current(i))
            self._group.addButton(button)
            self._buttons.append(button)
            layout.addWidget(button)
        layout.addStretch()
        layout.addWidget(self.timer_pill)
        self._buttons[0].setChecked(True)
        self._current = 0
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.update()
        for button in self._buttons:
            button.update()
        self.timer_pill.update()

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

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color("sidebar"))
        painter.end()
