# EyeExercise 설계 계획 (확정)

## Context
CLAUDE.md의 원칙에 맞춰 폴더 구조, 모듈 의존 관계, 구현 순서, 데이터 구조를 정하고 기능 단위로 하나씩 구현한다.

합의한 내용:
- 알림은 화면 구석의 작은 팝업 창(항상 위, [시작] [미루기] [건너뛰기])으로 한다.
- 유휴 시간이 일시정지 기준(기본 1분) 이상이면 경과 시간 누적을 멈추고, 리셋 기준(기본 5분) 이상이면 타이머를 처음부터 다시 센다. 두 기준 모두 설정에서 바꿀 수 있다.
- 데이터는 `%APPDATA%\EyeExercise\`에 저장한다.
- 카메라는 인터페이스만 정의하고 구현은 나중에 한다.
- Python은 3.12를 사용한다. (3.10은 보안 지원 종료)
- 의존성은 `requirements.txt`에만 둔다. `pyproject.toml`은 패키지 정보와 pytest 설정만 담는다.

---

## 1. 폴더 구조와 모듈 역할

```
EyeExercise/
├─ pyproject.toml          # 패키지 정보, pytest 설정 (의존성은 넣지 않음)
├─ requirements.txt        # 런타임 의존성: PySide6
├─ requirements-dev.txt    # requirements.txt + pytest, pyinstaller
├─ .gitignore              # .venv/, build/, dist/, __pycache__/ 등
├─ README.md
├─ docs/plan.md            # 이 문서
├─ assets/icons/           # 트레이와 앱 아이콘 (.ico, .png)
├─ eyeexercise.spec        # PyInstaller 빌드 설정 (8단계)
├─ src/eyeexercise/
│  ├─ __main__.py          # 진입점: python -m eyeexercise
│  ├─ app.py               # 모든 모듈을 연결하는 조립 지점. QApplication 생성, 단일 인스턴스(QLockFile)
│  ├─ core/                # 순수 Python. PySide6 import 금지
│  │  ├─ clock.py          # Clock 프로토콜: monotonic(), now()
│  │  ├─ idle.py           # IdleSource 프로토콜: idle_seconds()
│  │  ├─ scheduler.py      # ReminderScheduler 상태 머신
│  │  ├─ settings.py       # Settings 데이터클래스, 기본값, 값 검증·보정
│  │  ├─ history.py        # 기록 이벤트 모델, 일별 집계
│  │  ├─ exercises.py      # 운동 정의, 단계 타임라인, 점 경로 계산
│  │  └─ camera.py         # BlinkDetector 프로토콜과 NullDetector만 둠
│  ├─ storage/
│  │  ├─ paths.py          # %APPDATA%\EyeExercise 경로 계산
│  │  └─ json_store.py     # 원자적 저장, 손상된 파일 백업 후 복구
│  ├─ platform/
│  │  └─ win_idle.py       # ctypes로 GetLastInputInfo 호출해 IdleSource 구현
│  └─ ui/                  # PySide6 사용
│     ├─ controller.py     # QTimer(1초)로 scheduler.tick() 호출, 결과 이벤트를 UI에 전달
│     ├─ tray.py           # 트레이 아이콘과 메뉴: 열기 / 지금 운동 / 일시정지 / 종료
│     ├─ reminder_popup.py # 알림 팝업
│     ├─ exercise_window.py# 깜빡임 운동과 점 따라가기 화면
│     └─ main_window.py    # 대시보드(기록 탭, 설정 탭). 닫으면 hide() 처리
└─ tests/                  # core와 storage 테스트. Qt 없이 실행
   ├─ fakes.py             # FakeClock, FakeIdle
   ├─ test_settings.py
   ├─ test_json_store.py
   ├─ test_scheduler.py
   ├─ test_history.py
   └─ test_exercises.py
```

src 레이아웃을 쓰는 이유: 테스트가 패키지 기준으로 import되므로 경로 문제를 일찍 잡을 수 있고, PyInstaller 진입점도 명확해진다.

## 2. 의존 관계 (GUI와 로직의 분리)

```
            app.py (조립)
           /    |     \
         ui/  storage/  platform/
          \     |      /
           ▼    ▼     ▼
              core/          ← 아무것도 import하지 않음 (표준 라이브러리만)
