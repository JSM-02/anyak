import pytest
from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest

from eyeexercise.core.exercises import Phase, blink_timeline
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
    window.start(blink_timeline(30))
    assert window.isVisible() and window.running
    assert window._message.text() == "편안하게 앉아 화면을 바라보세요"
    assert window.size().width() >= 480 and window.size().height() >= 320
    window.close()


def test_시간이_흐르면_안내와_진행률이_바뀐다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 3000
    window._on_frame()
    assert window._message.text() == "천천히 눈을 감으세요"
    window._elapsed.ms = 15000
    window._on_frame()
    assert window._progress.value() == 500
    window.close()


def test_끝까지_하면_완료를_한_번만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    window._on_frame()  # 다시 호출돼도 중복 알림이 없어야 한다
    assert events == [("completed", "blink", 30)]
    assert not window.running
    assert window._button.text() == "닫기"


def test_완료_뒤_창을_닫아도_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    window.close()
    assert events == [("completed", "blink", 30)]


def test_Esc로_중단하면_완료_없이_중단만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 10000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert events == [("aborted",)]
    assert not window.isVisible()


def test_중단_버튼도_중단으로_처리한다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._button.click()
    assert events == [("aborted",)]


def test_너무_짧은_설정도_창은_정상_동작한다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(5))  # 최소 12초(사이클 1회)로 보정된다
    window._elapsed.ms = 12000
    window._on_frame()
    assert events == [("completed", "blink", 12)]


# ---- 먼 곳 바라보기 카운트다운과 자동 닫기 ----


def test_운동이_끝나면_먼_곳_바라보기_카운트다운이_표시된다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    assert window._message.text() == "먼 곳을 바라보세요 · 20"
    window._elapsed.ms = 40500
    window._on_frame()
    assert window._message.text() == "먼 곳을 바라보세요 · 10"
    window._elapsed.ms = 49500
    window._on_frame()
    assert window._message.text() == "먼 곳을 바라보세요 · 1"
    assert window.isVisible()
    window.close()


def test_카운트다운_중에는_진행_막대가_줄어든다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    assert window._progress.value() == 1000
    window._elapsed.ms = 40000
    window._on_frame()
    assert window._progress.value() == 500
    window.close()


def test_카운트다운이_끝나면_저절로_닫히고_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    window._elapsed.ms = 50000
    window._on_frame()
    assert not window.isVisible()
    assert events == [("completed", "blink", 30)]


def test_카운트다운_중에_닫아도_완료는_이미_기록되고_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 35000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.isVisible()
    assert events == [("completed", "blink", 30)]


# ---- 소리 안내 ----


def test_단계가_바뀔_때마다_소리_안내를_한_번씩_낸다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(blink_timeline(30))
    for ms in (500, 1000, 2900):  # 같은 단계(준비)에서는 다시 말하지 않는다
        window._elapsed.ms = ms
        window._on_frame()
    assert speaker.phases == [Phase.PREPARE]
    # 감기(2초) → 유지(1초) → 뜨기(2초) → 쉬기(1초)가 6초마다 이어진다
    steps = [(3000, Phase.CLOSE), (5000, Phase.HOLD), (6000, Phase.OPEN), (8000, Phase.REST), (9000, Phase.CLOSE)]
    for ms, phase in steps:
        window._elapsed.ms = ms
        window._on_frame()
        assert speaker.phases[-1] is phase
    window.close()


def test_사이클이_딱_맞지_않아_남는_시간이_있으면_마지막에_쉬기_안내가_나온다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(blink_timeline(31))  # 준비 3 + 사이클 4회(24초) + 남는 1초 + 마무리 3
    window._elapsed.ms = 27000
    window._on_frame()
    assert speaker.phases[-1] is Phase.REST
    window.close()


def test_먼_곳_바라보기_안내도_소리로_나온다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(blink_timeline(30))
    window._elapsed.ms = 28000
    window._on_frame()
    window._elapsed.ms = 30000
    window._on_frame()
    assert speaker.phases[-2:] == [Phase.FINISH, Phase.LOOK_AWAY]
    window.close()


def test_창을_닫으면_소리를_멈춘다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(blink_timeline(30))
    window.close()
    assert speaker.stopped == 1


def test_다시_시작하면_첫_단계_안내를_다시_한다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(blink_timeline(30))
    window.close()
    window.start(blink_timeline(30))
    assert speaker.phases == [Phase.PREPARE, Phase.PREPARE]
    window.close()


def test_소리가_꺼져_있어도_운동은_진행된다(qapp):
    window, events = make_window(qapp, None)
    window.start(blink_timeline(30))
    window._elapsed.ms = 30000
    window._on_frame()
    assert events == [("completed", "blink", 30)]
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
    controller.complete_exercise("blink", 30)
    assert controller.state is State.RUNNING
    assert [(e.type, e.exercise, e.duration_seconds) for e in history.events] == [("completed", "blink", 30)]


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
    controller.complete_exercise("blink", 30)
    assert history.events == ()


