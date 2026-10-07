import re

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from eyeexercise.core.exercises import blink_seconds_for_cycles
from eyeexercise.core.settings import (
    BLINK_SECONDS_RANGE,
    DOT_FOLLOW_SECONDS_RANGE,
    IDLE_PAUSE_MINUTES_RANGE,
    IDLE_RESET_MINUTES_RANGE,
    INTERVAL_MINUTES_RANGE,
    SNOOZE_MINUTES_RANGE,
    Settings,
    settings_to_dict,
)
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.ui.controls import LabeledSlider, Segmented, Switch
from eyeexercise.ui.settings_page import EXERCISE_OFF_MESSAGE, SAVE_FAILED_MESSAGE, SettingsPage


def make_page(qapp, settings=None, save=None):
    saved = []
    manager = SettingsManager(settings or Settings(), save=save if save is not None else saved.append)
    page = SettingsPage(manager)
    page.resize(900, 1200)
    page.show()
    qapp.processEvents()
    return page, manager, saved


def label_text(page, name):
    return [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == name][0]


def flatten(data, prefix=""):
    paths = []
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths += flatten(value, f"{path}.")
        elif path != "version":
            paths.append(path)
    return paths


# ---- 처음 상태 ----


def test_모든_설정_항목이_화면에_있다(qapp):
    page, _, _ = make_page(qapp)
    assert sorted(page.paths) == sorted(flatten(settings_to_dict(Settings())))  # 새 설정을 추가하면 화면도 만들어야 한다


def test_입력칸은_현재_설정_값으로_채워진다(qapp):
    page, _, _ = make_page(qapp)
    assert page.control("interval_minutes").value() == 20
    assert page.control("snooze_minutes").value() == 5
    assert page.control("idle_pause_minutes").value() == 1
    assert page.control("idle_reset_minutes").value() == 5
    assert page.control("exercises.blink.enabled").isChecked()
    assert page.control("exercises.blink.duration_seconds").value() == 5  # 36초 = 깜빡임 5회
    assert page.control("exercises.daily_goal").value() == 2
    assert page.control("exercises.dot_follow.enabled").isChecked()
    assert page.control("exercises.dot_follow.duration_seconds").value() == 6  # 60초 = 10초 단위로 6칸
    assert page.control("exercises.dot_follow.speed").currentData() == "normal"
    assert page.control("sound.enabled").isChecked()
    assert page.control("show_main_window_on_start").isChecked()  # 기본은 시작할 때 창을 보인다


def test_바꾼_설정으로_시작하면_그_값이_보인다(qapp):
    settings = Settings()
    manager = SettingsManager(settings)
    manager.update({"interval_minutes": 45, "exercises.dot_follow.speed": "fast", "sound.enabled": False})
    page = SettingsPage(manager)
    assert page.control("interval_minutes").value() == 45
    assert page.control("exercises.dot_follow.speed").currentData() == "fast"
    assert not page.control("sound.enabled").isChecked()


