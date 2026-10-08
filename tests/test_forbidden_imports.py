"""프로젝트 원칙(카메라·네트워크·키 입력·창/프로그램 정보 수집 없음)을 코드로 고정하는 검사.

소스를 실행하지 않고 AST로 import와 위험한 이름을 훑는다. 원칙을 바꿀 때(예: 새 기능 추가)는
CLAUDE.md·docs/plan.md·README의 안내를 먼저 고치고, 아래 금지 목록이나 허용 예외를 함께 바꾼다.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [ROOT / "src", ROOT / "tools"]

# 최상위 모듈 이름이 이것이면 금지. 하위 모듈은 모듈 이름의 앞부분이 같으면 함께 금지된다.
FORBIDDEN_MODULES = {
    # 네트워크
    "socket": "네트워크 통신 없음",
    "ssl": "네트워크 통신 없음",
    "urllib": "네트워크 통신 없음",
    "urllib3": "네트워크 통신 없음",
    "http": "네트워크 통신 없음",
    "ftplib": "네트워크 통신 없음",
    "smtplib": "네트워크 통신 없음",
    "xmlrpc": "네트워크 통신 없음",
    "asyncio": "네트워크 통신 없음(비동기 소켓)",
    "requests": "네트워크 통신 없음",
    "httpx": "네트워크 통신 없음",
    "aiohttp": "네트워크 통신 없음",
    "websocket": "네트워크 통신 없음",
    "websockets": "네트워크 통신 없음",
    "PySide6.QtNetwork": "네트워크 통신 없음 (단일 인스턴스용 로컬 파이프만 예외)",
    "PySide6.QtWebEngineCore": "네트워크 통신 없음",
    "PySide6.QtWebEngineWidgets": "네트워크 통신 없음",
    "PySide6.QtWebSockets": "네트워크 통신 없음",
    "PySide6.QtWebChannel": "네트워크 통신 없음",
    # 카메라
    "cv2": "카메라를 사용하지 않는다",
    "PySide6.QtMultimediaWidgets": "카메라 미리보기 화면은 쓰지 않는다",
    "mediapipe": "카메라를 사용하지 않는다",
    "dlib": "카메라를 사용하지 않는다",
    "imageio": "카메라를 사용하지 않는다",
    "pygrabber": "카메라를 사용하지 않는다",
    # 키 입력 수집
    "pynput": "키 입력 내용을 수집하지 않는다",
    "keyboard": "키 입력 내용을 수집하지 않는다",
    "mouse": "입력 수집 후킹 없음",
    "pyHook": "키 입력 내용을 수집하지 않는다",
    "pyautogui": "입력 수집·제어 없음",
    # 창 제목·프로그램 이름 수집
    "psutil": "어떤 프로그램을 쓰는지 수집하지 않는다",
    "win32gui": "창 제목을 수집하지 않는다",
    "win32process": "프로그램 이름을 수집하지 않는다",
    "win32api": "Win32 호출은 ctypes로 필요한 것만 쓴다",
    "pygetwindow": "창 제목을 수집하지 않는다",
    "pywinauto": "창 제목을 수집하지 않는다",
    "wmi": "프로그램 이름을 수집하지 않는다",
    # 외부 프로그램 실행·동적 import (위 금지 목록을 우회하는 길을 막는다)
    "subprocess": "외부 프로그램을 실행하지 않는다",
    "importlib": "동적 import로 이 검사를 피하지 않는다",
}

# 경로(ROOT 기준) → 그 파일에서만 허용하는 금지 모듈
ALLOWED_EXCEPTIONS = {
    "src/eyeexercise/ui/single_instance.py": {"PySide6.QtNetwork"},
}

# 코드에 이름으로 나오면 안 되는 Win32 함수·호출 (키 입력·창 제목·프로그램 이름 수집용)
FORBIDDEN_NAMES = {
    "SetWindowsHookEx": "키보드·마우스 훅",
    "SetWindowsHookExA": "키보드·마우스 훅",
    "SetWindowsHookExW": "키보드·마우스 훅",
    "GetAsyncKeyState": "키 입력 수집",
    "GetKeyState": "키 입력 수집",
    "GetKeyboardState": "키 입력 수집",
    "RegisterRawInputDevices": "키 입력 수집",
    "GetForegroundWindow": "지금 쓰는 창 수집",
    "GetWindowText": "창 제목 수집",
    "GetWindowTextA": "창 제목 수집",
    "GetWindowTextW": "창 제목 수집",
    "EnumWindows": "창 목록 수집",
    "GetWindowThreadProcessId": "프로그램 이름 수집",
    "OpenProcess": "프로그램 이름 수집",
    "QueryFullProcessImageName": "프로그램 이름 수집",
    "CreateToolhelp32Snapshot": "프로그램 목록 수집",
    "__import__": "동적 import로 이 검사를 피하지 않는다",
    "import_module": "동적 import로 이 검사를 피하지 않는다",
}


def _is_forbidden(module: str) -> str | None:
    """module이 금지 목록 항목과 같거나 그 하위 모듈이면 항목 이름을 돌려준다."""
    for banned in FORBIDDEN_MODULES:
        if module == banned or module.startswith(banned + "."):
            return banned
    return None


def find_violations(source: str, rel_path: str) -> list[str]:
    """소스 한 파일에서 금지 import·이름을 찾아 사람이 읽을 수 있는 문장으로 돌려준다."""
    allowed = ALLOWED_EXCEPTIONS.get(rel_path, set())
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # `from PySide6 import QtNetwork`처럼 가져온 이름이 하위 모듈일 수도 있어 함께 검사한다.
            modules = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
        for module in modules:
            banned = _is_forbidden(module)
            if banned and banned not in allowed:
                found.append(f"{rel_path}:{node.lineno}: import {module} ({FORBIDDEN_MODULES[banned]})")
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            name = node.name.split(".")[-1]
        if name in FORBIDDEN_NAMES:
            found.append(f"{rel_path}:{getattr(node, 'lineno', '?')}: {name} ({FORBIDDEN_NAMES[name]})")
    return found


def _source_files() -> list[Path]:
    return sorted(p for base in SCAN_DIRS for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def test_소스_파일을_찾는다():
    # 경로가 바뀌어 검사 대상이 0개가 되면 검사가 조용히 통과해 버리므로 막는다.
    files = _source_files()
    assert any(p.name == "app.py" for p in files)
    assert len(files) > 30


def test_금지된_모듈과_함수를_쓰지_않는다():
    violations: list[str] = []
    for path in _source_files():
        rel = path.relative_to(ROOT).as_posix()
        violations += find_violations(path.read_text(encoding="utf-8"), rel)
    assert not violations, "프로젝트 원칙에 어긋나는 코드:\n" + "\n".join(violations)


def test_허용_예외는_실제로_쓰이는_파일에만_둔다():
    # 예외 목록이 낡아서 쓰지 않는 구멍으로 남는 것을 막는다.
    for rel, modules in ALLOWED_EXCEPTIONS.items():
        path = ROOT / rel
        assert path.exists(), f"허용 예외의 파일이 없다: {rel}"
        text = path.read_text(encoding="utf-8")
        for module in modules:
            assert module.split(".")[-1] in text, f"{rel}는 {module}을 더 이상 쓰지 않는다. 예외를 지운다"


@pytest.mark.parametrize(
    "source",
    [
        "import socket",
        "import urllib.request",
        "from http import client",
        "import requests",
        "from PySide6.QtNetwork import QTcpSocket",
        "from PySide6 import QtNetwork",
        "import cv2",
        "import pynput.keyboard",
        "from pynput import keyboard",
        "import psutil",
        "import subprocess",
        "import importlib",
        "import ctypes\nctypes.windll.user32.SetWindowsHookExW(0, 0, 0, 0)",
        "import ctypes\nctypes.windll.user32.GetAsyncKeyState(0x41)",
        "import ctypes\nctypes.windll.user32.GetForegroundWindow()",
        "__import__('socket')",
        "def f():\n    import socket",
    ],
)
def test_검사기는_금지된_코드를_잡는다(source):
    assert find_violations(source, "src/eyeexercise/x.py")


@pytest.mark.parametrize(
    "source",
    [
        "import ctypes\nfrom ctypes import wintypes",
        "from PySide6.QtCore import QObject",
        "from PySide6.QtMultimedia import QSoundEffect",
        "import json, logging, datetime",
        "import mouse_helper",
        "from . import keyboard_layout",
    ],
)
def test_검사기는_허용된_코드를_통과시킨다(source):
    assert not find_violations(source, "src/eyeexercise/x.py")


def test_단일_인스턴스만_QtNetwork를_쓸_수_있다():
    source = "from PySide6.QtNetwork import QLocalServer"
    assert not find_violations(source, "src/eyeexercise/ui/single_instance.py")
    assert find_violations(source, "src/eyeexercise/ui/tray.py")
