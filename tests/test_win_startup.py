import sys
import uuid

import pytest

from eyeexercise.platform import win_startup
from eyeexercise.platform.win_startup import WinAutoStart, startup_command

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")

EXE = r"C:\Program Files\쉬엄 테스트\Swieom.exe"


@pytest.fixture
def key_path():
    """진짜 Run 키 대신 이번 테스트만 쓰는 임시 키. 끝나면 지운다."""
    import winreg

    path = rf"Software\SwieomTest\{uuid.uuid4().hex}"
    yield path
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\SwieomTest")
    except OSError:
        pass  # 다른 테스트의 키가 남아 있거나 이미 없다


def make(key_path, command=f'"{EXE}"') -> WinAutoStart:
    return WinAutoStart(command=command, key_path=key_path)


def test_처음에는_꺼져_있다(key_path):
    auto = make(key_path)
    assert auto.is_available() is True
    assert auto.is_enabled() is False


def test_켜면_등록되고_끄면_지워진다(key_path):
    auto = make(key_path)
    auto.set_enabled(True)
    assert auto.is_enabled() is True
    auto.set_enabled(False)
    assert auto.is_enabled() is False


def test_이미_꺼져_있을_때_다시_꺼도_오류가_없다(key_path):
    auto = make(key_path)
    auto.set_enabled(False)
    auto.set_enabled(False)
    assert auto.is_enabled() is False


def test_이미_켜져_있을_때_다시_켜도_오류가_없다(key_path):
    auto = make(key_path)
    auto.set_enabled(True)
    auto.set_enabled(True)
    assert auto.is_enabled() is True


def test_등록한_값은_따옴표로_감싼_실행_파일_경로다(key_path):
    import winreg

    make(key_path).set_enabled(True)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        value, kind = winreg.QueryValueEx(key, win_startup.VALUE_NAME)
    assert value == f'"{EXE}"'  # 공백이 든 경로도 하나로 읽히게
    assert kind == winreg.REG_SZ


def test_폴더를_옮겨_경로가_달라지면_켜져_있을_때만_갱신한다(key_path):
    import winreg

    old = make(key_path, '"D:\\old\\Swieom.exe"')
    old.set_enabled(True)
    moved = make(key_path, '"E:\\new\\Swieom.exe"')
    moved.refresh()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        assert winreg.QueryValueEx(key, win_startup.VALUE_NAME)[0] == '"E:\\new\\Swieom.exe"'

    moved.set_enabled(False)
    moved.refresh()  # 꺼져 있으면 건드리지 않는다
    assert moved.is_enabled() is False


def test_다른_이름의_값은_건드리지_않는다(key_path):
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "OtherApp", 0, winreg.REG_SZ, r"C:\other.exe")
    auto = make(key_path)
    auto.set_enabled(True)
    auto.set_enabled(False)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        assert winreg.QueryValueEx(key, "OtherApp")[0] == r"C:\other.exe"


def test_명령이_없으면_쓸_수_없고_켜지_않는다(key_path):
    auto = WinAutoStart(command=None, key_path=key_path)
    assert auto.is_available() is False
    assert auto.is_enabled() is False
    auto.set_enabled(True)  # 소스로 개발 중일 때: 아무것도 쓰지 않는다
    assert auto.is_enabled() is False
    auto.refresh()


def test_레지스트리_쓰기가_거부돼도_예외를_밖으로_내지_않는다(key_path, monkeypatch):
    import winreg

    def deny(*args, **kwargs):
        raise PermissionError("거부됨")

    monkeypatch.setattr(winreg, "CreateKeyEx", deny)
    auto = make(key_path)
    assert auto.set_enabled(True) is False  # 실패했다고 알려 준다
    assert auto.is_enabled() is False


def test_소스로_실행하면_명령이_없다(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert startup_command() is None


def test_exe로_실행하면_실행_파일_경로를_따옴표로_감싼다(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", EXE)
    assert startup_command() == f'"{EXE}"'