def test_입력_범위는_설정_모델의_범위와_같다(qapp):
    page, _, _ = make_page(qapp)
    expected = {
        "interval_minutes": INTERVAL_MINUTES_RANGE,
        "snooze_minutes": SNOOZE_MINUTES_RANGE,
        "idle_pause_minutes": IDLE_PAUSE_MINUTES_RANGE,
        "idle_reset_minutes": IDLE_RESET_MINUTES_RANGE,
        "exercises.dot_follow.duration_seconds": (DOT_FOLLOW_SECONDS_RANGE[0] // 10, DOT_FOLLOW_SECONDS_RANGE[1] // 10),  # 10초 단위
    }
    for path, (low, high) in expected.items():
        spin = page.control(path)
        assert (spin.minimum(), spin.maximum()) == (low, high), path


def test_깜빡임_횟수_범위는_설정_시간_범위_안이다(qapp):
    page, _, _ = make_page(qapp)
    blink = page.control("exercises.blink.duration_seconds")
    assert (blink.minimum(), blink.maximum()) == (1, 15)
    assert BLINK_SECONDS_RANGE[0] <= blink_seconds_for_cycles(blink.minimum())
    assert blink_seconds_for_cycles(blink.maximum()) <= BLINK_SECONDS_RANGE[1]  # 15회 = 96초, 보정되어 어긋나지 않는다


def test_단위가_입력칸에_붙어_있다(qapp):
    page, _, _ = make_page(qapp)
    assert page.control("interval_minutes").suffix() == " 분"
    assert page.control("exercises.blink.duration_seconds").suffix() == "회"


def test_속도는_분할_버튼으로_고른다(qapp):
    page, _, _ = make_page(qapp)
    segmented = page.control("exercises.dot_follow.speed")
    assert isinstance(segmented, Segmented)
    assert [b.text() for b in segmented.buttons()] == ["느리게", "보통", "빠르게"]
    assert [b.isChecked() for b in segmented.buttons()] == [False, True, False]  # 보통이 선택돼 있다


# ---- 값을 바꾸면 즉시 저장하고 반영한다 ----


def test_숫자를_바꾸면_바로_저장된다(qapp):
    page, manager, saved = make_page(qapp)
    page.control("interval_minutes").setValue(45)
    assert manager.settings.interval_minutes == 45
    assert len(saved) == 1 and saved[0].interval_minutes == 45


@pytest.mark.parametrize(
    ("path", "value", "read"),
    [
        ("snooze_minutes", 10, lambda s: s.snooze_minutes),
        ("idle_pause_minutes", 2, lambda s: s.idle_pause_minutes),
        ("idle_reset_minutes", 10, lambda s: s.idle_reset_minutes),
        ("exercises.blink.duration_seconds", 15, lambda s: s.exercises.blink.duration_seconds),
        ("exercises.dot_follow.duration_seconds", 12, lambda s: s.exercises.dot_follow.duration_seconds),
    ],
)
def test_숫자_입력칸_모두_설정에_반영된다(qapp, path, value, read):
    page, manager, _ = make_page(qapp)
    page.control(path).setValue(value)
    expected = {"exercises.blink.duration_seconds": 96, "exercises.dot_follow.duration_seconds": 120}.get(path, value)  # 15회=96초, 12칸=120초
    assert read(manager.settings) == expected


def test_체크박스를_바꾸면_반영된다(qapp):
    page, manager, _ = make_page(qapp)
    page.control("sound.enabled").setChecked(False)
    page.control("show_main_window_on_start").setChecked(True)
    page.control("exercises.blink.enabled").setChecked(False)
    page.control("exercises.dot_follow.enabled").setChecked(False)
    s = manager.settings
    assert not s.sound.enabled and s.show_main_window_on_start
    assert not s.exercises.blink.enabled and not s.exercises.dot_follow.enabled


def test_속도를_고르면_반영된다(qapp):
    page, manager, _ = make_page(qapp)
    buttons = page.control("exercises.dot_follow.speed").buttons()
    buttons[2].click()
    assert manager.settings.exercises.dot_follow.speed == "fast"
    assert [b.isChecked() for b in buttons] == [False, False, True]
    buttons[0].click()
    assert manager.settings.exercises.dot_follow.speed == "slow"
    assert [b.isChecked() for b in buttons] == [True, False, False]


def test_이미_선택한_속도를_다시_눌러도_저장하지_않는다(qapp):
    page, manager, saved = make_page(qapp)
    page.control("exercises.dot_follow.speed").buttons()[1].click()  # 이미 보통
    assert saved == [] and manager.settings.exercises.dot_follow.speed == "normal"


def test_바꿀_때마다_한_번만_저장하고_알린다(qapp):
    page, manager, saved = make_page(qapp)
    calls = []
    manager.subscribe(lambda new, old: calls.append(1))
    page.control("interval_minutes").setValue(30)
    assert len(saved) == 1 and calls == [1]  # 입력칸을 다시 채우는 것이 또 다른 변경으로 이어지지 않는다


def test_화면이_입력칸을_다시_채워도_저장하지_않는다(qapp):
    page, manager, saved = make_page(qapp)
    manager.update({"interval_minutes": 30})  # 다른 곳에서 바꿨다
    assert len(saved) == 1
    assert page.control("interval_minutes").value() == 30
    assert len(saved) == 1  # 화면이 따라 바뀌어도 다시 저장하지 않는다


def test_다른_곳에서_설정이_바뀌면_화면이_따라간다(qapp):
    page, manager, _ = make_page(qapp)
    manager.update({"snooze_minutes": 15, "exercises.blink.enabled": False, "exercises.dot_follow.speed": "slow"})
    assert page.control("snooze_minutes").value() == 15
    assert not page.control("exercises.blink.enabled").isChecked()
    assert page.control("exercises.dot_follow.speed").currentData() == "slow"


# ---- 보정 ----


def test_멈춤_기준을_초기화_기준_이상으로_올리면_보정된_값으로_되돌아온다(qapp):
    page, manager, _ = make_page(qapp)  # 초기화 기준 5분
    page.control("idle_pause_minutes").setValue(10)
    assert manager.settings.idle_pause_minutes == 4
    assert page.control("idle_pause_minutes").value() == 4  # 입력칸도 보정된 값을 보여 준다


def test_초기화_기준을_멈춤_기준_이하로_내리면_멈춤_기준이_낮아져_보인다(qapp):
    settings = SettingsManager(Settings())
    settings.update({"idle_pause_minutes": 4})
    page = SettingsPage(settings)
    page.control("idle_reset_minutes").setValue(3)
    assert settings.settings.idle_pause_minutes == 2
    assert page.control("idle_pause_minutes").value() == 2 and page.control("idle_reset_minutes").value() == 3


def test_입력칸은_범위를_벗어난_값을_받지_않는다(qapp):
    page, _, _ = make_page(qapp)
    spin = page.control("interval_minutes")
    spin.setValue(999)
    assert spin.value() == 120
    spin.setValue(-5)
    assert spin.value() == 1


# ---- 입력 방식 ----


def test_슬라이더를_끄는_동안에는_값만_미리_보여_주고_놓으면_저장한다(qapp):
    page, manager, saved = make_page(qapp)
    control = page.control("interval_minutes")
    assert control.value_label.text() == "20 분"
    control.slider.setSliderDown(True)  # 끌기 시작
    control.slider.setValue(45)
    assert control.value_label.text() == "45 분"  # 값은 미리 보인다
    assert manager.settings.interval_minutes == 20 and saved == []  # 아직 저장하지 않는다
    control.slider.setValue(47)
    control.slider.setSliderDown(False)  # 놓는다
    assert manager.settings.interval_minutes == 47 and len(saved) == 1  # 놓은 값을 한 번만 저장한다


def test_키보드로_슬라이더를_움직이면_바로_반영한다(qapp):
    page, manager, _ = make_page(qapp)
    slider = page.control("interval_minutes").slider
    slider.setFocus()
    QTest.keyClick(slider, Qt.Key.Key_Right)
    assert manager.settings.interval_minutes == 21
    QTest.keyClick(slider, Qt.Key.Key_PageUp)
    assert manager.settings.interval_minutes == 26  # 한 번에 5분씩
    QTest.keyClick(slider, Qt.Key.Key_Left)
    assert manager.settings.interval_minutes == 25


def test_슬라이더_값_표시는_사람이_세는_말이고_바뀐_값을_따라간다(qapp):
    page, _, _ = make_page(qapp)
    blink = page.control("exercises.blink.duration_seconds")
    assert blink.value_label.text() == "5회"  # 36초가 아니라 5회
    blink.setValue(15)
    assert blink.value_label.text() == "15회"
    dot = page.control("exercises.dot_follow.duration_seconds")
    assert dot.value_label.text() == "1분"
    dot.setValue(9)
    assert dot.value_label.text() == "1분 30초"
    dot.setValue(3)
    assert dot.value_label.text() == "30초"


def _wheel(widget):
    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False
    )
    QApplication.sendEvent(widget, event)
    return event


