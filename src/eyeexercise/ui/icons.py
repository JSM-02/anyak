"""앱 아이콘. 코드로 그려서 크기마다 또렷하게 만들고, exe용 .ico는 `tools/make_icon.py`가 같은 그림으로 만든다.

디자인: 초록 둥근 사각형 위에 흰 눈. 트레이는 라이트·다크 작업 표시줄 어느 쪽에서도 보여야 해서
눈만 그리지 않고 초록 바탕을 깔았다. 이 아이콘은 테마를 따르지 않고 늘 같은 모양이다(브랜드 색).
"""

import struct

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # 트레이·작업 표시줄·알림 창에서 쓰는 크기들(배율 포함)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)  # .ico 파일에 담는 크기

_GREEN_TOP = "#34a853"
_GREEN_BOTTOM = "#188038"
_IRIS = "#137333"
_PUPIL = "#0b2b17"


def render_icon(size: int) -> QImage:
    """size×size 투명 이미지에 아이콘을 그린다. 작은 크기에서는 세부를 줄이고 눈을 키운다."""
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

    # 눈: 아몬드 모양. 작은 크기에서는 위아래를 더 두껍게 해서 뭉개지지 않게 한다
    half_w = (25 if small else 23) * u
    lid = (15 if small else 13) * u  # 위아래 눈꺼풀 높이
    cx, cy = size / 2, size / 2
    eye = QPainterPath()
    eye.moveTo(cx - half_w, cy)
    eye.cubicTo(cx - half_w * 0.45, cy - lid * 1.45, cx + half_w * 0.45, cy - lid * 1.45, cx + half_w, cy)
    eye.cubicTo(cx + half_w * 0.45, cy + lid * 1.45, cx - half_w * 0.45, cy + lid * 1.45, cx - half_w, cy)
    painter.setBrush(QColor("#ffffff"))
    painter.drawPath(eye)

    # 홍채·동공·반짝임 (눈 모양 안쪽으로만)
    painter.setClipPath(eye)
    center = QPointF(cx, cy)
    painter.setBrush(QColor(_IRIS))
    painter.drawEllipse(center, 11 * u, 11 * u)
    painter.setBrush(QColor(_PUPIL))
    painter.drawEllipse(center, (5.5 if not small else 5) * u, (5.5 if not small else 5) * u)
    if not small:
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(cx - 4 * u, cy - 4 * u), 2.4 * u, 2.4 * u)
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
