import os

import eyeexercise
from eyeexercise.core.history import History
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.storage import paths


def test_앱_이름은_쉬엄이다():
    assert eyeexercise.APP_NAME == "쉬엄"


def test_창_제목과_사이드바_이름이_앱_이름을_쓴다(qapp):
    from PySide6.QtWidgets import QLabel

    window = MainWindow(History())
    assert window.windowTitle() == eyeexercise.APP_NAME
    assert any(label.text() == eyeexercise.APP_NAME for label in window.sidebar.findChildren(QLabel))


def test_트레이_툴팁에_앱_이름이_나온다(qapp):
    from fakes import FakeClock, FakeIdle

    from eyeexercise.core.scheduler import ReminderScheduler
    from eyeexercise.core.settings import Settings
    from eyeexercise.ui.controller import Controller
    from eyeexercise.ui.icons import app_icon
    from eyeexercise.ui.tray import TrayIcon

    clock = FakeClock()
    tray = TrayIcon(Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now), app_icon())
    assert tray._tray.toolTip().startswith(eyeexercise.APP_NAME)


def test_버전_출력에_앱_이름이_나온다(capsys, monkeypatch):
    import sys

    from eyeexercise.__main__ import main

    monkeypatch.setattr(sys, "argv", ["eyeexercise", "--version"])
    assert main() == 0
    assert capsys.readouterr().out.startswith("쉬엄 ")


# ---- 데이터 폴더 이름이 바뀌어도 기록이 남는다 ----


def test_옛_이름의_폴더가_있으면_새_이름으로_옮긴다(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "EyeExercise"
    old.mkdir()
    (old / "history.json").write_text('{"version": 1, "events": []}', encoding="utf-8")
    (old / "settings.json.corrupt-2026.json").write_text("x", encoding="utf-8")

    assert paths.migrate_legacy_data() is True
    assert not old.exists()
    assert (paths.app_data_dir() / "history.json").read_text(encoding="utf-8") == '{"version": 1, "events": []}'
    assert (paths.app_data_dir() / "settings.json.corrupt-2026.json").exists()  # 백업 파일도 같이 간다


def test_새_폴더가_이미_있으면_옛_폴더를_건드리지_않는다(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "EyeExercise").mkdir()
    (tmp_path / "EyeExercise" / "history.json").write_text("old", encoding="utf-8")
    (tmp_path / "Swieom").mkdir()
    (tmp_path / "Swieom" / "history.json").write_text("new", encoding="utf-8")

    assert paths.migrate_legacy_data() is False
    assert (tmp_path / "Swieom" / "history.json").read_text(encoding="utf-8") == "new"  # 새 기록을 덮어쓰지 않는다
    assert (tmp_path / "EyeExercise" / "history.json").read_text(encoding="utf-8") == "old"


def test_옛_폴더가_없으면_아무것도_하지_않는다(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.migrate_legacy_data() is False
    assert not paths.app_data_dir().exists()


def test_이름_바꾸기가_안_되면_복사로_옮긴다(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "EyeExercise"
    old.mkdir()
    (old / "usage.json").write_text("data", encoding="utf-8")

    def locked(self, target):
        raise PermissionError("다른 프로그램이 쓰는 중")

    monkeypatch.setattr(Path, "rename", locked)
    assert paths.migrate_legacy_data() is True
    assert (paths.app_data_dir() / "usage.json").read_text(encoding="utf-8") == "data"
    assert (old / "usage.json").exists()  # 복사했으니 옛 폴더는 그대로 남는다


def test_복사도_안_되면_새_폴더를_남기지_않고_실패로_알린다(monkeypatch, tmp_path):
    import shutil
    from pathlib import Path

    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "EyeExercise").mkdir()
    (tmp_path / "EyeExercise" / "usage.json").write_text("data", encoding="utf-8")
    monkeypatch.setattr(Path, "rename", lambda self, target: (_ for _ in ()).throw(PermissionError()))

    def fail(src, dst):
        os.makedirs(dst)  # 반쯤 복사된 폴더를 흉내 낸다
        raise OSError("디스크가 가득 찼다")

    monkeypatch.setattr(shutil, "copytree", fail)
    assert paths.migrate_legacy_data() is False
    assert not paths.app_data_dir().exists()
