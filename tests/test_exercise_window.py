import pytest
from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest

from eyeexercise.core.exercises import Phase, dot_follow_timeline
from eyeexercise.core.history import History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.exercise_window import ExerciseWindow, window_size


class FakeElapsed:
    """QElapsedTimer 대신 쓰는 가짜. 밀리초를 직접 정한다."""

    def __init__(self) -> None:
        self.ms = 0

    def start(self) -> None:
        self.ms = 0

    def elapsed(self) -> int:
        return self.ms


class FakeSpeaker:
    def __init__(self) -> None:
        self.phases: list[Phase] = []
        self.stopped = 0

    def cue(self, phase: Phase) -> None:
        self.phases.append(phase)

    def stop(self) -> None:
        self.stopped += 1


def make_window(qapp, speaker=None):
    window = ExerciseWindow(speaker)
    window._elapsed = FakeElapsed()
    events = []
    window.completed.connect(lambda name, sec: events.append(("completed", name, sec)))
    window.aborted.connect(lambda: events.append(("aborted",)))
    return window, events


def test_시작하면_창이_뜨고_첫_안내가_보인다(qapp):
    window, _ = make_window(qapp)
    window.start(dot_follow_timeline(30))
    assert window.isVisible() and window.running
    assert "고개" in window._message.text() and "점" in window._message.text()
    assert window.size().width() >= 640 and window.size().height() >= 440
    window.close()


def test_시간이_흐르면_안내와_진행률이_바뀐다(qapp):
    window, _ = make_window(qapp)
    window.start(dot_follow_timeline(30))
    window._elapsed.ms = 3000
    window._on_frame()
    assert window._message.text() == "점을 좌우로 따라가세요"  # 첫 패턴
    window._elapsed.ms = 15000
    window._on_frame()
    assert window.progress == pytest.approx(0.5)
    window.close()


