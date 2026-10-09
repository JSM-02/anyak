"""개발용 샘플 데이터 생성: 실제 사용한 것처럼 보이는 눈 휴식·눈 운동 기록(history.json)과 스크린 타임(usage.json)을 만든다.

기록 탭의 하루 타임라인·차트를 눈으로 확인할 때 쓴다. 앱이 켜져 있으면 곧 메모리의 값으로 덮어쓰므로
**앱을 종료한 뒤** 실행한다.

    .venv\\Scripts\\python tools\\make_sample_data.py                  # %APPDATA%\\Swieom 에 쓴다
    .venv\\Scripts\\python tools\\make_sample_data.py --target 폴더    # 다른 폴더에 쓴다 (실제 데이터를 건드리지 않음)

- 오늘 기록은 그대로 두고, 오늘 이전 `--days`일(기본 14일)을 새로 만든다. 그 기간에 있던 기존 기록은 교체된다.
- 쓰기 전에 기존 파일을 `*.bak-날짜시각`으로 복사해 둔다.
- 같은 `--seed`면 같은 데이터가 나온다.
"""

import argparse
import random
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eyeexercise.core.exercises import EXERCISE_REST, EXERCISE_DOT_FOLLOW  # noqa: E402
from eyeexercise.core.history import ACTIVITY_REST, EVENT_COMPLETED, EVENT_SKIPPED, EVENT_SNOOZED, HistoryEvent  # noqa: E402
from eyeexercise.core.usage import UsageLog  # noqa: E402
from eyeexercise.storage import json_store, paths  # noqa: E402

REMINDER_MINUTES = 20  # 일하는 동안 알림이 오는 간격 (앱 기본값)
SNOOZE_MINUTES = 5
REST_SECONDS = 20  # 눈 휴식(먼 곳 바라보기 20초)
EXERCISE_SECONDS = 60  # 눈 운동(점 따라가기)


def _sessions(day: date, rng: random.Random) -> list[tuple[int, int]]:
    """그날 PC 앞에 있었던 구간 목록 [(시작 분, 끝 분)] (자정부터의 분)."""
    if day.weekday() < 5:  # 평일
        if rng.random() < 0.08:  # 연차·외근처럼 거의 안 쓰는 날
            return [(rng.randint(20 * 60, 21 * 60), rng.randint(21 * 60 + 30, 22 * 60))]
        start = 9 * 60 + rng.randint(-30, 40)
        lunch = 12 * 60 + rng.randint(5, 30)
        back = lunch + rng.randint(40, 70)
        end = 18 * 60 + rng.randint(-20, 70)
        sessions = [(start, lunch), (back, end)]
        if rng.random() < 0.35:  # 저녁에 잠깐 더
            sessions.append((rng.randint(20 * 60 + 30, 21 * 60 + 30), rng.randint(22 * 60, 23 * 60)))
        return sessions
    sessions = []  # 주말
    if rng.random() < 0.6:
        sessions.append((rng.randint(10 * 60 + 30, 12 * 60), rng.randint(14 * 60, 16 * 60)))
    if rng.random() < 0.55:
        sessions.append((rng.randint(19 * 60 + 30, 20 * 60 + 30), rng.randint(22 * 60, 23 * 60 + 15)))
    return sessions


