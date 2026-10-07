"""앱 아이콘 파일 생성: assets/icons/app.ico(여러 크기)와 app.png(256)를 만든다.

아이콘 그림은 `eyeexercise.ui.icons`가 코드로 그린다. 디자인을 바꿨다면 이 스크립트를 다시 실행해
파일을 갱신한 뒤 커밋한다 (8단계 exe 빌드가 이 .ico를 쓴다).

    .venv\\Scripts\\python tools\\make_icon.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eyeexercise.ui.icons import ico_bytes, render_icon  # noqa: E402


def main() -> None:
    out = ROOT / "assets" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    (out / "app.ico").write_bytes(ico_bytes())
    render_icon(256).save(str(out / "app.png"), "PNG")
    print(f"만들었어요: {out / 'app.ico'}, {out / 'app.png'}")


if __name__ == "__main__":
    main()
