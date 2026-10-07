"""JSON 파일 읽기/쓰기. 원자적 저장, 손상된 파일은 백업 후 기본값으로 복구한다."""

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from eyeexercise.core.history import HistoryEvent, history_from_dict, history_to_dict
from eyeexercise.core.settings import Settings, settings_from_dict, settings_to_dict
from eyeexercise.core.usage import UsageLog, usage_from_dict, usage_to_dict
from eyeexercise.core.vision import VisionRecord, vision_from_dict, vision_to_dict


def write_json(path: Path, data: dict) -> None:
    """임시 파일에 먼저 쓴 뒤 교체한다. 도중에 실패해도 기존 파일은 온전하다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json(path: Path, now: Callable[[], datetime] = datetime.now) -> dict | None:
    """파일이 없거나 손상되었으면 None을 돌려준다.

    손상된 파일은 `<이름>.corrupt-<날짜시각>.json`으로 옮겨 보존한다.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # ValueError: JSONDecodeError와 UnicodeDecodeError를 모두 포함
        _backup_corrupt(path, now())
        return None
    if not isinstance(data, dict):
        _backup_corrupt(path, now())
        return None
    return data


def _backup_corrupt(path: Path, when: datetime) -> None:
    backup = path.with_name(f"{path.stem}.corrupt-{when:%Y%m%d-%H%M%S}{path.suffix}")
    try:
        os.replace(path, backup)
    except OSError:
        pass  # 백업에 실패해도 기본값으로 계속 동작한다


def load_settings(path: Path, now: Callable[[], datetime] = datetime.now) -> Settings:
    return settings_from_dict(read_json(path, now))


def save_settings(path: Path, settings: Settings) -> None:
    write_json(path, settings_to_dict(settings))


def load_history(path: Path, now: Callable[[], datetime] = datetime.now) -> list[HistoryEvent]:
    return history_from_dict(read_json(path, now))


def save_history(path: Path, events: list[HistoryEvent]) -> None:
    write_json(path, history_to_dict(events))


def load_vision(path: Path, now: Callable[[], datetime] = datetime.now) -> list[VisionRecord]:
    return vision_from_dict(read_json(path, now))


def save_vision(path: Path, records: list[VisionRecord]) -> None:
    write_json(path, vision_to_dict(records))


def load_usage(path: Path, now: Callable[[], datetime] = datetime.now) -> UsageLog:
    return usage_from_dict(read_json(path, now))


def save_usage(path: Path, usage: UsageLog) -> None:
    write_json(path, usage_to_dict(usage))
