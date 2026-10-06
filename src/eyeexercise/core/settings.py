"""앱 설정 모델. 기본값, 값 검증·보정, dict 변환을 담당한다 (파일 I/O 없음)."""

from dataclasses import dataclass, field
from typing import Any

SETTINGS_VERSION = 1
SPEEDS = ("slow", "normal", "fast")

# (최솟값, 최댓값)
INTERVAL_MINUTES_RANGE = (1, 120)
SNOOZE_MINUTES_RANGE = (1, 60)
IDLE_PAUSE_MINUTES_RANGE = (1, 59)
IDLE_RESET_MINUTES_RANGE = (2, 120)
BLINK_SECONDS_RANGE = (5, 300)
DOT_FOLLOW_SECONDS_RANGE = (10, 600)


@dataclass(frozen=True)
class BlinkSettings:
    enabled: bool = True
    duration_seconds: int = 30


@dataclass(frozen=True)
class DotFollowSettings:
    enabled: bool = True
    duration_seconds: int = 60
    speed: str = "normal"


@dataclass(frozen=True)
class ExercisesSettings:
    blink: BlinkSettings = field(default_factory=BlinkSettings)
    dot_follow: DotFollowSettings = field(default_factory=DotFollowSettings)


@dataclass(frozen=True)
class CameraSettings:
    enabled: bool = False


@dataclass(frozen=True)
class Settings:
    interval_minutes: int = 20
    snooze_minutes: int = 5
    idle_pause_minutes: int = 1
    idle_reset_minutes: int = 5
    exercises: ExercisesSettings = field(default_factory=ExercisesSettings)
    show_main_window_on_start: bool = False
    camera: CameraSettings = field(default_factory=CameraSettings)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: Any, default: int, bounds: tuple[int, int]) -> int:
    """정수가 아니면(bool 포함) 기본값, 범위를 벗어나면 가까운 경계값으로 보정한다."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    low, high = bounds
    return max(low, min(high, value))


def _speed(value: Any, default: str) -> str:
    return value if value in SPEEDS else default


def settings_from_dict(data: Any) -> Settings:
    """dict에서 Settings를 만든다. 모르는 키는 무시하고, 없거나 잘못된 값은 기본값/경계값으로 채운다."""
    d = Settings()
    raw = _as_dict(data)
    raw_ex = _as_dict(raw.get("exercises"))
    raw_blink = _as_dict(raw_ex.get("blink"))
    raw_dot = _as_dict(raw_ex.get("dot_follow"))
    raw_camera = _as_dict(raw.get("camera"))

    idle_reset = _int(raw.get("idle_reset_minutes"), d.idle_reset_minutes, IDLE_RESET_MINUTES_RANGE)
    idle_pause = _int(raw.get("idle_pause_minutes"), d.idle_pause_minutes, IDLE_PAUSE_MINUTES_RANGE)
    # 누적 정지 기준은 리셋 기준보다 항상 작아야 한다.
    if idle_pause >= idle_reset:
        idle_pause = idle_reset - 1

    return Settings(
        interval_minutes=_int(raw.get("interval_minutes"), d.interval_minutes, INTERVAL_MINUTES_RANGE),
        snooze_minutes=_int(raw.get("snooze_minutes"), d.snooze_minutes, SNOOZE_MINUTES_RANGE),
        idle_pause_minutes=idle_pause,
        idle_reset_minutes=idle_reset,
        exercises=ExercisesSettings(
            blink=BlinkSettings(
                enabled=_bool(raw_blink.get("enabled"), d.exercises.blink.enabled),
                duration_seconds=_int(
                    raw_blink.get("duration_seconds"), d.exercises.blink.duration_seconds, BLINK_SECONDS_RANGE
                ),
            ),
            dot_follow=DotFollowSettings(
                enabled=_bool(raw_dot.get("enabled"), d.exercises.dot_follow.enabled),
                duration_seconds=_int(
                    raw_dot.get("duration_seconds"),
                    d.exercises.dot_follow.duration_seconds,
                    DOT_FOLLOW_SECONDS_RANGE,
                ),
                speed=_speed(raw_dot.get("speed"), d.exercises.dot_follow.speed),
            ),
        ),
        show_main_window_on_start=_bool(raw.get("show_main_window_on_start"), d.show_main_window_on_start),
        camera=CameraSettings(enabled=_bool(raw_camera.get("enabled"), d.camera.enabled)),
    )


def settings_to_dict(settings: Settings) -> dict:
    return {
        "version": SETTINGS_VERSION,
        "interval_minutes": settings.interval_minutes,
        "snooze_minutes": settings.snooze_minutes,
        "idle_pause_minutes": settings.idle_pause_minutes,
        "idle_reset_minutes": settings.idle_reset_minutes,
        "exercises": {
            "blink": {
                "enabled": settings.exercises.blink.enabled,
                "duration_seconds": settings.exercises.blink.duration_seconds,
            },
            "dot_follow": {
                "enabled": settings.exercises.dot_follow.enabled,
                "duration_seconds": settings.exercises.dot_follow.duration_seconds,
                "speed": settings.exercises.dot_follow.speed,
            },
        },
        "show_main_window_on_start": settings.show_main_window_on_start,
        "camera": {"enabled": settings.camera.enabled},
    }
