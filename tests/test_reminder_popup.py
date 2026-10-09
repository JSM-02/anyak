import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QPushButton

from eyeexercise.ui import theme
from eyeexercise.ui.reminder_popup import _TOP_MARGIN, SURFACE_Y, ReminderPopup


@pytest.fixture(autouse=True)
def clean_theme():
    theme._reset_for_tests()
    yield
    theme._reset_for_tests()


def popup(animations=False, clock=None):
    return ReminderPopup(5, animations=lambda: animations, motion_clock=clock or (lambda: 0.0))


def pixel(widget, x, y) -> QColor:
    return QColor(widget.grab().toImage().pixel(x, y))


def shown(qapp, **kwargs):
    p = popup(**kwargs)
    p.show()
    qapp.processEvents()
    return p


# ---- 물 ----


def test_팝업은_거의_가득_찬_물이고_위쪽_얇은_띠에만_수면이_보인다(qapp):
    p = shown(qapp)
    front, _back, _line = p.water_paths()
    assert front.boundingRect().top() > -1 and front.boundingRect().top() < SURFACE_Y  # 수면이 위쪽 띠 안에 있고 맨 위까지 덮지는 않는다
    assert _line.boundingRect().bottom() < _TOP_MARGIN  # 수면의 가장 낮은 곳도 글자 시작 위치(위 여백)보다 위라 글자가 수면에 걸치지 않는다
    assert front.contains(QPointF(p.width() / 2, p.height() / 2))
    assert not front.contains(QPointF(p.width() / 2, 1))
    assert 0.8 <= p.water_level() < 1.0
    assert abs(_line.pointAtPercent(0.0).y() - SURFACE_Y) < 12  # 수면은 위에서 일정한 깊이에 있다
    p.hide()


def test_팝업_몸통은_물_색이다(qapp):
    p = shown(qapp)
    assert pixel(p, 8, p.height() // 2).name() == theme.color("hero").name()
    p.hide()


def test_다크_모드에서도_물_색이다(qapp):
    theme.set_dark(True)
    p = shown(qapp)
    assert pixel(p, 8, p.height() // 2).name() == theme.DARK.hero
    p.hide()


def test_팝업_모서리는_둥글게_투명하다(qapp):
    p = shown(qapp)
    assert p.grab().toImage().pixelColor(0, 0).alpha() == 0
    p.hide()


def test_글자는_물_속에서_읽히도록_모래색이다(qapp):
    p = popup()
    sheet = p.styleSheet()
    assert "#title" in sheet and theme.LIGHT.sand in sheet
    assert contrast_ok()


def contrast_ok() -> bool:
    from test_theme import contrast

    return contrast(theme.LIGHT.sand, theme.LIGHT.hero) >= 6 and contrast(theme.DARK.sand, theme.DARK.hero) >= 4.5


def test_단추_이름은_그대로다(qapp):
    p = popup()
    assert [b.text() for b in p.findChildren(QPushButton)][:3] == ["시작", "5분 미루기", "건너뛰기"]
    assert any(label.text() == "눈 쉬는 시간이에요" for label in p.findChildren(QLabel))


# ---- 움직임 ----


def test_애니메이션을_켜면_보이는_동안에만_물결이_움직인다(qapp):
    moving = popup(animations=True)
    moving.show()
    assert moving._frame.isActive()
    moving.hide()
    assert not moving._frame.isActive()
    moving.deleteLater()


def test_애니메이션을_끄면_물결이_멈춰_있다(qapp):
    now = {"t": 10.0}
    still = popup(animations=False, clock=lambda: now["t"])
    still.show()
    assert not still._frame.isActive()
    now["t"] = 15.0
    still._on_frame()
    assert still._wave_t == 0.0
    still.hide()
    still.deleteLater()


def test_파도_시간은_움직임_시계를_따라간다(qapp):
    now = {"t": 100.0}
    moving = popup(animations=True, clock=lambda: now["t"])
    now["t"] = 103.5
    moving._on_frame()
    assert moving._wave_t == 3.5
    moving.deleteLater()


def test_보인_뒤에는_물결_모양이_바뀐다(qapp):
    now = {"t": 0.0}
    moving = popup(animations=True, clock=lambda: now["t"])
    moving.resize(380, 250)
    first = moving.water_paths()[2].boundingRect().top()
    now["t"] = 4.0
    moving._on_frame()
    assert moving.water_paths()[2].boundingRect().top() != first
    moving.deleteLater()


# ---- 크기 ----


def test_팝업은_작게_뜬다(qapp):
    p = shown(qapp)
    p.set_exercise_offer(0, 2)
    p.adjustSize()
    assert p.width() == 340 and p.height() <= 230  # 화면 구석에 조용히 뜨는 크기를 넘지 않는다
    p.hide()


def test_팝업_높이가_달라져도_위쪽_띠의_두께는_같다(qapp):
    p = popup()
    tops = []
    for height in (150, 200, 260):
        p.resize(340, height)
        tops.append(round(p.water_paths()[2].boundingRect().top(), 1))
    assert max(tops) - min(tops) < 0.5
    p.deleteLater()
