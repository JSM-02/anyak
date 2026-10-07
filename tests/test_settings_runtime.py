import json

from fakes import FakeClock, FakeIdle
from PySide6.QtWidgets import QPushButton

from eyeexercise.core.history import History
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.storage import json_store, paths
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.exercise_window import ExerciseWindow
from eyeexercise.ui.reminder_popup import ReminderPopup

# ---- 컨트롤러: 설정 변경을 스케줄러에 전달 ----


def make_controller(settings=None):
    clock, idle = FakeClock(), FakeIdle()
    scheduler = ReminderScheduler(settings or Settings(), clock, idle)
    return Controller(scheduler, History(), now=clock.now), clock


def tick(controller, clock, seconds):
    for _ in range(seconds):
        clock.advance(1)
        controller._on_tick()


def test_알림_주기를_줄이면_이미_센_시간은_유지하고_새_주기로_알린다(qapp):
    controller, clock = make_controller()  # 기본 20분
    tick(controller, clock, 30)
    manager = SettingsManager(Settings())
    controller.apply_settings(manager.update({"interval_minutes": 1}).settings)
    assert controller.state is State.RUNNING
    tick(controller, clock, 29)
    assert controller.state is State.RUNNING
    tick(controller, clock, 2)
    assert controller.state is State.DUE  # 30초 + 31초가 새 주기(60초)를 넘었다


def test_알림_주기를_늘리면_더_늦게_알린다(qapp):
    controller, clock = make_controller(Settings(interval_minutes=1))
    controller.apply_settings(Settings(interval_minutes=2))
    tick(controller, clock, 90)
    assert controller.state is State.RUNNING
    tick(controller, clock, 31)
    assert controller.state is State.DUE


def test_남은_시간은_새_주기로_계산된다(qapp):
    controller, clock = make_controller()
    tick(controller, clock, 10)
    controller.apply_settings(Settings(interval_minutes=5))
    assert controller.remaining_seconds == 5 * 60 - 10


# ---- 알림 팝업: 미루기 시간 ----


def test_팝업은_미루기_시간이_바뀌면_버튼_글자를_바꾼다(qapp):
    popup = ReminderPopup(5)
    texts = lambda: [b.text() for b in popup.findChildren(QPushButton)]  # noqa: E731
    assert "5분 미루기" in texts()
    popup.set_snooze_minutes(15)
    assert "15분 미루기" in texts() and "5분 미루기" not in texts()


# ---- 운동 창: 소리 ----


class FakeSpeaker:
    def __init__(self):
        self.stopped = 0
        self.phases = []

    def cue(self, phase):
        self.phases.append(phase)

    def stop(self):
        self.stopped += 1


def test_소리를_바꾸면_이전_소리를_멈추고_새_소리를_쓴다(qapp):
    old, new = FakeSpeaker(), FakeSpeaker()
    window = ExerciseWindow(old)
    window.set_speaker(new)
    assert old.stopped == 1 and window._speaker is new
    window.set_speaker(None)  # 소리 끄기
    assert new.stopped == 1 and window._speaker is None


def test_소리가_꺼져_있다가_켜져도_된다(qapp):
    window = ExerciseWindow(None)
    speaker = FakeSpeaker()
    window.set_speaker(speaker)
    assert window._speaker is speaker


# ---- 앱 전체: 설정을 바꾸면 실행 중인 부분에 따라간다 ----


def make_app(qapp, tmp_path, monkeypatch, sound=False):
    """임시 폴더(%APPDATA%)에 앱을 조립한다. 시작하지는 않는다(타이머·트레이를 켜지 않음)."""
    from eyeexercise import app as app_module

    monkeypatch.setenv("APPDATA", str(tmp_path))
    speakers = []
    monkeypatch.setattr(app_module, "create_speaker", lambda enabled: speakers.append(enabled) or (FakeSpeaker() if enabled else None))
    settings = json_store.load_settings(paths.settings_path())
    settings = SettingsManager(settings).update({"sound.enabled": sound}).settings
    tray_app = app_module.TrayApp(qapp, settings)
    speakers.clear()  # 조립할 때 만든 것은 센 대상이 아니다
    return tray_app, speakers


