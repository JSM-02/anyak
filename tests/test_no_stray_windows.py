"""화면을 만들거나 갱신하는 동안 독립된 작은 창이 잠깐 뜨는 일이 없어야 한다.

부모가 없는 위젯에 setVisible(True)를 부르면 독립된 창으로 뜬다. 레이아웃에 붙이기 전에 보이게 만들면
실제 화면에서 작은 창이 깜빡였다 사라진다. offscreen 테스트에서는 눈에 보이지 않으므로 Show 이벤트로 잡는다.
"""

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.stats import Period
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui.exercise_window import ExerciseWindow
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.records_tab import Mode, RecordsTab
from eyeexercise.ui.reminder_popup import ReminderPopup
from eyeexercise.ui.settings_page import SettingsPage


class ShowSpy(QObject):
    """독립된 창(부모 없는 위젯)이 Show 되는 것을 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.windows: list[str] = []

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            text = obj.text() if hasattr(obj, "text") else ""
            self.windows.append(f"{type(obj).__name__}({obj.objectName()!r}, {text!r})")
        return False


@pytest.fixture
def spy(qapp):
    spy = ShowSpy()
    qapp.installEventFilter(spy)
    yield spy
    qapp.removeEventFilter(spy)


def test_설정_화면을_만드는_동안_작은_창이_뜨지_않는다(qapp, spy):
    SettingsPage(SettingsManager(Settings()))
    qapp.processEvents()
    assert spy.windows == []


def test_설정을_바꾸고_화면이_다시_채워지는_동안에도_작은_창이_뜨지_않는다(qapp, spy):
    manager = SettingsManager(Settings())
    page = SettingsPage(manager)
    manager.update({"exercises.dot_follow.enabled": False, "interval_minutes": 30})
    manager.update({"exercises.dot_follow.enabled": True})
    qapp.processEvents()
    assert spy.windows == []


def test_기록_탭을_만들고_넘겨_보는_동안_작은_창이_뜨지_않는다(qapp, spy):
    from datetime import datetime, timedelta, timezone

    kst = timezone(timedelta(hours=9))
    now = datetime(2026, 10, 7, 14, 30, tzinfo=kst)
    events = [HistoryEvent(now - timedelta(hours=h), "completed", "blink", 66) for h in range(1, 15)]
    usage = UsageLog()
    usage.add(now, 600)
    tab = RecordsTab(lambda: events, now=lambda: now, tz=kst, usage_provider=lambda: usage)
    for mode in (Mode.SCREEN_TIME, Mode.REST):
        tab.set_mode(mode)
        for period in (Period.DAY, Period.MONTH, Period.WEEK):
            tab.set_period(period)
            tab.go(-1)
    tab._more.click()
    tab.refresh()
    qapp.processEvents()
    assert spy.windows == []


def test_메인_창을_만드는_동안_작은_창이_뜨지_않는다(qapp, spy):
    window = MainWindow(History(), settings_manager=SettingsManager(Settings()))
    for row in range(window.sidebar.count()):  # 메뉴를 하나씩 눌러 본다 (창을 띄우지는 않는다)
        window.sidebar.set_current(row)
    qapp.processEvents()
    assert spy.windows == []


def test_알림_팝업과_운동_창을_만드는_동안_작은_창이_뜨지_않는다(qapp, spy):
    popup = ReminderPopup(5)
    popup.set_snooze_minutes(10)
    ExerciseWindow(None)
    qapp.processEvents()
    assert spy.windows == []


def test_앱_전체를_조립하는_동안_작은_창이_뜨지_않는다(qapp, spy, tmp_path, monkeypatch):
    from eyeexercise import app as app_module
    from eyeexercise.storage import json_store, paths

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(app_module, "create_speaker", lambda enabled: None)
    settings = json_store.load_settings(paths.settings_path())
    tray_app = app_module.TrayApp(qapp, settings)
    tray_app.settings_manager.update({"snooze_minutes": 9, "sound.enabled": False})
    qapp.processEvents()
    assert spy.windows == []


def test_감시_장치_자체가_독립된_창을_잡아낸다(qapp, spy):
    """이 검사가 실제로 동작하는지 확인한다: 부모 없는 위젯을 보이게 만들면 기록돼야 한다."""
    from PySide6.QtWidgets import QLabel

    stray = QLabel("깜빡이는 창")
    stray.setVisible(True)
    qapp.processEvents()
    stray.hide()
    assert spy.windows == ["QLabel('', '깜빡이는 창')"]


def test_고급_설정을_펼치고_접는_동안에도_작은_창이_뜨지_않는다(qapp, spy):
    page = SettingsPage(SettingsManager(Settings()))
    for _ in range(3):
        page._advanced_toggle.click()
    page.preset_control.buttons()[0].click()
    page.control("exercises.dot_follow.duration_seconds").setValue(7)
    qapp.processEvents()
    assert spy.windows == []


def test_알림_팝업이_나타나는_동안에도_작은_창이_뜨지_않고_끝에는_선명해진다(qapp, spy):
    from PySide6.QtCore import QEventLoop, QTimer

    popup = ReminderPopup(5)
    popup.show_at_corner()
    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)
    loop.exec()
    popup.hide()
    assert spy.windows == ["ReminderPopup('popup', '')"]  # 팝업 하나만 (다른 독립 창은 없다)