def test_포커스가_없으면_마우스_휠로_값이_바뀌지_않는다(qapp):
    page, manager, saved = make_page(qapp)
    for path in ("interval_minutes", "exercises.blink.duration_seconds", "idle_reset_minutes"):
        slider = page.control(path).slider
        slider.clearFocus()
        before = manager.settings
        event = _wheel(slider)
        assert not event.isAccepted(), path  # 페이지 스크롤로 넘긴다
        assert manager.settings == before and saved == []


def test_슬라이더에_포커스가_있으면_휠로_값을_바꿀_수_있다(qapp):
    page, manager, _ = make_page(qapp)
    slider = page.control("interval_minutes").slider
    slider.setFocus()
    qapp.processEvents()
    if not slider.hasFocus():
        pytest.skip("이 환경에서는 포커스를 줄 수 없다")
    _wheel(slider)
    assert manager.settings.interval_minutes > 20  # 위로 굴리면 커진다


# ---- 설명 문구 ----


def test_깜빡임_설명은_걸리는_시간을_분과_초로_보여_준다(qapp):
    page, _, _ = make_page(qapp)
    hint = page._hints["blink_hint"]
    assert hint.text() == "준비·마무리 포함 약 36초"
    page.control("exercises.blink.duration_seconds").setValue(4)  # 4회 → 6 + 24 = 30초
    assert "약 30초" in hint.text()


