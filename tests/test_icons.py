import struct
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

from eyeexercise.ui.icons import ICO_SIZES, ICON_SIZES, app_icon, ico_bytes, render_icon

ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


def parse_ico(data: bytes):
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    entries = []
    for i in range(count):
        w, h, _c, _r, _planes, bits, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        entries.append((w or 256, h or 256, bits, data[offset : offset + size]))
    return reserved, kind, entries


@pytest.mark.parametrize("size", ICON_SIZES)
def test_아이콘은_크기마다_초록_바탕에_흰_눈이_그려진다(size):
    image = render_icon(size)
    assert (image.width(), image.height()) == (size, size)
    assert image.pixelColor(0, 0).alpha() == 0  # 모서리는 투명(둥근 사각형)
    top = image.pixelColor(size // 2, max(1, size // 10))  # 눈 위쪽 바탕
    assert top.green() > top.red() + 40 and top.green() > top.blue() + 30  # 초록 계열
    # 눈 가장자리 안쪽 흰 부분
    white = image.pixelColor(int(size * 0.27), size // 2)
    assert min(white.red(), white.green(), white.blue()) > 200


def test_아이콘에_여러_크기가_담겨_배율에서도_또렷하다(qapp):
    icon = app_icon()
    sizes = {s.width() for s in icon.availableSizes()}
    assert {16, 24, 32, 48, 256} <= sizes
    assert not icon.isNull()


def test_ico_파일은_여러_크기의_PNG를_담는다():
    reserved, kind, entries = parse_ico(ico_bytes())
    assert (reserved, kind) == (0, 1)
    assert [(w, h) for w, h, _b, _d in entries] == [(s, s) for s in ICO_SIZES]
    assert all(bits == 32 and data[:8] == b"\x89PNG\r\n\x1a\n" for _w, _h, bits, data in entries)


def test_배포용_ico와_png가_저장소에_있고_올바른_모양이다():
    reserved, kind, entries = parse_ico((ICON_DIR / "app.ico").read_bytes())
    assert (reserved, kind) == (0, 1)
    assert [w for w, _h, _b, _d in entries] == list(ICO_SIZES)
    assert (ICON_DIR / "app.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_아이콘_색은_테마와_상관없이_늘_같다(qapp):
    from eyeexercise.ui import theme

    theme._reset_for_tests()
    light = render_icon(64)
    theme.set_dark(True)
    dark = render_icon(64)
    theme._reset_for_tests()
    assert light == dark
