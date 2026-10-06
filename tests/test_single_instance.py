import uuid

import pytest
from PySide6.QtTest import QTest

from eyeexercise.ui.single_instance import SingleInstance


def wait_until(condition, timeout_ms: int = 3000) -> bool:
    """이벤트를 처리하면서 조건이 참이 될 때까지 기다린다 (PySide6의 QTest에는 qWaitFor가 없다)."""
    waited = 0
    while waited < timeout_ms:
        if condition():
            return True
        QTest.qWait(20)
        waited += 20
    return condition()


@pytest.fixture
def name(qapp):
    # 테스트끼리, 그리고 실제 앱과 이름이 겹치지 않게 매번 새 이름을 쓴다
    return f"EyeExercise-test-{uuid.uuid4().hex}"


def test_첫_인스턴스만_획득에_성공한다(name):
    first, second = SingleInstance(name), SingleInstance(name)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()


def test_두_번째_인스턴스가_알리면_첫_인스턴스에_activated가_온다(name):
    first, second = SingleInstance(name), SingleInstance(name)
    assert first.acquire()
    received = []
    first.activated.connect(lambda: received.append(1))

    assert second.acquire() is False
    assert second.notify_primary() is True

    assert wait_until(lambda: bool(received))
    first.release()


def test_첫_인스턴스가_없으면_알리기에_실패한다(name):
    assert SingleInstance(name).notify_primary(timeout_ms=200) is False


def test_해제하면_다른_인스턴스가_획득할_수_있다(name):
    first, second = SingleInstance(name), SingleInstance(name)
    assert first.acquire()
    first.release()
    assert second.acquire() is True
    second.release()
