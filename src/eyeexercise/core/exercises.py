"""눈 휴식과 눈 운동의 정의와 단계 타임라인 (GUI와 시간 의존 없음).

화면은 `step_at(경과 초)`가 돌려주는 값을 그리기만 한다.

- **눈 휴식**(`LookAwayTimeline`): 20분마다. 알림 팝업 안에서 먼 곳을 20초 바라본다(카운트다운). 20초가 지나야 `done`이다.
- **눈 운동**(`exercise_timeline`): 하루 1~2회. 점 따라가기(`dot_follow_timeline`)만 한다. 준비 → 점 따라가기 → 마무리가 끝나는
  `total_seconds`에서 곧바로 `finished`와 `done`이 된다(먼 곳 바라보기는 이어지지 않는다).

(예전에 있던 눈 깜빡임 운동은 없앴다. 저장된 기록에서 휴식을 가리키는 이름 `"blink"`는 이미 쌓인 기록이 이어지도록 그대로 쓴다.)
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from eyeexercise.core.settings import ExercisesSettings

EXERCISE_REST = "blink"  # 저장된 기록에서 눈 휴식을 가리키는 이름. 예전 깜빡임 운동의 이름을 그대로 써서 기록이 이어진다
EXERCISE_DOT_FOLLOW = "dot_follow"

PREPARE_SECONDS = 3
FINISH_SECONDS = 3
LOOK_AWAY_SECONDS = 20  # 휴식에서 먼 곳을 바라보는 시간 (20-20-20 규칙)


class Phase(Enum):
    PREPARE = "prepare"
    TRACK = "track"  # 점 따라가기: 점을 눈으로 따라가는 중
    FINISH = "finish"
    LOOK_AWAY = "look_away"


MESSAGES = {
    Phase.PREPARE: "편안하게 앉아 화면을 바라보세요",
    Phase.TRACK: "",  # 점 따라가기의 문구는 패턴마다 다르다 (DotPattern.message)
    Phase.FINISH: "잘했어요",
    Phase.LOOK_AWAY: "먼 곳을 바라보세요",
}

# 소리로 하는 짧은 음성 안내. None이면 말하지 않는다.
SPOKEN = {
    Phase.PREPARE: "준비하세요",
    Phase.TRACK: None,  # 눈을 뜨고 점을 보는 운동이라 소리 없이 진행한다
    Phase.FINISH: "잘했어요",
    Phase.LOOK_AWAY: "이제 먼 곳을 바라보세요",
}


@dataclass(frozen=True)
class ExerciseStep:
    phase: Phase
    message: str
    progress: float  # 진행. 운동 동안 0→1로 차오르고, 먼 곳 바라보기 동안 1→0으로 줄어든다
    finished: bool  # 운동이 끝났다 (기록을 남길 시점)
    countdown: int | None = None  # 먼 곳 바라보기의 남은 초 (20→1). 그 외에는 None
    done: bool = False  # 모두 끝났다 (창을 닫을 시점)
    dot: tuple[float, float] | None = None  # 점 따라가기: 점의 위치 (0~1 정규화 좌표). 그 외에는 None
    pattern: int | None = None  # 점 따라가기: 지금 따라가는 경로의 번호(DOT_PATTERNS의 순서). 점을 따라가는 중이 아니면 None


def _look_away_step(t: float) -> ExerciseStep:
    message = MESSAGES[Phase.LOOK_AWAY]
    if t >= LOOK_AWAY_SECONDS:
        return ExerciseStep(Phase.LOOK_AWAY, message, 0.0, True, 0, True)
    countdown = math.ceil(LOOK_AWAY_SECONDS - t)
    return ExerciseStep(Phase.LOOK_AWAY, message, 1.0 - t / LOOK_AWAY_SECONDS, True, countdown)


# ---- 점 따라가기 ----
# 점이 화면 안을 움직이고, 사용자는 고개를 가만히 둔 채 눈으로만 따라간다.
# 좌표는 0~1로 정규화한다. (0, 0)은 왼쪽 위, (1, 1)은 오른쪽 아래이고 실제 크기는 화면이 곱한다.

_TAU = 2 * math.pi
DOT_CENTER = (0.5, 0.5)
DOT_SEGMENT_SECONDS = 9.0  # 패턴 하나를 보여 주는 목표 길이
DOT_TRANSITION_SECONDS = 1.0  # 패턴이 바뀔 때 점이 순간이동하지 않고 이어지는 시간
MIN_DOT_SEGMENT_SECONDS = 6
MIN_DOT_SECONDS = PREPARE_SECONDS + MIN_DOT_SEGMENT_SECONDS + FINISH_SECONDS
# 속도: 점이 초당 도는 횟수(한 번 = 왕복 한 번 또는 한 바퀴). normal은 한 번에 5초
DOT_SPEED_HZ = {"slow": 0.12, "normal": 0.2, "fast": 0.3}


@dataclass(frozen=True)
class DotPattern:
    key: str
    message: str
    position: Callable[[float], tuple[float, float]]  # 지금까지 돈 횟수 u → 점의 위치. 항상 0.1~0.9 안


def _horizontal(u: float) -> tuple[float, float]:
    return 0.5 + 0.4 * math.sin(_TAU * u), 0.5


def _vertical(u: float) -> tuple[float, float]:
    return 0.5, 0.5 + 0.4 * math.sin(_TAU * u)


def _diagonal_down(u: float) -> tuple[float, float]:  # 왼쪽 위 ↔ 오른쪽 아래
    s = 0.4 * math.sin(_TAU * u)
    return 0.5 + s, 0.5 + s


def _diagonal_up(u: float) -> tuple[float, float]:  # 왼쪽 아래 ↔ 오른쪽 위
    s = 0.4 * math.sin(_TAU * u)
    return 0.5 + s, 0.5 - s


def _circle(u: float) -> tuple[float, float]:
    return 0.5 + 0.38 * math.cos(_TAU * u), 0.5 + 0.38 * math.sin(_TAU * u)


def _figure_eight(u: float) -> tuple[float, float]:
    return 0.5 + 0.4 * math.sin(_TAU * u), 0.5 + 0.3 * math.sin(2 * _TAU * u)


DOT_PATTERNS = (
    DotPattern("horizontal", "점을 좌우로 따라가세요", _horizontal),
    DotPattern("vertical", "점을 위아래로 따라가세요", _vertical),
    DotPattern("diagonal_down", "점을 대각선으로 따라가세요", _diagonal_down),
    DotPattern("diagonal_up", "점을 반대 대각선으로 따라가세요", _diagonal_up),
    DotPattern("circle", "점이 그리는 원을 따라가세요", _circle),
    DotPattern("figure_eight", "점이 그리는 8자를 따라가세요", _figure_eight),
)

DOT_PREPARE_MESSAGE = "고개는 가만히, 눈으로만 점을 따라가세요"


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _lerp(a: tuple[float, float], b: tuple[float, float], w: float) -> tuple[float, float]:
    return a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w


@dataclass(frozen=True)
class DotFollowTimeline:
    exercise: ClassVar[str] = EXERCISE_DOT_FOLLOW
    total_seconds: int
    speed_hz: float
    segments: int  # 보여 줄 패턴 수. 패턴이 6개보다 많이 필요하면 처음부터 다시 돈다

    @property
    def _body_end(self) -> float:
        return self.total_seconds - FINISH_SECONDS

    @property
    def _segment_seconds(self) -> float:
        return (self._body_end - PREPARE_SECONDS) / self.segments

    def pattern_at(self, index: int) -> DotPattern:
        return DOT_PATTERNS[index % len(DOT_PATTERNS)]

    def _raw(self, index: int, t_in_segment: float) -> tuple[float, float]:
        return self.pattern_at(index).position(self.speed_hz * t_in_segment)

    def _segment_end(self, index: int) -> tuple[float, float]:
        return self._raw(index, self._segment_seconds)

    def step_at(self, elapsed: float) -> ExerciseStep:
        total = float(self.total_seconds)
        elapsed = max(0.0, elapsed)
        progress = min(1.0, elapsed / total)
        if elapsed >= total:  # 점 따라가기 뒤에는 먼 곳 바라보기를 하지 않는다. 마무리가 끝나면 바로 끝난다
            return ExerciseStep(Phase.FINISH, MESSAGES[Phase.FINISH], 1.0, True, done=True, dot=DOT_CENTER)
        if elapsed < PREPARE_SECONDS:
            return ExerciseStep(Phase.PREPARE, DOT_PREPARE_MESSAGE, progress, False, dot=DOT_CENTER)
        if elapsed >= self._body_end:
            # 마지막 패턴이 끝난 자리에서 가운데로 부드럽게 돌아온다
            w = _smoothstep((elapsed - self._body_end) / DOT_TRANSITION_SECONDS)
            dot = _lerp(self._segment_end(self.segments - 1), DOT_CENTER, w)
            return ExerciseStep(Phase.FINISH, MESSAGES[Phase.FINISH], progress, False, dot=dot)

        seg = self._segment_seconds
        body_t = elapsed - PREPARE_SECONDS
        index = min(int(body_t // seg), self.segments - 1)
        t = body_t - index * seg
        # 패턴이 바뀐 직후에는 앞 패턴이 끝난 자리에서 새 경로로 부드럽게 갈아탄다 (순간이동 없음)
        start = DOT_CENTER if index == 0 else self._segment_end(index - 1)
        dot = _lerp(start, self._raw(index, t), _smoothstep(t / DOT_TRANSITION_SECONDS))
        return ExerciseStep(
            Phase.TRACK, self.pattern_at(index).message, progress, False, dot=dot, pattern=index % len(DOT_PATTERNS)
        )


def dot_follow_timeline(duration_seconds: int, speed: str = "normal") -> DotFollowTimeline:
    """설정된 총 시간과 속도로 타임라인을 만든다.

    패턴 하나를 약 9초씩 보여 주므로 기본 60초에서는 6가지 패턴이 한 번씩 나온다.
    총 시간이 12초보다 짧게 설정돼도 12초(패턴 1개) 아래로는 줄지 않는다.
    """
    total = max(int(duration_seconds), MIN_DOT_SECONDS)
    body = total - PREPARE_SECONDS - FINISH_SECONDS
    segments = max(1, round(body / DOT_SEGMENT_SECONDS))
    return DotFollowTimeline(total_seconds=total, speed_hz=DOT_SPEED_HZ.get(speed, DOT_SPEED_HZ["normal"]), segments=segments)


# ---- 눈 휴식: 먼 곳 바라보기 20초 ----


@dataclass(frozen=True)
class LookAwayTimeline:
    """눈 휴식. 알림 팝업 안에서 먼 곳을 20초 바라본다. 본 활동의 길이가 0초이고 20초가 지나야 `done`이다."""

    exercise: ClassVar[str] = EXERCISE_REST  # 기록은 '휴식'으로 남는다
    total_seconds: int = 0

    def step_at(self, elapsed: float) -> ExerciseStep:
        return _look_away_step(max(0.0, elapsed))


# ---- 눈 운동 선택 ----


def exercise_timeline(settings: ExercisesSettings) -> DotFollowTimeline | None:
    """눈 운동(점 따라가기)의 타임라인. 꺼져 있으면 None."""
    if not settings.dot_follow.enabled:
        return None
    return dot_follow_timeline(settings.dot_follow.duration_seconds, settings.dot_follow.speed)


# ---- 길이 프리셋 (설정 화면에서 "짧게/보통/길게"로 고른다) ----


@dataclass(frozen=True)
class LengthPreset:
    key: str
    label: str
    dot_seconds: int  # 운동(점 따라가기) 총 시간(초)


LENGTH_PRESETS = (
    LengthPreset("short", "짧게", 30),
    LengthPreset("normal", "보통", 60),  # 기본값과 같다
    LengthPreset("long", "길게", 90),
)


def preset_changes(key: str) -> dict[str, int]:
    """프리셋을 고르면 바꿀 설정 경로와 값. 알 수 없는 키는 KeyError."""
    for preset in LENGTH_PRESETS:
        if preset.key == key:
            return {"exercises.dot_follow.duration_seconds": preset.dot_seconds}
    raise KeyError(key)


def current_preset(settings: ExercisesSettings) -> str | None:
    """지금 설정이 어느 프리셋과 같은지. 고급 설정에서 따로 정했다면 None."""
    for preset in LENGTH_PRESETS:
        if settings.dot_follow.duration_seconds == preset.dot_seconds:
            return preset.key
    return None
