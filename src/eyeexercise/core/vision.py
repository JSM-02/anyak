"""병원 시력검사 기록. 사용자가 직접 입력하는 값이며 앱이 시력을 측정하지 않는다 (파일 I/O 없음).

저장은 주입받은 `save` 콜백이 맡는다. 운동 기록과 달리 사용자가 일부러 입력한 데이터이므로,
저장에 실패하면 예외를 그대로 올려 UI가 알릴 수 있게 하고 메모리 상태도 바꾸지 않는다.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

VISION_VERSION = 1
ACUITY_RANGE = (0.0, 2.0)  # 소수 시력
MEMO_MAX_LENGTH = 200


class RecordNotFound(LookupError):
    pass


@dataclass(frozen=True)
class VisionRecord:
    id: str
    date: date
    left: float | None
    right: float | None
    corrected: bool = False  # True: 교정시력(안경·렌즈 착용), False: 나안시력
    memo: str = ""


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _acuity(value: Any, name: str) -> float | None:
    """입력 검증. 잘못된 값은 ValueError (저장된 파일을 읽을 때는 쓰지 않는다)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 시력은 숫자여야 합니다.")
    low, high = ACUITY_RANGE
    if not low <= value <= high:
        raise ValueError(f"{name} 시력은 {low}~{high} 범위여야 합니다.")
    return round(float(value), 2)  # 0.15 같은 값은 허용하고, 부동소수 잡음만 정리한다


def _validated(
    day: date, left: Any, right: Any, corrected: bool, memo: str, today: date
) -> tuple[date, float | None, float | None, bool, str]:
    if day > today:
        raise ValueError("검사일은 오늘 이후일 수 없습니다.")
    left_v, right_v = _acuity(left, "왼쪽"), _acuity(right, "오른쪽")
    if left_v is None and right_v is None:
        raise ValueError("왼쪽과 오른쪽 중 하나 이상은 입력해야 합니다.")
    memo = memo.strip()
    if len(memo) > MEMO_MAX_LENGTH:
        raise ValueError(f"메모는 {MEMO_MAX_LENGTH}자 이하여야 합니다.")
    return day, left_v, right_v, bool(corrected), memo


