import pytest

from eyeexercise.core.formatting import format_remaining


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1200, "20분"),
        (750, "12분 30초"),
        (61, "1분 1초"),
        (60, "1분"),
        (59.2, "1분"),  # 올림
        (45, "45초"),
        (0.4, "1초"),
        (0, "0초"),
        (-5, "0초"),
    ],
)
def test_남은_시간_표기(seconds, expected):
    assert format_remaining(seconds) == expected
