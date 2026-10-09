"""앱 아이콘. 코드로 그려서 크기마다 또렷하게 만들고, exe용 .ico는 `tools/make_icon.py`가 같은 그림으로 만든다.

디자인((안)약): 납작한 깊은 초록 둥근 사각형 위에 모래색 괄호 ( )와 물방울. 이름 "(안)약"의 괄호와 안약 한 방울을
그대로 그렸다. 그라데이션은 쓰지 않는다. 트레이는 라이트·다크 작업 표시줄 어느 쪽에서도 보여야 해서 초록 바탕을 깔았고,
이 아이콘은 테마를 따르지 않고 늘 같은 모양이다(브랜드 색).
"""

import struct

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # 트레이·작업 표시줄·알림 창에서 쓰는 크기들(배율 포함)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)  # .ico 파일에 담는 크기

BACKGROUND = "#12544F"  # 깊은 초록 (앱의 물 색)
MARK = "#F2E3B3"  # 괄호와 물방울 (모래색)


def _drop(cx: float, cy: float, w: float, h: float) -> QPainterPath:
    """물방울: 위가 뾰족하고 아래가 둥글다. (cx, cy)는 전체의 가운데."""
    top, bottom, r = cy - h / 2, cy + h / 2, w / 2
    center = bottom - r
    path = QPainterPath()
    path.moveTo(cx, top)
    path.cubicTo(cx + r * 0.12, top + (center - top) * 0.50, cx + r, center - r * 0.60, cx + r, center)
    path.arcTo(QRectF(cx - r, center - r, 2 * r, 2 * r), 0, -180)
    path.cubicTo(cx - r, center - r * 0.60, cx - r * 0.12, top + (center - top) * 0.50, cx, top)
    path.closeSubpath()
    return path


def render_icon(size: int) -> QImage:
    """size×size 투명 이미지에 아이콘을 그린다. 작은 크기에서는 괄호를 굵게, 물방울을 크게 해서 뭉개지지 않게 한다."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    small = size <= 24

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BACKGROUND))
    painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.26, s * 0.26)

    # 괄호: 큰 원의 일부(호)라서 기하학적이고 깔끔하다
    radius, theta = 0.60 * s, 34 if not small else 36
    pen = QPen(QColor(MARK), (0.085 if small else 0.062) * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    left_rect = QRectF(0.19 * s, s / 2 - radius, 2 * radius, 2 * radius)
    left = QPainterPath()
    left.arcMoveTo(left_rect, 180 - theta)
    left.arcTo(left_rect, 180 - theta, 2 * theta)
    painter.drawPath(left)
    right_rect = QRectF(0.81 * s - 2 * radius, s / 2 - radius, 2 * radius, 2 * radius)
    right = QPainterPath()
    right.arcMoveTo(right_rect, theta)
    right.arcTo(right_rect, theta, -2 * theta)
    painter.drawPath(right)

    # 물방울(안약 한 방울)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(MARK))
    width, height = (0.26, 0.40) if small else (0.23, 0.35)
    painter.drawPath(_drop(s / 2, s * 0.50, s * width, s * height))
    painter.end()
    return image


def app_icon() -> QIcon:
    """여러 크기를 담은 아이콘. 화면 배율(125%·150%)에서도 알맞은 크기가 골라진다."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_icon(size)))
    return icon


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def ico_bytes(sizes: tuple[int, ...] = ICO_SIZES) -> bytes:
    """여러 크기를 PNG로 담은 .ico 파일 내용 (Windows Vista 이후 형식). 256은 폭·높이 칸에 0으로 적는다."""
    pngs = [_png_bytes(render_icon(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for size, png in zip(sizes, pngs, strict=True):
        dimension = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    return header + entries + b"".join(pngs)
