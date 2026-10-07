from datetime import date, datetime

import pytest

from eyeexercise.core.vision import (
    MEMO_MAX_LENGTH,
    RecordNotFound,
    VisionLog,
    VisionRecord,
    vision_from_dict,
    vision_to_dict,
)
from eyeexercise.storage import json_store, paths

TODAY = date(2026, 10, 7)


def make_log(records=(), save=None) -> VisionLog:
    ids = iter(f"id{i}" for i in range(1, 100))
    return VisionLog(records, save=save, today=lambda: TODAY, new_id=lambda: next(ids))


# ---- 추가와 검증 ----


def test_좌우_시력_추가():
    log = make_log()
    r = log.add(date(2026, 9, 20), 0.8, 1.0, corrected=False, memo="  OO안과  ")
    assert (r.left, r.right, r.corrected, r.memo) == (0.8, 1.0, False, "OO안과")
    assert log.get(r.id) == r


def test_한쪽만_입력해도_된다():
    log = make_log()
    assert log.add(date(2026, 9, 20), 0.5, None).right is None
    assert log.add(date(2026, 9, 21), None, 0.7).left is None


def test_양쪽_모두_비면_거부한다():
    with pytest.raises(ValueError, match="하나 이상"):
        make_log().add(date(2026, 9, 20), None, None)


@pytest.mark.parametrize("bad", [-0.1, 2.1, 10])
def test_범위를_벗어난_시력은_거부한다(bad):
    with pytest.raises(ValueError, match="범위"):
        make_log().add(date(2026, 9, 20), bad, 1.0)


@pytest.mark.parametrize("bad", ["1.0", True, [1.0]])
def test_숫자가_아닌_시력은_거부한다(bad):
    with pytest.raises(ValueError, match="숫자"):
        make_log().add(date(2026, 9, 20), 1.0, bad)


def test_경계값_0과_2는_허용한다():
    r = make_log().add(date(2026, 9, 20), 0.0, 2.0)
    assert (r.left, r.right) == (0.0, 2.0)


def test_0점15_같은_값은_그대로_두고_부동소수_잡음만_정리한다():
    r = make_log().add(date(2026, 9, 20), 0.15, 0.1 + 0.2)
    assert (r.left, r.right) == (0.15, 0.3)


def test_미래_날짜는_거부하고_오늘은_허용한다():
    log = make_log()
    with pytest.raises(ValueError, match="오늘 이후"):
        log.add(date(2026, 10, 8), 1.0, 1.0)
    assert log.add(TODAY, 1.0, 1.0).date == TODAY


def test_메모가_너무_길면_자르지_않고_거부한다():
    log = make_log()
    log.add(date(2026, 9, 20), 1.0, 1.0, memo="가" * MEMO_MAX_LENGTH)
    with pytest.raises(ValueError, match="메모"):
        log.add(date(2026, 9, 20), 1.0, 1.0, memo="가" * (MEMO_MAX_LENGTH + 1))


def test_검증에_실패하면_아무것도_추가되지_않는다():
    log = make_log()
    with pytest.raises(ValueError):
        log.add(date(2026, 9, 20), 5.0, 1.0)
    assert log.records == ()


# ---- 같은 날 여러 건, 정렬 ----


def test_같은_날_여러_건을_허용한다():
    log = make_log()
    a = log.add(date(2026, 9, 20), 0.8, 0.8, memo="나안")
    b = log.add(date(2026, 9, 20), 1.0, 1.0, corrected=True, memo="교정")
    assert a.id != b.id and len(log.records) == 2


def test_날짜_내림차순이고_같은_날은_나중에_추가한_것이_먼저():
    log = make_log()
    old = log.add(date(2026, 3, 1), 0.7, 0.7)
    mid_a = log.add(date(2026, 9, 20), 0.8, 0.8)
    mid_b = log.add(date(2026, 9, 20), 0.9, 0.9)
    new = log.add(date(2026, 10, 1), 1.0, 1.0)
    assert [r.id for r in log.records] == [new.id, mid_b.id, mid_a.id, old.id]


