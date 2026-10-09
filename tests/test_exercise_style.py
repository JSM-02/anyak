from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from test_exercise_window import make_window

from eyeexercise.core.exercises import blink_timeline, dot_follow_timeline
from eyeexercise.ui import theme
from eyeexercise.ui.exercise_window import DotCanvas, EyeWidget
from eyeexercise.ui.reminder_popup import ReminderPopup


def pixel(widget, x, y) -> QColor:
    return QColor(widget.grab().toImage().pixel(x, y))


# ---- 운동 창: 모든 구간이 같은 바탕(paper)과 아래쪽 물 ----


def test_운동_창은_처음부터_끝까지_같은_바탕이다(qapp):
    for timeline in (blink_timeline(30), dot_follow_timeline(60)):
        window, _ = make_window(qapp)
        window.start(timeline)
        seconds = (0, 5, timeline.total_seconds - 1, timeline.total_seconds + 1)  # 준비·진행·마무리·먼 곳 바라보기
        backgrounds = set()
        for second in seconds:
            window._elapsed.ms = second * 1000
            window._on_frame()
            backgrounds.add(pixel(window, 6, window.height() // 2).name())  # 왼쪽 가장자리(글자가 없는 곳), 물보다 위
        assert backgrounds == {theme.color("paper").name()}, timeline.exercise  # 구간이 바뀌어도 바탕이 달라지지 않는다
        window.close()


def test_운동_창_모서리는_둥글게_투명하다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    assert window.grab().toImage().pixelColor(0, 0).alpha() == 0
    window.close()


def test_운동_창_이름표는_깊은_초록_알약이고_버튼도_같은_초록이다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    box = window._tag.geometry()
    assert pixel(window, box.left() + 2, box.center().y()).name() == theme.color("hero").name()
    button = window._button.geometry()
    assert pixel(window, button.left() + 6, button.center().y()).name() == theme.color("hero").name()
    window.close()


def test_진행에_따라_아래쪽_물이_차오른다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))  # 총 30초
    tops = []
    for ms in (0, 15000, 29000):
        window._elapsed.ms = ms
        window._on_frame()
        tops.append(window.water_paths()[1].boundingRect().top())
    assert tops[0] > tops[1] > tops[2]  # 수면이 점점 올라간다
    window._elapsed.ms = 0
    window._on_frame()
    assert pixel(window, 40, window.height() - 3).name() == theme.color("hero").name()  # 시작할 때도 바닥에 얇게 깔려 있다
    window.close()


def test_먼_곳_바라보기_동안에는_물이_줄어든다(qapp):
    window, _ = make_window(qapp)
    timeline = blink_timeline(30)
    window.start(timeline)
    window._elapsed.ms = timeline.total_seconds * 1000 + 100
    window._on_frame()
    start = window.water_paths()[1].boundingRect().top()
    window._elapsed.ms = (timeline.total_seconds + 15) * 1000
    window._on_frame()
    assert window.water_paths()[1].boundingRect().top() > start  # 낮아진다(화면 좌표에서 아래로)
    window.close()


def test_물_높이는_아래쪽_안내_자리를_넘지_않는다(qapp):
    from eyeexercise.ui.exercise_window import BAND_MAX

    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 29900
    window._on_frame()
    top = window.water_paths()[1].boundingRect().top()
    hint = window._hint.geometry()
    assert top >= hint.bottom() - 4 or top >= window.height() - BAND_MAX - 30  # 힌트·버튼 글자가 물에 잠기지 않는다
    window.close()


