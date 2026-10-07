"""눈 휴식과 눈 운동이 분리된 화면 흐름 (7.6b): 컨트롤러·팝업·트레이·앱·운동 창."""

from datetime import datetime

from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QPushButton
from test_exercise_window import FakeElapsed
from test_settings_runtime import make_app

from eyeexercise.core.exercises import LookAwayTimeline, Phase, blink_timeline
from eyeexercise.core.history import ACTIVITY_EXERCISE, ACTIVITY_REST, History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.exercise_window import ExerciseWindow
from eyeexercise.ui.reminder_popup import ReminderPopup


def make_controller():
    clock = FakeClock()
    return Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now)


# ---- 컨트롤러 ----


def test_휴식과_운동을_시작하면_어떤_활동인지_알린다(qapp):
    controller = make_controller()
    started = []
    controller.activity_started.connect(started.append)
    controller.start_rest()
    assert started == [ACTIVITY_REST] and controller.activity == ACTIVITY_REST
    assert controller.state is State.EXERCISING
    controller.abort_exercise()
    assert controller.activity is None and controller.state is State.RUNNING
    controller.start_exercise()
    assert started == [ACTIVITY_REST, ACTIVITY_EXERCISE] and controller.activity == ACTIVITY_EXERCISE
    controller.complete_exercise("dot_follow", 60)
    assert controller.activity is None


def test_이미_하는_중에_시작을_또_눌러도_무시한다(qapp):
    controller = make_controller()
    started = []
    controller.activity_started.connect(started.append)
    controller.start_rest()
    controller.start_exercise()  # EXERCISING 상태에서는 시작할 수 없다
    assert started == [ACTIVITY_REST] and controller.activity == ACTIVITY_REST


def test_휴식_알림의_미루기와_건너뛰기는_휴식으로_기록한다(qapp):
    clock = FakeClock()
    history = History()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), history, now=clock.now)
    for _ in range(20 * 60 + 1):
        clock.advance(1)
        controller._on_tick()
    assert controller.state is State.DUE
    controller.snooze()
    assert [(e.type, e.activity) for e in history.events] == [("snoozed", ACTIVITY_REST)]


# ---- 알림 팝업 ----


def test_팝업은_휴식_알림이고_운동_버튼은_처음엔_숨겨져_있다(qapp):
    popup = ReminderPopup(5)
    labels = [b.text() for b in popup.findChildren(QPushButton)]
    assert labels[:3] == ["시작", "5분 미루기", "건너뛰기"]
    assert popup._exercise_button.isHidden()


def test_운동_제안_버튼은_오늘_진행_상황을_보여_주고_누르면_알린다(qapp):
    popup = ReminderPopup(5)
    clicked = []
    popup.exercise_clicked.connect(lambda: clicked.append(1))
    popup.set_exercise_offer(1, 2)
    assert not popup._exercise_button.isHidden()
    assert popup._exercise_button.text() == "운동도 할래요? (오늘 1/2)"
    popup._exercise_button.click()
    assert clicked == [1]
    popup.set_exercise_offer(None, 0)  # 목표를 채웠다
    assert popup._exercise_button.isHidden()


def test_팝업의_세_버튼은_각각_신호를_낸다(qapp):
    popup = ReminderPopup(5)
    got = []
    popup.start_clicked.connect(lambda: got.append("start"))
    popup.snooze_clicked.connect(lambda: got.append("snooze"))
    popup.skip_clicked.connect(lambda: got.append("skip"))
    for b in popup.findChildren(QPushButton)[:3]:
        b.click()
    assert got == ["start", "snooze", "skip"]


# ---- 앱 전체 ----


def test_알림이_뜨면_목표를_채우지_못했을_때만_운동을_제안한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.controller.reminder_due.emit()
    assert not tray_app.popup._exercise_button.isHidden()
    assert tray_app.popup._exercise_button.text() == "운동도 할래요? (오늘 0/2)"
    tray_app.popup.hide()

    tray_app.history.record_completed(datetime.now().astimezone(), "dot_follow", 60)
    tray_app.controller.reminder_due.emit()
    assert tray_app.popup._exercise_button.text() == "운동도 할래요? (오늘 1/2)"
    tray_app.popup.hide()

    tray_app.history.record_completed(datetime.now().astimezone(), "dot_follow", 60)
    tray_app.controller.reminder_due.emit()
    assert tray_app.popup._exercise_button.isHidden()  # 목표(2회)를 채웠다
    tray_app.popup.hide()