def test_깜빡임_횟수를_가장_적게_하면_한_사이클이다(qapp):
    page, manager, _ = make_page(qapp)
    page.control("exercises.blink.duration_seconds").setValue(1)
    assert manager.settings.exercises.blink.duration_seconds == 12
    assert "약 12초" in page._hints["blink_hint"].text()


def test_점_따라가기_설명은_걸리는_시간만_짧게_보여_준다(qapp):
    page, _, _ = make_page(qapp)
    assert page._hints["dot_hint"].text() == "준비·마무리 포함 약 1분"
    page.control("exercises.dot_follow.duration_seconds").setValue(3)  # 30초
    assert "약 30초" in page._hints["dot_hint"].text()


# ---- 운동 켜기/끄기에 따른 입력칸 ----


def test_운동을_끄면_그_운동의_시간과_속도_입력칸이_꺼진다(qapp):
    page, _, _ = make_page(qapp)
    page.control("exercises.dot_follow.enabled").setChecked(False)
    assert not page.control("exercises.dot_follow.duration_seconds").isEnabled()
    assert not page.control("exercises.dot_follow.speed").isEnabled()
    assert page.control("exercises.blink.duration_seconds").isEnabled()  # 다른 운동은 그대로
    page.control("exercises.blink.enabled").setChecked(False)
    assert not page.control("exercises.blink.duration_seconds").isEnabled()
    page.control("exercises.blink.enabled").setChecked(True)
    assert page.control("exercises.blink.duration_seconds").isEnabled()


def test_점_따라가기를_끄면_안내가_보이고_다시_켜면_사라진다(qapp):
    page, _, _ = make_page(qapp)
    warning = label_text(page, "warning")
    assert warning.isHidden() and warning.text() == EXERCISE_OFF_MESSAGE
    page.control("exercises.blink.enabled").setChecked(False)
    assert warning.isHidden()  # 깜빡임을 꺼도 휴식은 먼 곳 바라보기로 계속된다
    page.control("exercises.dot_follow.enabled").setChecked(False)
    assert not warning.isHidden()
    page.control("exercises.dot_follow.enabled").setChecked(True)
    assert warning.isHidden()


def test_꺼진_상태로_시작해도_입력칸이_꺼져_있다(qapp):
    manager = SettingsManager(Settings())
    manager.update({"exercises.blink.enabled": False})
    page = SettingsPage(manager)
    assert not page.control("exercises.blink.duration_seconds").isEnabled()


# ---- 저장 실패 ----


def test_저장에_실패하면_안내가_보이고_값은_이번_실행에_적용된다(qapp):
    def fail(_settings):
        raise OSError("디스크 오류")

    page, manager, _ = make_page(qapp, save=fail)
    status = label_text(page, "saveStatus")
    assert status.isHidden()
    page.control("interval_minutes").setValue(30)
    assert not status.isHidden() and status.text() == SAVE_FAILED_MESSAGE
    assert manager.settings.interval_minutes == 30 and page.control("interval_minutes").value() == 30


def test_저장이_다시_성공하면_안내가_사라진다(qapp):
    fail = [True]

    def save(_settings):
        if fail[0]:
            raise OSError("디스크 오류")

    page, _, _ = make_page(qapp, save=save)
    status = label_text(page, "saveStatus")
    page.control("interval_minutes").setValue(30)
    assert not status.isHidden()
    fail[0] = False
    page.control("interval_minutes").setValue(31)
    assert status.isHidden()


def test_저장할_것이_없는_변경은_안내를_바꾸지_않는다(qapp):
    page, _, _ = make_page(qapp)
    page.control("interval_minutes").setValue(20)  # 이미 20
    assert label_text(page, "saveStatus").isHidden()


# ---- 구성 ----


