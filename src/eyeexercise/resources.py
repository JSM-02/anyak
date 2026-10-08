"""앱에 묶어 배포하는 파일(효과음 등)의 위치. 소스로 실행할 때와 exe로 묶었을 때를 모두 다룬다."""

import sys
from pathlib import Path


def assets_dir() -> Path:
    """`assets` 폴더. exe(PyInstaller)에서는 묶인 파일이 풀리는 위치, 소스에서는 저장소 루트의 `assets`."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        return (Path(base) if base else Path(sys.executable).resolve().parent) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"
