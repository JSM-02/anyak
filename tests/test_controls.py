"""직접 그리는 컨트롤이 흰 카드 위에서 실제로 보이는지 픽셀로 확인한다.

예전에는 기본 입력칸·체크박스에 스타일시트를 일부만 입혀서 Windows에서 테두리가 사라져 흰 배경에 묻혔다.
"""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QStyleFactory, QVBoxLayout, QWidget

from eyeexercise.core.settings import Settings, with_changes
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.ui import theme
from eyeexercise.ui.controls import CONTROLS_STYLE, LabeledSlider, Segmented, Switch
from eyeexercise.ui.settings_page import SettingsPage


_cards: list[QFrame] = []  # 테스트가 카드를 변수에 담지 않아도 컨트롤이 먼저 지워지지 않게 붙들어 둔다


@pytest.fixture(autouse=True)
def _close_cards():
    yield
    for card in _cards:
        card.close()
        card.deleteLater()
    _cards.clear()


def white_card(*widgets):
    """흰 카드 위에 컨트롤을 올린다 (설정 화면과 같은 배경)."""
    card = QFrame()
    _cards.append(card)
    card.setStyleSheet("QFrame { background: #ffffff; }" + theme.render(CONTROLS_STYLE))
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    for widget in widgets:
        layout.addWidget(widget)
    card.resize(420, 140)
    card.show()
    QApplication.processEvents()
    return card


def render_on_white(widget) -> QImage:
    """위젯을 흰 바탕 위에 그린다. render()의 기본값은 창 기본 배경(회색)을 먼저 깔아서 실제 흰 카드와 달라진다."""
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    widget.render(painter, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)  # DrawWindowBackground는 뺀다
    painter.end()
    return image


def pixel(widget, x, y) -> QColor:
    return QColor(render_on_white(widget).pixel(x, y))


def distance_from_white(color: QColor) -> int:
    return 255 * 3 - (color.red() + color.green() + color.blue())


def assert_visible(color: QColor, minimum: int = 60):
    """흰색에서 충분히 떨어진 색인지 (세 채널 합이 minimum 이상 어둡다)."""
    assert distance_from_white(color) >= minimum, color.name()


# ---- 스위치 ----


def test_스위치는_끄고_켜는_모양이_다르다(qapp):
    switch = Switch()
    white_card(switch)
    off = render_on_white(switch)
    switch.setChecked(True)
    on = render_on_white(switch)
    assert off != on


