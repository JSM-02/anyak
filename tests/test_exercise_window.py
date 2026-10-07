from fakes import FakeClock, FakeIdle
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from eyeexercise.core.exercises import Phase
from eyeexercise.core.history import History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.exercise_window import ExerciseWindow


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
    window.start(30)
    assert window.isVisible() and window.running
    assert window._message.text() == "편안하게 앉아 화면을 바라보세요"
    assert window.size().width() >= 480 and window.size().height() >= 320
    window.close()


def test_시간이_흐르면_안내와_진행률이_바뀐다(qapp):
    window, _ = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 3000
    window._on_frame()
    assert window._message.text() == "천천히 눈을 감으세요"
    window._elapsed.ms = 15000
    window._on_frame()
    assert window._progress.value() == 500
    window.close()


def test_끝까지_하면_완료를_한_번만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 30000
    window._on_frame()
    window._on_frame()  # 다시 호출돼도 중복 알림이 없어야 한다
    assert events == [("completed", "blink", 30)]
    assert not window.running
    assert window._button.text() == "닫기"


def test_완료_뒤_창을_닫아도_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 30000
    window._on_frame()
    window.close()
    assert events == [("completed", "blink", 30)]


def test_Esc로_중단하면_완료_없이_중단만_알린다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 10000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert events == [("aborted",)]
    assert not window.isVisible()


def test_중단_버튼도_중단으로_처리한다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._button.click()
    assert events == [("aborted",)]


def test_너무_짧은_설정도_창은_정상_동작한다(qapp):
    window, events = make_window(qapp)
    window.start(5)  # 최소 12초(사이클 1회)로 보정된다
    window._elapsed.ms = 12000
    window._on_frame()
    assert events == [("completed", "blink", 12)]


# ---- 먼 곳 바라보기 카운트다운과 자동 닫기 ----


def test_운동이_끝나면_먼_곳_바라보기_카운트다운이_표시된다(qapp):
    window, _ = make_window(qapp)
    window.start(30)
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
    window.start(30)
    window._elapsed.ms = 30000
    window._on_frame()
    assert window._progress.value() == 1000
    window._elapsed.ms = 40000
    window._on_frame()
    assert window._progress.value() == 500
    window.close()


def test_카운트다운이_끝나면_저절로_닫히고_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 30000
    window._on_frame()
    window._elapsed.ms = 50000
    window._on_frame()
    assert not window.isVisible()
    assert events == [("completed", "blink", 30)]


def test_카운트다운_중에_닫아도_완료는_이미_기록되고_중단으로_알리지_않는다(qapp):
    window, events = make_window(qapp)
    window.start(30)
    window._elapsed.ms = 35000
    window._on_frame()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.isVisible()
    assert events == [("completed", "blink", 30)]


# ---- 소리 안내 ----


def test_단계가_바뀔_때마다_소리_안내를_한_번씩_낸다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(30)
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
    window.start(31)  # 준비 3 + 사이클 4회(24초) + 남는 1초 + 마무리 3
    window._elapsed.ms = 27000
    window._on_frame()
    assert speaker.phases[-1] is Phase.REST
    window.close()


def test_먼_곳_바라보기_안내도_소리로_나온다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(30)
    window._elapsed.ms = 28000
    window._on_frame()
    window._elapsed.ms = 30000
    window._on_frame()
    assert speaker.phases[-2:] == [Phase.FINISH, Phase.LOOK_AWAY]
    window.close()


def test_창을_닫으면_소리를_멈춘다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(30)
    window.close()
    assert speaker.stopped == 1


def test_다시_시작하면_첫_단계_안내를_다시_한다(qapp):
    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker)
    window.start(30)
    window.close()
    window.start(30)
    assert speaker.phases == [Phase.PREPARE, Phase.PREPARE]
    window.close()


def test_소리가_꺼져_있어도_운동은_진행된다(qapp):
    window, events = make_window(qapp, None)
    window.start(30)
    window._elapsed.ms = 30000
    window._on_frame()
    assert events == [("completed", "blink", 30)]
    window.close()


# ---- 컨트롤러 연결: 완료는 기록하고 중단은 기록하지 않는다. 카메라는 어디에도 없다. ----


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
    window.start(30)
    window._elapsed.ms = 8500  # 첫 사이클의 쉬기(8~9초)
    window._on_frame()
    assert window._message.text() == ""
    assert window._message.minimumHeight() >= 40  # 문구가 비어도 높이가 유지된다
    window.close()
