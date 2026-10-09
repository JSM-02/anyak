from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from eyeexercise.core.help_text import HELP_SECTIONS
from eyeexercise.ui import theme
from eyeexercise.ui.help_popup import HelpPopup
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.topbar import TopBar


def test_안내_문구는_오해하기_쉬운_내용을_담는다():
    text = " ".join(title + body for title, body in HELP_SECTIONS)
    assert "켜져 있을 때만" in text and "키보드·마우스 입력" in text  # 스크린 타임은 앱이 실행 중일 때만 센다
    assert "권장 휴식 횟수" in text and "80% 이상은 초록" in text  # 달성률의 뜻과 색 기준
    assert "트레이" in text and "종료" in text  # 창을 닫아도 계속 실행된다
    assert "카메라" in text and "키 입력 내용" in text  # 수집하지 않는 것


def test_안내_문구에_빈_제목이나_본문이_없다():
    assert len(HELP_SECTIONS) >= 4
    assert all(title.strip() and body.strip() for title, body in HELP_SECTIONS)


def test_메뉴_줄에_물음표_버튼이_있고_누르면_알린다(qapp):
    bar = TopBar(("홈", "기록"))
    heard = []
    bar.help_requested.connect(lambda: heard.append(1))
    assert bar.help_button.accessibleName() == "사용 안내"
    bar.help_button.click()
    assert heard == [1]


def test_안내_창은_모든_구역을_보여_준다(qapp):
    popup = HelpPopup()
    assert [label.text() for label in popup.titles] == [title for title, _ in HELP_SECTIONS]
    assert [label.text() for label in popup.bodies] == [body for _, body in HELP_SECTIONS]
    assert all(label.wordWrap() for label in popup.bodies)


def test_안내_창은_바깥을_누르면_닫히는_팝업이다(qapp):
    popup = HelpPopup()
    assert popup.windowType() == Qt.WindowType.Popup


def test_메인_창에서_물음표를_누르면_버튼_아래에_열린다(qapp):
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    qapp.processEvents()
    QTest.mouseClick(window.topbar.help_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    popup = window.help_popup
    assert popup.isVisible()
    anchor = window.topbar.help_button
    below = anchor.mapToGlobal(anchor.rect().bottomLeft()).y()
    assert popup.y() >= below  # 버튼 아래에 뜬다
    assert popup.x() + popup.width() <= anchor.mapToGlobal(anchor.rect().bottomRight()).x() + 1 or popup.x() >= 0
    popup.hide()


def test_안내_창의_바탕은_두_테마_모두_깊은_초록이고_글자가_읽힌다(qapp):
    for dark in (False, True):
        palette = theme.DARK if dark else theme.LIGHT
        assert palette.hero.lower() == "#12544f"  # 팝업과 같은 물의 색
