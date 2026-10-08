from PySide6.QtWidgets import QWidget

from eyeexercise.core.history import History
from eyeexercise.ui.main_window import MainWindow
from eyeexercise.ui.page_column import MAX_CONTENT_WIDTH, centered_column


def test_본문은_최대_너비를_넘어_늘어나지_않고_가운데에_놓인다(qapp):
    content = QWidget()
    wrapper = centered_column(content)
    wrapper.resize(2000, 400)
    wrapper.show()
    qapp.processEvents()
    assert content.width() == MAX_CONTENT_WIDTH
    assert content.x() == (2000 - MAX_CONTENT_WIDTH) // 2  # 양옆 여백이 같다
    wrapper.close()


def test_창이_좁으면_본문은_창_너비에_맞춰_줄어든다(qapp):
    content = QWidget()
    wrapper = centered_column(content)
    wrapper.resize(700, 400)
    wrapper.show()
    qapp.processEvents()
    assert 690 <= content.width() <= 700  # 거의 창 너비 전부
    wrapper.close()


def test_메인_창을_크게_키워도_모든_화면의_본문_너비가_그대로다(qapp):
    window = MainWindow(History())
    window.resize(2200, 1000)
    window.show()
    qapp.processEvents()
    for index, page in enumerate((window.home_page, window.records_tab, window.vision_page, window.settings_page)):
        window.sidebar.set_current(index)
        qapp.processEvents()
        scroll_content = page.findChildren(QWidget, "pageColumn")[0]
        inner = scroll_content.layout().itemAt(1).widget()
        assert inner.width() <= MAX_CONTENT_WIDTH, index
        assert inner.width() > 800, index  # 너무 좁아지지도 않는다
    window.close()
