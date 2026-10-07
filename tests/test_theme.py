import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from eyeexercise.core.history import History
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.ui import theme
from eyeexercise.ui.exercise_window import ExerciseWindow
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.reminder_popup import ReminderPopup


@pytest.fixture(autouse=True)
def clean_theme():
    theme._reset_for_tests()
    yield
    theme._reset_for_tests()  # 다른 테스트에 다크가 남지 않게


def luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def contrast(a: str, b: str) -> float:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def rel(h):
        c = QColor(h)
        return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())

    hi, lo = sorted((rel(a), rel(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_모든_스타일시트_틀이_두_테마_모두에서_빈칸_없이_채워진다(qapp):
    from eyeexercise.ui import exercise_window, main_window, records_tab, reminder_popup, settings_page, vision_page

    for module in (exercise_window, main_window, records_tab, reminder_popup, settings_page, vision_page):
        for dark in (False, True):
            theme.set_dark(dark)
            assert "$" not in theme.render(module._STYLE), module.__name__


def test_글자와_바탕의_대비가_두_테마_모두_충분하다():
    for p in (theme.LIGHT, theme.DARK):
        for bg in (p.bg, p.surface):
            assert contrast(p.text, bg) >= 7
            assert contrast(p.text_body, bg) >= 5
            assert contrast(p.text_secondary, bg) >= 4.5
            assert contrast(p.danger, bg) >= 4.5
            assert contrast(p.warning, bg) >= 4.5
            assert contrast(p.accent, bg) >= 3  # 큰 글자·컨트롤 기준
        assert contrast(p.on_accent, p.accent) >= 3


def test_다크_팔레트는_라이트보다_어둡다():
    assert luminance(theme.DARK.bg) < 80 < luminance(theme.LIGHT.bg)
    assert luminance(theme.DARK.text) > 180 > luminance(theme.LIGHT.text)


def test_테마를_바꾸면_이미_만든_화면의_스타일시트가_바뀐다(qapp):
    window = MainWindow(History(), settings_manager=SettingsManager(Settings()))
    popup = ReminderPopup(5)
    exercise = ExerciseWindow(None)
    before = [w.styleSheet() for w in (window.vision_page, window.settings_page, window.records_tab, popup, exercise)]
    theme.set_dark(True)
    after = [w.styleSheet() for w in (window.vision_page, window.settings_page, window.records_tab, popup, exercise)]
    assert all(b != a for b, a in zip(before, after, strict=True))
    assert theme.DARK.surface in popup.styleSheet()
    theme.set_dark(False)
    assert popup.styleSheet() == before[3]


def test_다크에서_화면이_실제로_어둡게_칠해진다(qapp):
    window = MainWindow(History(), settings_manager=SettingsManager(Settings()))
    theme.set_dark(True)
    window.resize(1000, 700)
    for row in range(window._nav.count()):
        window._nav.setCurrentRow(row)
        image = window.grab().toImage()
        # 본문 한가운데와 왼쪽 메뉴 아래쪽 바탕이 어두워야 한다
        assert QColor(image.pixel(900, 20)).lightness() < 100, row
        assert QColor(image.pixel(20, 650)).lightness() < 100, row


def test_기록_탭의_큰_숫자_색이_테마를_따라간다(qapp):
    from eyeexercise.ui.records_tab import RecordsTab

    tab = RecordsTab(lambda: (), now=lambda: __import__("datetime").datetime(2026, 10, 7, 12))
    tab._set_number(3)
    assert theme.LIGHT.text in tab._number.text()
    theme.set_dark(True)
    tab._set_number(3)
    assert theme.DARK.text in tab._number.text()


def test_테마를_바꿔도_사라진_위젯은_문제가_되지_않는다(qapp):
    label = QLabel()
    theme.bind(label, "QLabel { color: $text; }")
    label.deleteLater()
    qapp.processEvents()
    theme.set_dark(True)  # 예외 없이 지나간다


def test_글꼴은_영문과_한글_순서로_지정한다(qapp):
    from PySide6.QtGui import QFont

    before = QFont(qapp.font())
    try:
        theme.apply_app_font(qapp)
        assert list(qapp.font().families())[:2] == ["Segoe UI", "Malgun Gothic"]
    finally:
        qapp.setFont(before)


def test_화면_모드를_고정하면_시스템_설정과_상관없이_따른다(qapp):
    theme.set_mode("dark")
    assert theme.is_dark()
    theme.set_mode("light")
    assert not theme.is_dark()
    theme.set_mode("system")  # 시스템이 라이트이므로 라이트 (오프스크린 테스트 환경)
    assert not theme.is_dark()
    theme.set_mode("엉뚱한 값")  # 모르는 값은 시스템 설정으로 본다
    assert theme._mode == "system"


def test_포인트_색은_초록이다():
    for p in (theme.LIGHT, theme.DARK):
        c = QColor(p.accent)
        assert c.green() > c.red() + 40 and c.green() > c.blue() + 20, p.accent