def test_위젯_종류(qapp):
    page, _, _ = make_page(qapp)
    kinds = {
        LabeledSlider: ["interval_minutes", "snooze_minutes", "idle_pause_minutes", "idle_reset_minutes", "exercises.blink.duration_seconds", "exercises.dot_follow.duration_seconds", "exercises.daily_goal"],
        Switch: ["exercises.blink.enabled", "exercises.dot_follow.enabled", "sound.enabled", "show_main_window_on_start"],
        Segmented: ["exercises.dot_follow.speed", "appearance"],
    }
    for kind, paths in kinds.items():
        for path in paths:
            assert isinstance(page.control(path), kind), path
    assert sorted(sum(kinds.values(), [])) == sorted(page.paths)


def test_섹션_제목이_보인다(qapp):
    page, _, _ = make_page(qapp)
    titles = [lbl.text() for lbl in page.findChildren(QLabel) if lbl.objectName() == "sectionTitle"]
    assert titles == ["눈 휴식", "눈 운동", "화면", "소리와 시작", "휴식·운동 세부", "알림 세부", "자리 비움"]  # 앞의 넷이 기본, 뒤의 셋은 고급


def test_보정한_결과가_이전_값과_같아도_입력칸은_보정된_값으로_돌아온다(qapp):
    # 멈춤 기준이 이미 4분(초기화 기준 5분 바로 아래)일 때 8로 올리면 4로 보정되어 설정은 그대로다.
    # 이때는 설정 변경 알림이 없으므로, 화면이 직접 입력칸을 되돌려야 한다.
    manager = SettingsManager(Settings())
    manager.update({"idle_pause_minutes": 4})
    page = SettingsPage(manager)
    saved = []
    manager.subscribe(lambda new, old: saved.append(1))
    page.control("idle_pause_minutes").setValue(8)
    assert manager.settings.idle_pause_minutes == 4 and saved == []  # 바뀐 게 없다
    assert page.control("idle_pause_minutes").value() == 4  # 입력칸은 8이 아니라 4를 보여 준다


# ---- 글자 색: 개별 규칙이 기본 규칙에 가려지지 않는다 ----


def label_pixels(page, label):
    """실제 화면과 같이 페이지 전체를 그린 뒤 그 라벨 영역만 잘라 색을 돌려준다.
    (라벨 하나만 grab()하면 부모의 스타일시트가 반영되지 않아 실제와 다르다.)"""
    from PySide6.QtCore import QRect

    full = page.grab().toImage()
    crop = full.copy(QRect(label.mapTo(page, QPoint(0, 0)), label.size()))
    return [QColor(crop.pixel(x, y)) for x in range(crop.width()) for y in range(crop.height())]


def first_label(page, name):
    return [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == name][0]


def test_설명_문구는_제목보다_옅은_회색이다(qapp):
    page, _, _ = make_page(qapp)
    title = min(label_pixels(page, first_label(page, "rowTitle")), key=lambda c: c.lightness())
    hint = min(label_pixels(page, first_label(page, "rowHint")), key=lambda c: c.lightness())
    assert title.lightness() < 40  # 제목은 거의 검정
    assert hint.name() == "#4f6b66"  # 설명은 회색


def test_경고와_저장_실패_안내는_색이_있는_글자로_보인다(qapp):
    def fail(_settings):
        raise OSError("디스크 오류")

    page, manager, _ = make_page(qapp, save=fail)
    manager.update({"exercises.dot_follow.enabled": False})
    page.control("interval_minutes").setValue(30)  # 저장 실패 안내도 함께 띄운다
    warning, status = first_label(page, "warning"), first_label(page, "saveStatus")
    assert not warning.isHidden() and not status.isHidden()
    qapp.processEvents()
    assert min(label_pixels(page, warning), key=lambda c: c.lightness()).name() == "#9a5400"  # 주황
    assert min(label_pixels(page, status), key=lambda c: c.lightness()).name() == "#c5221f"  # 빨강


def test_꺼진_운동의_슬라이더_값은_옅게_보인다(qapp):
    page, _, _ = make_page(qapp)
    page._advanced_toggle.click()  # 고급 설정을 펼친다
    qapp.processEvents()
    value = page.control("exercises.blink.duration_seconds").value_label
    before = min(label_pixels(page, value), key=lambda c: c.lightness())
    page.control("exercises.blink.enabled").setChecked(False)
    qapp.processEvents()
    after = min(label_pixels(page, value), key=lambda c: c.lightness())
    assert after.lightness() > before.lightness()

# ---- 길이: 짧게 / 보통 / 길게 ----


