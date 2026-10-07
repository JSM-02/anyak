import logging

import pytest

from eyeexercise.core.settings import Settings, settings_from_dict, settings_to_dict, with_changes
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.storage import json_store

# ---- with_changes ----


def test_바꾼_값만_달라진_새_설정을_만든다():
    old = Settings()
    new = with_changes(old, {"interval_minutes": 45})
    assert new.interval_minutes == 45
    assert new.snooze_minutes == old.snooze_minutes and new.exercises == old.exercises
    assert old.interval_minutes == 20  # 원본은 그대로


def test_중첩된_경로도_바꾼다():
    s = with_changes(
        Settings(),
        {
            "exercises.blink.enabled": False,
            "exercises.blink.duration_seconds": 90,
            "exercises.dot_follow.speed": "fast",
            "exercises.dot_follow.duration_seconds": 90,
            "sound.enabled": False,
            "show_main_window_on_start": True,
        },
    )
    assert s.exercises.blink.enabled is False and s.exercises.blink.duration_seconds == 90
    assert s.exercises.dot_follow.speed == "fast" and s.exercises.dot_follow.duration_seconds == 90
    assert s.sound.enabled is False and s.show_main_window_on_start is True


def test_범위를_벗어난_값은_파일을_읽을_때와_같이_보정한다():
    assert with_changes(Settings(), {"interval_minutes": 0}).interval_minutes == 1
    assert with_changes(Settings(), {"interval_minutes": 999}).interval_minutes == 120
    assert with_changes(Settings(), {"exercises.blink.duration_seconds": 1}).exercises.blink.duration_seconds == 12


def test_잘못된_타입과_속도는_기본값으로_보정한다():
    assert with_changes(Settings(), {"interval_minutes": "abc"}).interval_minutes == 20
    assert with_changes(Settings(), {"exercises.dot_follow.speed": "turbo"}).exercises.dot_follow.speed == "normal"
    assert with_changes(Settings(), {"sound.enabled": "no"}).sound.enabled is True


def test_정지_기준이_초기화_기준_이상이면_정지_기준을_낮춘다():
    s = with_changes(Settings(), {"idle_pause_minutes": 10})  # 초기화 기준은 5분
    assert s.idle_reset_minutes == 5 and s.idle_pause_minutes == 4
    s = with_changes(Settings(), {"idle_reset_minutes": 3})  # 정지 기준 1분 < 3분 이라 그대로
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (1, 3)
    s = with_changes(Settings(idle_pause_minutes=4), {"idle_reset_minutes": 3})
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (2, 3)


def test_여러_값을_한_번에_바꿔도_보정은_전체에_적용된다():
    s = with_changes(Settings(), {"idle_pause_minutes": 10, "idle_reset_minutes": 30})
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (10, 30)  # 둘 다 바꾸면 보정할 필요가 없다


@pytest.mark.parametrize("path", ["unknown", "exercises.unknown", "exercises.blink.unknown", "sound.enabled.deeper", "version", "exercises.blink"])
def test_없는_경로나_version은_거부한다(path):
    with pytest.raises(KeyError):
        with_changes(Settings(), {path: 1})


def test_변경_결과는_다시_저장하고_읽어도_같다():
    s = with_changes(Settings(), {"interval_minutes": 33, "exercises.dot_follow.speed": "slow"})
    assert settings_from_dict(settings_to_dict(s)) == s


# ---- SettingsManager ----


def make_manager(save=None):
    saved = []
    manager = SettingsManager(Settings(), save=save if save is not None else saved.append)
    return manager, saved


def test_바꾸면_보정된_설정을_돌려주고_저장한다():
    manager, saved = make_manager()
    result = manager.update({"interval_minutes": 30})
    assert result.changed and result.saved and result.settings.interval_minutes == 30
    assert manager.settings is result.settings and saved == [result.settings]


def test_바뀐_게_없으면_저장도_알림도_하지_않는다():
    manager, saved = make_manager()
    calls = []
    manager.subscribe(lambda new, old: calls.append(1))
    result = manager.update({"interval_minutes": 20})  # 이미 20
    assert not result.changed and result.saved and saved == [] and calls == []


def test_보정_결과_바뀐_게_없어도_저장하지_않는다():
    manager, saved = make_manager()
    manager.update({"interval_minutes": 120})
    saved.clear()
    result = manager.update({"interval_minutes": 9999})  # 120으로 보정되어 그대로
    assert not result.changed and saved == []


def test_바뀌면_구독한_쪽에_새_설정과_이전_설정을_알린다():
    manager, _ = make_manager()
    calls = []
    manager.subscribe(lambda new, old: calls.append((new.interval_minutes, old.interval_minutes)))
    manager.update({"interval_minutes": 30})
    manager.update({"interval_minutes": 40})
    assert calls == [(30, 20), (40, 30)]


def test_구독을_끊으면_더_알리지_않는다():
    manager, _ = make_manager()
    calls = []
    unsubscribe = manager.subscribe(lambda new, old: calls.append(1))
    manager.update({"interval_minutes": 30})
    unsubscribe()
    unsubscribe()  # 두 번 끊어도 문제없다
    manager.update({"interval_minutes": 40})
    assert calls == [1]