def test_다크_모드에서는_운동_창도_어두운_바탕이다(qapp):
    window, _ = make_window(qapp)
    theme.set_dark(True)
    try:
        window.start(blink_timeline(30))
        assert pixel(window, 6, window.height() // 2).name() == theme.DARK.paper
        assert theme.DARK.hero in window.styleSheet()  # 이름표·버튼의 초록
    finally:
        theme.set_dark(False)
        window.close()


def test_움직임을_줄이면_운동_창의_파도와_점의_물결이_멈춘다(qapp):
    from eyeexercise.ui.exercise_window import ExerciseWindow

    window = ExerciseWindow(None, animations=lambda: False)
    from test_exercise_window import FakeElapsed

    window._elapsed = FakeElapsed()
    window.start(dot_follow_timeline(60))
    for ms in (4000, 5000, 6000):
        window._elapsed.ms = ms
        window._on_frame()
    assert window._wave_t == 0.0 and not window._dots.animated
    window.close()


def test_눈_윤곽과_홍채는_포인트_초록이고_눈_안쪽은_카드_바탕색이다(qapp):
    eye = EyeWidget()
    eye.resize(300, 160)
    image = eye.grab().toImage()
    colors = {QColor(image.pixel(x, y)).name() for x in range(0, 300, 2) for y in range(0, 160, 2)}
    assert theme.color("accent").name() in colors  # 윤곽선·홍채
    assert theme.color("surface").name() in colors  # 눈 안쪽


def test_점_화면은_상자_없이_물방울_점이다(qapp):
    canvas = DotCanvas()
    canvas.resize(300, 200)
    canvas.set_dot((0.5, 0.5))
    pos = canvas.dot_position()
    assert pixel(canvas, 6, 100).name() != theme.color("hover").name()  # 예전처럼 영역을 회녹색 상자로 두르지 않는다
    assert pixel(canvas, int(pos.x()) + 10, int(pos.y())).name() == canvas.dot_color().name()  # 물방울(가운데는 모래색)
    assert pixel(canvas, int(pos.x()), int(pos.y())).name() == theme.color("sand").name()


def test_점의_색은_밝은_바탕에서는_깊은_초록_어두운_바탕에서는_밝은_초록이다(qapp):
    canvas = DotCanvas()
    assert canvas.dot_color().name() == theme.color("hero").name()
    theme.set_dark(True)
    try:
        assert canvas.dot_color().name() == theme.color("accent").name()
    finally:
        theme.set_dark(False)


def test_점은_지나온_자리에_꼬리를_남기지_않는다(qapp):
    canvas = DotCanvas()
    canvas.resize(400, 200)
    canvas.set_dot((0.2, 0.5), 0.0)
    old = canvas.dot_position()
    for i in range(1, 8):  # 오른쪽으로 옮긴다
        canvas.set_dot((0.2 + i * 0.08, 0.5), i * 0.05)
    # 옛 자리는 배경 그대로다(점 반지름 14 + 물결 최대 56보다 멀리 옮겼다)
    assert pixel(canvas, int(old.x()), int(old.y())).name() == pixel(canvas, 6, 6).name()


def test_점_둘레에는_물결이_퍼지고_끄면_점만_그려진다(qapp):
    canvas = DotCanvas()
    canvas.resize(300, 200)
    canvas.set_dot((0.5, 0.5), 0.4375)  # 첫 물결이 반지름 약 30까지 퍼진 때
    pos = canvas.dot_position()
    background = pixel(canvas, 6, 6).name()
    ring = pixel(canvas, int(pos.x()) + 30, int(pos.y()))
    assert ring.name() != background  # 물결이 있다
    canvas.set_animate(False)
    assert pixel(canvas, int(pos.x()) + 30, int(pos.y())).name() == background
    assert pixel(canvas, int(pos.x()) + 10, int(pos.y())).name() == canvas.dot_color().name()  # 점은 그대로


def test_점이_움직이면_점_둘레만_다시_그린다(qapp, monkeypatch):
    canvas = DotCanvas()
    canvas.resize(900, 600)
    canvas.set_dot((0.2, 0.5), 0.0)
    regions = []
    monkeypatch.setattr(canvas, "update", lambda *args: regions.append(args))
    canvas.set_dot((0.21, 0.5), 0.016)
    (region,) = regions[0]
    assert region.width() < 200 and region.height() < 200  # 900×600 전체가 아니라 점 둘레(옛 자리와 새 자리를 합친 곳)다


def test_경로_그림_여섯_개가_있고_지금_경로가_정해진다(qapp):
    from eyeexercise.core.exercises import DOT_PATTERNS
    from eyeexercise.ui.exercise_window import PatternRow

    row = PatternRow()
    row.resize(400, 40)
    assert row.current is None
    row.set_current(2)
    assert row.current == 2
    from PySide6.QtCore import QRectF

    rect = QRectF(0, 0, 28, 20)
    for i in range(len(DOT_PATTERNS)):
        box = row.icon_path(i, rect).boundingRect()
        assert box.left() >= -0.01 and box.right() <= 28.01 and box.top() >= -0.01 and box.bottom() <= 20.01  # 그림이 칸 안에 들어온다
    assert not row.grab().isNull()


def test_점_따라가기_창은_지금_경로를_알려_주고_다른_구간에서는_숨긴다(qapp):
    window, _ = make_window(qapp)
    window.start(dot_follow_timeline(60))
    assert window._patterns.isVisible() and window._patterns.current is None  # 준비
    window._elapsed.ms = (3 + 2 * 9 + 4) * 1000  # 세 번째 패턴
    window._on_frame()
    assert window._patterns.current == 2
    window._elapsed.ms = 60 * 1000 + 500  # 먼 곳 바라보기
    window._on_frame()
    assert not window._patterns.isVisible()
    window.close()
    blink, _ = make_window(qapp)
    blink.start(blink_timeline(30))
    assert not blink._patterns.isVisible()
    blink.close()


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


# ---- 프레임 속도: 모니터 주사율에 맞춘다 ----


def test_프레임_간격은_모니터_주사율에_맞춘다():
    from eyeexercise.ui.exercise_window import frame_interval_ms

    assert frame_interval_ms(60.0) == 16 and frame_interval_ms(59.94) == 16
    assert frame_interval_ms(120.0) == 8 and frame_interval_ms(144.0) == 7 and frame_interval_ms(165.0) == 6
    assert frame_interval_ms(240.0) == 4
    assert frame_interval_ms(1000.0) == 4  # 너무 잘게 나누지 않는다
    assert frame_interval_ms(None) == 16 and frame_interval_ms(0) == 16 and frame_interval_ms(30.0) == 16  # 모르거나 느리면 60fps 기준


def test_운동_창은_시작할_때_주사율에_맞는_간격으로_그린다(qapp, monkeypatch):
    from eyeexercise.ui.exercise_window import ExerciseWindow

    monkeypatch.setattr(ExerciseWindow, "_refresh_hz", lambda self: 144.0)
    window, _ = make_window(qapp)
    window.start(dot_follow_timeline(60))
    assert window._timer.interval() == 7 and window._timer.timerType() == Qt.TimerType.PreciseTimer
    window.close()


def test_프레임마다_아래쪽_물_영역만_다시_그린다(qapp, monkeypatch):
    window, _ = make_window(qapp)
    window.start(dot_follow_timeline(60))
    regions = []
    monkeypatch.setattr(window, "update", lambda *args: regions.append(args))
    window._elapsed.ms = 10000
    window._on_frame()
    x, y, w, h = regions[-1]
    assert (x, w) == (0, window.width()) and y > window.height() * 0.8 and h < window.height() * 0.2  # 창 전체가 아니다
    window.close()
