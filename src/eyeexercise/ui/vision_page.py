"""시력 기록 화면. 병원에서 받은 검사 결과를 직접 입력하고, 좌/우 시력의 추이를 목록으로 본다.

앱이 시력을 측정하는 것이 아니다. 입력값의 검증·저장·추이 계산은 core의 VisionLog와 함수가 하고,
이 모듈은 입력칸을 그리고 결과(또는 오류 메시지)를 보여 주기만 한다.
저장에 실패하면 입력한 내용을 지우지 않고 오류를 알린다.
"""

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eyeexercise.core.vision import (
    MEMO_MAX_LENGTH,
    RecordNotFound,
    VisionLog,
    VisionRecord,
    parse_acuity_text,
    parse_date_text,
    trend_deltas,
)
from eyeexercise.ui import theme
from eyeexercise.ui.controls import CONTROLS_STYLE, Segmented

SAVE_FAILED_MESSAGE = "파일에 저장하지 못했어요. 입력한 내용은 그대로 두었으니 잠시 후 다시 눌러 주세요."
DELETE_FAILED_MESSAGE = "파일에 저장하지 못해 삭제하지 못했어요."
EMPTY_MESSAGE = "아직 기록이 없어요. 병원에서 시력검사를 받았다면 위에서 결과를 남겨 보세요."
CONFIRM_DELETE_TEXT = "정말 삭제"

_STYLE = """
#visionPage, #visionContent { background: $bg; }
#visionPage QLabel { background: transparent; }
#pageTitle { font-size: $fs_title; font-weight: 900; }
#sectionTitle { font-size: $fs_heading; font-weight: 800; padding-top: 6px; }
#card { background: $surface; border: 1px solid $border; border-radius: 18px; }
#fieldLabel { font-size: $fs_small; color: $text_secondary; }
#hint { font-size: $fs_caption; color: $text_secondary; }
#formError { font-size: $fs_small; color: $danger; }
#empty { font-size: $fs_body; color: $text_muted; padding: 18px 0; }
#visionPage QLineEdit {
    background: $surface; border: 1px solid $input_border; border-radius: 6px; padding: 6px 8px; color: $text;
}
#visionPage QLineEdit:focus { border: 1px solid $accent; }
#primaryButton {
    background: $accent; color: $on_accent; border: none; border-radius: 10px; padding: 9px 22px; font-weight: 800;
}
#primaryButton:hover { background: $accent_hover; }
#secondaryButton {
    background: $surface; color: $text_body; border: 1px solid $input_border; border-radius: 6px; padding: 7px 14px;
}
#secondaryButton:hover { background: $chip; }
#rowButton { background: transparent; border: none; color: $accent; padding: 4px 8px; }
#rowButton:hover { color: $accent_hover; text-decoration: underline; }
#dangerButton { background: transparent; border: none; color: $danger; padding: 4px 8px; }
#dangerButton:hover { text-decoration: underline; }
#rowDate { font-size: $fs_body; font-weight: 800; }
#acuity { font-size: $fs_body; }
#delta { font-size: $fs_caption; color: $text_secondary; }
#delta[trend="up"] { color: $accent; }
#delta[trend="down"] { color: $warning; }
#divider { background: $divider; }
#kind { font-size: $fs_caption; color: $text_secondary; background: $chip; border-radius: 8px; padding: 2px 8px; }
#memo { font-size: $fs_caption; color: $text_secondary; }
""" + CONTROLS_STYLE

_KIND_OPTIONS = (("나안", False), ("교정(안경·렌즈)", True))