def test_끝까지_하면_완료를_한_번만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(dot_follow_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    window._on_frame()  # 다시 호출돼도 중복 알림이 없어야 한다
    assert events == [("completed", "dot_follow", 30)]
    assert not window.running
    assert window._button.text() == "닫기"


def test_완료_뒤_창을_닫아도_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(dot_follow_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    window.close()
    assert events == [("completed", "dot_follow", 30)]


def test_Esc로_중단하면_완료_없이_중단만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(dot_follow_timeline(30))
    window._elapsed.ms = 10000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert events == [("aborted",)]
    assert not window.isVisible()


def test_중단_버튼도_중단으로_처리한다(qapp):
    window, events = make_window(qapp)
    window.start(dot_follow_timeline(30))
    window._button.click()
    assert events == [("aborted",)]


def test_너무_짧은_설정도_창은_정상_동작한다(qapp):
    window, events = make_window(qapp)
    window.start(dot_follow_timeline(5))  # 최소 12초(패턴 1개)로 보정된다
    window._elapsed.ms = 12000
    window._on_frame()
    assert events == [("completed", "dot_follow", 12)]






# ---- 소리 안내 ----


def test_단계가_바뀔_때마다_소리_안내를_한_번씩_낸다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(dot_follow_timeline(30))
    for ms in (500, 1000, 2900):  # 같은 단계(준비)에서는 다시 말하지 않는다
        window._elapsed.ms = ms
        window._on_frame()
    assert speaker.phases == [Phase.PREPARE]
    # 준비(3초) → 점 따라가기 → 마무리(3초)
    for ms, phase in ((3000, Phase.TRACK), (10000, Phase.TRACK), (28000, Phase.FINISH)):
        window._elapsed.ms = ms
        window._on_frame()
        assert speaker.phases[-1] is phase
    assert speaker.phases == [Phase.PREPARE, Phase.TRACK, Phase.FINISH]  # 같은 단계에서는 다시 말하지 않는다
    window.close()


def test_창을_닫으면_소리를_멈춘다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(dot_follow_timeline(30))
    window.close()
    assert speaker.stopped == 1


def test_다시_시작하면_첫_단계_안내를_다시_한다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(dot_follow_timeline(30))
    window.close()
    window.start(dot_follow_timeline(30))
    assert speaker.phases == [Phase.PREPARE, Phase.PREPARE]
    window.close()


def test_소리가_꺼져_있어도_운동은_진행된다(qapp):
    window, events = make_window(qapp, None)
    window.start(dot_follow_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    assert events == [("completed", "dot_follow", 30)]
    window.close()


# ---- 컨트롤러 연결: 완료는 기록하고 중단은 기록하지 않는다 ----


def _exercising_controller(history):
    clock = FakeClock()
    sched = ReminderScheduler(Settings(), clock, FakeIdle())
    controller = Controller(sched, history, now=clock.now)
    controller.start_exercise()
    assert controller.state is State.EXERCISING
    return controller


def test_완료하면_기록하고_타이머를_다시_센다(qapp):
    history = History()
    controller = _exercising_controller(history)
    controller.complete_exercise("dot_follow", 30)
    assert controller.state is State.RUNNING
    assert [(e.type, e.exercise, e.duration_seconds) for e in history.events] == [("completed", "dot_follow", 30)]


def test_중단하면_기록하지_않고_타이머만_다시_센다(qapp):
    history = History()
    controller = _exercising_controller(history)
    controller.abort_exercise()
    assert controller.state is State.RUNNING
    assert history.events == ()


def test_운동_중이_아닐_때의_완료_요청은_기록하지_않는다(qapp):
    history = History()
    controller = _exercising_controller(history)
    controller.abort_exercise()
    controller.complete_exercise("dot_follow", 30)
    assert history.events == ()



# ---- 점 따라가기 ----


SCREEN = QRect(0, 0, 1920, 1040)  # 작업 표시줄을 뺀 1920×1080 모니터


def dot_window(qapp, speaker=None, duration=60, area=SCREEN):
    from eyeexercise.core.exercises import dot_follow_timeline

    window, events = make_window(qapp, speaker)
    window._screen_area = lambda: area  # 실제 모니터와 상관없이 같은 화면 크기에서 시험한다
    window.start(dot_follow_timeline(duration))
    return window, events


def test_점_따라가기는_화면의_큰_창과_점_화면을_쓴다(qapp):
    window, _ = dot_window(qapp)
    assert window.isVisible() and window.running
    assert window._dots.isVisible() and window._patterns.isVisible()
    assert (window.width(), window.height()) == (1344, 915)  # 1920×1040의 너비 70%·높이 88%
    window.close()


def test_점_따라가기_창은_화면_가운데에_뜬다(qapp):
    window, _ = dot_window(qapp)
    center = window.geometry().center()
    assert abs(center.x() - SCREEN.center().x()) <= 1 and abs(center.y() - SCREEN.center().y()) <= 1
    window.close()




def test_준비_문구와_점_위치가_보인다(qapp):
    window, _ = dot_window(qapp)
    assert "고개" in window._message.text()
    pos = window._dots.dot_position()
    assert pos is not None
    assert pos.x() == pytest.approx(window._dots.width() / 2, abs=1.0)  # 가운데
    window.close()


def test_시간이_흐르면_패턴_문구가_나오고_점이_움직인다(qapp):
    window, _ = dot_window(qapp)
    window._elapsed.ms = 3000 + 1500
    window._on_frame()
    first = window._dots.dot_position()
    assert window._message.text() == "점을 좌우로 따라가세요"
    window._elapsed.ms = 3000 + 2500
    window._on_frame()
    second = window._dots.dot_position()
    assert (first.x(), first.y()) != (second.x(), second.y())
    window._elapsed.ms = 3000 + 9000 + 4500  # 두 번째 패턴(상하)
    window._on_frame()
    assert window._message.text() == "점을 위아래로 따라가세요"
    window.close()


def test_점은_항상_화면_영역_안에_그려진다(qapp):
    window, _ = dot_window(qapp)
    canvas = window._dots
    for ms in range(0, 57000, 700):
        window._elapsed.ms = ms
        window._on_frame()
        pos = canvas.dot_position()
        assert 0 <= pos.x() <= canvas.width() and 0 <= pos.y() <= canvas.height()
    window.close()


def test_점_따라가기를_끝까지_하면_완료를_점_따라가기_이름으로_알린다(qapp):
    window, events = dot_window(qapp)
    window._elapsed.ms = 60000
    window._on_frame()
    window._on_frame()
    assert events == [("completed", "dot_follow", 60)]
    assert not window.running and window._button.text() == "닫기"


def test_점_따라가기가_끝나면_먼_곳_바라보기_없이_완료를_알리고_닫힌다(qapp):
    window, events = dot_window(qapp)
    window._elapsed.ms = 59000  # 마무리(점이 가운데로 돌아오는 중)
    window._on_frame()
    assert window.isVisible() and events == []
    window._elapsed.ms = 60000
    window._on_frame()
    assert events == [("completed", "dot_follow", 60)]
    assert not window.isVisible()  # 카운트다운 없이 바로 닫힌다
    assert "먼 곳" not in window._message.text()


def test_점_따라가기_창은_끝까지_같은_큰_창이다(qapp):
    window, _ = dot_window(qapp)
    size = (window.width(), window.height())
    for ms in (500, 20000, 58000, 59900):
        window._elapsed.ms = ms
        window._on_frame()
        assert (window.width(), window.height()) == size
        assert window._dots.isVisible() and window._patterns.isVisible()
    window.close()


def test_점_따라가기_도중_Esc로_중단하면_완료_없이_중단만_알린다(qapp):
    window, events = dot_window(qapp)
    window._elapsed.ms = 20000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert events == [("aborted",)]
    assert not window.isVisible()


def test_점_따라가기의_소리는_준비와_마무리에서만_난다(qapp):
    speaker = FakeSpeaker()
    window, _ = dot_window(qapp, speaker)
    for ms in (500, 3000, 20000, 40000, 57000, 60000):
        window._elapsed.ms = ms
        window._on_frame()
    # 추적 중에는 단계가 TRACK 하나라서 한 번만 알리고, TRACK에는 소리가 정의돼 있지 않다. 먼 곳 바라보기는 하지 않는다
    assert speaker.phases == [Phase.PREPARE, Phase.TRACK, Phase.FINISH]
    window.close()


# ---- 창 크기 ----


def test_창은_화면_너비_70퍼센트_높이_88퍼센트이고_큰_화면일수록_커진다():
    assert window_size(QRect(0, 0, 1920, 1040)) == (1344, 915)
    assert window_size(QRect(0, 0, 2560, 1400)) == (1792, 1232)
    assert window_size(QRect(0, 0, 1366, 728)) == (956, 641)  # 728*0.88=640.6


def test_창은_작은_화면에서도_최소_크기를_지키되_화면_밖으로_나가지_않는다():
    assert window_size(QRect(0, 0, 800, 600)) == (640, 528)  # 너비는 70%(560)가 최소 640보다 작아 최소 크기, 높이는 88%(528)
    w, h = window_size(QRect(0, 0, 600, 400))
    assert w <= 600 - 40 and h <= 400 - 40  # 최소 크기(640×440)보다 화면이 작으면 화면 안에 들어오게 줄인다
    assert window_size(QRect(0, 0, 1024, 600)) == (717, 528)  # 너비 70%(717)와 높이 88%(528)가 모두 최소보다 크다


# ---- 부드러운 움직임: 약 60fps의 정밀 타이머 ----


def test_프레임은_약_60fps의_정밀_타이머로_그린다(qapp):
    window, _ = make_window(qapp)
    assert window._timer.interval() <= 17
    assert window._timer.timerType() == Qt.TimerType.PreciseTimer
