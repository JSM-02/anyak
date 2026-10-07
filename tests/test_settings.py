import pytest

from eyeexercise.core.settings import Settings, settings_from_dict, settings_to_dict


def test_기본값():
    s = Settings()
    assert s.interval_minutes == 20
    assert s.snooze_minutes == 5
    assert s.idle_pause_minutes == 1
    assert s.idle_reset_minutes == 5
    assert s.exercises.blink.enabled is True
    assert s.exercises.blink.duration_seconds == 36  # 깜빡임 5회
    assert s.exercises.dot_follow.duration_seconds == 60
    assert s.exercises.daily_goal == 2
    assert s.exercises.dot_follow.speed == "normal"
    assert s.show_main_window_on_start is True


def test_빈_dict나_dict가_아닌_값은_기본값():
    assert settings_from_dict({}) == Settings()
    assert settings_from_dict(None) == Settings()
    assert settings_from_dict([1, 2]) == Settings()


def test_dict_변환_왕복():
    original = Settings(interval_minutes=45, snooze_minutes=10)
    assert settings_from_dict(settings_to_dict(original)) == original


def test_저장_dict에_version이_있다():
    assert settings_to_dict(Settings())["version"] == 1


def test_모르는_키는_무시한다():
    s = settings_from_dict({"interval_minutes": 30, "unknown": 1, "exercises": {"foo": {}}})
    assert s.interval_minutes == 30


def test_누락된_키는_기본값으로_채운다():
    s = settings_from_dict({"exercises": {"blink": {"enabled": False}}})
    assert s.exercises.blink.enabled is False
    assert s.exercises.blink.duration_seconds == 36
    assert s.interval_minutes == 20


def test_범위를_벗어난_값은_경계값으로_보정한다():
    assert settings_from_dict({"interval_minutes": 0}).interval_minutes == 1
    assert settings_from_dict({"interval_minutes": 9999}).interval_minutes == 120
    assert settings_from_dict({"snooze_minutes": -3}).snooze_minutes == 1
    s = settings_from_dict({"exercises": {"blink": {"duration_seconds": 1}}})
    assert s.exercises.blink.duration_seconds == 12  # 깜빡임 1회


def test_고급_설정_범위는_깜빡임_1에서_15회_점_따라가기_10초에서_2분이다():
    from eyeexercise.core.exercises import blink_cycles_for_seconds
    from eyeexercise.core.settings import BLINK_SECONDS_RANGE, DOT_FOLLOW_SECONDS_RANGE

    assert (blink_cycles_for_seconds(BLINK_SECONDS_RANGE[0]), blink_cycles_for_seconds(BLINK_SECONDS_RANGE[1])) == (1, 15)
    assert DOT_FOLLOW_SECONDS_RANGE == (10, 120)
    s = settings_from_dict({"exercises": {"blink": {"duration_seconds": 999}, "dot_follow": {"duration_seconds": 999}}})
    assert (s.exercises.blink.duration_seconds, s.exercises.dot_follow.duration_seconds) == (96, 120)
    s = settings_from_dict({"exercises": {"dot_follow": {"duration_seconds": 1}}})
    assert s.exercises.dot_follow.duration_seconds == 10


def test_타입이_잘못된_값은_기본값():
    s = settings_from_dict(
        {
            "interval_minutes": "20",
            "snooze_minutes": 5.5,
            "idle_reset_minutes": True,  # bool은 정수로 취급하지 않는다
            "show_main_window_on_start": "yes",
            "exercises": {"dot_follow": {"speed": "turbo"}},
        }
    )
    assert s.interval_minutes == 20
    assert s.snooze_minutes == 5
    assert s.idle_reset_minutes == 5
    assert s.show_main_window_on_start is True  # 잘못된 값이면 기본값(켜짐)
    assert s.exercises.dot_follow.speed == "normal"


def test_idle_pause는_idle_reset보다_작게_보정된다():
    s = settings_from_dict({"idle_pause_minutes": 10, "idle_reset_minutes": 5})
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (4, 5)

    same = settings_from_dict({"idle_pause_minutes": 5, "idle_reset_minutes": 5})
    assert (same.idle_pause_minutes, same.idle_reset_minutes) == (4, 5)


def test_idle_reset이_최솟값이어도_pause는_1_이상():
    s = settings_from_dict({"idle_pause_minutes": 30, "idle_reset_minutes": 2})
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (1, 2)


def test_유효한_idle_설정은_그대로_유지된다():
    s = settings_from_dict({"idle_pause_minutes": 2, "idle_reset_minutes": 10})
    assert (s.idle_pause_minutes, s.idle_reset_minutes) == (2, 10)


def test_소리는_기본으로_켜져_있다():
    assert Settings().sound.enabled is True


def test_예전_설정_파일처럼_sound가_없으면_기본값으로_채운다():
    assert settings_from_dict({"interval_minutes": 30}).sound.enabled is True


def test_소리_설정을_끄고_저장해도_유지된다():
    s = settings_from_dict({"sound": {"enabled": False}})
    assert s.sound.enabled is False
    assert settings_to_dict(s)["sound"] == {"enabled": False}
    assert settings_from_dict(settings_to_dict(s)) == s


def test_소리_설정_타입이_잘못되면_기본값():
    assert settings_from_dict({"sound": {"enabled": "no"}}).sound.enabled is True
    assert settings_from_dict({"sound": "off"}).sound.enabled is True


# ---- 화면 모드 ----


def test_화면_모드_기본은_시스템_설정을_따르는_것이다():
    assert Settings().appearance == "system"
    assert settings_from_dict({}).appearance == "system"


def test_화면_모드를_저장하고_다시_읽는다():
    from eyeexercise.core.settings import settings_to_dict, with_changes

    s = with_changes(Settings(), {"appearance": "dark"})
    assert s.appearance == "dark"
    assert settings_from_dict(settings_to_dict(s)).appearance == "dark"


@pytest.mark.parametrize("value", ["blue", 1, None, "DARK"])
def test_알_수_없는_화면_모드는_기본값으로_보정한다(value):
    assert settings_from_dict({"appearance": value}).appearance == "system"


# ---- 하루 운동 목표 (7.6a) ----


@pytest.mark.parametrize(("value", "expected"), [(0, 0), (5, 5), (3, 3), (-1, 0), (99, 5), ("2", 2), ("x", 2), (None, 2), (True, 2), (2.5, 2)])
def test_하루_운동_목표는_범위로_보정한다(value, expected):
    assert settings_from_dict({"exercises": {"daily_goal": value}}).exercises.daily_goal == expected


def test_하루_운동_목표를_저장하고_바꾼다():
    from eyeexercise.core.settings import with_changes

    s = with_changes(Settings(), {"exercises.daily_goal": 4})
    assert s.exercises.daily_goal == 4
    assert settings_from_dict(settings_to_dict(s)).exercises.daily_goal == 4
