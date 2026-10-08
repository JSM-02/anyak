"""앱 전체가 함께 쓰는 색·글자 크기와 라이트/다크 전환.

화면마다 색을 직접 적지 않고 여기의 이름(토큰)을 쓴다. 스타일시트 문자열에는 `$text`, `$card` 같은
자리표시자를 쓰고 `bind()`로 위젯에 붙이면, Windows 설정이 바뀔 때 모든 화면이 새 색으로 다시 칠해진다.
직접 그리는 위젯(차트·스위치·점 화면)은 그릴 때마다 `palette()`에서 색을 읽는다.
"""

import weakref
from dataclasses import asdict, dataclass
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class Palette:
    # 바탕
    bg: str  # 페이지 바탕
    surface: str  # 카드·팝업·입력칸 바탕
    sidebar: str
    sidebar_border: str
    hover: str  # 버튼에 마우스를 올렸을 때, 분할 버튼의 바탕
    chip: str  # 연한 버튼·표시 바탕
    # 선
    border: str  # 카드 테두리
    border_strong: str  # 팝업·창 테두리
    input_border: str
    divider: str  # 카드 안 구분선
    grid: str  # 차트 가로선
    # 글자
    text: str
    text_body: str
    text_secondary: str
    text_muted: str
    text_faint: str
    on_accent: str  # 강조색 버튼 위의 글자
    # 강조
    accent: str
    accent_hover: str
    accent_soft: str
    accent_disabled: str
    disabled: str
    track: str  # 슬라이더 홈
    switch_off: str
    switch_off_disabled: str
    knob: str  # 스위치·슬라이더 손잡이
    danger: str
    warning: str
    # 디자인 토대(9a): 히어로 카드·포인트 모래색·달성률 게이지의 세 색·사이드바
    hero: str
    sand: str
    gauge_good: str
    gauge_mid: str
    gauge_low: str
    sidebar_text: str
    sidebar_pill: str
    ink: str  # 모래색·밝은 초록처럼 채운 바탕 위에 쓰는 글자색. 라이트·다크 모두 같은 짙은 초록이다


LIGHT = Palette(
    bg="#EAF1EE",
    surface="#ffffff",
    sidebar="#092328",
    sidebar_border="#092328",
    hover="#D5E4DE",
    chip="#DFEBE6",
    border="#DDE8E4",
    border_strong="#B7CBC4",
    input_border="#8AA39C",
    divider="#E3ECE8",
    grid="#DDE8E4",
    text="#092328",
    text_body="#2F4A46",
    text_secondary="#4F6B66",
    text_muted="#5F7B76",
    text_faint="#8AA39C",
    on_accent="#ffffff",
    accent="#2A835F",
    accent_hover="#206B4D",
    accent_soft="#D6EBDD",
    accent_disabled="#A9CFBD",
    disabled="#B7CBC4",
    track="#DDE8E4",
    switch_off="#8AA39C",
    switch_off_disabled="#DDE8E4",
    knob="#ffffff",
    danger="#c5221f",
    warning="#9a5400",
    hero="#12544F",
    sand="#F2E3B3",
    gauge_good="#2A835F",
    gauge_mid="#D9A03A",
    gauge_low="#D9622B",
    sidebar_text="#9FC8A6",
    sidebar_pill="#12544F",
    ink="#092328",
)

DARK = Palette(
    bg="#0c1a1d",
    surface="#13262a",
    sidebar="#071316",
    sidebar_border="#071316",
    hover="#1d3338",
    chip="#1a2f33",
    border="#223a3f",
    border_strong="#33545a",
    input_border="#4d6e73",
    divider="#1f353a",
    grid="#223a3f",
    text="#e6f0ec",
    text_body="#c5d8d2",
    text_secondary="#9db9b2",
    text_muted="#7fa099",
    text_faint="#5e7e7a",
    on_accent="#06231a",
    accent="#5bc293",
    accent_hover="#82d6ab",
    accent_soft="#173b33",
    accent_disabled="#2e5a4b",
    disabled="#35494d",
    track="#2a4247",
    switch_off="#587276",
    switch_off_disabled="#2a4247",
    knob="#e6f0ec",
    danger="#f28b82",
    warning="#fdc569",
    hero="#12544f",
    sand="#e8d79c",
    gauge_good="#5bc293",
    gauge_mid="#e3b04b",
    gauge_low="#f0805a",
    sidebar_text="#9fc8a6",
    sidebar_pill="#15423c",
    ink="#092328",
)

# 글자 크기(px). 화면마다 제각각이던 값을 이 여덟 가지로 맞춘다.
FONT_SIZES = {
    "fs_caption": 12,
    "fs_small": 13,
    "fs_body": 14,
    "fs_heading": 16,
    "fs_icon": 20,
    "fs_title": 24,
    "fs_stat": 28,
    "fs_display": 40,
}
FONT_FAMILIES = ("Segoe UI", "Malgun Gothic")  # 영문·숫자는 Segoe UI, 한글은 맑은 고딕

_palette = LIGHT
_system_palette: QPalette | None = None  # 다크로 바꾸기 전의 기본 팔레트. 라이트로 돌아올 때 되돌린다

