import sys
import threading
import types

from eyeexercise.core.exercises import SPOKEN, Phase
from eyeexercise.ui import speech
from eyeexercise.ui.speech import (
    BEEP_HZ,
    POOL_SIZE,
    BeepSpeaker,
    FileSpeaker,
    TtsSpeaker,
    create_speaker,
)


class FakeTts:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def stop(self) -> None:
        self.calls.append(("stop",))

    def say(self, text: str) -> None:
        self.calls.append(("say", text))


def test_음성은_안내가_있는_단계만_말한다():
    tts = FakeTts()
    speaker = TtsSpeaker(tts)
    speaker.cue(Phase.HOLD)
    speaker.cue(Phase.REST)
    assert tts.calls == []
    speaker.cue(Phase.CLOSE)
    assert tts.calls == [("stop",), ("say", SPOKEN[Phase.CLOSE])]


def test_음성은_앞_안내를_끊고_새_안내를_말한다():
    tts = FakeTts()
    speaker = TtsSpeaker(tts)
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.OPEN)
    assert [c for c in tts.calls if c[0] == "say"] == [("say", "눈을 감으세요"), ("say", "눈을 뜨세요")]
    assert tts.calls[2] == ("stop",)


def test_음성_stop은_엔진을_멈춘다():
    tts = FakeTts()
    TtsSpeaker(tts).stop()
    assert tts.calls == [("stop",)]


def test_알림음은_감을_때_낮고_뜰_때_높다():
    assert BEEP_HZ[Phase.CLOSE] < BEEP_HZ[Phase.OPEN]


def test_알림음은_안내가_없는_단계에서는_울리지_않는다(monkeypatch):
    beeps = []
    monkeypatch.setattr(BeepSpeaker, "_beep", staticmethod(lambda freq: beeps.append(freq)))
    speaker = BeepSpeaker()
    speaker.cue(Phase.HOLD)
    speaker.cue(Phase.REST)
    assert beeps == []


def test_알림음은_단계별_높이로_울린다(monkeypatch):
    beeps = []
    done = threading.Event()

    def fake_beep(freq):
        beeps.append(freq)
        done.set()

    monkeypatch.setattr(BeepSpeaker, "_beep", staticmethod(fake_beep))
    BeepSpeaker().cue(Phase.CLOSE)
    assert done.wait(2)
    assert beeps == [BEEP_HZ[Phase.CLOSE]]


def test_알림음을_낼_수_없는_환경에서도_예외가_나지_않는다(monkeypatch):
    def broken(*_args):
        raise RuntimeError("소리 장치 없음")

    monkeypatch.setitem(sys.modules, "winsound", types.SimpleNamespace(Beep=broken))
    BeepSpeaker._beep(440)  # 예외 없이 끝나야 한다


def test_소리가_꺼져_있으면_만들지_않는다():
    assert create_speaker(False) is None


def test_한국어_음성이_없으면_알림음으로_대신한다(monkeypatch, tmp_path):
    monkeypatch.setattr(speech, "_korean_tts", lambda: None)
    speaker = create_speaker(True, tmp_path)
    assert isinstance(speaker, FileSpeaker) and isinstance(speaker._fallback, BeepSpeaker)


def test_한국어_음성이_있으면_음성을_쓴다(monkeypatch, tmp_path):
    monkeypatch.setattr(speech, "_korean_tts", lambda: FakeTts())
    speaker = create_speaker(True, tmp_path)
    assert isinstance(speaker, FileSpeaker) and isinstance(speaker._fallback, TtsSpeaker)


# ---- 소리 파일 ----


class FakeEffect:
    def __init__(self, path, failed=False) -> None:
        self.path = path
        self.failed = failed
        self.played = 0
        self.stopped = 0
        self.playing = False

    def play(self) -> None:
        self.played += 1
        self.playing = True

    def stop(self) -> None:
        self.stopped += 1
        self.playing = False

    def isPlaying(self) -> bool:
        return self.playing

    def status(self):
        return types.SimpleNamespace(name="Error" if self.failed else "Ready")


class FakeFallback:
    def __init__(self) -> None:
        self.cues: list[Phase] = []
        self.stopped = 0

    def cue(self, phase: Phase) -> None:
        self.cues.append(phase)

    def stop(self) -> None:
        self.stopped += 1


def make_files(directory, *names):
    for name in names:
        (directory / f"{name}.wav").write_bytes(b"RIFF")
    return directory


def make_file_speaker(directory, fallback=None, failed=()):
    created: dict[str, list[FakeEffect]] = {}

    def factory(path):
        effect = FakeEffect(path, failed=path.stem in failed)
        created.setdefault(path.stem, []).append(effect)
        return effect

    return FileSpeaker(directory, fallback, factory), created


ALL_FILES = ("prepare", "cycle", "finish", "look_away")


def test_감기_시작에서_사이클_파일을_재생한다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, *ALL_FILES), fallback)
    speaker.cue(Phase.CLOSE)
    assert sum(e.played for e in effects["cycle"]) == 1
    assert fallback.cues == []


def test_준비_마무리_먼_곳_바라보기도_각자_파일을_재생한다(tmp_path):
    speaker, effects = make_file_speaker(make_files(tmp_path, *ALL_FILES), FakeFallback())
    for phase, name in [(Phase.PREPARE, "prepare"), (Phase.FINISH, "finish"), (Phase.LOOK_AWAY, "look_away")]:
        speaker.cue(phase)
        assert sum(e.played for e in effects[name]) == 1