def _acuity_text(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def _delta_text(delta: float | None) -> tuple[str, str]:
    """(글자, 추세). 시력은 높을수록 좋으므로 오르면 파랑(up), 내리면 주황(down)으로 보인다."""
    if delta is None:
        return "", ""
    if delta > 0:
        return f"▲ {delta:g}", "up"
    if delta < 0:
        return f"▼ {-delta:g}", "down"
    return "변화 없음", ""


class VisionPage(QWidget):
    def __init__(
        self, log: VisionLog | None = None, today: Callable[[], date] = date.today, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._log = log or VisionLog()
        self._today = today
        self._editing_id: str | None = None
        self._pending_delete: str | None = None

        self.setObjectName("visionPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        theme.bind(self, _STYLE)

        title = QLabel("시력 기록")
        title.setObjectName("pageTitle")
        hint = QLabel("병원에서 받은 시력검사 결과를 직접 남기는 곳이에요. 앱이 시력을 측정하지는 않아요.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        # ---- 입력 폼 ----
        self._form_title = QLabel()
        self._form_title.setObjectName("sectionTitle")
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("2026-09-20")
        self.date_edit.setFixedWidth(130)
        self.left_edit = QLineEdit()
        self.left_edit.setPlaceholderText("예: 0.8")
        self.left_edit.setFixedWidth(90)
        self.right_edit = QLineEdit()
        self.right_edit.setPlaceholderText("예: 1.0")
        self.right_edit.setFixedWidth(90)
        self.kind = Segmented(_KIND_OPTIONS)
        self.memo_edit = QLineEdit()
        self.memo_edit.setPlaceholderText("병원 이름, 소견 등 (선택)")
        self.memo_edit.setMaxLength(MEMO_MAX_LENGTH)
        self.error_label = QLabel()
        self.error_label.setObjectName("formError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.save_button = QPushButton()
        self.save_button.setObjectName("primaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self._on_save)
        self.cancel_button.clicked.connect(self._reset_form)
        for edit in (self.date_edit, self.left_edit, self.right_edit, self.memo_edit):
            edit.returnPressed.connect(self._on_save)

        fields = QHBoxLayout()
        fields.setSpacing(14)
        fields.addLayout(self._field("검사일", self.date_edit))
        fields.addLayout(self._field("왼쪽 시력", self.left_edit))
        fields.addLayout(self._field("오른쪽 시력", self.right_edit))
        fields.addLayout(self._field("종류", self.kind))
        fields.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        form = QFrame()
        form.setObjectName("card")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(12)
        form_layout.addLayout(fields)
        form_layout.addLayout(self._field("메모", self.memo_edit))
        form_layout.addWidget(self.error_label)
        form_layout.addLayout(buttons)

        # ---- 기록 목록 ----
        list_title = QLabel("검사 기록")
        list_title.setObjectName("sectionTitle")
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(24, 6, 24, 6)
        self._rows.setSpacing(0)
        list_card = QFrame()
        list_card.setObjectName("card")
        list_card.setLayout(self._rows)

        content = QWidget()
        content.setObjectName("visionContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 22, 28, 24)
        body.setSpacing(14)
        body.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)  # 창이 작아지면 눌리지 않고 스크롤된다
        body.addWidget(title)
        body.addWidget(hint)
        body.addWidget(self._form_title)
        body.addWidget(form)
        body.addWidget(list_title)
        body.addWidget(list_card)
        body.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._reset_form()
        self.refresh()

    @staticmethod
    def _field(label: str, widget: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        text = QLabel(label)
        text.setObjectName("fieldLabel")
        layout.addWidget(text)
        layout.addWidget(widget)
        return layout

    # ---- 폼 ----

    def _reset_form(self) -> None:
        """입력칸을 비우고 '새 기록' 상태로 돌린다."""
        self._editing_id = None
        self._form_title.setText("새 기록 추가")
        self.save_button.setText("저장")
        self.cancel_button.hide()
        self.date_edit.setText(self._today().isoformat())
        self.left_edit.clear()
        self.right_edit.clear()
        self.memo_edit.clear()
        self.kind.setCurrentData(False)
        self._show_error("")

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def _on_save(self) -> None:
        try:
            day = parse_date_text(self.date_edit.text())
            left = parse_acuity_text(self.left_edit.text(), "왼쪽")
            right = parse_acuity_text(self.right_edit.text(), "오른쪽")
            corrected = bool(self.kind.currentData())
            memo = self.memo_edit.text()
            if self._editing_id is None:
                self._log.add(day, left, right, corrected, memo)
            else:
                self._log.update(self._editing_id, day, left, right, corrected, memo)
        except ValueError as e:  # 입력 검증 실패: 입력한 내용은 남겨 둔다
            self._show_error(str(e))
            return
        except RecordNotFound:
            self._reset_form()
            self.refresh()
            return
        except OSError:
            self._show_error(SAVE_FAILED_MESSAGE)
            return
        self._reset_form()
        self.refresh()

    def _start_edit(self, record: VisionRecord) -> None:
        self._editing_id = record.id
        self._form_title.setText("기록 수정")
        self.save_button.setText("수정 저장")
        self.cancel_button.show()
        self.date_edit.setText(record.date.isoformat())
        self.left_edit.setText("" if record.left is None else f"{record.left:g}")
        self.right_edit.setText("" if record.right is None else f"{record.right:g}")
        self.memo_edit.setText(record.memo)
        self.kind.setCurrentData(record.corrected)
        self._show_error("")
        self._pending_delete = None
        self.refresh()
        self.date_edit.setFocus()

    def _on_delete(self, record_id: str) -> None:
        """첫 번째 클릭은 확인을 묻고, 같은 줄을 한 번 더 누르면 삭제한다 (확인 창을 따로 띄우지 않는다)."""
        if self._pending_delete != record_id:
            self._pending_delete = record_id
            self.refresh()
            return
        self._pending_delete = None
        try:
            self._log.delete(record_id)
        except RecordNotFound:
            pass
        except OSError:
            self._show_error(DELETE_FAILED_MESSAGE)
            self.refresh()
            return
        if self._editing_id == record_id:
            self._reset_form()
        self.refresh()

    # ---- 목록 ----

    def refresh(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        records = self._log.records
        if not records:
            empty = QLabel(EMPTY_MESSAGE)
            empty.setObjectName("empty")
            empty.setWordWrap(True)
            self._rows.addWidget(empty)
            return
        deltas = trend_deltas(records)
        for i, record in enumerate(records):
            if i:
                line = QFrame()
                line.setFixedHeight(1)
                line.setObjectName("divider")
                self._rows.addWidget(line)
            self._rows.addWidget(self._row(record, deltas[record.id]))

    def _row(self, record: VisionRecord, delta: tuple[float | None, float | None]) -> QWidget:
        row = QWidget()
        outer = QHBoxLayout(row)
        outer.setContentsMargins(0, 10, 0, 10)
        outer.setSpacing(16)

        day = QLabel(record.date.isoformat())
        day.setObjectName("rowDate")
        day.setMinimumWidth(92)
        kind = QLabel("교정" if record.corrected else "나안")
        kind.setObjectName("kind")

        info = QVBoxLayout()
        info.setSpacing(2)
        eyes = QHBoxLayout()
        eyes.setSpacing(20)
        for name, value, d in (("왼쪽", record.left, delta[0]), ("오른쪽", record.right, delta[1])):
            eyes.addLayout(self._eye(name, value, d))
        eyes.addStretch(1)
        info.addLayout(eyes)
        if record.memo:
            memo = QLabel(record.memo)
            memo.setObjectName("memo")
            memo.setWordWrap(True)
            info.addWidget(memo)

        edit = QPushButton("수정")
        edit.setObjectName("rowButton")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda _=False, r=record: self._start_edit(r))
        remove = QPushButton(CONFIRM_DELETE_TEXT if self._pending_delete == record.id else "삭제")
        remove.setObjectName("dangerButton")
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda _=False, rid=record.id: self._on_delete(rid))
        # 눈에 띄도록 속성으로도 남긴다 (테스트·접근성)
        row.setProperty("recordId", record.id)
        edit.setProperty("role", "edit")
        remove.setProperty("role", "delete")

        outer.addWidget(day, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addWidget(kind, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addLayout(info, stretch=1)
        outer.addWidget(edit, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addWidget(remove, alignment=Qt.AlignmentFlag.AlignTop)
        return row

    @staticmethod
    def _eye(name: str, value: float | None, delta: float | None) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(6)
        label = QLabel(f"{name} {_acuity_text(value)}")
        label.setObjectName("acuity")
        layout.addWidget(label)
        text, trend = _delta_text(delta)
        if text:
            change = QLabel(text)
            change.setObjectName("delta")
            change.setProperty("trend", trend)
            layout.addWidget(change)
        return layout

    # ---- 테스트·외부에서 쓰는 조회 ----

    def row_widgets(self) -> list[QWidget]:
        return [
            self._rows.itemAt(i).widget()
            for i in range(self._rows.count())
            if self._rows.itemAt(i).widget() is not None and self._rows.itemAt(i).widget().property("recordId")
        ]

    def row_button(self, record_id: str, role: str) -> QPushButton:
        for row in self.row_widgets():
            if row.property("recordId") == record_id:
                for button in row.findChildren(QPushButton):
                    if button.property("role") == role:
                        return button
        raise LookupError((record_id, role))
