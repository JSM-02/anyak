"""앱 아이콘. 코드로 그려서 크기마다 또렷하게 만들고, exe용 .ico는 `tools/make_icon.py`가 같은 그림으로 만든다.

디자인(쉬엄): 초록 둥근 사각형 위에 편안하게 감은 눈(흰 곡선과 속눈썹)과 새싹. 트레이는 라이트·다크 작업 표시줄
어느 쪽에서도 보여야 해서 초록 바탕을 깔았다. 이 아이콘은 테마를 따르지 않고 늘 같은 모양이다(브랜드 색).
"""

import struct

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # 트레이·작업 표시줄·알림 창에서 쓰는 크기들(배율 포함)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)  # .ico 파일에 담는 크기

_GREEN_TOP = "#2F9A6E"
_GREEN_BOTTOM = "#12544F"
LEAF = "#F2E3B3"  # 새싹 큰 잎 (모래색)
LEAF_SMALL = "#CFE8D8"  # 새싹 작은 잎


def render_icon(size: int) -> QImage:
    """size×size 투명 이미지에 아이콘을 그린다. 작은 크기에서는 선을 굵게 해서 뭉개지지 않게 한다."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 64  # 64칸 격자 기준 단위
    small = size <= 24

    # 바탕: 위가 밝은 초록 그라데이션의 둥근 사각형
    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0, QColor(_GREEN_TOP))
    gradient.setColorAt(1, QColor(_GREEN_BOTTOM))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    margin = 1 * u
    painter.drawRoundedRect(QRectF(margin, margin, size - 2 * margin, size - 2 * margin), 15 * u, 15 * u)

    # 감은 눈: 아래로 둥근 흰 곡선
    eye_pen = QPen(QColor("#ffffff"), (7.2 if small else 5.6) * u)
    eye_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(eye_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    eye = QPainterPath()
    eye.moveTo(10 * u, 33 * u)
    eye.quadTo(32 * u, 54 * u, 54 * u, 33 * u)
    painter.drawPath(eye)

    # 속눈썹 세 개
    lash_pen = QPen(QColor("#ffffff"), (5.4 if small else 4.2) * u)
    lash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(lash_pen)
    for x1, y1, x2, y2 in ((19, 43, 14.5, 49), (32, 48, 32, 55), (45, 43, 49.5, 49)):
        painter.drawLine(QPointF(x1 * u, y1 * u), QPointF(x2 * u, y2 * u))

    # 새싹: 큰 잎(모래색)과 작은 잎
    painter.setPen(Qt.PenStyle.NoPen)
    big = QPainterPath()
    big.moveTo(40 * u, 22 * u)
    big.cubicTo(40 * u, 14 * u, 46 * u, 11 * u, 51 * u, 12 * u)
    big.cubicTo(51 * u, 19 * u, 47 * u, 23 * u, 40 * u, 22 * u)
    painter.setBrush(QColor(LEAF))
    painter.drawPath(big)
    if not small:
        little = QPainterPath()
        little.moveTo(40 * u, 22 * u)
        little.cubicTo(40 * u, 18 * u, 36 * u, 16 * u, 33 * u, 17 * u)
        little.cubicTo(33 * u, 21 * u, 36 * u, 23 * u, 40 * u, 22 * u)
        painter.setBrush(QColor(LEAF_SMALL))
        painter.drawPath(little)
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