def test_id가_겹치면_새_id를_받는다():
    ids = iter(["x", "x", "y"])
    log = VisionLog(today=lambda: TODAY, new_id=lambda: next(ids))
    a = log.add(date(2026, 9, 20), 1.0, 1.0)
    b = log.add(date(2026, 9, 21), 1.0, 1.0)
    assert (a.id, b.id) == ("x", "y")


# ---- 수정과 삭제 ----


def test_수정():
    log = make_log()
    r = log.add(date(2026, 9, 20), 0.8, 1.0)
    updated = log.update(r.id, date(2026, 9, 21), 0.9, None, corrected=True, memo="수정")
    assert updated == VisionRecord(r.id, date(2026, 9, 21), 0.9, None, True, "수정")
    assert log.records == (updated,)


def test_수정_검증_실패_시_기존_기록이_유지된다():
    log = make_log()
    r = log.add(date(2026, 9, 20), 0.8, 1.0)
    with pytest.raises(ValueError):
        log.update(r.id, date(2026, 9, 20), 3.0, 1.0)
    assert log.get(r.id) == r


def test_삭제():
    log = make_log()
    a = log.add(date(2026, 9, 20), 0.8, 1.0)
    b = log.add(date(2026, 9, 21), 0.9, 1.0)
    log.delete(a.id)
    assert log.records == (b,)


def test_없는_id는_수정_삭제_조회_모두_RecordNotFound():
    log = make_log()
    with pytest.raises(RecordNotFound):
        log.get("none")
    with pytest.raises(RecordNotFound):
        log.update("none", date(2026, 9, 20), 1.0, 1.0)
    with pytest.raises(RecordNotFound):
        log.delete("none")


# ---- 저장 콜백 ----


def test_추가_수정_삭제마다_저장한다():
    saved = []
    log = make_log(save=lambda recs: saved.append(len(recs)))
    r = log.add(date(2026, 9, 20), 0.8, 1.0)
    log.update(r.id, date(2026, 9, 20), 0.9, 1.0)
    log.delete(r.id)
    assert saved == [1, 1, 0]


def test_저장에_실패하면_예외를_올리고_메모리는_바뀌지_않는다():
    fail = False

    def save(_recs):
        if fail:
            raise OSError("디스크 오류")

    log = make_log(save=save)
    r = log.add(date(2026, 9, 20), 0.8, 1.0)
    fail = True
    with pytest.raises(OSError):
        log.add(date(2026, 9, 21), 1.0, 1.0)
    with pytest.raises(OSError):
        log.update(r.id, date(2026, 9, 20), 0.5, 0.5)
    with pytest.raises(OSError):
        log.delete(r.id)
    assert log.records == (r,)


# ---- dict 변환 ----


def test_dict_변환_왕복():
    records = [
        VisionRecord("a1", date(2026, 9, 20), 0.8, 1.0, False, "OO안과"),
        VisionRecord("a2", date(2026, 3, 1), None, 0.5, True, ""),
    ]
    data = vision_to_dict(records)
    assert data["version"] == 1 and data["records"][0]["date"] == "2026-09-20"
    assert vision_from_dict(data) == records


def test_깨진_레코드는_건너뛰고_나머지는_살린다():
    data = {
        "records": [
            {"id": "ok", "date": "2026-09-20", "left": 0.8, "right": 1.0},
            {"id": "d", "date": "날짜아님", "left": 0.8},
            {"id": "n", "date": "2026-09-20", "left": None, "right": None},
            {"id": "r", "date": "2026-09-20", "left": 9.9, "right": "x"},
            "문자열",
            {"left": 1.0},
        ]
    }
    assert [r.id for r in vision_from_dict(data)] == ["ok"]


def test_한쪽_값만_깨졌으면_그_쪽만_없는_값으로_본다():
    (r,) = vision_from_dict({"records": [{"id": "a", "date": "2026-09-20", "left": 0.8, "right": 9.9}]})
    assert (r.left, r.right) == (0.8, None)


def test_모르는_키는_무시하고_없는_필드는_기본값():
    (r,) = vision_from_dict({"records": [{"id": "a", "date": "2026-09-20", "left": 1.0, "extra": 1}]})
    assert (r.corrected, r.memo, r.right) == (False, "", None)