class VisionLog:
    def __init__(
        self,
        records: Iterable[VisionRecord] = (),
        save: Callable[[list[VisionRecord]], None] | None = None,
        today: Callable[[], date] = date.today,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self._records = list(records)
        self._save = save
        self._today = today
        self._new_id = new_id

    @property
    def records(self) -> tuple[VisionRecord, ...]:
        """검사일 내림차순. 같은 날이면 나중에 추가한 기록이 먼저 온다."""
        indexed = list(enumerate(self._records))
        indexed.sort(key=lambda p: (p[1].date, p[0]), reverse=True)
        return tuple(r for _, r in indexed)

    def get(self, record_id: str) -> VisionRecord:
        for r in self._records:
            if r.id == record_id:
                return r
        raise RecordNotFound(record_id)

    def add(
        self, day: date, left: float | None, right: float | None, corrected: bool = False, memo: str = ""
    ) -> VisionRecord:
        fields = _validated(day, left, right, corrected, memo, self._today())
        existing = {r.id for r in self._records}
        new_id = self._new_id()
        while new_id in existing:
            new_id = self._new_id()
        record = VisionRecord(new_id, *fields)
        self._commit(self._records + [record])
        return record

    def update(
        self,
        record_id: str,
        day: date,
        left: float | None,
        right: float | None,
        corrected: bool = False,
        memo: str = "",
    ) -> VisionRecord:
        self.get(record_id)  # 없는 id면 RecordNotFound
        fields = _validated(day, left, right, corrected, memo, self._today())
        record = VisionRecord(record_id, *fields)
        self._commit([record if r.id == record_id else r for r in self._records])
        return record

    def delete(self, record_id: str) -> None:
        self.get(record_id)
        self._commit([r for r in self._records if r.id != record_id])

    def _commit(self, new_records: list[VisionRecord]) -> None:
        if self._save is not None:
            self._save(list(new_records))  # 실패하면 예외가 올라가고 메모리는 그대로다
        self._records = new_records


def vision_to_dict(records: Iterable[VisionRecord]) -> dict:
    return {
        "version": VISION_VERSION,
        "records": [
            {
                "id": r.id,
                "date": r.date.isoformat(),
                "left": r.left,
                "right": r.right,
                "corrected": r.corrected,
                "memo": r.memo,
            }
            for r in records
        ],
    }


def _stored_acuity(value: Any) -> float | None:
    """파일에서 읽을 때는 관대하게: 잘못된 값은 없는 값으로 본다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    low, high = ACUITY_RANGE
    return float(value) if low <= value <= high else None


def _record_from_dict(raw: Any) -> VisionRecord | None:
    if not isinstance(raw, dict):
        return None
    try:
        day = date.fromisoformat(raw["date"])
    except (KeyError, TypeError, ValueError):
        return None
    left, right = _stored_acuity(raw.get("left")), _stored_acuity(raw.get("right"))
    if left is None and right is None:
        return None
    record_id = raw.get("id")
    if not isinstance(record_id, str) or not record_id:
        record_id = _new_id()
    corrected = raw.get("corrected")
    memo = raw.get("memo")
    return VisionRecord(
        record_id,
        day,
        left,
        right,
        corrected if isinstance(corrected, bool) else False,
        memo[:MEMO_MAX_LENGTH] if isinstance(memo, str) else "",
    )


def vision_from_dict(data: Any) -> list[VisionRecord]:
    """깨진 레코드는 건너뛰고 나머지는 살린다. id가 겹치면 먼저 나온 것만 남긴다."""
    raw_records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(raw_records, list):
        return []
    result: list[VisionRecord] = []
    seen: set[str] = set()
    for raw in raw_records:
        r = _record_from_dict(raw)
        if r is None or r.id in seen:
            continue
        seen.add(r.id)
        result.append(r)
    return result


# ---- 입력 화면용 변환 (문자열 → 값, 추이 계산). Qt 없이 테스트할 수 있게 여기 둔다 ----


def parse_date_text(text: str) -> date:
    """'2026-09-20' 또는 '2026.9.20' 같은 입력을 날짜로. 잘못되면 ValueError."""
    parts = text.strip().replace(".", "-").replace("/", "-").split("-")
    parts = [p for p in parts if p]
    try:
        if len(parts) != 3:
            raise ValueError
        return date(*(int(p) for p in parts))
    except ValueError:
        raise ValueError("검사일은 2026-09-20 같은 형식으로 입력해 주세요.") from None


def parse_acuity_text(text: str, name: str) -> float | None:
    """시력 입력칸의 글자를 값으로. 빈 칸은 None(측정 안 함), 숫자가 아니면 ValueError."""
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{name} 시력은 0.8처럼 숫자로 입력해 주세요.") from None
    return _acuity(value, name)


def trend_deltas(records: Iterable[VisionRecord]) -> dict[str, tuple[float | None, float | None]]:
    """기록마다 (왼쪽 변화, 오른쪽 변화)를 계산한다. id → 값.

    같은 종류(나안끼리, 교정끼리)의 바로 앞 검사와 비교한다. 비교할 이전 값이 없으면 None.
    """
    ordered = sorted(enumerate(records), key=lambda p: (p[1].date, p[0]))
    last: dict[tuple[bool, str], float] = {}
    result: dict[str, tuple[float | None, float | None]] = {}
    for _, r in ordered:
        deltas: list[float | None] = []
        for eye, value in (("left", r.left), ("right", r.right)):
            key = (r.corrected, eye)
            if value is None:
                deltas.append(None)
                continue
            previous = last.get(key)
            deltas.append(None if previous is None else round(value - previous, 2))
            last[key] = value
        result[r.id] = (deltas[0], deltas[1])
    return result
