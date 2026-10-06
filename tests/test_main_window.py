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
