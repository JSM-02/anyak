# PyInstaller 설정. 빌드: .venv\Scripts\python -m PyInstaller eyeexercise.spec --noconfirm
#
# - 폴더형(onedir): PySide6(LGPL)의 Qt 라이브러리가 별도 파일로 들어가 사용자가 교체할 수 있다.
# - UPX 압축은 쓰지 않는다 (백신 오탐이 잦다).
# - 관리자 권한을 요구하지 않는다 (uac_admin=False).
# - 창 없는 앱(console=False): 트레이에 상주한다.

a = Analysis(
    ["src/eyeexercise/__main__.py"],
    pathex=["src"],
    datas=[("assets/sounds", "assets/sounds"), ("THIRD-PARTY-NOTICES.txt", "."), ("LICENSE", "."), ("LICENSES", "LICENSES")],
    hiddenimports=[],
    excludes=[
        # 쓰지 않는 Qt 모듈은 빼서 용량과 공격 면적을 줄인다. (네트워크·웹·카메라 관련은 원칙상 반드시 뺀다)
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtWebView",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtSql",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtRemoteObjects",
        "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Swieom",
    icon="assets/icons/app.ico",
    console=False,
    upx=False,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Swieom",
)