def test_쉬는_동안에는_문구가_비고_창_구성은_그대로다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    window._elapsed.ms = 8500  # 첫 사이클의 쉬기(8~9초)
    window._on_frame()
    assert window._message.text() == ""
    assert window._message.minimumHeight() >= 40  # 문구가 비어도 높이가 유지된다
    window.close()


# ---- 점 따라가기 ----


SCREEN = QRect(0, 0, 1920, 1040)  # 작업 표시줄을 뺀 1920×1080 모니터


def dot_window(qapp, speaker=None, duration=60, area=SCREEN):
    from eyeexercise.core.exercises import dot_follow_timeline

    window, events = make_window(qapp, speaker)
    window._screen_area = lambda: area  # 실제 모니터와 상관없이 같은 화면 크기에서 시험한다
    window.start(dot_follow_timeline(duration))
    return window, events


def test_점_따라가기는_화면의_70퍼센트_크기_창과_점_화면을_쓴다(qapp):
    window, _ = dot_window(qapp)
    assert window.isVisible() and window.running
    assert window._dots.isVisible() and not window._eye.isVisible()
    assert (window.width(), window.height()) == (1344, 728)  # 1920×1040의 70%
    window.close()


def test_점_따라가기_창은_화면_가운데에_뜬다(qapp):
    window, _ = dot_window(qapp)
    center = window.geometry().center()
    assert abs(center.x() - SCREEN.center().x()) <= 1 and abs(center.y() - SCREEN.center().y()) <= 1
    window.close()


def test_깜빡임은_작은_창과_눈_모양을_쓴다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    assert window._eye.isVisible() and not window._dots.isVisible()
    assert (window.width(), window.height()) == (480, 320)
    window.close()


def test_운동을_바꿔_다시_띄우면_창_크기와_화면이_따라_바뀐다(qapp):
    window, _ = dot_window(qapp)
    window.close()
    window.start(blink_timeline(30))
    assert (window.width(), window.height()) == (480, 320) and window._eye.isVisible()
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


def test_먼_곳_바라보기_동안에는_점이_사라지고_카운트다운이_보인다(qapp):
    window, _ = dot_window(qapp)
    window._elapsed.ms = 60000
    window._on_frame()
    assert window._dots.dot_position() is None
    assert window._message.text() == "먼 곳을 바라보세요 · 20"
    window._elapsed.ms = 70500
    window._on_frame()
    assert window._message.text() == "먼 곳을 바라보세요 · 10"
    window.close()


def test_카운트다운이_끝나면_저절로_닫힌다(qapp):
    window, events = dot_window(qapp)
    window._elapsed.ms = 60000
    window._on_frame()
    window._elapsed.ms = 80000
    window._on_frame()
    assert not window.isVisible()
    assert events == [("completed", "dot_follow", 60)]


def test_점_따라가기_도중_Esc로_중단하면_완료_없이_중단만_알린다(qapp):
    window, events = dot_window(qapp)
    window._elapsed.ms = 20000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert events == [("aborted",)]
    assert not window.isVisible()


def test_점_따라가기의_소리는_준비_마무리_먼_곳_보기에서만_난다(qapp):
    speaker = FakeSpeaker()
    window, _ = dot_window(qapp, speaker)
    for ms in (500, 3000, 20000, 40000, 57000, 60000):
        window._elapsed.ms = ms
        window._on_frame()
    # 추적 중에는 단계가 TRACK 하나라서 한 번만 알리고, TRACK에는 소리가 정의돼 있지 않다
    assert speaker.phases == [Phase.PREPARE, Phase.TRACK, Phase.FINISH, Phase.LOOK_AWAY]
    window.close()


# ---- 창 크기 ----


def test_깜빡임_창은_화면_크기와_상관없이_고정이다():
    for area in (QRect(0, 0, 1280, 720), QRect(0, 0, 3840, 2100)):
        assert window_size("blink", area) == (480, 320)


def test_점_따라가기_창은_화면의_70퍼센트이고_큰_화면일수록_커진다():
    assert window_size("dot_follow", QRect(0, 0, 1920, 1040)) == (1344, 728)
    assert window_size("dot_follow", QRect(0, 0, 2560, 1400)) == (1792, 980)
    assert window_size("dot_follow", QRect(0, 0, 1366, 728)) == (956, 510)  # 728*0.7=509.6