def test_id가_없으면_새로_만들고_겹치면_먼저_나온_것만_남긴다():
    records = vision_from_dict(
        {
            "records": [
                {"date": "2026-09-20", "left": 1.0},
                {"id": "a", "date": "2026-09-20", "left": 0.5},
                {"id": "a", "date": "2026-09-21", "left": 0.9},
            ]
        }
    )
    assert len(records) == 2 and records[0].id and records[1].left == 0.5


def test_구조가_잘못되면_빈_목록():
    assert vision_from_dict(None) == []
    assert vision_from_dict({"records": "x"}) == []


# ---- 저장소 ----


def test_파일에_저장_후_다시_읽기(tmp_path):
    path = paths.vision_path(tmp_path)
    assert path.name == "vision.json"
    records = [VisionRecord("a1", date(2026, 9, 20), 0.8, 1.0, True, "OO안과 정기검진")]
    json_store.save_vision(path, records)
    assert json_store.load_vision(path) == records


def test_파일이_없으면_빈_목록(tmp_path):
    assert json_store.load_vision(tmp_path / "vision.json") == []


def test_손상된_파일은_백업하고_빈_목록으로_시작한다(tmp_path):
    path = tmp_path / "vision.json"
    path.write_text("{깨진 json", encoding="utf-8")
    assert json_store.load_vision(path, now=lambda: datetime(2026, 10, 7, 12, 0, 0)) == []
    assert (tmp_path / "vision.corrupt-20261007-120000.json").exists()


def test_VisionLog와_파일_저장소_연결(tmp_path):
    path = tmp_path / "vision.json"
    log = VisionLog(save=lambda recs: json_store.save_vision(path, recs), today=lambda: TODAY)
    r = log.add(date(2026, 9, 20), 0.8, 1.0, memo="메모")
    reloaded = VisionLog(json_store.load_vision(path), today=lambda: TODAY)
    assert reloaded.records == (r,)


# ---- 입력 화면용 변환 ----


def test_날짜_글자를_여러_형식으로_읽는다():
    from eyeexercise.core.vision import parse_date_text

    assert parse_date_text("2026-09-20") == date(2026, 9, 20)
    assert parse_date_text(" 2026.9.5 ") == date(2026, 9, 5)
    assert parse_date_text("2026/09/05") == date(2026, 9, 5)


@pytest.mark.parametrize("text", ["", "abc", "2026-13-01", "2026-09", "2026-02-30"])
def test_잘못된_날짜_글자는_거부한다(text):
    from eyeexercise.core.vision import parse_date_text

    with pytest.raises(ValueError, match="검사일"):
        parse_date_text(text)


def test_시력_글자를_읽는다():
    from eyeexercise.core.vision import parse_acuity_text

    assert parse_acuity_text("0.8", "왼쪽") == 0.8
    assert parse_acuity_text(" 1,2 ", "왼쪽") == 1.2  # 쉼표 소수점
    assert parse_acuity_text("", "왼쪽") is None  # 빈 칸은 측정 안 함
    assert parse_acuity_text("0", "왼쪽") == 0.0


@pytest.mark.parametrize("text", ["abc", "2.5", "-0.1", "nan"])
def test_잘못된_시력_글자는_거부한다(text):
    from eyeexercise.core.vision import parse_acuity_text

    with pytest.raises(ValueError, match="오른쪽 시력"):
        parse_acuity_text(text, "오른쪽")


def test_추이는_같은_종류의_바로_앞_검사와_비교한다():
    from eyeexercise.core.vision import trend_deltas

    records = [
        VisionRecord("a", date(2026, 1, 1), 0.8, 1.0, False),
        VisionRecord("b", date(2026, 3, 1), 0.7, None, False),
        VisionRecord("c", date(2026, 4, 1), 1.0, 1.2, True),  # 교정은 나안과 따로 비교한다
        VisionRecord("d", date(2026, 5, 1), 0.7, 1.0, False),
    ]
    d = trend_deltas(records)
    assert d["a"] == (None, None)
    assert d["b"] == (-0.1, None)
    assert d["c"] == (None, None)
    assert d["d"] == (0.0, 0.0)  # 오른쪽은 b에 값이 없어 그 앞(a)의 1.0과 비교한다