def test_저장이_실패해도_이번_실행에는_적용하고_실패를_알린다(caplog):
    def fail(_settings):
        raise OSError("디스크 오류")

    manager, _ = make_manager(save=fail)
    calls = []
    manager.subscribe(lambda new, old: calls.append(new.interval_minutes))
    with caplog.at_level(logging.WARNING):
        result = manager.update({"interval_minutes": 30})
    assert result.changed and not result.saved
    assert manager.settings.interval_minutes == 30 and calls == [30]
    assert "설정을 저장하지 못했습니다" in caplog.text


def test_알림을_받는_쪽에서_오류가_나도_다른_쪽은_계속_받는다(caplog):
    manager, saved = make_manager()
    calls = []

    def broken(new, old):
        raise RuntimeError("버그")

    manager.subscribe(broken)
    manager.subscribe(lambda new, old: calls.append(new.interval_minutes))
    with caplog.at_level(logging.ERROR):
        result = manager.update({"interval_minutes": 30})
    assert calls == [30] and result.saved and len(saved) == 1
    assert "오류가 났습니다" in caplog.text


def test_없는_경로는_설정을_바꾸지_않고_예외를_낸다():
    manager, saved = make_manager()
    with pytest.raises(KeyError):
        manager.update({"interval_minutes": 30, "typo": 1})
    assert manager.settings == Settings() and saved == []


def test_저장_콜백이_없어도_동작한다():
    manager = SettingsManager(Settings())
    result = manager.update({"interval_minutes": 30})
    assert result.changed and result.saved and manager.settings.interval_minutes == 30


def test_파일에_저장하고_다시_읽는다(tmp_path):
    path = tmp_path / "settings.json"
    manager = SettingsManager(Settings(), save=lambda s: json_store.save_settings(path, s))
    manager.update({"interval_minutes": 33, "exercises.blink.duration_seconds": 90, "sound.enabled": False})
    loaded = json_store.load_settings(path)
    assert loaded == manager.settings
    assert loaded.interval_minutes == 33 and loaded.sound.enabled is False


def test_정지_기준_보정_결과를_돌려준다():
    manager, _ = make_manager()
    result = manager.update({"idle_pause_minutes": 10})
    assert result.settings.idle_pause_minutes == 4  # 화면은 이 값으로 입력칸을 되돌린다


# ---- 설정 초기화 ----


def test_초기화하면_모든_설정이_기본값으로_돌아가고_저장하고_알린다():
    saved, heard = [], []
    manager = SettingsManager(Settings(), save=saved.append)
    manager.update({"interval_minutes": 33, "appearance": "dark", "exercises.daily_goal": 4})
    saved.clear()
    manager.subscribe(lambda new, old: heard.append((new, old)))
    result = manager.reset()
    assert result.settings == Settings() and result.changed and result.saved
    assert saved == [Settings()]
    assert heard[0][0] == Settings() and heard[0][1].interval_minutes == 33


def test_이미_기본값이면_초기화해도_저장하지_않는다():
    saved = []
    manager = SettingsManager(Settings(), save=saved.append)
    result = manager.reset()
    assert not result.changed and result.saved and saved == []


def test_초기화_저장에_실패해도_이번_실행에는_적용한다():
    def fail(_settings):
        raise OSError("디스크 오류")

    manager = SettingsManager(Settings(), save=fail)
    manager.update({"interval_minutes": 33})
    result = manager.reset()
    assert result.settings == Settings() and not result.saved and manager.settings == Settings()


def test_초기화하면_정해_둔_기본값으로_돌아간다():
    from eyeexercise.core.exercises import blink_cycles_for_seconds, current_preset

    manager = SettingsManager(Settings())
    manager.update(
        {
            "interval_minutes": 45, "exercises.daily_goal": 5, "show_main_window_on_start": False,
            "exercises.blink.duration_seconds": 96, "exercises.dot_follow.duration_seconds": 120,
            "exercises.dot_follow.speed": "fast", "snooze_minutes": 15, "idle_pause_minutes": 10, "idle_reset_minutes": 30,
        }
    )
    s = manager.reset().settings
    assert s.interval_minutes == 20  # 휴식 주기
    assert s.exercises.daily_goal == 2  # 하루 운동 목표
    assert current_preset(s.exercises) == "normal"  # 길이는 보통
    assert s.show_main_window_on_start is True  # 시작할 때 화면 보이기
    assert blink_cycles_for_seconds(s.exercises.blink.duration_seconds) == 5  # 깜빡임 5회
    assert s.exercises.dot_follow.duration_seconds == 60  # 운동 시간 1분
    assert s.exercises.dot_follow.speed == "normal"  # 점 따라가기 속도 보통
    assert (s.snooze_minutes, s.idle_pause_minutes, s.idle_reset_minutes) == (5, 1, 5)  # 미루기·알림 멈춤·처음부터
