import sys

from eyeexercise import APP_NAME, __version__


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {__version__}")
        return 0

    from eyeexercise.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
