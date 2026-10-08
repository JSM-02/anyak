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
    return f"Swieom-test-{uuid.uuid4().hex}"


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


# ---- 다른 프로세스가 파이프로 쓰레기 데이터를 보내도 안전한지 (8a-②) ----


def _connect_raw(name):
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(name)
    assert socket.waitForConnected(1000)
    return socket


def _buffered_bytes(instance) -> int:
    """서버가 들고 있는 연결들이 읽지 않고 쌓아 둔 바이트 수."""
    from PySide6.QtNetwork import QLocalSocket

    return sum(s.bytesAvailable() for s in instance._server.findChildren(QLocalSocket))


def test_큰_데이터를_보내도_서버가_메모리에_쌓아_두지_않는다(name):
    import os

    first = SingleInstance(name)
    assert first.acquire()
    client = _connect_raw(name)
    chunk = os.urandom(1024 * 1024)
    for _ in range(8):
        client.write(chunk)
        client.waitForBytesWritten(200)
        QTest.qWait(30)
    QTest.qWait(200)
    assert _buffered_bytes(first) < 64 * 1024
    client.abort()
    first.release()


@pytest.mark.parametrize(
    "payload",
    [b"", b"\x00" * 100_000, b"\xff\xfe\xfd" * 5000, b"activate" * 20_000, "쉬엄".encode("utf-16"), b"\r\n" * 1000],
    ids=["빈_데이터", "널_바이트", "깨진_바이트", "activate_반복", "utf16_글자", "줄바꿈_반복"],
)
def test_쓰레기_데이터를_받아도_이후_알림은_정상이다(name, payload):
    first = SingleInstance(name)
    assert first.acquire()
    received = []
    first.activated.connect(lambda: received.append(1))

    client = _connect_raw(name)
    if payload:
        client.write(payload)
        client.waitForBytesWritten(500)
    client.abort()
    QTest.qWait(100)

    before = len(received)
    _connect_raw(name).abort()  # 이후 연결이 정상으로 받아들여지는지 (notify_primary는 느려서 쓰지 않는다)
    assert wait_until(lambda: len(received) > before)
    first.release()


def test_연결만_하고_아무것도_보내지_않아도_다음_알림이_된다(name):
    first = SingleInstance(name)
    assert first.acquire()
    received = []
    first.activated.connect(lambda: received.append(1))
    idle = [_connect_raw(name) for _ in range(5)]  # 연결을 쥐고만 있는 클라이언트들

    _connect_raw(name).abort()
    assert wait_until(lambda: len(received) >= 6)
    for c in idle:
        c.abort()
    first.release()


def test_끊긴_연결의_소켓은_정리된다(name):
    from PySide6.QtNetwork import QLocalSocket

    first = SingleInstance(name)
    assert first.acquire()
    for _ in range(10):
        _connect_raw(name).abort()
    QTest.qWait(100)
    # deleteLater는 이벤트 루프가 돌아야 처리된다
    assert wait_until(lambda: not first._server.findChildren(QLocalSocket))
    first.release()
