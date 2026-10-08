from fakes import FakeAutoStart
from PySide6.QtWidgets import QLabel

from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.ui.settings_page import AUTOSTART_FAILED_MESSAGE, SettingsPage


def make_page(qapp, autostart=None):
    saved = []
    page = SettingsPage(SettingsManager(Settings(), save=saved.append), autostart=autostart)
    page.resize(900, 1200)
    page.show()
    qapp.processEvents()
    return page, saved


def status_text(page):
    label = [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "saveStatus"][0]
    return label.text() if label.isVisible() else ""


def test_꺼져_있으면_스위치도_꺼져_있다(qapp):
    page, _ = make_page(qapp, FakeAutoStart(enabled=False))
    assert page.autostart_switch.isEnabled() and not page.autostart_switch.isChecked()


def test_이미_등록돼_있으면_스위치가_켜져_있다(qapp):
    page, _ = make_page(qapp, FakeAutoStart(enabled=True))
    assert page.autostart_switch.isChecked()


def test_스위치를_켜면_등록하고_끄면_지운다(qapp):
    auto = FakeAutoStart()
    page, _ = make_page(qapp, auto)
    page.autostart_switch.click()
    assert auto.enabled is True and page.autostart_switch.isChecked()
    page.autostart_switch.click()
    assert auto.enabled is False and not page.autostart_switch.isChecked()
    assert auto.calls == [True, False]


def test_등록에_실패하면_스위치를_되돌리고_안내한다(qapp):
    auto = FakeAutoStart(succeeds=False)
    page, _ = make_page(qapp, auto)
    page.autostart_switch.click()
    assert not page.autostart_switch.isChecked()
    assert status_text(page) == AUTOSTART_FAILED_MESSAGE


def test_해제에_실패하면_켜진_채로_되돌린다(qapp):
    auto = FakeAutoStart(enabled=True, succeeds=False)
    page, _ = make_page(qapp, auto)
    page.autostart_switch.click()
    assert page.autostart_switch.isChecked()
    assert status_text(page) == AUTOSTART_FAILED_MESSAGE


def test_쓸_수_없으면_스위치를_비활성으로_보인다(qapp):
    auto = FakeAutoStart(available=False)
    page, _ = make_page(qapp, auto)
    assert not page.autostart_switch.isEnabled()
    assert auto.calls == []


def test_자동_실행_객체가_없어도_화면이_뜬다(qapp):
    page, _ = make_page(qapp, None)
    assert not page.autostart_switch.isEnabled()


def test_자동_실행은_설정_파일에_저장하지_않는다(qapp):
    page, saved = make_page(qapp, FakeAutoStart())
    page.autostart_switch.click()
    assert saved == []
    assert "autostart" not in page.paths  # 설정 항목이 아니다


def test_설정_초기화는_자동_실행_등록을_건드리지_않는다(qapp):
    auto = FakeAutoStart(enabled=True)
    page, _ = make_page(qapp, auto)
    page.reset_button.click()  # 첫 클릭은 확인을 묻는다
    page.reset_button.click()
    assert auto.enabled is True and auto.calls == []
    assert page.autostart_switch.isChecked()


def test_앱을_조립하면_등록_경로를_갱신하고_설정_화면에_연결한다(qapp, tmp_path, monkeypatch):
    from eyeexercise import app as app_module
    from eyeexercise.storage import json_store, paths

    monkeypatch.setenv("APPDATA", str(tmp_path))
    auto = FakeAutoStart(enabled=True)
    settings = json_store.load_settings(paths.settings_path())
    tray_app = app_module.TrayApp(qapp, settings, autostart=auto)
    assert auto.refreshed == 1
    switch = tray_app.main_window.settings_page.autostart_switch
    assert switch.isEnabled() and switch.isChecked()
