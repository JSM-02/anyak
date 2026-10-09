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


def test_모서리는_둥글고_테두리_선도_그림자도_없다(qapp):
    p = shown(qapp)
    image = p.grab().toImage()
    assert image.pixelColor(0, 0).alpha() == 0  # 둥근 모서리 바깥은 투명하다
    assert image.pixelColor(p.width() // 2, p.height() - 1).name() == theme.color("hero").name()  # 가장자리에 다른 색의 테두리 선이 없다
    assert image.pixelColor(p.width() // 2, p.height() - 1).alpha() == 255
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


# ---- 팝업 안의 20초 카운트다운 (먼 곳 바라보기) ----


class FakeElapsed:
    def __init__(self) -> None:
        self.ms = 0

    def start(self) -> None:
        self.ms = 0

    def elapsed(self) -> int:
        return self.ms


class FakeSpeaker:
    def __init__(self) -> None:
        self.phases = []
        self.stopped = 0

    def cue(self, phase) -> None:
        self.phases.append(phase)

    def stop(self) -> None:
        self.stopped += 1


def counting(qapp, animations=False, speaker=None):
    from eyeexercise.core.exercises import LookAwayTimeline

    p = popup(animations=animations)
    p._elapsed = FakeElapsed()
    if speaker is not None:
        p.set_speaker(speaker)
    events = []
    p.completed.connect(lambda name, sec: events.append(("completed", name, sec)))
    p.aborted.connect(lambda: events.append(("aborted",)))
    p.start_countdown(LookAwayTimeline())
    qapp.processEvents()
    return p, events


def test_카운트다운을_시작하면_팝업_안에서_20초를_센다(qapp):
    p, _ = counting(qapp)
    assert p.isVisible() and p.counting
    assert p.countdown_text == "20"
    assert p._abort_button.isVisible()
    assert all(not b.isVisible() for b in (p._snooze_button, p._exercise_button))  # 알림 단추는 숨는다
    p.hide()


def test_시간이_흐르면_숫자가_줄고_물이_빠진다(qapp):
    p, _ = counting(qapp)
    top0 = p.water_paths()[2].boundingRect().top()
    p._elapsed.ms = 5200
    p._on_frame()
    assert p.countdown_text == "15"
    top1 = p.water_paths()[2].boundingRect().top()
    p._elapsed.ms = 15000
    p._on_frame()
    top2 = p.water_paths()[2].boundingRect().top()
    assert top0 < top1 < top2  # 수면이 점점 내려간다
    p.hide()


def test_20초가_지나면_휴식을_한_번만_완료로_알리고_닫힌다(qapp):
    p, events = counting(qapp)
    p._elapsed.ms = 20000
    p._on_frame()
    p._on_frame()
    assert events == [("completed", "blink", 20)]  # 휴식은 '깜빡임' 이름으로 센다(기록 구조 그대로)
    assert not p.counting and not p.isVisible()


def test_20초가_되기_전에는_완료로_알리지_않는다(qapp):
    p, events = counting(qapp)
    p._elapsed.ms = 19900
    p._on_frame()
    assert events == [] and p.counting
    p.hide()


def test_중단_버튼은_완료_없이_중단만_알린다(qapp):
    p, events = counting(qapp)
    p._elapsed.ms = 8000
    p._abort_button.click()
    assert events == [("aborted",)] and not p.counting and not p.isVisible()


def test_카운트다운_중에_팝업이_숨겨지면_중단으로_알린다(qapp):
    p, events = counting(qapp)
    p.hide()
    assert events == [("aborted",)] and not p.counting


def test_완료_뒤_숨겨져도_중단으로_알리지_않는다(qapp):
    p, events = counting(qapp)
    p._elapsed.ms = 20000
    p._on_frame()
    p.hide()
    assert events == [("completed", "blink", 20)]


def test_시작과_끝에서_소리_안내를_낸다(qapp):
    from eyeexercise.core.exercises import Phase

    speaker = FakeSpeaker()
    p, _ = counting(qapp, speaker=speaker)
    assert speaker.phases == [Phase.LOOK_AWAY]  # 시작할 때 '먼 곳을 바라보세요'
    p._elapsed.ms = 20000
    p._on_frame()
    assert speaker.phases == [Phase.LOOK_AWAY, Phase.FINISH]  # 끝나면 눈을 돌려도 되도록 알려 준다


def test_중단하면_소리를_멈춘다(qapp):
    speaker = FakeSpeaker()
    p, _ = counting(qapp, speaker=speaker)
    p._abort_button.click()
    assert speaker.stopped >= 1


def test_카운트다운_중에는_애니메이션을_꺼도_숫자와_물이_갱신된다(qapp):
    p, _ = counting(qapp, animations=False)
    assert p._frame.isActive()
    p._elapsed.ms = 10000
    p._on_frame()
    assert p.countdown_text == "10" and p._wave_t == 0.0
    p.hide()
    assert not p._frame.isActive()


def test_카운트다운이_끝난_뒤_알림이_다시_뜨면_알림_모양으로_돌아온다(qapp):
    p, _ = counting(qapp)
    p._abort_button.click()
    p.show_at_corner()
    assert not p.counting and p._snooze_button.isVisible() and not p._abort_button.isVisible()
    p.hide()


def test_알림에서_바로_카운트다운으로_바뀌어도_팝업은_숨지_않는다(qapp):
    from PySide6.QtCore import QEvent, QObject

    from eyeexercise.core.exercises import LookAwayTimeline

    class Watcher(QObject):
        def __init__(self):
            super().__init__()
            self.hidden = 0

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Hide:
                self.hidden += 1
            return False

    p = popup()
    p._elapsed = FakeElapsed()
    watcher = Watcher()
    p.installEventFilter(watcher)
    p.show_at_corner()
    p.start_countdown(LookAwayTimeline())
    qapp.processEvents()
    assert watcher.hidden == 0 and p.isVisible() and p.counting  # 깜빡이지 않는다
    p.hide()


def test_운동_제안이_있던_팝업도_카운트다운에서_아래쪽_자리를_지킨다(qapp):
    from eyeexercise.core.exercises import LookAwayTimeline

    p = popup()
    p._elapsed = FakeElapsed()
    p.set_exercise_offer(0, 2)
    p.show_at_corner()
    bottom = p.geometry().bottom()
    p.start_countdown(LookAwayTimeline())
    qapp.processEvents()
    assert abs(p.geometry().bottom() - bottom) <= 1  # 줄어들어도 화면 구석의 아래 위치는 그대로
    p.hide()


def test_카운트다운_글자는_물_밖에서는_짙은색_물_안에서는_모래색으로_두_번_그린다(qapp, monkeypatch):
    calls = []
    original = ReminderPopup._paint_count_content

    def spy(self, painter, color):
        calls.append((color.name(), painter.hasClipping()))
        original(self, painter, color)

    monkeypatch.setattr(ReminderPopup, "_paint_count_content", spy)
    p, _ = counting(qapp)
    p._elapsed.ms = 9000
    p._on_frame()
    calls.clear()  # 앞서 화면에 뜰 때 그려진 것은 뺀다
    p.grab()
    assert calls == [(theme.color("text").name(), True), (theme.color("sand").name(), True)]  # 둥근 모서리로 이미 잘라 둔 상태
    p.hide()


def test_카운트다운_바탕은_물이_빠질수록_드러난다(qapp):
    p, _ = counting(qapp)
    assert pixel(p, 8, p.height() // 2).name() == theme.color("hero").name()  # 시작: 물 속
    p._elapsed.ms = 17000
    p._on_frame()
    assert pixel(p, 8, p.height() // 2).name() == theme.color("paper").name()  # 거의 끝: 물이 빠졌다
    p.hide()
