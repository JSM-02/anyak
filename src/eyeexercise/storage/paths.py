"""데이터 파일 위치. 기본은 %APPDATA%\\EyeExercise."""

import os
from pathlib import Path

APP_DIR_NAME = "EyeExercise"


def app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME


def settings_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "settings.json"


def history_path(base_dir: Path | None = None) -> Path:
    return (base_dir or app_data_dir()) / "history.json"