def test_운동_길이는_짧게_보통_길게_중_보통이_선택돼_있다(qapp):
    page, _, _ = make_page(qapp)
    buttons = page.preset_control.buttons()
    assert [b.text() for b in buttons] == ["짧게", "보통", "길게"]
    assert [b.isChecked() for b in buttons] == [False, True, False]
    assert page._hints["preset_hint"].text() == "깜빡임 5회 · 점 따라가기 1분"


def test_짧게를_고르면_두_운동의_길이가_함께_줄어든다(qapp):
    page, manager, saved = make_page(qapp)
    page.preset_control.buttons()[0].click()
    assert manager.settings.exercises.blink.duration_seconds == 24 and manager.settings.exercises.dot_follow.duration_seconds == 30
    assert len(saved) == 1  # 한 번에 저장한다
    assert [b.isChecked() for b in page.preset_control.buttons()] == [True, False, False]
    assert page._hints["preset_hint"].text() == "깜빡임 3회 · 점 따라가기 30초"
    assert page.control("exercises.blink.duration_seconds").value() == 3  # 고급 슬라이더도 따라간다
    assert page.control("exercises.dot_follow.duration_seconds").value() == 3


def test_길게를_고르면_두_운동의_길이가_함께_늘어난다(qapp):
    page, manager, _ = make_page(qapp)
    page.preset_control.buttons()[2].click()
    assert manager.settings.exercises.blink.duration_seconds == 66 and manager.settings.exercises.dot_follow.duration_seconds == 90
    assert page._hints["preset_hint"].text() == "깜빡임 10회 · 점 따라가기 1분 30초"


def test_이미_고른_길이를_다시_눌러도_저장하지_않는다(qapp):
    page, _, saved = make_page(qapp)
    page.preset_control.buttons()[1].click()  # 이미 보통
    assert saved == []


def test_고급_설정에서_길이를_따로_정하면_아무것도_선택되지_않고_안내가_나온다(qapp):
    page, manager, _ = make_page(qapp)
    page.control("exercises.blink.duration_seconds").setValue(7)  # 깜빡임 7회
    assert [b.isChecked() for b in page.preset_control.buttons()] == [False, False, False]
    assert page._hints["preset_hint"].text() == "고급 설정에서 운동마다 따로 정한 길이를 쓰고 있어요."
    page.preset_control.buttons()[1].click()  # 보통을 고르면 다시 맞춰진다
    assert manager.settings.exercises.blink.duration_seconds == 36
    assert [b.isChecked() for b in page.preset_control.buttons()] == [False, True, False]


def test_점_따라가기_시간만_바꿔도_프리셋은_풀린다(qapp):
    page, _, _ = make_page(qapp)
    page.control("exercises.dot_follow.duration_seconds").setValue(7)  # 1분 10초
    assert [b.isChecked() for b in page.preset_control.buttons()] == [False, False, False]


def test_길이_선택은_운동을_꺼도_켜져_있다(qapp):
    page, _, _ = make_page(qapp)
    assert page.preset_control.isEnabled()
    page.control("exercises.blink.enabled").setChecked(False)
    page.control("exercises.dot_follow.enabled").setChecked(False)
    assert page.preset_control.isEnabled()  # 휴식은 깜빡임 없이도 계속된다


def test_한_운동을_꺼도_길이_선택은_두_운동에_저장된다(qapp):
    page, manager, _ = make_page(qapp)
    page.control("exercises.dot_follow.enabled").setChecked(False)
    page.preset_control.buttons()[2].click()
    assert manager.settings.exercises.blink.duration_seconds == 66 and manager.settings.exercises.dot_follow.duration_seconds == 90


def test_설정_파일에_들어_있는_어긋난_값도_화면에_이상하게_나오지_않는다(qapp):
    manager = SettingsManager(Settings())
    manager.update({"exercises.blink.duration_seconds": 70, "exercises.dot_follow.duration_seconds": 65})
    page = SettingsPage(manager)
    assert page.control("exercises.blink.duration_seconds").value_label.text() == "10회"  # 70초 = 10회(남는 시간은 마지막 쉬기)
    assert page.control("exercises.dot_follow.duration_seconds").value_label.text() == "1분 10초"  # 65초는 가까운 칸으로 보인다
    assert manager.settings.exercises.dot_follow.duration_seconds == 65  # 화면을 열기만 해서는 값을 바꾸지 않는다


