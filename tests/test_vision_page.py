from datetime import date

import pytest
from PySide6.QtWidgets import QLabel

from eyeexercise.core.vision import VisionLog
from eyeexercise.ui import vision_page as vp
from eyeexercise.ui.vision_page import VisionPage

TODAY = date(2026, 10, 7)


def make_page(records=(), save=None):
    ids = iter(f"id{i}" for i in range(1, 100))
    log = VisionLog(records, save=save, today=lambda: TODAY, new_id=lambda: next(ids))
    return VisionPage(log, today=lambda: TODAY), log


def fill(page, day="2026-09-20", left="0.8", right="1.0", memo="", corrected=False):
    page.date_edit.setText(day)
    page.left_edit.setText(left)
    page.right_edit.setText(right)
    page.memo_edit.setText(memo)
    page.kind.setCurrentData(corrected)


def test_처음에는_오늘_날짜가_채워지고_기록이_없다(qapp):
    page, _ = make_page()
    assert page.date_edit.text() == "2026-10-07"
    assert page.row_widgets() == []
    assert page.error_label.isHidden()
    assert page.cancel_button.isHidden()


def test_입력하고_저장하면_목록에_나타나고_입력칸이_초기화된다(qapp):
    page, log = make_page()
    fill(page, memo="OO안과", corrected=True)
    page.save_button.click()
    (record,) = log.records
    assert (record.left, record.right, record.corrected, record.memo) == (0.8, 1.0, True, "OO안과")
    assert len(page.row_widgets()) == 1
    assert page.left_edit.text() == "" and page.memo_edit.text() == ""
    assert page.kind.currentData() is False


def test_한쪽만_입력해도_저장된다(qapp):
    page, log = make_page()
    fill(page, right="")
    page.save_button.click()
    assert (log.records[0].left, log.records[0].right) == (0.8, None)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"day": "어제"}, "검사일"),
        ({"day": "2026-10-08"}, "오늘 이후"),
        ({"left": "", "right": ""}, "하나 이상"),
        ({"left": "abc"}, "왼쪽 시력은 0.8처럼"),
        ({"right": "3"}, "오른쪽 시력은 0.0~2.0"),
    ],
)
def test_잘못된_입력은_메시지를_보이고_입력한_내용을_남긴다(qapp, kwargs, message):
    page, log = make_page()
    fill(page, **kwargs)
    page.save_button.click()
    assert log.records == ()
    assert not page.error_label.isHidden()
    assert message in page.error_label.text()
    assert page.left_edit.text() == kwargs.get("left", "0.8")  # 지워지지 않는다


def test_메모_입력칸은_길이_제한이_있다(qapp):
    page, _ = make_page()
    page.memo_edit.setText("가" * 500)
    assert len(page.memo_edit.text()) == 200


def test_저장에_실패하면_오류를_알리고_입력을_남기고_기록은_늘지_않는다(qapp):
    def broken(_records):
        raise PermissionError("읽기 전용")

    page, log = make_page(save=broken)
    fill(page)
    page.save_button.click()
    assert log.records == ()
    assert page.error_label.text() == vp.SAVE_FAILED_MESSAGE
    assert page.left_edit.text() == "0.8"


def test_수정하면_입력칸이_채워지고_저장하면_기록이_바뀐다(qapp):
    page, log = make_page()
    fill(page, memo="처음")
    page.save_button.click()
    rid = log.records[0].id
    page.row_button(rid, "edit").click()
    assert page.left_edit.text() == "0.8" and page.memo_edit.text() == "처음"
    assert page.save_button.text() == "수정 저장"
    assert not page.cancel_button.isHidden()
    page.left_edit.setText("0.9")
    page.save_button.click()
    assert len(log.records) == 1 and log.records[0].left == 0.9 and log.records[0].id == rid
    assert page.save_button.text() == "저장" and page.cancel_button.isHidden()


def test_수정을_취소하면_기록은_그대로이고_폼이_초기화된다(qapp):
    page, log = make_page()
    fill(page)
    page.save_button.click()
    page.row_button(log.records[0].id, "edit").click()
    page.left_edit.setText("0.1")
    page.cancel_button.click()
    assert log.records[0].left == 0.8
    assert page.left_edit.text() == "" and page.save_button.text() == "저장"


def test_삭제는_한_번_더_눌러야_지워진다(qapp):
    page, log = make_page()
    fill(page)
    page.save_button.click()
    rid = log.records[0].id
    page.row_button(rid, "delete").click()
    assert len(log.records) == 1
    assert page.row_button(rid, "delete").text() == vp.CONFIRM_DELETE_TEXT
    page.row_button(rid, "delete").click()
    assert log.records == ()
    assert page.row_widgets() == []


def test_삭제_저장에_실패하면_기록을_지키고_오류를_알린다(qapp):
    calls = []

    def flaky(_records):
        calls.append(1)
        if len(calls) > 1:
            raise OSError("디스크 오류")

    page, log = make_page(save=flaky)
    fill(page)
    page.save_button.click()
    rid = log.records[0].id
    page.row_button(rid, "delete").click()
    page.row_button(rid, "delete").click()
    assert len(log.records) == 1
    assert page.error_label.text() == vp.DELETE_FAILED_MESSAGE


def test_목록은_날짜_내림차순이고_추이를_보여_준다(qapp):
    page, log = make_page()
    fill(page, day="2026-01-01", left="0.8", right="1.0")
    page.save_button.click()
    fill(page, day="2026-06-01", left="0.6", right="1.0")
    page.save_button.click()
    rows = page.row_widgets()
    assert [r.property("recordId") for r in rows] == [r.id for r in log.records]
    texts = [label.text() for label in rows[0].findChildren(QLabel)]
    assert "2026-06-01" in texts and "▼ 0.2" in texts and "변화 없음" in texts


def test_수정_중인_기록을_삭제하면_폼이_초기화된다(qapp):
    page, log = make_page()
    fill(page)
    page.save_button.click()
    rid = log.records[0].id
    page.row_button(rid, "edit").click()
    page.row_button(rid, "delete").click()
    page.row_button(rid, "delete").click()
    assert page.save_button.text() == "저장" and log.records == ()


def test_만들고_갱신하는_동안_독립된_작은_창이_뜨지_않는다(qapp):
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QWidget

    shown = []

    class Spy(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(type(obj).__name__)
            return False

    spy = Spy()
    qapp.installEventFilter(spy)
    try:
        page, log = make_page()
        fill(page)
        page.save_button.click()
        rid = log.records[0].id
        page.row_button(rid, "edit").click()
        page.cancel_button.click()
        page.row_button(rid, "delete").click()
        qapp.processEvents()
    finally:
        qapp.removeEventFilter(spy)
    assert shown == []