def test_앱에서_설정을_바꾸면_파일에_저장된다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"interval_minutes": 30, "exercises.dot_follow.speed": "fast"})
    saved = json.loads(paths.settings_path().read_text(encoding="utf-8"))
    assert saved["interval_minutes"] == 30 and saved["exercises"]["dot_follow"]["speed"] == "fast"


def test_알림_주기를_바꾸면_스케줄러가_따라간다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"interval_minutes": 30})
    assert tray_app.controller.remaining_seconds == 30 * 60


def test_미루기_시간을_바꾸면_팝업_버튼이_바뀐다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"snooze_minutes": 12})
    assert "12분 미루기" in [b.text() for b in tray_app.popup.findChildren(QPushButton)]


def test_다음_운동은_바꾼_운동_시간과_속도로_시작한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"exercises.blink.enabled": False, "exercises.dot_follow.duration_seconds": 90, "exercises.dot_follow.speed": "fast"})
    tray_app.controller.start_exercise()  # 알림 팝업 없이 지금 운동
    timeline = tray_app.exercise_window._timeline
    assert timeline.exercise == "dot_follow" and timeline.total_seconds == 90 and timeline.speed_hz == 0.3
    tray_app.exercise_window.close()


def test_운동을_모두_끄면_운동이_시작되지_않고_타이머만_다시_센다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    tray_app.settings_manager.update({"exercises.blink.enabled": False, "exercises.dot_follow.enabled": False})
    tray_app.controller.start_exercise()
    assert not tray_app.exercise_window.isVisible()
    assert tray_app.controller.state is State.RUNNING


def test_소리를_켜고_끄면_운동_창의_소리가_바뀐다(qapp, tmp_path, monkeypatch):
    tray_app, created = make_app(qapp, tmp_path, monkeypatch, sound=False)
    assert tray_app.exercise_window._speaker is None
    tray_app.settings_manager.update({"sound.enabled": True})
    assert created == [True] and tray_app.exercise_window._speaker is not None
    tray_app.settings_manager.update({"sound.enabled": False})
    assert created == [True, False] and tray_app.exercise_window._speaker is None


def test_소리와_상관없는_설정을_바꾸면_소리를_다시_만들지_않는다(qapp, tmp_path, monkeypatch):
    tray_app, created = make_app(qapp, tmp_path, monkeypatch, sound=True)
    tray_app.settings_manager.update({"interval_minutes": 30, "snooze_minutes": 9})
    assert created == []


def test_자리_비움_기준을_바꾸면_스크린_타임_기준도_따라간다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    threshold = tray_app.controller._usage._threshold
    assert threshold() == 60
    tray_app.settings_manager.update({"idle_pause_minutes": 3, "idle_reset_minutes": 10})
    assert threshold() == 180


def test_설정_화면과_앱이_같은_설정을_본다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    page = tray_app.main_window.settings_page
    page.control("interval_minutes").setValue(45)  # 화면에서 바꾸면
    assert tray_app.controller.remaining_seconds == 45 * 60  # 스케줄러가 따라간다
    tray_app.settings_manager.update({"snooze_minutes": 8})  # 다른 곳에서 바꾸면
    assert page.control("snooze_minutes").value() == 8  # 화면이 따라간다


def test_저장에_실패해도_앱은_바뀐_설정으로_동작한다(qapp, tmp_path, monkeypatch):
    tray_app, _ = make_app(qapp, tmp_path, monkeypatch)
    monkeypatch.setattr(json_store, "write_json", lambda *a, **k: (_ for _ in ()).throw(OSError("디스크 오류")))
    result = tray_app.settings_manager.update({"interval_minutes": 25})
    assert not result.saved
    assert tray_app.controller.remaining_seconds == 25 * 60