def test_점_따라가기_시간은_10초에서_2분까지다(qapp):
    page, _, _ = make_page(qapp)
    dot = page.control("exercises.dot_follow.duration_seconds")
    assert dot.value_label.text() == "1분"
    dot.setValue(dot.maximum())
    assert dot.value_label.text() == "2분"
    dot.setValue(dot.minimum())
    assert dot.value_label.text() == "10초"


# ---- 고급 설정은 접혀 있다 ----

BASIC_PATHS = ["interval_minutes", "exercises.blink.enabled", "exercises.dot_follow.enabled", "exercises.daily_goal", "appearance", "sound.enabled", "show_main_window_on_start"]
ADVANCED_PATHS = ["snooze_minutes", "idle_pause_minutes", "idle_reset_minutes", "exercises.blink.duration_seconds", "exercises.dot_follow.duration_seconds", "exercises.dot_follow.speed"]


def test_처음에는_기본_설정만_보이고_고급_설정은_접혀_있다(qapp):
    page, _, _ = make_page(qapp)
    assert not page.advanced_open
    for path in BASIC_PATHS:
        assert page.control(path).isVisible(), path
    assert page.preset_control.isVisible()
    for path in ADVANCED_PATHS:
        assert not page.control(path).isVisible(), path
    assert page._advanced_toggle.text() == "▸  고급 설정"


def test_고급_설정을_누르면_펼쳐지고_다시_누르면_접힌다(qapp):
    page, _, _ = make_page(qapp)
    page._advanced_toggle.click()
    qapp.processEvents()
    assert page.advanced_open and page._advanced_toggle.text() == "▾  고급 설정"
    assert all(page.control(path).isVisible() for path in ADVANCED_PATHS)
    page._advanced_toggle.click()
    qapp.processEvents()
    assert not page.advanced_open and page._advanced_toggle.text() == "▸  고급 설정"
    assert not any(page.control(path).isVisible() for path in ADVANCED_PATHS)


def test_접혀_있어도_고급_값은_채워져_있고_펼치면_바로_보인다(qapp):
    manager = SettingsManager(Settings())
    manager.update({"snooze_minutes": 12, "idle_pause_minutes": 3, "exercises.dot_follow.speed": "fast"})
    page = SettingsPage(manager)
    page._advanced_toggle.click()
    assert page.control("snooze_minutes").value() == 12 and page.control("idle_pause_minutes").value() == 3
    assert page.control("exercises.dot_follow.speed").currentData() == "fast"


def test_접힌_동안에도_고급_값을_바꾸면_반영된다(qapp):
    page, manager, _ = make_page(qapp)
    manager.update({"snooze_minutes": 15})  # 다른 곳에서 바꿨다
    assert page.control("snooze_minutes").value() == 15


def test_기본_설정은_여섯_가지_컨트롤이다(qapp):
    page, _, _ = make_page(qapp)
    visible = [p for p in page.paths if page.control(p).isVisible()]
    assert sorted(visible) == sorted(BASIC_PATHS)
    assert sorted(BASIC_PATHS + ADVANCED_PATHS) == sorted(page.paths)


# ---- 사람이 쓰는 말: 66초 같은 숫자는 화면에 나오지 않는다 ----


def all_texts(page):
    return [lbl.text() for lbl in page.findChildren(QLabel)]


def long_seconds(page):
    """분 없이 초로만 말한 60 이상의 값 (예: "66초", "96 초"). "1분 6초"의 6초는 해당하지 않는다."""
    found = []
    for text in all_texts(page):
        found += [int(n) for n in re.findall(r"(?<!분 )(?<!\d)(\d+)\s?초", text) if int(n) >= 60]
    return found


def test_기본_화면에는_60초가_넘는_값을_초로만_말하지_않는다(qapp):
    page, _, _ = make_page(qapp)
    assert long_seconds(page) == []
    assert "66" not in " ".join(all_texts(page))


def test_고급_설정을_펼쳐도_초로만_말하지_않는다(qapp):
    page, _, _ = make_page(qapp)
    page._advanced_toggle.click()
    texts = " ".join(all_texts(page))
    assert long_seconds(page) == []
    assert "5회" in texts and "36초" in texts  # 횟수와 분·초로 말한다


def test_모든_프리셋에서도_60초가_넘는_값을_초로만_말하지_않는다(qapp):
    page, _, _ = make_page(qapp)
    page._advanced_toggle.click()
    for button in page.preset_control.buttons():
        button.click()
        assert long_seconds(page) == [], button.text()


