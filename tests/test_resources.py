import sys
from pathlib import Path

from eyeexercise import resources


def test_소스로_실행하면_저장소의_assets를_가리킨다():
    root = resources.assets_dir().parent
    assert resources.assets_dir().name == "assets"
    assert (root / "pyproject.toml").is_file()
    assert (resources.assets_dir() / "sounds" / "alert.wav").is_file()


def test_exe로_묶이면_압축_해제_위치의_assets를_가리킨다(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resources.assets_dir() == tmp_path / "assets"


def test_exe인데_MEIPASS가_없으면_실행_파일_옆의_assets를_쓴다(monkeypatch, tmp_path):
    # onedir 빌드: PyInstaller 6은 _MEIPASS를 `_internal` 폴더로 주지만, 없을 때도 죽지 않게 한다.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Swieom.exe"))
    assert resources.assets_dir() == Path(tmp_path) / "assets"
