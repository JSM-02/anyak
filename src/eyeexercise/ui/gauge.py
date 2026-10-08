"""휴식 달성률 원형 게이지. 위에서 시계 방향으로 차오르고, 80% 지점에 목표선이 있다.

색은 80% 이상 초록, 50~79% 노랑, 50% 미만 빨강이다(`core/home.gauge_tone`). '잘 쉬고 있어요' 같은 상태 문구는 쓰지 않는다.
"""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from eyeexercise.core.home import GAUGE_TARGET, TONE_GOOD, TONE_LOW, TONE_MID, gauge_tone
from eyeexercise.ui import theme

_TONE_COLORS = {TONE_GOOD: "gauge_good", TONE_MID: "gauge_mid", TONE_LOW: "gauge_low"}
_START_ANGLE = 90 * 16  # Qt의 각도는 3시 방향이 0, 반시계 방향이 양수이고 단위는 1/16도. 12시에서 시작한다
_TARGET_ANGLE = math.radians(90 - GAUGE_TARGET * 360)  # 목표선의 각도(수학 좌표, 반시계가 양수)


class RingGauge(QWidget):
    """가운데에 퍼센트를 쓰는 원형 게이지. 달성률이 없으면(None) 빈 고리에 '–'를 쓴다."""

    def __init__(self, min_size: int = 150, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rate: float | None = None
        self.setMinimumSize(min_size, min_size)
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.update()

    @property
    def rate(self) -> float | None:
        return self._rate

    @property
    def tone(self) -> str:
        return gauge_tone(self._rate)

    @property
    def text(self) -> str:
        return "–" if self._rate is None else f"{round(self._rate * 100)}%"

    def set_rate(self, rate: float | None) -> None:
        rate = None if rate is None else min(1.0, max(0.0, rate))
        if rate == self._rate:
            return
        self._rate = rate
        self.setAccessibleDescription(f"휴식 달성률 {self.text}")
        self.update()

    def ring_width(self) -> float:
        """고리 굵기. 게이지 크기에 비례한다(큰 홈 화면 게이지와 작은 카드 게이지가 같은 비율로 보인다)."""
        return max(6.0, min(self.width(), self.height()) * 0.1)

    def ring_rect(self) -> QRectF:
        """고리가 그려지는 정사각형(선 굵기의 절반만큼 안쪽)."""
        side = min(self.width(), self.height())
        margin = self.ring_width() / 2 + 2
        return QRectF((self.width() - side) / 2 + margin, (self.height() - side) / 2 + margin, side - 2 * margin, side - 2 * margin)

    def target_point(self):
        """80% 목표선이 고리와 만나는 바깥쪽 지점(테스트용). 12시에서 시계 방향으로 80%만큼 돈 곳이다."""
        rect = self.ring_rect()
        angle = _TARGET_ANGLE
        radius = rect.width() / 2
        return (rect.center().x() + radius * math.cos(angle), rect.center().y() - radius * math.sin(angle))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.ring_rect()

        pen = QPen(theme.color("track"), self.ring_width())
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        if self._rate is not None and self._rate > 0:
            pen.setColor(theme.color(_TONE_COLORS[self.tone]))
            painter.setPen(pen)
            painter.drawArc(rect, _START_ANGLE, int(-self._rate * 360 * 16))

        # 80% 목표선: 고리를 가로지르는 짧은 선
        angle = _TARGET_ANGLE
        cx, cy, radius = rect.center().x(), rect.center().y(), rect.width() / 2
        inner, outer = radius - self.ring_width() / 2 - 3, radius + self.ring_width() / 2 + 3
        painter.setPen(QPen(theme.color("text"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(
            int(cx + inner * math.cos(angle)), int(cy - inner * math.sin(angle)), int(cx + outer * math.cos(angle)), int(cy - outer * math.sin(angle))
        )

        font = QFont(self.font())
        font.setPixelSize(max(theme.FONT_SIZES["fs_small"], round(rect.width() * 0.26)))
        font.setWeight(QFont.Weight.Black)
        painter.setFont(font)
        painter.setPen(theme.color("text"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        painter.end()