def test_초로만_말한_긴_값을_잡아내는_검사가_동작한다(qapp):
    page, _, _ = make_page(qapp)
    page._hints["dot_hint"].setText("약 66초 걸려요. 1분 6초도 있어요. 짧은 30초.")
    assert long_seconds(page) == [66]  # 1분 6초의 6초와 30초는 걸리지 않는다


# ---- 짧은 고급 설정 설명, 슬라이더 값 말풍선 ----


def test_고급_설정_설명은_짧다(qapp):
    page, _, _ = make_page(qapp)
    page._advanced_toggle.click()
    hints = [lbl.text() for lbl in page._advanced.findChildren(QLabel) if lbl.objectName() == "rowHint" and lbl.text()]
    assert hints and all(len(text) <= 30 for text in hints), hints


def test_슬라이더_값_말풍선은_손잡이를_따라_움직이고_정수_값만_보여_준다(qapp):
    page, _, _ = make_page(qapp)
    page.resize(900, 700)
    page.show()
    qapp.processEvents()
    slider = page.control("interval_minutes")
    xs = []
    for value in (slider.minimum(), 20, slider.maximum()):
        slider.setValue(value)
        qapp.processEvents()
        xs.append(slider.bubble.handle_center_x())
        assert slider.value_label.text() == f"{value} 분"
    assert xs[0] < xs[1] < xs[2]
    assert slider.slider.singleStep() == 1 and isinstance(slider.value(), int)
    img = slider.bubble.grab().toImage()
    blue = sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).green() > 100 and img.pixelColor(x, y).red() < 60 and img.pixelColor(x, y).blue() < 120)
    assert blue > 100  # 초록 말풍선이 실제로 그려진다


def test_화면_모드를_고르면_저장되고_테마가_바뀐다(qapp):
    from eyeexercise.ui import theme

    theme._reset_for_tests()
    manager = SettingsManager(Settings())
    manager.subscribe(lambda new, old: theme.set_mode(new.appearance))
    page = SettingsPage(manager)
    control = page.control("appearance")
    assert control.currentData() == "system"
    assert [b.text() for b in control.buttons()] == ["시스템 설정", "라이트", "다크"]
    control.buttons()[2].click()
    assert manager.settings.appearance == "dark" and theme.is_dark()
    control.buttons()[1].click()
    assert manager.settings.appearance == "light" and not theme.is_dark()
    theme._reset_for_tests()


# ---- 설정 초기화 ----


def test_초기화_버튼은_한_번_더_눌러야_초기화된다(qapp):
    from eyeexercise.ui.settings_page import RESET_CONFIRM_TEXT, RESET_TEXT

    page, manager, saved = make_page(qapp)
    manager.update({"interval_minutes": 33, "exercises.daily_goal": 4, "appearance": "dark"})
    page._load(manager.settings)
    saved.clear()
    assert page.reset_button.text() == RESET_TEXT
    page.reset_button.click()
    assert page.reset_button.text() == RESET_CONFIRM_TEXT  # 첫 클릭은 확인만 묻는다
    assert manager.settings.interval_minutes == 33 and saved == []
    page.reset_button.click()
    assert manager.settings == Settings() and len(saved) == 1
    assert page.reset_button.text() == RESET_TEXT
    assert page.control("interval_minutes").value() == 20  # 입력칸도 기본값으로 돌아온다
    assert page.control("exercises.daily_goal").value() == 2
    assert page.control("appearance").currentData() == "system"


def test_초기화_확인은_시간이_지나면_취소된다(qapp):
    from eyeexercise.ui.settings_page import RESET_TEXT

    page, manager, _ = make_page(qapp)
    manager.update({"interval_minutes": 33})
    page.reset_button.click()
    assert page._reset_timer.isActive()
    page._cancel_reset()  # 5초가 지났을 때와 같다
    assert page.reset_button.text() == RESET_TEXT
    page.reset_button.click()  # 다시 처음부터 확인을 묻는다
    assert manager.settings.interval_minutes == 33


def test_초기화_저장에_실패하면_안내하고_기록은_건드리지_않는다(qapp):
    def fail(_settings):
        raise OSError("디스크 오류")

    page, manager, _ = make_page(qapp, save=fail)
    manager.update({"interval_minutes": 33})
    page.reset_button.click()
    page.reset_button.click()
    assert manager.settings == Settings()
    assert not first_label(page, "saveStatus").isHidden()