# 스크롤바는 스타일시트로 칠하지 않으면 시스템 기본(밝은) 모양이 남는다
_SCROLLBAR_STYLE = """
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $track; border-radius: 4px; min-height: 28px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: $switch_off; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: $track; border-radius: 4px; min-width: 28px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: $switch_off; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; border: none; width: 0; height: 0; }
"""


_listeners: list = []  # 테마가 바뀐 뒤 부를 함수. 메서드는 약한 참조로 들고 있어 위젯이 지워지는 것을 막지 않는다
_bound: list[tuple[weakref.ref, str]] = []


def palette() -> Palette:
    return _palette


def is_dark() -> bool:
    return _palette is DARK


def color(name: str) -> QColor:
    """팔레트의 이름으로 QColor를 얻는다. 직접 그리는 위젯이 쓴다."""
    return QColor(getattr(_palette, name))


def render(template: str) -> str:
    """스타일시트 틀의 `$이름`을 지금 팔레트·글자 크기로 채운다."""
    values: dict[str, str | int] = dict(asdict(_palette))
    values.update({name: f"{px}px" for name, px in FONT_SIZES.items()})
    return Template(template + _SCROLLBAR_STYLE).substitute(values)


def bind(widget: QWidget, template: str) -> None:
    """위젯에 스타일시트를 붙이고, 테마가 바뀌면 다시 채워서 붙인다."""
    _bound.append((weakref.ref(widget), template))
    widget.setStyleSheet(render(template))


def set_dark(dark: bool) -> None:
    """라이트/다크를 바꾸고 붙여 둔 스타일시트를 모두 다시 적용한다."""
    global _palette
    new = DARK if dark else LIGHT
    if new is _palette:
        return
    _palette = new
    _apply_app_palette()
    alive = []
    for ref, template in _bound:
        widget = ref()
        if widget is None:
            continue
        try:
            widget.setStyleSheet(render(template))
            _repolish(widget)
        except RuntimeError:  # C++ 쪽이 이미 사라진 위젯
            continue
        alive.append((ref, template))
    _bound[:] = alive
    for listener in list(_listeners):
        callback = listener() if isinstance(listener, weakref.WeakMethod) else listener
        if callback is None:
            _listeners.remove(listener)
            continue
        try:
            callback()
        except RuntimeError:  # C++ 쪽이 이미 사라진 위젯의 메서드
            _listeners.remove(listener)


def _repolish(widget: QWidget) -> None:
    """스타일을 새로 적용한다. 아직 한 번도 보이지 않은 창(팝업·운동 창)은 스타일 시트만 바꾸면 이전 색이 남아서,
    다크 모드로 바뀐 뒤 처음 뜰 때 옛 색으로 보인다."""
    for w in (widget, *widget.findChildren(QWidget)):
        w.style().unpolish(w)
        w.style().polish(w)


def on_changed(callback) -> None:
    """테마가 바뀐 뒤 불린다. 스타일시트로 칠하지 않는 위젯이 다시 그리도록 쓴다."""
    _listeners.append(weakref.WeakMethod(callback) if hasattr(callback, "__self__") else callback)


def _apply_app_palette() -> None:
    """스타일시트가 닿지 않는 기본 위젯(글자, 선택 색 등)도 같은 색을 쓰도록 앱 팔레트를 맞춘다."""
    global _system_palette
    app = QGuiApplication.instance()
    if app is None:
        return
    if _palette is LIGHT:
        if _system_palette is not None:
            app.setPalette(_system_palette)
            _system_palette = None
        return
    if _system_palette is None:
        _system_palette = QPalette(app.palette())
    p, qp = _palette, QPalette()
    for role, name in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "chip"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "chip"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "on_accent"),
        (QPalette.ColorRole.PlaceholderText, "text_muted"),
        (QPalette.ColorRole.ToolTipBase, "surface"),
        (QPalette.ColorRole.ToolTipText, "text"),
    ):
        qp.setColor(role, QColor(getattr(p, name)))
    app.setPalette(qp)


def _reset_for_tests() -> None:
    """테스트가 앞선 테스트에서 남은 위젯·연결에 영향받지 않도록 등록을 비운다."""
    _bound.clear()
    global _mode
    _mode = "system"
    _listeners.clear()
    set_dark(False)


_mode = "system"  # 설정의 화면 모드: system(Windows를 따라감) / light / dark
_SCHEMES = {"system": Qt.ColorScheme.Unknown, "light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}


def _resolve() -> None:
    if _mode == "system":
        app = QGuiApplication.instance()
        set_dark(app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    else:
        set_dark(_mode == "dark")


def set_mode(mode: str) -> None:
    """화면 모드를 정한다. 'system'이면 Windows의 앱 모드를 따라가고, 'light'·'dark'면 고정한다."""
    global _mode
    _mode = mode if mode in _SCHEMES else "system"
    app = QGuiApplication.instance()
    if app is not None:
        app.styleHints().setColorScheme(_SCHEMES[_mode])  # 창 제목 막대 같은 시스템 부분도 같은 모드로
    _resolve()


def follow_system(app: QGuiApplication) -> None:
    """Windows의 앱 모드(라이트/다크)가 바뀌면 바로 반영한다 ('시스템 설정' 모드일 때만 따라간다)."""
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: _resolve())
    _resolve()


def apply_app_font(app: QGuiApplication) -> None:
    font = QFont(app.font())
    font.setFamilies(list(FONT_FAMILIES))
    app.setFont(font)
