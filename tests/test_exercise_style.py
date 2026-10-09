from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from test_exercise_window import make_window

from eyeexercise.core.exercises import blink_timeline, dot_follow_timeline
from eyeexercise.ui import theme
from eyeexercise.ui.exercise_window import DotCanvas, EyeWidget
from eyeexercise.ui.reminder_popup import ReminderPopup


def pixel(widget, x, y) -> QColor:
    return QColor(widget.grab().toImage().pixel(x, y))


# ---- 운동 창: 모든 구간이 같은 연한 민트 바탕 ----


def test_운동_창은_처음부터_끝까지_같은_연한_민트_바탕이다(qapp):
    for timeline in (blink_timeline(30), dot_follow_timeline(60)):
        window, _ = make_window(qapp)
        window.start(timeline)
        seconds = (0, 5, timeline.total_seconds - 1, timeline.total_seconds + 1)  # 준비·진행·마무리·먼 곳 바라보기
        backgrounds = set()
        for second in seconds:
            window._elapsed.ms = second * 1000
            window._on_frame()
            backgrounds.add(pixel(window, 40, window.height() - 8).name())
        assert backgrounds == {theme.color("bg").name()}, timeline.exercise  # 구간이 바뀌어도 바탕이 달라지지 않는다
        window.close()


def test_운동_창_이름표는_연한_초록_알약이고_진행_바는_포인트_초록이다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    box = window._tag.geometry()
    assert pixel(window, box.left() + 2, box.center().y()).name() == theme.color("accent_soft").name()
    bar = window._progress.geometry()
    window._elapsed.ms = 15000
    window._on_frame()
    assert pixel(window, bar.left() + 8, bar.center().y()).name() == theme.color("accent").name()
    window.close()


def test_다크_모드에서는_운동_창도_어두운_바탕이다(qapp):
    window, _ = make_window(qapp)
    theme.set_dark(True)
    try:
        window.start(blink_timeline(30))
        assert pixel(window, 40, window.height() - 8).name() == theme.DARK.bg
        assert window.styleSheet().count(theme.DARK.bg) >= 1
    finally:
        theme.set_dark(False)
        window.close()


def test_눈_윤곽과_홍채는_포인트_초록이고_눈_안쪽은_카드_바탕색이다(qapp):
    eye = EyeWidget()
    eye.resize(300, 160)
    image = eye.grab().toImage()
    colors = {QColor(image.pixel(x, y)).name() for x in range(0, 300, 2) for y in range(0, 160, 2)}
    assert theme.color("accent").name() in colors  # 윤곽선·홍채
    assert theme.color("surface").name() in colors  # 눈 안쪽


def test_점_화면은_연한_영역에_초록_점이다(qapp):
    canvas = DotCanvas()
    canvas.resize(300, 200)
    canvas.set_dot((0.5, 0.5))
    pos = canvas.dot_position()
    assert pixel(canvas, 6, 100).name() == theme.color("hover").name()
    assert pixel(canvas, int(pos.x()) + 7, int(pos.y())).name() == theme.color("accent").name()  # 점의 가장자리 (가운데 점은 밝은 색)


# ---- 알림 팝업: 짙은 초록 물 ----


def test_알림_팝업은_짙은_초록_물이고_시작_버튼이_모래색이다(qapp):
    popup = ReminderPopup(5, animations=lambda: False)
    popup.show()
    qapp.processEvents()
    assert pixel(popup, 6, popup.height() // 2).name() == theme.color("hero").name()
    start = popup.findChild(type(popup._snooze_button), "primary")
    inside = start.mapTo(popup, QPoint(8, start.height() // 2))  # 글자를 피해 버튼 왼쪽 안쪽(버튼 좌표를 팝업 좌표로)
    assert pixel(popup, inside.x(), inside.y()).name() == theme.color("sand").name()
    popup.hide()


# ---- 알림음 ----


class FakeAlert:
    def __init__(self) -> None:
        self.played = 0

    def play(self) -> None:
        self.played += 1


def test_팝업이_뜰_때_알림음이_한_번_울린다(qapp):
    popup = ReminderPopup(5)
    alert = FakeAlert()
    popup.set_alert(alert)
    popup.show_at_corner()
    assert alert.played == 1
    popup.hide()
    popup.show_at_corner()
    assert alert.played == 2  # 팝업이 다시 뜰 때마다 한 번씩
    popup.hide()


def test_알림음을_끄면_조용히_뜬다(qapp):
    popup = ReminderPopup(5)
    alert = FakeAlert()
    popup.set_alert(alert)
    popup.set_alert(None)
    popup.show_at_corner()
    assert alert.played == 0 and popup.isVisible()
    popup.hide()