```

규칙:
- `core`는 PySide6, ctypes, 파일 I/O를 모른다. 시간은 `Clock`, 유휴 시간은 `IdleSource` 프로토콜로 주입받는다.
- 스케줄러는 스스로 타이머를 돌리지 않고 `tick()` 방식으로 동작한다. `controller`가 1초마다 `scheduler.tick()`을 호출하고, 스케줄러는 `ReminderDue` 같은 이벤트 목록을 반환한다. 테스트에서는 FakeClock으로 시간을 감아 검증한다.
- 사용자 동작(미루기, 건너뛰기, 시작, 완료)은 `ui` → `controller` → `scheduler`의 `snooze()`, `skip()`, `start_exercise()`, `finish_exercise()` 호출로 전달한다.
- `storage`는 `core`의 데이터클래스와 dict 사이를 변환하고 파일을 읽고 쓴다.
- `platform/win_idle.py`는 Windows 전용이다. 다른 모듈은 `IdleSource` 프로토콜에만 의존한다.

### 스케줄러 상태와 규칙
상태: `RUNNING`, `DUE`(팝업 표시 중), `SNOOZED`, `EXERCISING`, `PAUSED`(트레이에서 일시정지)

- RUNNING: 경과 시간이 `interval_minutes` 이상이면 DUE로 바뀌고 `ReminderDue` 이벤트를 낸다.
- DUE: 시작 → EXERCISING / 미루기 → SNOOZED(`snooze_minutes` 후 다시 DUE) / 건너뛰기 → RUNNING으로 리셋하고 기록에 남긴다.
- EXERCISING: 완료 또는 중단 → RUNNING으로 리셋한다.
- **유휴 시간 규칙** (RUNNING과 SNOOZED의 카운트다운에 적용):
  - 유휴 시간 < `idle_pause_minutes`(기본 1분): 정상 누적.
  - `idle_pause_minutes` ≤ 유휴 시간 < `idle_reset_minutes`(기본 5분): 경과 시간 누적을 멈춘다. 입력이 돌아오면 멈췄던 지점에서 이어서 센다. 유휴로 판정된 구간(유휴 시간 전체)은 누적에서 제외한다.
  - 유휴 시간 ≥ `idle_reset_minutes`: 타이머를 0으로 리셋한다. 돌아오면 처음부터 다시 센다.
  - 같은 규칙이 SNOOZED에도 적용된다. 5분 이상 비우면 미루기 대기도 취소하고 RUNNING으로 리셋한다.
  - DUE 상태(팝업이 떠 있는 중)에는 유휴로 팝업을 닫지 않는다. 사용자가 응답할 때까지 유지한다.
- 절전 후 복귀: 두 tick 사이 간격이 비정상적으로 크면(예: 10초 초과) 그 시간만큼 유휴였던 것으로 보고 위 규칙을 적용한다.

## 3. 데이터 저장

위치: `%APPDATA%\EyeExercise\`
- 저장은 원자적으로 한다. 임시 파일에 먼저 쓰고 `os.replace`로 교체한다.
- 파일이 손상되었으면 `*.corrupt-<날짜>.json`으로 백업하고 기본값으로 시작한다.
- 모든 파일에 `version` 필드를 넣어 나중에 마이그레이션할 수 있게 한다.

### settings.json
```json
{
  "version": 1,
  "interval_minutes": 20,
  "snooze_minutes": 5,
  "idle_pause_minutes": 1,
  "idle_reset_minutes": 5,
  "exercises": {
    "blink":      { "enabled": true, "duration_seconds": 30 },
    "dot_follow": { "enabled": true, "duration_seconds": 60, "speed": "normal" }
  },
  "show_main_window_on_start": false,
  "camera": { "enabled": false }
}
```
- 범위를 벗어난 값은 보정한다. 예: interval은 1~120분.
- `idle_pause_minutes`는 `idle_reset_minutes`보다 작아야 한다. 어긋나면 pause를 reset보다 작은 값으로 보정한다.
- 모르는 키는 무시하고, 없는 키는 기본값으로 채운다.

### history.json (이벤트 단위로 저장하고, 집계는 core/history가 계산)
```json
{
  "version": 1,
  "events": [
    { "ts": "2026-10-06T14:20:05+09:00", "type": "completed", "exercise": "blink", "duration_seconds": 30 },
    { "ts": "2026-10-06T14:40:10+09:00", "type": "snoozed" },
    { "ts": "2026-10-06T14:45:10+09:00", "type": "skipped" }
  ]
}
```
- 이벤트 단위로 저장하면 기능이 늘어도 데이터를 다시 해석할 수 있다.
- 일별 집계(완료·건너뜀·미룸 횟수, 운동 시간)는 로컬 날짜 기준으로 계산한다.

## 4. 구현 순서

각 단계는 작게 진행한다. 끝날 때마다 바꾼 내용과 이유를 설명하고 커밋을 제안하며, 사용자가 승인한 뒤에만 커밋한다.

진행 표시: ✅ = 완료. 단계가 끝나면 커밋 전에 이 표를 먼저 갱신해서 같은 커밋에 포함한다.

| 단계 | 내용 | 테스트 |
|---|---|---|
| ✅ 0. 골격 | Python 3.12로 `.venv` 재생성, `.gitignore`, pyproject.toml(패키지 정보·pytest 설정), requirements.txt, requirements-dev.txt, src와 tests 폴더, 빈 `__main__` | pytest 스모크 테스트 1개, `python -m eyeexercise` 실행, `python --version`이 3.12인지 확인 |
| ✅ 1. 설정과 저장소 | `core/settings`, `storage/paths`, `storage/json_store` | 기본값, 범위 보정, pause < reset 보정, 저장 후 다시 읽기, 손상 파일 백업과 복구, 모르는 키·누락 키 처리 (경로는 tmp_path) |
| ✅ 2. 스케줄러 | `core/clock`, `core/idle`, `core/scheduler` | FakeClock으로 20분 후 DUE, 미루기 후 다시 DUE, 건너뛰기 리셋, 일시정지·재개, 유휴 59초는 정상 누적, 1분 유휴는 누적 정지 후 복귀 시 이어서 계산, 4분 59초는 리셋하지 않음, 5분은 리셋, SNOOZED 중 유휴 규칙, DUE 중에는 유휴여도 유지, 절전으로 tick 간격이 큰 경우, 설정 변경 반영 |
| ✅ 3a. 트레이와 팝업 | `ui/controller`, `ui/tray`, `ui/reminder_popup`, 최소 `app.py` (유휴는 FakeIdle 대신 항상 0을 돌려주는 임시 구현) | 수동 체크리스트: interval 1분으로 팝업 표시, 미루기·건너뛰기·시작 버튼 동작, 트레이 메뉴(일시정지·종료) |
| 3b. 유휴 감지·단일 인스턴스·메인 창 | `platform/win_idle`, 단일 인스턴스(QLockFile), `ui/main_window`(빈 화면, 닫으면 트레이로 숨김) | `win_idle`이 0 이상의 값을 반환하는지 (Windows 전용 테스트). 수동 체크리스트: 입력 없이 1분 지나면 누적 정지, 5분이면 리셋, 두 번째 실행이 첫 인스턴스를 앞으로 가져옴, 창 닫아도 종료되지 않음 |
| 4. 기록 | `core/history`, controller에서 이벤트 기록 | 이벤트 추가, 일별 집계, 자정 경계(23:59와 00:01), 저장 후 다시 읽기 |
| 5. 깜빡임 운동 | `core/exercises`(단계 타임라인), `core/camera`(프로토콜과 NullDetector), `ui/exercise_window` | 경과 시간별 단계·안내 문구, 총 시간, 중단 처리. 카메라 없이 동작하는지 확인 |
| 6. 점 따라가기 | `core/exercises`에 경로 함수 `t → (x, y)` 추가 (0~1 정규화 좌표), 화면 렌더링 | 모든 t에서 좌표가 0~1 범위, 경로가 연속적인지, 패턴별 시작점과 끝점, 속도 설정 반영 |
| 7. 대시보드 | `ui/main_window`의 기록 탭(오늘, 최근 7일)과 설정 탭(변경 즉시 저장하고 스케줄러에 반영) | 표시용 요약 함수(최근 7일, 빈 날은 0)는 pytest로, UI는 수동으로 확인 |
| 8. exe 빌드 | `eyeexercise.spec`, 아이콘, `--windowed` | 빌드한 exe로 수동 체크리스트: 실행, 트레이, 알림, `%APPDATA%`에 저장, 중복 실행 방지 |
| 9. (나중) 카메라 | opt-in 깜빡임 감지 구현. 라이브러리와 exe 용량은 이 단계에서 결정 | 이 단계에서 별도로 설계 |

GUI 자동 테스트(pytest-qt)는 지금은 넣지 않는다. 로직이 `core`에 있으므로 GUI는 수동 체크리스트로 충분하다.

## 5. 검증 방법 (공통)
- `.venv\Scripts\python -m pytest`: core와 storage 테스트 전체 통과
- `.venv\Scripts\python -m eyeexercise`: 각 단계의 수동 체크리스트 수행 (개발 중에는 interval을 1분으로 설정)
- 8단계 이후: `dist\EyeExercise.exe`로 같은 체크리스트 반복

## 나중에 결정할 것
- Windows 시작 시 자동 실행 옵션 (레지스트리 Run 키)
- 기록 보관 기간 (오래된 이벤트 정리)
- 운동 순서 (번갈아 진행 / 무작위 / 사용자 지정)
