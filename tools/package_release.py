"""빌드한 폴더(dist/Anyak)를 배포용 zip으로 묶는다.

사용법 (먼저 exe를 빌드한다):
    .venv\\Scripts\\python -m PyInstaller eyeexercise.spec --noconfirm
    .venv\\Scripts\\python tools\\package_release.py

zip 맨 위에 README·LICENSE·서드파티 고지·라이선스 전문을 함께 넣어, 받는 사람이 바로 볼 수 있게 한다.
"""

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from eyeexercise import __version__  # noqa: E402

TOP_FILES = ["README.md", "LICENSE", "THIRD-PARTY-NOTICES.txt"]
TOP_DIRS = ["LICENSES", "docs/images"]  # README의 스크린샷이 압축을 푼 뒤에도 보이게 한다


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "Anyak", help="빌드 결과 폴더")
    parser.add_argument("--out", type=Path, default=None, help="만들 zip 경로 (기본: dist/Anyak-<버전>-win64.zip)")
    args = parser.parse_args()

    if not (args.dist / "Anyak.exe").is_file():
        print(f"빌드 결과가 없습니다: {args.dist / 'Anyak.exe'}  (먼저 PyInstaller로 빌드하세요)", file=sys.stderr)
        return 1
    out = args.out or ROOT / "dist" / f"Anyak-{__version__}-win64.zip"
    folder = f"Anyak-{__version__}"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(args.dist.rglob("*")):
            if path.is_file():
                z.write(path, f"{folder}/{path.relative_to(args.dist).as_posix()}")
        for name in TOP_FILES:
            z.write(ROOT / name, f"{folder}/{name}")
        for name in TOP_DIRS:
            for path in sorted((ROOT / name).rglob("*")):
                if path.is_file():
                    z.write(path, f"{folder}/{name}/{path.relative_to(ROOT / name).as_posix()}")

    print(f"{out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
