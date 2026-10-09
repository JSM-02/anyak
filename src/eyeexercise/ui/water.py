"""물과 파도를 그리는 도우미. 홈 화면과 알림 팝업이 같은 물을 쓴다.

수면의 높이 계산은 core/tide가 하고, 여기서는 그 값을 QPainterPath로 옮긴다.
"""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath

from eyeexercise.core.tide import WaveStyle, wave_margin, wave_offset

WAVE_STEP = 12  # 수면 곡선을 이 간격(px)마다 계산한다


def water_paths(width: float, height: float, level: float, t: float, style: WaveStyle) -> tuple[QPainterPath, QPainterPath]:
    """(물, 수면의 선)을 만든다. level은 물이 차지하는 높이의 비율(0~1)이고 t는 초.

    수위 0%와 100%에서도 빈틈이 없도록 위아래로 파도 높이만큼 여백을 둔다."""
    w, h = float(width), float(height)
    margin = wave_margin(style)
    base = -margin + (h + 2 * margin) * (1 - level)
    xs = [min(float(x), w) for x in range(0, int(w) + WAVE_STEP, WAVE_STEP)]
    line = QPainterPath(QPointF(xs[0], base + wave_offset(xs[0], t, w, style)))
    for x in xs[1:]:
        line.lineTo(x, base + wave_offset(x, t, w, style))
    water = QPainterPath(line)
    water.lineTo(w, h + margin)
    water.lineTo(0, h + margin)
    water.closeSubpath()
    return water, line
