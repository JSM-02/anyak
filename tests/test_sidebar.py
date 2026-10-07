from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from eyeexercise.core.history import History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.ui import theme
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.sidebar import Sidebar


def make_sidebar():
    return Sidebar(("기록", "시력 기록", "설정"), ("chart", "eye", "gear"))


def test_처음에는_첫_메뉴가_선택돼_있다(qapp):
    side = make_sidebar()
    assert side.count() == 3 and side.current() == 0
    assert [side.label(i) for i in range(3)] == ["기록", "시력 기록", "설정"]
    assert side._buttons[0].isChecked() and not side._buttons[1].isChecked()


def test_메뉴를_누르면_선택이_바뀌고_알린다(qapp):
    side = make_sidebar()
    heard = []
    side.current_changed.connect(heard.append)
    side._buttons[2].click()
    assert side.current() == 2 and heard == [2] and side._buttons[2].isChecked() and not side._buttons[0].isChecked()
    side.set_current(2)  # 이미 고른 것을 또 골라도 알리지 않는다
    assert heard == [2]
    side.set_current(9)  # 없는 번호는 무시한다
    assert side.current() == 2


def test_선택한_메뉴는_포인트_색_블록으로_그려진다(qapp):
    side = make_sidebar()
    side.resize(212, 500)
    side.show()
    qapp.processEvents()
    image = side.grab().toImage()
    selected, other = side._buttons[0], side._buttons[1]
    on = QColor(image.pixel(selected.x() + 4, selected.y() + selected.height() // 2))
    off = QColor(image.pixel(other.x() + 4, other.y() + other.height() // 2))
    assert on.name() == theme.palette().accent.lower()  # 선택: 초록 블록
    assert off.name() == theme.palette().sidebar.lower()  # 나머지: 사이드바 바탕


def test_타이머_알약은_문구와_상태를_바꾼다(qapp):
    side = make_sidebar()
    side.set_timer("12:34 뒤 휴식", "normal")
    assert side.timer_pill.text == "12:34 뒤 휴식" and side.timer_pill.tone == "normal"
    assert side.timer_pill.toolTip() == "12:34 뒤 휴식"
    side.set_timer("일시정지 · 12:34", "paused")
    assert side.timer_pill.tone == "paused"


def test_알약은_상태마다_다른_색_점을_그린다(qapp):
    side = make_sidebar()
    side.resize(212, 500)
    side.show()
    colors = {}
    for tone in ("normal", "alert", "paused", "active"):
        side.set_timer("문구", tone)
        qapp.processEvents()
        image = side.timer_pill.grab().toImage()
        colors[tone] = image.pixelColor(20, side.timer_pill.height() // 2).name()
    assert len(set(colors.values())) == 4


def test_다크_모드로_바뀌어도_사이드바가_다시_그려진다(qapp):
    theme._reset_for_tests()
    side = make_sidebar()
    side.resize(212, 400)
    side.show()
    qapp.processEvents()
    before = side.grab().toImage().pixel(2, 2)
    theme.set_dark(True)
    qapp.processEvents()
    after = side.grab().toImage().pixel(2, 2)
    theme._reset_for_tests()
    assert before != after


def test_메인_창의_알약은_컨트롤러의_남은_시간을_따라간다(qapp):
    clock = FakeClock()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now)
    window = MainWindow()
    window.attach_controller(controller)
    assert window.sidebar.timer_pill.text == "20:00 뒤 휴식"
    for _ in range(90):
        clock.advance(1)
        controller._on_tick()
    assert window.sidebar.timer_pill.text == "18:30 뒤 휴식"
    controller.pause()
    assert window.sidebar.timer_pill.text == "일시정지 · 18:30" and window.sidebar.timer_pill.tone == "paused"
    controller.resume()
    controller.start_rest()
    assert window.sidebar.timer_pill.text == "눈 휴식 중" and window.sidebar.timer_pill.tone == "active"
    controller.abort_exercise()
    assert window.sidebar.timer_pill.text == "20:00 뒤 휴식"  # 마치면 타이머를 처음부터 다시 센다


def test_컨트롤러가_없으면_알약은_비어_있어도_창이_뜬다(qapp):
    window = MainWindow()
    assert window.sidebar.timer_pill.text == ""
    window.show()
    qapp.processEvents()
    assert window.isVisible()


def test_메뉴를_누르면_본문이_바뀐다(qapp):
    window = MainWindow()
    window.sidebar._buttons[1].click()
    assert window._stack.currentWidget() is window.vision_page
    QTest.mouseClick(window.sidebar._buttons[2], Qt.MouseButton.LeftButton)
    assert window._stack.currentWidget() is window.settings_page
