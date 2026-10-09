"""데이터 파일 위치. 기본은 %APPDATA%\\Swieom (처음 앱 이름 '쉬엄'의 영문 표기. 이름을 바꿔도 이미 쌓인 기록이 이어지도록 그대로 둔다)."""

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR_NAME = "Swieom"
LEGACY_DIR_NAME = "EyeExercise"  # 이름을 바꾸기 전에 쓰던 폴더


def _base_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"


def app_data_dir() -> Path:
    return _base_dir() / APP_DIR_NAME


def migrate_legacy_data() -> bool:
    """옛 이름(EyeExercise)의 데이터 폴더가 있고 새 폴더는 아직 없으면 기록을 새 폴더로 옮긴다. 옮겼으면 True.

    이름만 바꿨을 뿐인데 기록(운동·스크린 타임·시력)이 사라진 것처럼 보이지 않게 한다.
    폴더 이름 바꾸기가 안 되면(다른 프로그램이 파일을 쥐고 있을 때) 복사로 대신하고, 그것도 안 되면 옛 폴더를 그대로 둔다.
    """
    new, old = app_data_dir(), _base_dir() / LEGACY_DIR_NAME
    if new.exists() or not old.is_dir():
        return False
    try:
        old.rename(new)
        return True
    except OSError:
        log.warning("옛 데이터 폴더 이름을 바꾸지 못해 복사합니다.", exc_info=True)
    try:
        shutil.copytree(old, new)
        return True
    except OSError:
        shutil.rmtree(new, ignore_errors=True)  # 반쯤 복사된 폴더가 남지 않게 한다
        log.warning("옛 데이터 폴더를 옮기지 못했습니다. 새 폴더로 시작합니다.", exc_info=True)
        return False


def settings_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "settings.json"


def history_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "history.json"


def vision_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "vision.json"


def usage_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "usage.json"
