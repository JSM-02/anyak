from eyeexercise.ui.main_window import MainWindow


def test_닫으면_종료하지_않고_숨긴다(qapp):
    window = MainWindow()
    hidden = []
    window.hidden_to_tray.connect(lambda: hidden.append(1))
    window.show()
    assert window.isVisible()

    closed = window.close()

    assert closed is False  # closeEvent에서 닫기를 거부했다
    assert not window.isVisible()
    assert hidden == [1]


def test_숨긴_뒤_다시_열_수_있다(qapp):
    window = MainWindow()
    window.show()
    window.close()
    assert not window.isVisible()

    window.show_and_raise()
    assert window.isVisible()


def test_종료_준비_후에는_닫기를_막지_않는다(qapp):
    window = MainWindow()
    hidden = []
    window.hidden_to_tray.connect(lambda: hidden.append(1))
    window.show()
    window.prepare_to_quit()

    assert window.close() is True
    assert hidden == []  # 종료 중에는 "트레이로 숨었다"는 신호를 내지 않는다


def test_넉넉한_화면에서는_기본_크기를_쓴다():
    from PySide6.QtCore import QRect

    from eyeexercise.ui.main_window import fit_to_screen

    assert fit_to_screen(QRect(0, 0, 1920, 1040)) == ((1000, 700), (880, 560))


def test_배율이_높아_화면이_작으면_창이_화면_안에_들어온다():
    from PySide6.QtCore import QRect

    from eyeexercise.ui.main_window import fit_to_screen

    # 1080p 150%: 논리 크기 1280×720에서 작업 표시줄을 뺀 약 1280×672
    assert fit_to_screen(QRect(0, 0, 1280, 672)) == ((1000, 632), (880, 560))
    # 768p 125%: 논리 1092×614 → 작업 표시줄을 뺀 약 574. 최소 크기도 함께 줄어든다
    size, minimum = fit_to_screen(QRect(0, 0, 1092, 574))
    assert size == (1000, 534) and minimum == (880, 534)
    # 아주 작아도 화면을 넘지 않는다
    size, minimum = fit_to_screen(QRect(0, 0, 800, 600))
    assert size == (760, 560) and minimum == (760, 560)


def test_메인_창은_현재_화면에_맞는_크기로_만들어진다(qapp):
    from PySide6.QtGui import QGuiApplication

    area = QGuiApplication.primaryScreen().availableGeometry()
    window = MainWindow()
    assert window.width() <= area.width() and window.height() <= area.height()


def test_기록_탭은_설정의_휴식_주기를_따라간다(qapp):
    from eyeexercise.core.settings import Settings
    from eyeexercise.core.settings_manager import SettingsManager

    manager = SettingsManager(Settings())
    window = MainWindow(settings_manager=manager)
    assert window.records_tab._interval_minutes() == 20
    manager.update({"interval_minutes": 45})
    assert window.records_tab._interval_minutes() == 45  # 휴식 달성률의 권장 횟수가 새 주기를 쓴다
    assert MainWindow().records_tab._interval_minutes() == 20  # 설정이 없으면 기본 주기
