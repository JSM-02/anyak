"""눈 휴식과 눈 운동이 분리된 화면 흐름 (7.6b): 컨트롤러·팝업·트레이·앱·운동 창."""

from datetime import datetime

from fakes import FakeClock, FakeIdle
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QPushButton
from test_exercise_window import FakeElapsed
from test_settings_runtime import make_app

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



def test_휴식은_창_없이_팝업_안의_20초_카운트다운이다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup._elapsed = FakeElapsed()
    tray_app.controller.reminder_due.emit()
    tray_app.popup.start_clicked.emit()
    assert tray_app.popup.isVisible() and tray_app.popup.counting
    assert not tray_app.exercise_window.isVisible()  # 따로 뜨는 창이 없다
    assert tray_app.controller.state is State.EXERCISING and tray_app.controller.activity == ACTIVITY_REST
    tray_app.popup._elapsed.ms = 19000
    tray_app.popup._on_frame()
    assert list(tray_app.history.events) == []  # 20초가 지나기 전에는 기록하지 않는다
    tray_app.popup._elapsed.ms = 20000
    tray_app.popup._on_frame()
    assert [(e.type, e.exercise, e.duration_seconds) for e in tray_app.history.events] == [("completed", "blink", 20)]
    assert tray_app.controller.state is State.RUNNING and tray_app.controller.activity is None
    assert not tray_app.popup.isVisible()


def test_알림에서_시작해도_팝업이_깜빡이지_않고_바로_카운트다운이_된다(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent, QObject

    class Watcher(QObject):
        hidden = 0

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Hide:
                self.hidden += 1
            return False

    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup._elapsed = FakeElapsed()
    tray_app.controller.reminder_due.emit()
    watcher = Watcher()
    tray_app.popup.installEventFilter(watcher)
    tray_app.popup.start_clicked.emit()
    assert watcher.hidden == 0 and tray_app.popup.isVisible() and tray_app.popup.counting
    tray_app.popup.hide()


def test_홈이나_트레이의_지금_휴식도_팝업에서_카운트다운을_한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup._elapsed = FakeElapsed()
    assert not tray_app.popup.isVisible()
    tray_app.controller.start_rest()
    assert tray_app.popup.isVisible() and tray_app.popup.counting and not tray_app.exercise_window.isVisible()
    tray_app.popup.hide()


def test_카운트다운을_중단하면_기록_없이_타이머만_다시_센다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.popup._elapsed = FakeElapsed()
    tray_app.controller.reminder_due.emit()
    tray_app.popup.start_clicked.emit()
    tray_app.popup._elapsed.ms = 8000
    tray_app.popup._abort_button.click()
    assert list(tray_app.history.events) == []
    assert tray_app.controller.state is State.RUNNING and tray_app.controller.activity is None
    assert not tray_app.popup.isVisible()


def test_운동_제안으로_시작하면_팝업은_닫히고_점_따라가기_창이_뜬다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.controller.reminder_due.emit()
    tray_app.popup.exercise_clicked.emit()
    assert not tray_app.popup.isVisible() and not tray_app.popup.counting  # 팝업 안의 카운트다운으로 바뀌지 않는다
    assert tray_app.exercise_window.isVisible() and tray_app.exercise_window._timeline.exercise == "dot_follow"
    tray_app.exercise_window.close()


def test_팝업과_운동_창이_같은_소리_안내를_쓴다(qapp, tmp_path, monkeypatch):
    tray_app, speakers = make_app(qapp, tmp_path, monkeypatch, sound=True)
    assert tray_app.popup._speaker is tray_app.exercise_window._speaker is not None
    tray_app.settings_manager.update({"sound.enabled": False})
    assert tray_app.popup._speaker is None and tray_app.exercise_window._speaker is None
    assert speakers == [False]  # 소리 안내는 설정을 바꿀 때 한 번만 새로 만든다


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


def test_휴식을_마치면_휴식으로_운동을_마치면_점_따라가기로_기록한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.controller.start_rest()
    tray_app.exercise_window.completed.emit("blink", 20)  # 휴식은 기록에서 "blink"라는 옛 이름을 그대로 쓴다
    tray_app.controller.start_exercise()
    tray_app.exercise_window.completed.emit("dot_follow", 60)
    assert [(e.exercise, e.duration_seconds) for e in tray_app.history.events] == [("blink", 20), ("dot_follow", 60)]
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
    tray_app.popup.hide()


def test_트레이_안내_문구는_휴식_기준이다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray = tray_app.tray
    assert "다음 휴식까지" in tray._status_text(State.RUNNING)
    assert tray._status_text(State.DUE) == "눈이 쉴 시간이에요"
    tray_app.controller.start_rest()
    assert tray._status_text(State.EXERCISING) == "눈 쉬는 중"
    tray_app.popup.hide()  # 팝업 안의 20초를 멈춘다(휴식은 팝업 안에서 한다)
    tray_app.controller.start_exercise()
    assert tray._status_text(State.EXERCISING) == "눈 운동 중"
    tray_app.exercise_window.close()


# ---- 운동 창 ----


def make_window():
    window = ExerciseWindow(None)
    window._elapsed = FakeElapsed()
    window._screen_area = lambda: QRect(0, 0, 1920, 1040)
    return window


def test_운동_창은_눈_운동_이름표를_보여_준다(qapp):
    from eyeexercise.core.exercises import dot_follow_timeline

    window = make_window()
    window.start(dot_follow_timeline(60))
    assert window._tag.text() == "눈 운동"
    window.close()
