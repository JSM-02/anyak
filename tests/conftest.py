import os

# 테스트 중 창이 실제로 뜨지 않도록 화면 없는 플랫폼을 쓴다. QApplication을 만들기 전에 정해야 한다.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