def test_꺼진_스위치도_흰_카드_위에서_보인다(qapp):
    switch = Switch()
    white_card(switch)
    # 꺼짐일 때 동그라미는 왼쪽이므로 오른쪽 끝의 트랙 색을 본다
    assert_visible(pixel(switch, switch.width() - 8, switch.height() // 2))


def test_켜진_스위치는_초록으로_보인다(qapp):
    switch = Switch()
    switch.setChecked(True)
    white_card(switch)
    track = pixel(switch, 8, switch.height() // 2)  # 켜짐일 때 동그라미는 오른쪽이므로 왼쪽 끝의 트랙 색
    assert track.name() == "#188038"


def test_스위치를_누르면_바뀌고_신호를_낸다(qapp):
    switch = Switch()
    toggled = []
    switch.toggled.connect(toggled.append)
    white_card(switch)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert switch.isChecked() and toggled == [True]
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert not switch.isChecked() and toggled == [True, False]


def test_스위치는_키보드_스페이스로도_바뀐다(qapp):
    switch = Switch()
    white_card(switch)
    switch.setFocus()
    QTest.keyClick(switch, Qt.Key.Key_Space)
    assert switch.isChecked()


def test_꺼진_상태의_비활성_스위치도_보인다(qapp):
    switch = Switch()
    switch.setEnabled(False)
    white_card(switch)
    assert_visible(pixel(switch, switch.width() - 8, switch.height() // 2), minimum=30)


def test_프로그램으로_값을_바꿔도_다시_그려진다(qapp):
    switch = Switch()
    white_card(switch)
    before = render_on_white(switch)
    switch.setChecked(True)
    assert render_on_white(switch) != before


# ---- 슬라이더 ----


def test_슬라이더의_홈은_흰_카드_위에서_보인다(qapp):
    control = LabeledSlider(1, 120, " 분", 5)
    control.setValue(10)  # 손잡이는 왼쪽 끝 근처. 오른쪽의 아직 채워지지 않은 홈을 본다
    white_card(control)
    slider = control.slider
    assert_visible(pixel(slider, int(slider.width() * 0.8), slider.height() // 2), minimum=50)


def test_슬라이더의_채워진_부분은_초록이다(qapp):
    control = LabeledSlider(1, 120, " 분", 5)
    control.setValue(100)
    white_card(control)
    slider = control.slider
    assert pixel(slider, int(slider.width() * 0.4), slider.height() // 2).name() == "#188038"


def test_비활성_슬라이더도_보인다(qapp):
    control = LabeledSlider(1, 120, " 분", 5)
    control.setValue(100)
    control.setEnabled(False)
    white_card(control)
    slider = control.slider
    assert_visible(pixel(slider, int(slider.width() * 0.4), slider.height() // 2), minimum=50)


def test_슬라이더_값_표시의_단위와_범위(qapp):
    control = LabeledSlider(5, 300, " 초", 10)
    assert (control.minimum(), control.maximum(), control.suffix()) == (5, 300, " 초")
    control.setValue(1000)  # 범위 밖은 끝으로 맞춰진다
    assert control.value() == 300 and control.value_label.text() == "300 초"
    control.setValue(-5)
    assert control.value() == 5


def test_끄는_동안에는_확정하지_않고_놓으면_한_번_확정한다(qapp):
    control = LabeledSlider(1, 120, " 분", 5)
    committed = []
    control.value_committed.connect(committed.append)
    control.slider.setSliderDown(True)
    control.slider.setValue(30)
    control.slider.setValue(31)
    assert committed == [] and control.value_label.text() == "31 분"
    control.slider.setSliderDown(False)
    assert committed == [31]


def test_끄지_않고_값을_바꾸면_바로_확정한다(qapp):
    control = LabeledSlider(1, 120, " 분", 5)
    committed = []
    control.value_committed.connect(committed.append)
    control.setValue(10)
    assert committed == [10]


# ---- 분할 버튼 ----


def test_분할_버튼의_바탕은_흰_카드_위에서_보인다(qapp):
    segmented = Segmented([("느리게", "slow"), ("보통", "normal"), ("빠르게", "fast")])
    segmented.setCurrentData("normal")
    white_card(segmented)
    # 선택하지 않은 쪽(왼쪽 끝)의 회색 바탕
    assert_visible(pixel(segmented, 6, segmented.height() // 2), minimum=30)


def test_분할_버튼_선택_표시와_신호(qapp):
    segmented = Segmented([("느리게", "slow"), ("보통", "normal"), ("빠르게", "fast")])
    changed = []
    segmented.changed.connect(changed.append)
    white_card(segmented)
    segmented.setCurrentData("fast")
    assert segmented.currentData() == "fast" and changed == []  # 프로그램으로 고른 것은 알리지 않는다
    segmented.buttons()[0].click()
    assert segmented.currentData() == "slow" and changed == ["slow"]


def test_분할_버튼은_하나만_선택된다(qapp):
    segmented = Segmented([("가", 1), ("나", 2), ("다", 3)])
    segmented.setCurrentData(1)
    segmented.setCurrentData(3)
    assert [b.isChecked() for b in segmented.buttons()] == [False, False, True]
    assert Segmented([("가", 1)]).currentData() is None


# ---- 플랫폼 기본 스타일과 상관없이 보인다 ----


@pytest.mark.parametrize("style", [s for s in ("windows11", "windowsvista", "windows", "Fusion") if s in QStyleFactory.keys()] or ["Fusion"])
def test_어떤_기본_스타일에서도_설정_화면의_컨트롤이_보인다(qapp, style):
    previous = qapp.style().objectName()
    qapp.setStyle(style)
    try:
        page = SettingsPage(SettingsManager(with_changes(Settings(), {"show_main_window_on_start": False})))  # 꺼진 스위치를 보려고 끈다
        page.resize(900, 1100)
        page.show()
        qapp.processEvents()
        slider = page.control("interval_minutes").slider  # 20/120이라 손잡이가 왼쪽에 있고 오른쪽 홈이 비어 있다
        assert_visible(pixel(slider, int(slider.width() * 0.8), slider.height() // 2), minimum=50)
        switch = page.control("show_main_window_on_start")  # 꺼진 스위치
        assert_visible(pixel(switch, switch.width() - 8, switch.height() // 2))
        segmented = page.control("exercises.dot_follow.speed")
        assert_visible(pixel(segmented, 6, segmented.height() // 2), minimum=30)
    finally:
        qapp.setStyle(previous)


def test_세_컨트롤은_기본_위젯을_쓰지_않는다(qapp):
    """스타일시트로 일부만 꾸민 기본 입력칸(QSpinBox)·체크박스·콤보박스가 설정 화면에 남아 있지 않아야 한다."""
    from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox

    page = SettingsPage(SettingsManager(Settings()))
    for kind in (QSpinBox, QCheckBox, QComboBox):
        assert page.findChildren(kind) == [], kind.__name__


# ---- 슬라이더 손잡이가 잘리지 않는다 ----


def _is_accent(color: QColor) -> bool:
    return color.red() < 100 and color.green() > color.red() + 40 and color.green() > color.blue() + 40  # 손잡이 테두리 초록(#188038)


def _is_white(color: QColor) -> bool:
    return min(color.red(), color.green(), color.blue()) >= 250


def handle_ring_distances(slider) -> tuple[int, int] | None:
    """손잡이 가운데에서 위·아래로 테두리(초록)까지의 거리. 위나 아래가 잘려 테두리가 없으면 None."""
    image = render_on_white(slider)
    width, height = image.width(), image.height()
    cy = height // 2
    row = [QColor(image.pixel(x, cy)) for x in range(width)]
    center = None
    reach = 14  # 손잡이 속(흰색)의 지름이 14px 안팎이라 가운데에서 양쪽 테두리까지 이만큼은 본다
    for x in range(reach, width - reach):  # 흰 속의 양옆에 초록 테두리가 있는 자리를 찾는다
        if _is_white(row[x]) and any(_is_accent(row[x - d]) for d in range(1, reach)) and any(_is_accent(row[x + d]) for d in range(1, reach)):
            run_start = x
            while run_start > 0 and _is_white(row[run_start - 1]):
                run_start -= 1
            run_end = x
            while run_end < width - 1 and _is_white(row[run_end + 1]):
                run_end += 1
            if run_end - run_start >= 8:  # 속이 충분히 넓은 흰 구간(손잡이 안쪽)만 인정한다
                center = (run_start + run_end) // 2
                break
    if center is None:
        return None
    up = next((d for d in range(1, cy + 1) if _is_accent(QColor(image.pixel(center, cy - d)))), None)
    down = next((d for d in range(1, height - cy) if _is_accent(QColor(image.pixel(center, cy + d)))), None)
    return None if up is None or down is None else (up, down)


@pytest.mark.parametrize("value", [1, 30, 60, 90, 120])
def test_슬라이더_손잡이는_어느_위치에서도_위아래_테두리가_다_보인다(qapp, value):
    control = LabeledSlider(1, 120, " 분", 5)
    control.setValue(value)
    white_card(control)
    distances = handle_ring_distances(control.slider)
    assert distances is not None, "손잡이의 위나 아래가 잘렸다"
    up, down = distances
    assert abs(up - down) <= 1 and up >= 6  # 위아래가 대칭이고 충분한 크기의 동그라미


def test_잘린_손잡이는_이_검사에_걸린다(qapp):
    """검사 자체가 동작하는지 확인한다: 슬라이더를 손잡이보다 낮게 만들면 None이어야 한다."""
    control = LabeledSlider(1, 120, " 분", 5)
    control.slider.setMinimumHeight(0)  # 최소 높이를 없애면 기본 높이(15px 안팎)로 줄어 손잡이가 잘린다
    control.setValue(60)
    white_card(control)
    assert handle_ring_distances(control.slider) is None


def test_설정_화면의_슬라이더_손잡이도_잘리지_않는다(qapp):
    page = SettingsPage(SettingsManager(Settings()))
    page.resize(900, 1100)
    page.show()
    qapp.processEvents()
    for path in ("interval_minutes", "snooze_minutes", "idle_pause_minutes", "idle_reset_minutes", "exercises.blink.duration_seconds", "exercises.dot_follow.duration_seconds"):
        assert handle_ring_distances(page.control(path).slider) is not None, path
