"""운동 중 소리 안내. 눈을 감고 있어도 단계를 알 수 있게 한다.

단계마다 다음 순서로 소리를 고른다. 모두 오프라인이며 네트워크를 쓰지 않는다.
1. `assets/sounds/`의 녹음·효과음 파일이 있으면 그것을 재생한다.
2. 없으면 한국어 음성(Windows 내장)으로 말한다.
3. 한국어 음성도 없으면 단계별 알림음으로 대신한다.

사이클 소리(`cycle.wav`)는 감기가 시작될 때 한 번 재생한다. 감기·유지·뜨기 전체가 그 파일 하나에
이어서 들어 있고(뜨기 알림 종소리 포함), 파일 끝에는 다음 사이클과 겹치는 구간이 있다. 그래서
다음 사이클이 시작돼도 앞 소리를 끊지 않고 겹쳐 재생해야 소리가 이어진다.
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from eyeexercise.core.exercises import SPOKEN, Phase
from eyeexercise.resources import assets_dir

log = logging.getLogger(__name__)

SOUNDS_DIR = assets_dir() / "sounds"

# 단계가 시작될 때 재생하는 파일 (assets/sounds/<이름>.wav)
PHASE_FILES = {
    Phase.PREPARE: "prepare",
    Phase.CLOSE: "cycle",
    Phase.FINISH: "finish",
    Phase.LOOK_AWAY: "look_away",
}
# 이 단계들의 소리는 다른 단계의 파일 안에 이미 들어 있다. (뜨기 종소리는 사이클 파일에 있다.)
COVERED_BY = {Phase.HOLD: Phase.CLOSE, Phase.OPEN: Phase.CLOSE, Phase.REST: Phase.CLOSE}
ALERT_FILE = "alert"  # 알림 팝업이 뜰 때 나는 소리 (assets/sounds/alert.wav)
POOL_SIZE = 2  # 겹쳐 재생하려고 파일마다 재생기를 둘씩 두고 번갈아 쓴다

# 음성이 없을 때 쓰는 알림음 높이(Hz). 감을 때는 낮게, 뜰 때는 높게 해서 구분한다.
BEEP_HZ = {
    Phase.PREPARE: 600,
    Phase.CLOSE: 440,
    Phase.OPEN: 880,
    Phase.FINISH: 660,
    Phase.LOOK_AWAY: 660,
}
_BEEP_MS = 180


class Speaker(Protocol):
    def cue(self, phase: Phase) -> None:
        """단계가 바뀔 때 호출한다. 해당 단계에 안내가 없으면 아무것도 하지 않는다."""
        ...

    def stop(self) -> None:
        """진행 중인 소리를 멈춘다."""
        ...


def _make_effect(path: Path):
    """짧은 WAV를 지연 없이 재생하는 QSoundEffect."""
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QSoundEffect

    effect = QSoundEffect()
    effect.setSource(QUrl.fromLocalFile(str(path)))
    effect.setVolume(1.0)
    return effect


def _failed(effect) -> bool:
    status = getattr(effect, "status", None)
    return callable(status) and status().name == "Error"


def _playing(effect) -> bool:
    playing = getattr(effect, "isPlaying", None)
    return bool(playing()) if callable(playing) else False


class FileSpeaker:
    """단계별 녹음·효과음 파일을 재생한다. 파일이 없거나 재생할 수 없으면 `fallback`에 맡긴다."""

    def __init__(
        self,
        sounds_dir: Path,
        fallback: Speaker | None,
        effect_factory: Callable[[Path], object] = _make_effect,
    ) -> None:
        self._fallback = fallback
        self._pools: dict[Phase, list[object]] = {}
        self._next: dict[Phase, int] = {}
        for phase, name in PHASE_FILES.items():
            path = sounds_dir / f"{name}.wav"
            if not path.is_file():
                continue
            try:
                self._pools[phase] = [effect_factory(path) for _ in range(POOL_SIZE)]
                self._next[phase] = 0
            except Exception:  # 파일 하나가 문제여도 나머지 안내는 계속 쓴다
                log.warning("안내 소리 파일을 불러오지 못했습니다: %s", path, exc_info=True)

    @property
    def phases(self) -> set[Phase]:
        """파일을 쓰는 단계들."""
        return set(self._pools)

    def cue(self, phase: Phase) -> None:
        effect = self._pick(phase)
        if effect is not None:
            if self._fallback is not None:
                self._fallback.stop()  # 음성 합성이 남아 있으면 끊는다
            effect.play()  # 앞 소리는 끊지 않는다. 겹쳐서 이어진다.
            return
        covering = COVERED_BY.get(phase)
        if covering is not None and self._usable(covering):
            return  # 이 단계의 소리는 이미 사이클 파일 안에 있다
        if self._fallback is not None:
            self._fallback.cue(phase)

    def stop(self) -> None:
        for pool in self._pools.values():
            for effect in pool:
                effect.stop()
        if self._fallback is not None:
            self._fallback.stop()

    def _usable(self, phase: Phase) -> bool:
        return any(not _failed(e) for e in self._pools.get(phase, ()))

    def _pick(self, phase: Phase):
        """다음에 쓸 재생기를 번갈아 고른다. 재생 중이 아닌 것을 우선한다."""
        pool = self._pools.get(phase)
        if not pool:
            return None
        start = self._next[phase]
        order = [pool[(start + i) % len(pool)] for i in range(len(pool))]
        usable = [e for e in order if not _failed(e)]
        if not usable:
            return None
        chosen = next((e for e in usable if not _playing(e)), usable[0])
        self._next[phase] = (pool.index(chosen) + 1) % len(pool)
        return chosen


class TtsSpeaker:
    def __init__(self, tts) -> None:
        self._tts = tts

    def cue(self, phase: Phase) -> None:
        text = SPOKEN.get(phase)
        if text:
            self._tts.stop()  # 앞 안내가 밀려 있으면 끊고 지금 단계를 말한다
            self._tts.say(text)

    def stop(self) -> None:
        self._tts.stop()


class BeepSpeaker:
    def cue(self, phase: Phase) -> None:
        freq = BEEP_HZ.get(phase)
        if freq:
            threading.Thread(target=self._beep, args=(freq,), daemon=True).start()

    def stop(self) -> None:
        pass  # 알림음은 0.2초 미만이라 멈출 필요가 없다

    @staticmethod
    def _beep(freq: int) -> None:
        try:
            import winsound

            winsound.Beep(freq, _BEEP_MS)
        except (ImportError, RuntimeError):
            pass  # 소리를 낼 수 없는 환경이면 조용히 넘어간다


def _korean_tts():
    """한국어 음성을 쓸 수 있는 QTextToSpeech를 만든다. 쓸 수 없으면 None."""
    try:
        from PySide6.QtCore import QLocale
        from PySide6.QtTextToSpeech import QTextToSpeech
    except ImportError:
        return None
    try:
        for engine in QTextToSpeech.availableEngines():
            if engine == "mock":  # 테스트용 가짜 엔진
                continue
            tts = QTextToSpeech(engine)
            korean = [loc for loc in tts.availableLocales() if loc.language() == QLocale.Language.Korean]
            if not korean:
                continue
            tts.setLocale(korean[0])
            if tts.availableVoices():
                return tts
    except Exception:  # 엔진 초기화 실패는 어떤 종류든 소리 없이 쓰는 것보다 알림음으로 대신하는 게 낫다
        log.warning("음성 엔진을 초기화하지 못했습니다.", exc_info=True)
    return None


class AlertSound:
    """알림 팝업이 뜰 때 한 번 울리는 부드러운 알림음(`assets/sounds/alert.wav`).

    파일이 없거나 재생할 수 없으면 Windows 기본 알림음으로 대신한다.
    """

    def __init__(self, sounds_dir: Path, effect_factory: Callable[[Path], object] = _make_effect) -> None:
        self._effect = None
        path = sounds_dir / f"{ALERT_FILE}.wav"
        if path.is_file():
            try:
                self._effect = effect_factory(path)
            except Exception:  # 파일이 문제여도 기본 알림음으로 알린다
                log.warning("알림음 파일을 불러오지 못했습니다: %s", path, exc_info=True)

    def play(self) -> None:
        if self._effect is not None and not _failed(self._effect):
            self._effect.play()
            return
        threading.Thread(target=self._system_beep, daemon=True).start()

    def stop(self) -> None:
        if self._effect is not None:
            self._effect.stop()

    @staticmethod
    def _system_beep() -> None:
        try:
            import winsound

            winsound.MessageBeep()
        except (ImportError, RuntimeError):
            pass  # 소리를 낼 수 없는 환경이면 조용히 넘어간다


def create_alert(enabled: bool, sounds_dir: Path = SOUNDS_DIR) -> AlertSound | None:
    """설정에 따라 알림음을 만든다. 소리가 꺼져 있으면 None."""
    return AlertSound(sounds_dir) if enabled else None


def create_speaker(enabled: bool, sounds_dir: Path = SOUNDS_DIR) -> Speaker | None:
    """설정에 따라 소리 안내를 만든다. 꺼져 있으면 None."""
    if not enabled:
        return None
    tts = _korean_tts()
    if tts is not None:
        log.info("파일이 없는 단계는 내장 음성으로 안내합니다.")
        base: Speaker = TtsSpeaker(tts)
    else:
        log.info("한국어 음성을 쓸 수 없어 파일이 없는 단계는 알림음으로 안내합니다.")
        base = BeepSpeaker()
    speaker = FileSpeaker(sounds_dir, base)
    log.info("소리 파일을 쓰는 단계: %s", sorted(p.value for p in speaker.phases) or "없음")
    return speaker
