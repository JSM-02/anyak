"""화면 본문을 가운데 한 칸(최대 너비)으로 두는 도우미.

창을 크게 키워도 본문 배치와 비율이 지금(기본 창 크기) 그대로 보이게 한다. 본문이 최대 너비를 넘으면 늘어나지 않고,
남는 자리는 양옆의 바탕색 여백이 된다. 창이 그보다 좁으면 평소처럼 창 너비에 맞춰 줄어든다.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from eyeexercise.ui import theme

MAX_CONTENT_WIDTH = 980  # 기본 창(1000px)의 본문보다 조금 넓은 정도까지만 늘어난다
_WRAPPER_STYLE = "#pageColumn { background: $bg; }"


def centered_column(content: QWidget, max_width: int = MAX_CONTENT_WIDTH) -> QWidget:
    """content를 최대 너비를 정해 가운데에 놓은 바깥 위젯을 돌려준다. 스크롤 영역에는 이 바깥 위젯을 넣는다."""
    content.setMaximumWidth(max_width)
    wrapper = QWidget()
    wrapper.setObjectName("pageColumn")
    wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    theme.bind(wrapper, _WRAPPER_STYLE)
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addStretch(1)
    layout.addWidget(content, 1000, Qt.AlignmentFlag.AlignTop)  # 본문이 먼저 늘어나고 최대 너비를 넘는 만큼만 양옆 여백이 된다
    layout.addStretch(1)
    return wrapper
