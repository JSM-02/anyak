"""홈 화면의 '차오르는 물'에 쓰는 계산 (GUI·시간 의존 없음).

20분 타이머를 물의 높이로 보여 준다. 물은 시간이 갈수록 차오르고, 가득 차면 쉴 시간이다. 수면은 파도가 잔잔하게 일렁인다.
이 모듈은 수위와 수면 높이, 오늘의 눈 아이콘 줄을 숫자로만 계산하고, 그리는 일은 ui가 한다.

수면은 두 겹이다. 앞쪽 수면은 물과 글자 색이 바뀌는 경계이고, 뒤쪽 물결은 그 위에 옅게 깔리는 장식이다.
"""

import math
from dataclasses import dataclass

from eyeexercise.core.home import timer_progress
from eyeexercise.core.scheduler import State

_TAU = 2 * math.pi


@dataclass(frozen=True)
class WaveStyle:
    """파도의 세기. 높이(px)·파장(px)·주기(초)로 정한다."""

    a1: float  # 큰 물결 높이
    a2: float  # 작은 물결 높이
    l1: float  # 큰 물결 파장
    l2: float  # 작은 물결 파장
    breath: float  # 물결 높이가 숨 쉬듯 변하는 정도(0이면 일정)
    breath_period: float
    swell: float  # 수면 전체가 천천히 오르내리는 높이
    swell_period: float
    tilt: float  # 수면이 좌우로 번갈아 기울어지는 정도(양 끝의 높이 차)
    tilt_period: float
    foam_alpha: int  # 수면 거품선의 불투명도(0~255)
    foam_width: float


WAVE_WEAK = WaveStyle(5, 2.5, 300, 170, 0.0, 9, 0, 7, 0, 11, 76, 2.0)
WAVE_MID = WaveStyle(11, 5, 360, 200, 0.25, 9, 5, 7, 0, 11, 115, 2.5)
WAVE_STRONG = WaveStyle(18, 9, 420, 230, 0.35, 8, 9, 6, 14, 11, 150, 3.5)


def _swell_and_tilt(x: float, t: float, width: float, style: WaveStyle) -> tuple[float, float, float]:
    swell = style.swell * math.sin(t * _TAU / style.swell_period) if style.swell else 0.0
    side = ((x / width) - 0.5) * 2 if width > 0 else 0.0  # 왼쪽 끝 -1 ~ 오른쪽 끝 +1
    tilt = style.tilt * math.sin(t * _TAU / style.tilt_period + 1) * side if style.tilt else 0.0
    breath = 1 + style.breath * math.sin(t * _TAU / style.breath_period)
    return swell, tilt, breath


def wave_offset(x: float, t: float, width: float, style: WaveStyle) -> float:
    """앞쪽 수면이 기준 높이에서 얼마나 떨어져 있는지(px). 화면 좌표라 음수가 위쪽이다. t는 초."""
    swell, tilt, breath = _swell_and_tilt(x, t, width, style)
    big = style.a1 * math.sin(x * _TAU / style.l1 + t * 0.52)
    small = style.a2 * math.sin(x * _TAU / style.l2 - t * 0.78)
    return swell + tilt + breath * (big + small)


def back_offset(x: float, t: float, width: float, style: WaveStyle) -> float:
    """뒤쪽 옅은 물결의 높이. 앞쪽 수면보다 조금 위에서 더 느리게 반대 방향으로 흐른다."""
    swell, tilt, breath = _swell_and_tilt(x, t, width, style)
    lift = 10 + style.a1 * 0.35
    return (swell + tilt) * 0.8 - lift + 0.9 * breath * style.a1 * math.sin(x * _TAU / (style.l1 * 1.3) - t * 0.35 + 1.2)


def wave_margin(style: WaveStyle) -> float:
    """수위 0%와 100%에서 물이 화면 안으로 삐져나오거나 빈틈이 생기지 않게 위아래로 더 잡아 둘 여백(px).

    앞쪽과 뒤쪽 파도가 움직일 수 있는 최대 높이보다 크다."""
    top = 1 + style.breath
    front = abs(style.swell) + abs(style.tilt) + top * (style.a1 + style.a2)
    back = 0.8 * (abs(style.swell) + abs(style.tilt)) + 10 + style.a1 * 0.35 + 0.9 * top * style.a1
    return max(front, back) + 2


def water_level(state: State, remaining: float | None, target: float | None) -> float:
    """물의 높이(0~1). 기다리는 동안은 지난 비율, 알림이 떠 있으면 가득, 휴식·운동 중에는 빈다.

    일시정지 중에는 멈춘 자리의 높이를 그대로 보여 준다."""
    if state is State.DUE:
        return 1.0
    if state is State.EXERCISING:
        return 0.0
    return timer_progress(remaining, target)


MIN_VISIBLE_LEVEL = 0.07  # 수위 0%에서도 바닥에 이만큼은 깔려서 파도가 늘 보인다


def display_level(level: float) -> float:
    """화면에 그리는 물의 높이. 0%여도 바닥에 얇은 물이 있어 파도가 보이고, 100%는 가득이다.

    water_level은 '시간이 얼마나 지났나'이고, 이 값은 그것을 그림으로 옮긴 높이다."""
    level = min(1.0, max(0.0, level))
    return MIN_VISIBLE_LEVEL + (1 - MIN_VISIBLE_LEVEL) * level


@dataclass(frozen=True)
class EyeRow:
    """오늘의 휴식을 보여 주는 눈 아이콘 줄. 감은 눈은 쉰 횟수, 뜬 눈은 아직 남은 권장 횟수다."""

    closed: int
    open: int
    hidden: int  # 칸이 모자라 그리지 못한 수


def eye_row(rests: int, recommended: int, max_icons: int = 24) -> EyeRow:
    """쉰 횟수와 권장 횟수로 눈 아이콘 줄을 만든다. 아이콘은 max_icons개까지만 그린다(정확한 숫자는 글자로 따로 보여 준다)."""
    rests, recommended = max(0, rests), max(0, recommended)
    total = max(rests, recommended)
    closed = min(rests, max_icons)
    open_count = min(max(0, recommended - rests), max_icons - closed)
    return EyeRow(closed, open_count, total - closed - open_count)
