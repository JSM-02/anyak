"""눈 휴식과 눈 운동의 정의와 단계 타임라인 (GUI와 시간 의존 없음).

화면은 `step_at(경과 초)`가 돌려주는 값을 그리기만 한다.

- **눈 휴식**(`rest_timeline`): 20분마다. 깜빡임(`blink_timeline`)이 끝나면 곧바로 먼 곳 바라보기(20초 카운트다운)가
  이어진다. 깜빡임을 끄면 먼 곳 바라보기만 한다(`LookAwayTimeline`).
- **눈 운동**(`exercise_timeline`): 하루 1~2회. 점 따라가기(`dot_follow_timeline`) 뒤에도 먼 곳 바라보기가 이어진다.

타임라인은 모두 본 활동(준비 → 본 활동 → 마무리, 총 `total_seconds`) 뒤에 먼 곳 바라보기가 오고,
그것까지 끝나면 `done`이 된다.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from eyeexercise.core.settings import ExercisesSettings

EXERCISE_BLINK = "blink"
EXERCISE_DOT_FOLLOW = "dot_follow"

PREPARE_SECONDS = 3
FINISH_SECONDS = 3
LOOK_AWAY_SECONDS = 20  # 운동 뒤에 먼 곳을 바라보는 시간 (20-20-20 규칙)

# 깜빡임 운동 구성(초). 준비 → (감기 → 유지 → 뜨기 → 쉬기) 반복 → 마무리
# 심호흡처럼 천천히: 눈을 천천히 감고(2초) 잠시 머문 뒤(1초) 천천히 뜨고(2초) 숨을 돌린다(1초).
# 낮은 종(감기 시작)과 높은 종(뜨기 시작) 사이는 3초이고, 한 사이클은 6초다.
CLOSE_SECONDS = 2
HOLD_SECONDS = 1
OPEN_SECONDS = 2
REST_SECONDS = 1
CYCLE_SECONDS = CLOSE_SECONDS + HOLD_SECONDS + OPEN_SECONDS + REST_SECONDS
MIN_BLINK_SECONDS = PREPARE_SECONDS + CYCLE_SECONDS + FINISH_SECONDS  # 사이클 1회


class Phase(Enum):
    PREPARE = "prepare"
    CLOSE = "close"
    HOLD = "hold"
    OPEN = "open"
    REST = "rest"
    TRACK = "track"  # 점 따라가기: 점을 눈으로 따라가는 중
    FINISH = "finish"
    LOOK_AWAY = "look_away"


MESSAGES = {
    Phase.PREPARE: "편안하게 앉아 화면을 바라보세요",
    Phase.CLOSE: "천천히 눈을 감으세요",
    Phase.HOLD: "감은 채 잠시 머무세요",
    Phase.OPEN: "천천히 부드럽게 뜨세요",
    Phase.REST: "",  # 쉬는 동안에는 아무 문구도 보이지 않는다
    Phase.TRACK: "",  # 점 따라가기의 문구는 패턴마다 다르다 (DotPattern.message)
    Phase.FINISH: "잘했어요",
    Phase.LOOK_AWAY: "먼 곳을 바라보세요",
}

# 눈을 감고 있어도 들을 수 있는 짧은 음성 안내. None이면 말하지 않는다.
SPOKEN = {
    Phase.PREPARE: "준비하세요",
    Phase.CLOSE: "눈을 감으세요",
    Phase.HOLD: None,
    Phase.OPEN: "눈을 뜨세요",
    Phase.REST: None,
    Phase.TRACK: None,  # 눈을 뜨고 점을 보는 운동이라 소리 없이 진행한다
    Phase.FINISH: "잘했어요",
    Phase.LOOK_AWAY: "이제 먼 곳을 바라보세요",
}


@dataclass(frozen=True)
class ExerciseStep:
    phase: Phase
    message: str
    eye_openness: float | None  # 깜빡임: 1.0 = 활짝 뜸, 0.0 = 완전히 감음 (애니메이션용). 점 따라가기는 None
    progress: float  # 진행 막대. 운동 동안 0→1로 차오르고, 먼 곳 바라보기 동안 1→0으로 줄어든다
    finished: bool  # 운동이 끝났다 (기록을 남길 시점)
    countdown: int | None = None  # 먼 곳 바라보기의 남은 초 (20→1). 그 외에는 None
    done: bool = False  # 먼 곳 바라보기까지 모두 끝났다 (창을 닫을 시점)
    dot: tuple[float, float] | None = None  # 점 따라가기: 점의 위치 (0~1 정규화 좌표). 그 외에는 None


def _look_away_step(t: float, eye_openness: float | None) -> ExerciseStep:
    message = MESSAGES[Phase.LOOK_AWAY]
    if t >= LOOK_AWAY_SECONDS:
        return ExerciseStep(Phase.LOOK_AWAY, message, eye_openness, 0.0, True, 0, True)
    countdown = math.ceil(LOOK_AWAY_SECONDS - t)
    return ExerciseStep(Phase.LOOK_AWAY, message, eye_openness, 1.0 - t / LOOK_AWAY_SECONDS, True, countdown)


# ---- 깜빡임 운동 ----


@dataclass(frozen=True)
class BlinkTimeline:
    exercise: ClassVar[str] = EXERCISE_BLINK
    total_seconds: int
    cycles: int

    def step_at(self, elapsed: float) -> ExerciseStep:
        total = float(self.total_seconds)
        elapsed = max(0.0, elapsed)
        progress = min(1.0, elapsed / total)
        if elapsed >= total:
            return _look_away_step(elapsed - total, 1.0)
        if elapsed < PREPARE_SECONDS:
            return self._step(Phase.PREPARE, 1.0, progress)

        finish_start = total - FINISH_SECONDS
        if elapsed >= finish_start:
            return self._step(Phase.FINISH, 1.0, progress)

        # 남는 시간은 마지막 '쉬기'에 붙는다. 그래서 마지막 사이클만 길 수 있다.
        t = elapsed - PREPARE_SECONDS
        index = min(int(t // CYCLE_SECONDS), self.cycles - 1)
        t -= index * CYCLE_SECONDS
        if t < CLOSE_SECONDS:
            return self._step(Phase.CLOSE, 1.0 - t / CLOSE_SECONDS, progress)
        t -= CLOSE_SECONDS
        if t < HOLD_SECONDS:
            return self._step(Phase.HOLD, 0.0, progress)
        t -= HOLD_SECONDS
        if t < OPEN_SECONDS:
            return self._step(Phase.OPEN, t / OPEN_SECONDS, progress)
        return self._step(Phase.REST, 1.0, progress)

    @staticmethod
    def _step(phase: Phase, openness: float, progress: float) -> ExerciseStep:
        return ExerciseStep(phase, MESSAGES[phase], openness, progress, False)


def blink_timeline(duration_seconds: int) -> BlinkTimeline:
    """설정된 총 시간으로 타임라인을 만든다.

    사이클 수는 (총 시간 - 준비 - 마무리) // 6초이고 최소 1회다. 남는 시간은 마지막 '쉬기'가 흡수한다.
    그래서 총 시간이 사이클 1회(12초)보다 짧게 설정돼도 12초 아래로는 줄지 않는다.
    """
    total = max(int(duration_seconds), MIN_BLINK_SECONDS)
    cycles = max(1, (total - PREPARE_SECONDS - FINISH_SECONDS) // CYCLE_SECONDS)
    return BlinkTimeline(total_seconds=total, cycles=cycles)


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
        if elapsed >= total:
            return _look_away_step(elapsed - total, None)
        if elapsed < PREPARE_SECONDS:
            return ExerciseStep(Phase.PREPARE, DOT_PREPARE_MESSAGE, None, progress, False, dot=DOT_CENTER)
        if elapsed >= self._body_end:
            # 마지막 패턴이 끝난 자리에서 가운데로 부드럽게 돌아온다
            w = _smoothstep((elapsed - self._body_end) / DOT_TRANSITION_SECONDS)
            dot = _lerp(self._segment_end(self.segments - 1), DOT_CENTER, w)
            return ExerciseStep(Phase.FINISH, MESSAGES[Phase.FINISH], None, progress, False, dot=dot)

        seg = self._segment_seconds
        body_t = elapsed - PREPARE_SECONDS
        index = min(int(body_t // seg), self.segments - 1)
        t = body_t - index * seg
        # 패턴이 바뀐 직후에는 앞 패턴이 끝난 자리에서 새 경로로 부드럽게 갈아탄다 (순간이동 없음)
        start = DOT_CENTER if index == 0 else self._segment_end(index - 1)
        dot = _lerp(start, self._raw(index, t), _smoothstep(t / DOT_TRANSITION_SECONDS))
        return ExerciseStep(Phase.TRACK, self.pattern_at(index).message, None, progress, False, dot=dot)


def dot_follow_timeline(duration_seconds: int, speed: str = "normal") -> DotFollowTimeline:
    """설정된 총 시간과 속도로 타임라인을 만든다.

    패턴 하나를 약 9초씩 보여 주므로 기본 60초에서는 6가지 패턴이 한 번씩 나온다.
    총 시간이 12초보다 짧게 설정돼도 12초(패턴 1개) 아래로는 줄지 않는다.
    """
    total = max(int(duration_seconds), MIN_DOT_SECONDS)
    body = total - PREPARE_SECONDS - FINISH_SECONDS
    segments = max(1, round(body / DOT_SEGMENT_SECONDS))
    return DotFollowTimeline(total_seconds=total, speed_hz=DOT_SPEED_HZ.get(speed, DOT_SPEED_HZ["normal"]), segments=segments)


# ---- 먼 곳 바라보기만 하는 휴식 ----


@dataclass(frozen=True)
class LookAwayTimeline:
    """깜빡임 없이 먼 곳 바라보기(20초)만 하는 휴식. 본 활동의 길이가 0초다."""

    exercise: ClassVar[str] = EXERCISE_BLINK  # 기록은 깜빡임과 같은 '휴식'으로 남는다
    total_seconds: int = 0

    def step_at(self, elapsed: float) -> ExerciseStep:
        return _look_away_step(max(0.0, elapsed), None)


# ---- 휴식·운동 선택 ----


def rest_timeline(settings: ExercisesSettings) -> BlinkTimeline | LookAwayTimeline:
    """눈 휴식의 타임라인. 깜빡임이 켜져 있으면 깜빡임 + 먼 곳 바라보기, 꺼져 있으면 먼 곳 바라보기만."""
    if settings.blink.enabled:
        return blink_timeline(settings.blink.duration_seconds)
    return LookAwayTimeline()


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
    blink_cycles: int  # 휴식의 깜빡임 사이클(회) 수
    dot_seconds: int  # 운동(점 따라가기) 총 시간(초)


LENGTH_PRESETS = (
    LengthPreset("short", "짧게", 3, 30),
    LengthPreset("normal", "보통", 5, 60),  # 기본값과 같다: 휴식의 깜빡임 5회(36초) + 점 따라가기 1분
    LengthPreset("long", "길게", 10, 90),
)


def blink_seconds_for_cycles(cycles: int) -> int:
    """깜빡임 사이클 수에 맞는 설정 시간(초). 준비·마무리가 더해진다. 사용자는 '몇 회'로 생각하고 초는 몰라도 된다."""
    return PREPARE_SECONDS + FINISH_SECONDS + max(1, cycles) * CYCLE_SECONDS


def blink_cycles_for_seconds(duration_seconds: int) -> int:
    """설정된 시간(초)이 몇 사이클인지. 사이클 수로 나누어떨어지지 않으면 남는 시간은 마지막 쉬기가 흡수한다."""
    return blink_timeline(duration_seconds).cycles


def preset_changes(key: str) -> dict[str, int]:
    """프리셋을 고르면 바꿀 설정 경로와 값. 알 수 없는 키는 KeyError."""
    for preset in LENGTH_PRESETS:
        if preset.key == key:
            return {
                "exercises.blink.duration_seconds": blink_seconds_for_cycles(preset.blink_cycles),
                "exercises.dot_follow.duration_seconds": preset.dot_seconds,
            }
    raise KeyError(key)


def current_preset(settings: ExercisesSettings) -> str | None:
    """지금 설정이 어느 프리셋과 같은지. 고급 설정에서 따로 정했다면 None."""
    for preset in LENGTH_PRESETS:
        if (
            settings.blink.duration_seconds == blink_seconds_for_cycles(preset.blink_cycles)
            and settings.dot_follow.duration_seconds == preset.dot_seconds
        ):
            return preset.key
    return None
