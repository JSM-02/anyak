"""운동 정의와 단계 타임라인 (GUI와 시간 의존 없음).

화면은 `step_at(경과 초)`가 돌려주는 값을 그리기만 한다.

흐름: 깜빡임 운동(준비 → 사이클 반복 → 마무리, 총 `total_seconds`)이 끝나면 곧바로
먼 곳 바라보기(20초 카운트다운)가 이어지고, 그것까지 끝나면 `done`이 된다.
"""

import math
from dataclasses import dataclass
from enum import Enum

EXERCISE_BLINK = "blink"

# 깜빡임 운동 구성(초). 준비 → (감기 → 유지 → 뜨기 → 쉬기) 반복 → 마무리
# 심호흡처럼 천천히: 눈을 천천히 감고(2초) 잠시 머문 뒤(1초) 천천히 뜨고(2초) 숨을 돌린다(1초).
# 낮은 종(감기 시작)과 높은 종(뜨기 시작) 사이는 3초이고, 한 사이클은 6초다.
PREPARE_SECONDS = 3
FINISH_SECONDS = 3
CLOSE_SECONDS = 2
HOLD_SECONDS = 1
OPEN_SECONDS = 2
REST_SECONDS = 1
LOOK_AWAY_SECONDS = 20  # 깜빡임 운동 뒤에 먼 곳을 바라보는 시간 (20-20-20 규칙)
CYCLE_SECONDS = CLOSE_SECONDS + HOLD_SECONDS + OPEN_SECONDS + REST_SECONDS
MIN_BLINK_SECONDS = PREPARE_SECONDS + CYCLE_SECONDS + FINISH_SECONDS  # 사이클 1회


class Phase(Enum):
    PREPARE = "prepare"
    CLOSE = "close"
    HOLD = "hold"
    OPEN = "open"
    REST = "rest"
    FINISH = "finish"
    LOOK_AWAY = "look_away"


MESSAGES = {
    Phase.PREPARE: "편안하게 앉아 화면을 바라보세요",
    Phase.CLOSE: "천천히 눈을 감으세요",
    Phase.HOLD: "감은 채 잠시 머무세요",
    Phase.OPEN: "천천히 부드럽게 뜨세요",
    Phase.REST: "",  # 쉬는 동안에는 아무 문구도 보이지 않는다
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
    Phase.FINISH: "잘했어요",
    Phase.LOOK_AWAY: "이제 먼 곳을 바라보세요",
}


@dataclass(frozen=True)
class BlinkStep:
    phase: Phase
    message: str
    eye_openness: float  # 1.0 = 활짝 뜸, 0.0 = 완전히 감음 (애니메이션용)
    progress: float  # 진행 막대. 깜빡임 운동 동안 0→1로 차오르고, 먼 곳 바라보기 동안 1→0으로 줄어든다
    finished: bool  # 깜빡임 운동이 끝났다 (기록을 남길 시점)
    countdown: int | None = None  # 먼 곳 바라보기의 남은 초 (20→1). 그 외에는 None
    done: bool = False  # 먼 곳 바라보기까지 모두 끝났다 (창을 닫을 시점)


@dataclass(frozen=True)
class BlinkTimeline:
    total_seconds: int
    cycles: int

    def step_at(self, elapsed: float) -> BlinkStep:
        total = float(self.total_seconds)
        elapsed = max(0.0, elapsed)
        progress = min(1.0, elapsed / total)
        if elapsed >= total:
            return self._look_away_step(elapsed - total)
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
    def _look_away_step(t: float) -> BlinkStep:
        message = MESSAGES[Phase.LOOK_AWAY]
        if t >= LOOK_AWAY_SECONDS:
            return BlinkStep(Phase.LOOK_AWAY, message, 1.0, 0.0, True, 0, True)
        countdown = math.ceil(LOOK_AWAY_SECONDS - t)
        return BlinkStep(Phase.LOOK_AWAY, message, 1.0, 1.0 - t / LOOK_AWAY_SECONDS, True, countdown)

    @staticmethod
    def _step(phase: Phase, openness: float, progress: float, finished: bool = False) -> BlinkStep:
        return BlinkStep(phase, MESSAGES[phase], openness, progress, finished)


def blink_timeline(duration_seconds: int) -> BlinkTimeline:
    """설정된 총 시간으로 타임라인을 만든다.

    사이클 수는 (총 시간 - 준비 - 마무리) // 6초이고 최소 1회다. 남는 시간은 마지막 '쉬기'가 흡수한다.
    그래서 총 시간이 사이클 1회(12초)보다 짧게 설정돼도 12초 아래로는 줄지 않는다.
    """
    total = max(int(duration_seconds), MIN_BLINK_SECONDS)
    cycles = max(1, (total - PREPARE_SECONDS - FINISH_SECONDS) // CYCLE_SECONDS)
    return BlinkTimeline(total_seconds=total, cycles=cycles)