def test_휴식을_시작하면_깜빡임과_먼_곳_바라보기_창이_뜬다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup.start_clicked.emit()
    window = tray_app.exercise_window
    assert window.isVisible() and window._tag.text() == "눈 휴식"
    assert window._timeline.exercise == "blink" and window._timeline.total_seconds == 36  # 기본 5회
    window.close()


def test_깜빡임을_끄면_휴식은_먼_곳_바라보기만_한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"exercises.blink.enabled": False})
    tray_app.controller.start_rest()
    assert isinstance(tray_app.exercise_window._timeline, LookAwayTimeline)
    assert tray_app.exercise_window._tag.text() == "눈 휴식"
    tray_app.exercise_window.close()


def test_운동을_시작하면_점_따라가기_창이_뜬다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup.exercise_clicked.emit()
    window = tray_app.exercise_window
    assert window._tag.text() == "눈 운동" and window._timeline.exercise == "dot_follow"
    window.close()


def test_점_따라가기를_끄면_운동은_시작되지_않고_안내만_한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"exercises.dot_follow.enabled": False})
    tray_app.controller.start_exercise()
    assert not tray_app.exercise_window.isVisible()
    assert tray_app.controller.state is State.RUNNING and tray_app.controller.activity is None


def test_휴식을_마치면_깜빡임으로_운동을_마치면_점_따라가기로_기록한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.controller.start_rest()
    tray_app.exercise_window.completed.emit("blink", 24)
    tray_app.controller.start_exercise()
    tray_app.exercise_window.completed.emit("dot_follow", 60)
    assert [(e.exercise, e.duration_seconds) for e in tray_app.history.events] == [("blink", 24), ("dot_follow", 60)]
    tray_app.exercise_window.close()


# ---- 트레이 ----


def test_트레이_메뉴에_지금_휴식과_지금_운동이_있다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray = tray_app.tray
    labels = [a.text() for a in tray._menu.actions() if a.text()]
    assert labels == ["열기", "지금 휴식", "지금 운동", "일시정지", "종료"]
    tray._act_rest.trigger()
    assert tray_app.controller.activity == ACTIVITY_REST
    assert not tray._act_rest.isEnabled() and not tray._act_now.isEnabled()  # 하는 중에는 둘 다 못 누른다
    tray_app.exercise_window.close()


def test_트레이_안내_문구는_휴식_기준이다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray = tray_app.tray
    assert "다음 휴식까지" in tray._status_text(State.RUNNING)
    assert tray._status_text(State.DUE) == "눈 쉬는 시간이에요"
    tray_app.controller.start_rest()
    assert tray._status_text(State.EXERCISING) == "눈 쉬는 중"
    tray_app.exercise_window.close()
    tray_app.controller.start_exercise()
    assert tray._status_text(State.EXERCISING) == "눈 운동 중"
    tray_app.exercise_window.close()


# ---- 운동 창 ----


def make_window():
    window = ExerciseWindow(None)
    window._elapsed = FakeElapsed()
    window._screen_area = lambda: QRect(0, 0, 1920, 1040)
    return window


def test_운동_창은_휴식과_운동의_이름표를_보여_준다(qapp):
    window = make_window()
    window.start(blink_timeline(24))
    assert window._tag.text() == "눈 휴식"
    window.close()
    from eyeexercise.core.exercises import dot_follow_timeline

    window = make_window()
    window.start(dot_follow_timeline(60))
    assert window._tag.text() == "눈 운동"
    window.close()


def test_먼_곳_바라보기만_하는_휴식은_눈을_보이고_바로_완료로_센다(qapp):
    window = make_window()
    events = []
    window.completed.connect(lambda exercise, seconds: events.append((exercise, seconds)))
    window.start(LookAwayTimeline())
    assert not window._eye.isHidden() and window._dots.isHidden()
    window._on_frame()
    assert events == [("blink", 0)]
    assert window._message.text().startswith("먼 곳을 바라보세요")
    window._elapsed.ms = 20_000
    window._on_frame()
    assert not window.isVisible()  # 20초가 지나면 저절로 닫힌다
    assert window._last_phase is Phase.LOOK_AWAY
