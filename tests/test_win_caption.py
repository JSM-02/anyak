from eyeexercise.platform.win_caption import colorref
from eyeexercise.ui import theme
from eyeexercise.ui.main_window import MainWindow


def test_색은_BGR_순서의_COLORREF가_된다():
    assert colorref("#F8F8F5") == 0xF5F8F8
    assert colorref("#12544f") == 0x4F5412
    assert colorref("#000000") == 0 and colorref("#ffffff") == 0xFFFFFF


def test_창이_뜰_때_제목_막대를_종이색으로_맞춘다(qapp):
    theme._reset_for_tests()
    calls = []
    window = MainWindow(caption_colors=lambda hwnd, bg, text: calls.append((bg, text)))
    window.show()
    qapp.processEvents()
    paper = theme.palette().paper
    assert calls and calls[-1] == (paper, paper)  # 글자도 바탕색이라 이름이 두 번 보이지 않는다


def test_다크_모드로_바뀌면_제목_막대도_따라간다(qapp):
    theme._reset_for_tests()
    calls = []
    window = MainWindow(caption_colors=lambda hwnd, bg, text: calls.append(bg))
    window.show()
    theme.set_dark(True)
    qapp.processEvents()
    dark_paper = theme.palette().paper
    theme._reset_for_tests()
    assert calls[-1] == dark_paper and calls[-1] != theme.LIGHT.paper


def test_색을_못_바꾸는_환경에서도_예외가_나지_않는다(qapp):
    from eyeexercise.platform.win_caption import set_caption_colors

    assert set_caption_colors(0, "#F8F8F5", "#F8F8F5") in (True, False)
