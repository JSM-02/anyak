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
def test_아이콘은_크기마다_초록_바탕에_괄호와_물방울이_그려진다(size):
    image = render_icon(size)
    assert (image.width(), image.height()) == (size, size)
    assert image.pixelColor(0, 0).alpha() == 0  # 모서리는 투명(둥근 사각형)
    top = image.pixelColor(size // 2, max(2, size // 8))  # 위쪽 바탕은 깊은 초록 한 색이다
    assert top.name() == "#12544f"
    mark = QColor("#F2E3B3")

    def is_mark(c):
        return abs(c.red() - mark.red()) < 40 and abs(c.green() - mark.green()) < 40 and abs(c.blue() - mark.blue()) < 60

    # 물방울은 가운데 아래쪽에 모래색으로 있다
    assert is_mark(image.pixelColor(size // 2, round(size * 0.58)))
    # 괄호는 왼쪽과 오른쪽 가장자리 안쪽에 모래색 획으로 있다 (가운데 높이)
    row = round(size * 0.5)
    left = [image.pixelColor(x, row) for x in range(round(size * 0.12), round(size * 0.30))]
    right = [image.pixelColor(x, row) for x in range(round(size * 0.70), round(size * 0.88))]
    # 작은 크기에서는 얇은 획이 번지므로 바탕(빨강 18)보다 확실히 밝은 곳이 있는지만 본다
    assert any(c.red() > 110 for c in left) and any(c.red() > 110 for c in right)


def test_아이콘은_그라데이션_없이_납작한_한_색_바탕이다():
    image = render_icon(128)
    colors = {image.pixelColor(64, y).name() for y in (10, 14, 20, 100, 112, 118)}
    assert colors == {"#12544f"}  # 위·아래 어디서나 같은 색


def test_아이콘에는_눈이나_새싹_같은_옛_그림이_없다():
    """이름이 (안)약으로 바뀌며 감은 눈과 새싹은 빠졌다. 가운데 위쪽(옛 새싹·눈 자리)은 바탕색 그대로다."""
    image = render_icon(128)
    assert image.pixelColor(100, 20).name() == "#12544f"  # 옛 새싹(오른쪽 위)
    assert image.pixelColor(64, 100).name() == "#12544f"  # 옛 속눈썹 쪽


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
