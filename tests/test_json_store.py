import json
from datetime import datetime

from eyeexercise.core.settings import Settings
from eyeexercise.storage import json_store, paths

FIXED_NOW = datetime(2026, 10, 6, 14, 20, 5)


def test_파일이_없으면_None(tmp_path):
    assert json_store.read_json(tmp_path / "none.json") is None


def test_저장_후_다시_읽기_한글_포함(tmp_path):
    path = tmp_path / "a.json"
    json_store.write_json(path, {"version": 1, "이름": "눈 운동"})
    assert json_store.read_json(path) == {"version": 1, "이름": "눈 운동"}


def test_없는_폴더도_만들어서_저장한다(tmp_path):
    path = tmp_path / "sub" / "dir" / "a.json"
    json_store.write_json(path, {"x": 1})
    assert path.exists()


def test_저장_후_임시_파일이_남지_않는다(tmp_path):
    path = tmp_path / "a.json"
    json_store.write_json(path, {"x": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_저장_실패_시_기존_파일은_유지된다(tmp_path):
    path = tmp_path / "a.json"
    json_store.write_json(path, {"x": 1})
    try:
        json_store.write_json(path, {"x": object()})  # JSON으로 만들 수 없는 값
    except TypeError:
        pass
    assert json_store.read_json(path) == {"x": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]  # 임시 파일도 정리된다


def test_손상된_파일은_백업하고_None(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ 깨진 json", encoding="utf-8")

    assert json_store.read_json(path, now=lambda: FIXED_NOW) is None

    assert not path.exists()
    backup = tmp_path / "settings.corrupt-20261006-142005.json"
    assert backup.read_text(encoding="utf-8") == "{ 깨진 json"


def test_UTF8이_아닌_파일도_손상으로_처리한다(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe\x00\x80")
    assert json_store.read_json(path, now=lambda: FIXED_NOW) is None
    assert (tmp_path / "settings.corrupt-20261006-142005.json").exists()


def test_최상위가_dict가_아니면_손상으로_처리한다(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert json_store.read_json(path, now=lambda: FIXED_NOW) is None
    assert (tmp_path / "settings.corrupt-20261006-142005.json").exists()


def test_설정_저장_후_다시_읽기(tmp_path):
    path = paths.settings_path(tmp_path)
    saved = Settings(interval_minutes=45, idle_pause_minutes=2, idle_reset_minutes=10)
    json_store.save_settings(path, saved)
    assert json_store.load_settings(path) == saved


def test_설정_파일이_없으면_기본값(tmp_path):
    assert json_store.load_settings(paths.settings_path(tmp_path)) == Settings()


def test_손상된_설정_파일은_기본값으로_시작하고_백업을_남긴다(tmp_path):
    path = paths.settings_path(tmp_path)
    path.write_text("not json", encoding="utf-8")
    assert json_store.load_settings(path, now=lambda: FIXED_NOW) == Settings()
    assert (tmp_path / "settings.corrupt-20261006-142005.json").exists()


def test_파일의_모르는_키와_누락_키를_처리한다(tmp_path):
    path = paths.settings_path(tmp_path)
    path.write_text(json.dumps({"version": 1, "interval_minutes": 30, "future_key": True}), encoding="utf-8")
    loaded = json_store.load_settings(path)
    assert loaded.interval_minutes == 30
    assert loaded.snooze_minutes == 5


def test_기본_경로는_APPDATA_아래(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.app_data_dir() == tmp_path / "EyeExercise"
    assert paths.settings_path() == tmp_path / "EyeExercise" / "settings.json"
    assert paths.history_path() == tmp_path / "EyeExercise" / "history.json"
