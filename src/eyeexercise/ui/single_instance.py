"""단일 인스턴스.

- 첫 인스턴스 판별: QLockFile. (Windows에서는 QLocalServer.listen이 배타적이지 않아
  서로 다른 프로세스도 같은 이름으로 성공하므로, listen만으로는 중복 실행을 막을 수 없다.)
- 알림 전달: QLocalServer/QLocalSocket (로컬 이름 있는 파이프). 네트워크 통신이 아니다.
  두 번째 인스턴스가 첫 인스턴스에 "창을 열어 달라"고 알린 뒤 종료한다.
"""

import logging
import os
import re

from PySide6.QtCore import QDir, QElapsedTimer, QLockFile, QObject, QThread, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

_RETRY_SLEEP_MS = 50
_IO_TIMEOUT_MS = 1000


def default_name() -> str:
    """사용자별로 이름을 나눠 여러 Windows 세션이 서로 막지 않게 한다."""
    user = re.sub(r"[^A-Za-z0-9_]", "_", os.environ.get("USERNAME", "user"))
    return f"Swieom-{user}"


class SingleInstance(QObject):
    activated = Signal()  # 다른 인스턴스가 "창을 열어 달라"고 알려 왔다

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name or default_name()
        self._lock = QLockFile(os.path.join(QDir.tempPath(), f"{self._name}.lock"))
        # 오래 실행되는 앱이므로 '오래된 잠금'을 시간으로 판단하지 않는다.
        # 소유 프로세스가 사라진 잠금은 이 설정과 무관하게 정리된다.
        self._lock.setStaleLockTime(0)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)

    def acquire(self) -> bool:
        """이 프로세스가 첫 인스턴스면 True, 이미 다른 인스턴스가 있으면 False."""
        if not self._lock.tryLock(0):
            return False
        if not self._server.listen(self._name):
            log.warning("알림 수신용 서버를 열지 못했습니다: %s", self._server.errorString())
        return True

    def release(self) -> None:
        self._server.close()
        self._lock.unlock()

    def notify_primary(self, timeout_ms: int = _IO_TIMEOUT_MS) -> bool:
        """실행 중인 첫 인스턴스에 알린다. 첫 인스턴스가 서버를 여는 중일 수 있어 잠시 재시도한다."""
        deadline = QElapsedTimer()
        deadline.start()
        while True:
            socket = QLocalSocket()
            socket.connectToServer(self._name)
            if socket.waitForConnected(_IO_TIMEOUT_MS):
                socket.write(b"activate")
                socket.waitForBytesWritten(_IO_TIMEOUT_MS)
                socket.disconnectFromServer()
                if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                    socket.waitForDisconnected(_IO_TIMEOUT_MS)
                return True
            if deadline.hasExpired(timeout_ms):
                return False
            QThread.msleep(_RETRY_SLEEP_MS)

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.disconnected.connect(socket.deleteLater)
            self.activated.emit()