def _usage_hours(sessions: list[tuple[int, int]], rng: random.Random) -> list[float]:
    """구간 안에서 입력이 있던 시간(초)을 시간대별로. 자리를 비우는 짧은 틈 때문에 시간당 60~95%만 센다."""
    hours = [0.0] * 24
    for start, end in sessions:
        for hour in range(start // 60, min(24, (end - 1) // 60 + 1)):
            overlap = min(end, (hour + 1) * 60) - max(start, hour * 60)
            if overlap > 0:
                hours[hour] += overlap * 60 * rng.uniform(0.6, 0.95)
    return [min(3600.0, round(v, 1)) for v in hours]


def _events(day: date, sessions: list[tuple[int, int]], rng: random.Random, tz) -> list[HistoryEvent]:
    """눈 휴식은 20분마다 알림에 응한 결과(완료·건너뜀·미룸)이고, 눈 운동(점 따라가기)은 하루 0~2회다."""
    events: list[HistoryEvent] = []

    def at(minute: float) -> datetime:
        base = datetime(day.year, day.month, day.day, tzinfo=tz)
        return base + timedelta(minutes=minute, seconds=rng.randint(0, 59))

    def rest(minute: float) -> None:
        events.append(HistoryEvent(at(minute + 0.5), EVENT_COMPLETED, EXERCISE_REST, REST_SECONDS))

    for start, end in sessions:
        t = start + REMINDER_MINUTES + rng.uniform(-3, 6)  # 시작 후 한 주기가 지나면 첫 알림
        while t < end - 2:
            roll = rng.random()
            if roll < 0.55:
                rest(t)
            elif roll < 0.8:
                events.append(HistoryEvent(at(t), EVENT_SKIPPED, activity=ACTIVITY_REST))
            else:  # 미루기: 5분 뒤 다시 알림이 와서 대개 한다
                events.append(HistoryEvent(at(t), EVENT_SNOOZED, activity=ACTIVITY_REST))
                t += SNOOZE_MINUTES
                if t < end - 2:
                    if rng.random() < 0.65:
                        rest(t)
                    else:
                        events.append(HistoryEvent(at(t), EVENT_SKIPPED, activity=ACTIVITY_REST))
            t += REMINDER_MINUTES + rng.uniform(-2, 8)  # 자리를 잠깐 비우면 조금 늦어진다

    # 눈 운동: 하루 목표(2회) 안에서, 일한 날에만 휴식 알림 때 '운동도 할래요?'에 응한 것처럼 만든다
    chances = [(start, end) for start, end in sessions if end - start >= 90]
    for i, (start, end) in enumerate(chances[:2]):
        if rng.random() < (0.85 if i == 0 else 0.55):
            minute = rng.uniform(start + 45, end - 20)
            events.append(HistoryEvent(at(minute), EVENT_COMPLETED, EXERCISE_DOT_FOLLOW, EXERCISE_SECONDS))
    return events


def build(days: int, today: date, tz, seed: int) -> tuple[list[HistoryEvent], UsageLog]:
    rng = random.Random(seed)
    events: list[HistoryEvent] = []
    usage = UsageLog()
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        sessions = _sessions(day, rng)
        events.extend(_events(day, sessions, rng, tz))
        for hour, seconds in enumerate(_usage_hours(sessions, rng)):
            if seconds > 0:
                usage.add(datetime(day.year, day.month, day.day, hour, tzinfo=tz), seconds)
    return events, usage


def main() -> None:
    parser = argparse.ArgumentParser(description="실제처럼 보이는 샘플 기록을 만든다 (개발용).")
    parser.add_argument("--target", type=Path, default=None, help="저장할 폴더 (기본: %%APPDATA%%\\Swieom)")
    parser.add_argument("--days", type=int, default=14, help="오늘 이전 며칠을 만들지")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    tz = datetime.now().astimezone().tzinfo
    today = datetime.now(tz).date()
    history_file, usage_file = paths.history_path(args.target), paths.usage_path(args.target)
    history_file.parent.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for file in (history_file, usage_file):
        if file.exists():
            shutil.copy2(file, file.with_name(f"{file.name}.bak-{stamp}"))

    # 오늘 기록은 그대로 둔다. 만드는 기간(오늘 이전)에 있던 기존 기록은 교체한다.
    kept_events = [e for e in json_store.load_history(history_file) if e.ts.astimezone(tz).date() >= today]
    kept_usage = json_store.load_usage(usage_file)
    new_events, new_usage = build(args.days, today, tz, args.seed)

    merged_usage = UsageLog({day: hours for day, hours in kept_usage.days.items() if day >= today})
    for day, hours in new_usage.days.items():
        for hour, seconds in enumerate(hours):
            if seconds > 0:
                merged_usage.add(datetime(day.year, day.month, day.day, hour, tzinfo=tz), seconds)

    json_store.save_history(history_file, sorted(new_events + kept_events, key=lambda e: e.ts))
    json_store.save_usage(usage_file, merged_usage)
    print(f"운동 기록 {len(new_events)}건(오늘 {len(kept_events)}건은 그대로), 스크린 타임 {len(new_usage.days)}일을 만들었어요.")
    print(f"저장 위치: {history_file.parent}  (기존 파일은 *.bak-{stamp}로 복사해 뒀어요)")


if __name__ == "__main__":
    main()
