"""화면에 보여줄 문구 가공. Qt와 무관한 순수 함수만 둔다."""

import math

from eyeexercise.core.history import ACTIVITY_EXERCISE
from eyeexercise.core.scheduler import State


def format_remaining(seconds: float) -> str:
    """남은 시간을 '12분 30초' 형태로 만든다. 초는 올림해서 0초 표시를 피한다."""
    total = max(0, math.ceil(seconds))
    minutes, secs = divmod(total, 60)
    if minutes == 0:
        return f"{secs}초"
    if secs == 0:
        return f"{minutes}분"
    return f"{minutes}분 {secs}초"


def format_clock(seconds: float) -> str:
    """남은 시간을 타이머처럼 '12:34'로 만든다. 초는 올림해서 0:00이 먼저 보이지 않게 한다."""
    total = max(0, math.ceil(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}" if minutes < 10 else f"{minutes:02d}:{secs:02d}"


def home_timer(state: State, remaining: float | None, activity: str | None = None) -> tuple[str, str]:
    """홈 화면 타이머 카드의 (위 작은 글씨, 큰 글씨).

    기다리는 중이면 ('다음 눈 휴식까지', '12:34'), 미루는 중이면 ('다시 알림까지', '4:50'),
    일시정지면 ('일시정지됨', '12:34'), 알림이 떠 있으면 ('눈 휴식 시간', '지금'), 하는 중이면 ('눈 휴식 중', '–')."""
    clock = format_clock(remaining) if remaining is not None else "–"
    if state is State.DUE:
        return "눈 휴식 시간", "지금"
    if state is State.EXERCISING:
        return ("눈 운동 중" if activity == ACTIVITY_EXERCISE else "눈 휴식 중"), "–"
    if state is State.PAUSED:
        return "일시정지됨", clock
    if state is State.SNOOZED:
        return "다시 알림까지", clock
    return "다음 눈 휴식까지", clock


def timer_pill(state: State, remaining: float | None, activity: str | None = None) -> tuple[str, str]:
    """사이드바 타이머 알약의 (문구, 상태). 상태는 normal / alert / paused / active.

    - 기다리는 중: '12:34 뒤 휴식', 미루는 중: '4:50 뒤 다시 알림'
    - 알림이 떠 있으면: '지금 쉴 시간이에요'
    - 하는 중: '눈 휴식 중' / '눈 운동 중'
    - 일시정지: '일시정지 · 12:34'
    """
    clock = format_clock(remaining) if remaining is not None else ""
    if state is State.DUE:
        return "지금 쉴 시간이에요", "alert"
    if state is State.EXERCISING:
        return ("눈 운동 중" if activity == ACTIVITY_EXERCISE else "눈 휴식 중"), "active"
    if state is State.PAUSED:
        return (f"일시정지 · {clock}" if clock else "일시정지"), "paused"
    if state is State.SNOOZED:
        return (f"{clock} 뒤 다시 알림" if clock else "다시 알림 대기"), "normal"
    return (f"{clock} 뒤 휴식" if clock else "휴식 대기"), "normal"
