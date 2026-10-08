# 쉬엄

PC를 쓰는 동안 일정 간격으로 눈 운동을 알려 주는 Windows 트레이 상주 앱입니다.
(코드 이름: EyeExercise)

> 개발 중입니다. 아직 배포용 exe는 없고, 소스에서 직접 실행할 수 있습니다.

## 기능
- **주기 알림:** 기본 20분마다 눈 휴식을 알려 줍니다. 간격은 설정에서 바꿀 수 있습니다.
- **눈 휴식:** 눈 깜빡임 운동과 먼 곳 바라보기를 안내합니다. 눈을 감고도 들을 수 있게 음성이나 알림음으로 알려 줍니다.
- **눈 운동:** 화면의 점을 눈으로 따라가는 운동 가이드입니다.
- **미루기 / 건너뛰기:** 지금 쉬기 어려우면 알림을 미루거나 건너뜁니다.
- **기록:** 일별 휴식·운동 기록과 달성률, 스크린 타임(시간대별 PC 사용 시간), 시력 기록을 보여 줍니다.
- **트레이 상주:** 메인 창을 닫아도 종료하지 않고 트레이로 숨습니다. 종료는 트레이 메뉴의 "종료"로 합니다.
- 라이트·다크 모드를 지원합니다.

## 개인정보
쉬엄은 필요한 최소한의 정보만 이 PC에 저장합니다.

- **카메라를 사용하지 않습니다.**
- **네트워크 통신을 하지 않습니다.** 데이터를 외부로 전송하는 코드가 없습니다.
- **키 입력 내용을 수집하지 않습니다.** 자리 비움과 스크린 타임은 Windows의 "마지막 입력 시각"(`GetLastInputInfo`)만 보고 입력이 있었는지 여부만 판단합니다. 어떤 키를 눌렀는지는 알 수 없습니다.
- **어떤 프로그램을 쓰는지, 창 제목은 수집하지 않습니다.**
- 이 원칙은 자동 테스트(`tests/test_forbidden_imports.py`)로 고정되어 있어서, 네트워크·카메라·키 입력 관련 코드가 들어오면 테스트가 실패합니다.

### 저장되는 것
데이터는 이 PC의 `%APPDATA%\Swieom` 폴더에만 JSON 파일로 저장됩니다. 지우면 기록이 사라집니다.
(Windows 로밍 프로필이나 클라우드 백업을 켜 둔 환경에서는 Windows가 이 폴더를 동기화할 수 있습니다. 쉬엄이 보내는 것은 아닙니다.)

| 파일 | 내용 |
|---|---|
| `settings.json` | 설정 |
| `history.json` | 휴식·운동·미루기·건너뛰기 기록 |
| `usage.json` | 시간대별 PC 사용 시간 |
| `vision.json` | 직접 입력한 시력 기록 |

파일이 손상되면 `.corrupt` 이름으로 백업하고 새로 시작합니다.

## 소스에서 실행하기
Windows와 Python 3.12가 필요합니다.

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m eyeexercise
```

테스트:

```
.venv\Scripts\python -m pytest
```

## 구조
- `src/eyeexercise/core/`: 스케줄러, 미루기/건너뛰기, 기록 집계 같은 판단 로직. Qt 없는 순수 Python이라 pytest로 바로 테스트합니다.
- `src/eyeexercise/ui/`: PySide6 화면. 얇게 유지하고 `core/`를 호출만 합니다.
- `src/eyeexercise/platform/`: Windows 전용 호출(유휴 시간, 창 설정).
- `src/eyeexercise/storage/`: JSON 저장과 손상 복구.
- 시간과 유휴 시간은 주입할 수 있게 만들어서 테스트에서 가짜로 바꿉니다.

## 사용한 오픈소스
- [PySide6 (Qt for Python)](https://doc.qt.io/qtforpython-6/): GUI. LGPL v3 등으로 제공됩니다.
- [pytest](https://pytest.org/): 테스트.
- [PyInstaller](https://pyinstaller.org/): exe 빌드(예정).

## 라이선스
[MIT 라이선스](LICENSE)입니다. 작동에 대한 보증이 없고, 사용으로 생긴 문제에 책임지지 않습니다.

쉬엄이 사용하는 PySide6(Qt)는 별도의 라이선스(LGPL v3 등)를 따릅니다. 이 라이선스는 위 MIT와 별개이며, exe로 배포할 때는 해당 라이선스 고지를 함께 제공합니다.