def test_유지_뜨기_쉬기에서는_소리를_내지_않는다_뜨기_종소리는_사이클_파일_안에_있다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, *ALL_FILES), fallback)
    for phase in (Phase.HOLD, Phase.OPEN, Phase.REST):
        speaker.cue(phase)
    assert all(e.played == 0 for pool in effects.values() for e in pool)
    assert fallback.cues == []  # 음성이 "눈을 뜨세요"라고 덧붙이지 않는다


def test_사이클_파일이_없으면_뜨기도_대체_음성이_맡는다(tmp_path):
    fallback = FakeFallback()
    speaker, _ = make_file_speaker(make_files(tmp_path, "prepare", "finish"), fallback)
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.OPEN)
    assert fallback.cues == [Phase.CLOSE, Phase.OPEN]


def test_사이클_파일이_망가졌으면_뜨기도_대체_음성이_맡는다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, *ALL_FILES), fallback, failed={"cycle"})
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.OPEN)
    assert all(e.played == 0 for e in effects["cycle"])
    assert fallback.cues == [Phase.CLOSE, Phase.OPEN]


def test_다음_사이클이_시작돼도_앞_소리를_끊지_않고_겹쳐_재생한다(tmp_path):
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle"), FakeFallback())
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.CLOSE)  # 4초 뒤 다음 사이클. 앞 사이클 소리는 아직 울리고 있다
    first, second = effects["cycle"]
    assert (first.played, second.played) == (1, 1)
    assert first.stopped == 0 and second.stopped == 0
    assert first.playing and second.playing


def test_재생기를_번갈아_쓰고_끝난_것을_다시_쓴다(tmp_path):
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle"), FakeFallback())
    first, second = effects["cycle"]
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.CLOSE)
    first.playing = False  # 첫 소리가 끝났다
    speaker.cue(Phase.CLOSE)
    assert (first.played, second.played) == (2, 1)


def test_재생기는_파일마다_둘씩_만든다(tmp_path):
    _, effects = make_file_speaker(make_files(tmp_path, *ALL_FILES), FakeFallback())
    assert {name: len(pool) for name, pool in effects.items()} == dict.fromkeys(ALL_FILES, POOL_SIZE)


def test_파일이_없는_단계는_대체_음성에_맡긴다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle"), fallback)
    speaker.cue(Phase.LOOK_AWAY)
    assert fallback.cues == [Phase.LOOK_AWAY]
    assert "look_away" not in effects


def test_일부_파일만_있어도_동작한다(tmp_path):
    speaker, _ = make_file_speaker(make_files(tmp_path, "cycle", "finish"), FakeFallback())
    assert speaker.phases == {Phase.CLOSE, Phase.FINISH}


def test_폴더가_없거나_비어_있어도_대체_음성으로_동작한다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(tmp_path / "없는폴더", fallback)
    speaker.cue(Phase.CLOSE)
    assert effects == {} and fallback.cues == [Phase.CLOSE]


def test_예전_음성_파일_이름은_읽지_않는다(tmp_path):
    speaker, effects = make_file_speaker(make_files(tmp_path, "close", "open", "hold", "rest"), FakeFallback())
    assert effects == {} and speaker.phases == set()


def test_재생기_하나가_실패해도_나머지로_재생한다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle"), fallback)
    effects["cycle"][0].failed = True
    speaker.cue(Phase.CLOSE)
    assert effects["cycle"][1].played == 1 and fallback.cues == []


def test_파일_재생이_실패하면_대체_음성으로_넘어간다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, "prepare"), fallback, failed={"prepare"})
    speaker.cue(Phase.PREPARE)
    assert all(e.played == 0 for e in effects["prepare"]) and fallback.cues == [Phase.PREPARE]


def test_파일_하나를_불러오지_못해도_나머지는_쓴다(tmp_path):
    def factory(path):
        if path.stem == "prepare":
            raise RuntimeError("깨진 파일")
        return FakeEffect(path)

    fallback = FakeFallback()
    speaker = FileSpeaker(make_files(tmp_path, "prepare", "cycle"), fallback, factory)
    assert speaker.phases == {Phase.CLOSE}
    speaker.cue(Phase.PREPARE)
    assert fallback.cues == [Phase.PREPARE]


def test_stop은_모든_재생을_멈추고_대체_음성도_멈춘다(tmp_path):
    fallback = FakeFallback()
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle", "finish"), fallback)
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.CLOSE)
    speaker.stop()
    assert all(e.stopped == 1 for pool in effects.values() for e in pool)
    assert fallback.stopped >= 1


def test_대체_음성_없이도_동작한다(tmp_path):
    speaker, effects = make_file_speaker(make_files(tmp_path, "cycle"), None)
    speaker.cue(Phase.CLOSE)
    speaker.cue(Phase.OPEN)
    speaker.cue(Phase.LOOK_AWAY)  # 파일도 대체도 없으면 조용히 넘어간다
    speaker.stop()
    assert sum(e.played for e in effects["cycle"]) == 1


def test_프로젝트_assets_폴더_위치가_맞다():
    assert speech.SOUNDS_DIR.name == "sounds" and speech.SOUNDS_DIR.parent.name == "assets"
    assert (speech.SOUNDS_DIR.parents[1] / "pyproject.toml").is_file()
