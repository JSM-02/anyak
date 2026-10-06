"""앱 아이콘. 이미지 파일 없이 코드로 그린다 (exe용 .ico는 8단계에서 추가)."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_SIZE = 64


def app_icon() -> QIcon:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = QPointF(_SIZE / 2, _SIZE / 2)

    painter.setPen(QPen(QColor("#1a73e8"), 4))
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(center, 28, 18)  # 눈 모양

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1a73e8"))
    painter.drawEllipse(center, 11, 11)  # 홍채
    painter.setBrush(QColor("#202124"))
    painter.drawEllipse(center, 5, 5)  # 동공
    painter.end()
    return QIcon(pixmap)
