"""화면에 보여줄 문구 가공. Qt와 무관한 순수 함수만 둔다."""

import math


def format_remaining(seconds: float) -> str:
    """남은 시간을 '12분 30초' 형태로 만든다. 초는 올림해서 0초 표시를 피한다."""
    total = max(0, math.ceil(seconds))
    minutes, secs = divmod(total, 60)
    if minutes == 0:
        return f"{secs}초"
    if secs == 0:
        return f"{minutes}분"
    return f"{minutes}분 {secs}초"