def test_점_따라가기_창은_작은_화면에서도_최소_크기를_지키되_화면_밖으로_나가지_않는다():
    assert window_size("dot_follow", QRect(0, 0, 800, 600)) == (640, 440)  # 70%(560×420)가 최소 640×440보다 작으면 최소 크기
    w, h = window_size("dot_follow", QRect(0, 0, 600, 400))
    assert (w, h) == (560, 360)  # 화면보다 크게 뜨지 않는다 (여백 40)
    assert window_size("dot_follow", QRect(0, 0, 1024, 600)) == (717, 440)  # 너비만 70%가 최소보다 크다


def test_점_따라가기_창은_깜빡임_창보다_크다():
    w_dot, h_dot = window_size("dot_follow", QRect(0, 0, 1920, 1040))
    w_blink, h_blink = window_size("blink", QRect(0, 0, 1920, 1040))
    assert w_dot > w_blink and h_dot > h_blink


# ---- 먼 곳 바라보기: 점 따라가기도 깜빡임과 같은 화면 ----


def test_점_따라가기도_먼_곳_바라보기에서는_깜빡임과_같은_작은_창과_눈_모양이다(qapp):
    window, _ = dot_window(qapp)
    window._elapsed.ms = 59000  # 마무리(점이 가운데로 돌아오는 중)
    window._on_frame()
    assert window._dots.isVisible() and (window.width(), window.height()) == (1344, 728)
    before = window.geometry().center()

    window._elapsed.ms = 60000  # 먼 곳 바라보기 시작
    window._on_frame()
    assert (window.width(), window.height()) == (480, 320)  # 깜빡임 창과 같은 크기
    assert window._eye.isVisible() and not window._dots.isVisible()  # 점이 있던 회색 화면이 사라진다
    assert window._message.text() == "먼 곳을 바라보세요 · 20"
    after = window.geometry().center()
    assert abs(before.x() - after.x()) <= 1 and abs(before.y() - after.y()) <= 1  # 같은 자리에서 줄어든다
    window.close()


def test_먼_곳_바라보기_화면으로_바뀐_뒤에는_다시_바뀌지_않는다(qapp):
    window, _ = dot_window(qapp)
    window._elapsed.ms = 60000
    window._on_frame()
    geometry = window.geometry()
    for ms in (61000, 65000, 70000, 79000):
        window._elapsed.ms = ms
        window._on_frame()
        assert window.geometry() == geometry
        assert window._eye.isVisible() and not window._dots.isVisible()
    window.close()


def test_먼_곳_바라보기_뒤_다시_시작하면_큰_창으로_돌아온다(qapp):
    from eyeexercise.core.exercises import dot_follow_timeline

    window, _ = dot_window(qapp)
    window._elapsed.ms = 60000
    window._on_frame()
    window.close()
    window.start(dot_follow_timeline(60))
    assert (window.width(), window.height()) == (1344, 728)
    assert window._dots.isVisible() and not window._eye.isVisible()
    window.close()


def test_깜빡임은_먼_곳_바라보기에서도_창이_그대로다(qapp):
    window, _ = make_window(qapp)
    window.start(blink_timeline(30))
    before = (window.width(), window.height(), window.geometry().topLeft())
    window._elapsed.ms = 30000
    window._on_frame()
    assert (window.width(), window.height(), window.geometry().topLeft()) == before
    assert window._eye.isVisible()
    window.close()


# ---- 부드러운 움직임: 약 60fps의 정밀 타이머 ----


def test_프레임은_약_60fps의_정밀_타이머로_그린다(qapp):
    window, _ = make_window(qapp)
    assert window._timer.interval() <= 17
    assert window._timer.timerType() == Qt.TimerType.PreciseTimer


# ---- 눈 모양 (7.5c) ----


def test_눈은_감을수록_납작해지고_완전히_감으면_선이_된다(qapp):
    from eyeexercise.ui.exercise_window import EyeWidget

    eye = EyeWidget()
    eye.resize(260, 140)
    heights = []
    for openness in (1.0, 0.7, 0.4, 0.15, 0.0):
        eye.set_openness(openness)
        heights.append(eye.lid_path().boundingRect().height())
    assert heights == sorted(heights, reverse=True)
    assert heights[0] > 60 and heights[-1] < 8  # 활짝 뜬 눈은 높고, 감은 눈은 거의 선


def test_눈꺼풀_움직임은_양끝이_느리고_가운데가_빠르다():
    from eyeexercise.ui.exercise_window import _ease

    assert _ease(0.0) == 0.0 and _ease(1.0) == 1.0 and _ease(0.5) == pytest.approx(0.5)
    assert _ease(0.1) < 0.1 and _ease(0.9) > 0.9  # 시작과 끝은 선형보다 느리게 움직인다
    values = [_ease(i / 20) for i in range(21)]
    assert values == sorted(values)  # 항상 한 방향으로 움직인다
