"""실행 중인 설정을 들고 있다가 변경을 보정·저장하고 관심 있는 쪽에 알린다 (Qt와 파일 I/O 없음).

저장은 주입받은 `save` 콜백이 맡는다. 저장에 실패해도 바꾼 값은 이번 실행에 그대로 적용하고,
결과에 `saved=False`를 담아 화면이 알릴 수 있게 한다.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from eyeexercise.core.settings import Settings, with_changes

log = logging.getLogger(__name__)

Listener = Callable[[Settings, Settings], None]  # (새 설정, 이전 설정)


@dataclass(frozen=True)
class UpdateResult:
    settings: Settings  # 보정까지 끝난 현재 설정. 화면은 이 값으로 입력칸을 다시 채운다
    changed: bool  # 실제로 값이 바뀌었는가
    saved: bool  # 파일에 저장했는가 (바뀐 게 없으면 저장할 것이 없으니 True)


class SettingsManager:
    def __init__(self, settings: Settings, save: Callable[[Settings], None] | None = None) -> None:
        self._settings = settings
        self._save = save
        self._listeners: list[Listener] = []

    @property
    def settings(self) -> Settings:
        return self._settings

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """설정이 바뀔 때마다 listener(새 설정, 이전 설정)를 부른다. 구독을 끊는 함수를 돌려준다."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def update(self, changes: Mapping[str, Any]) -> UpdateResult:
        old = self._settings
        new = with_changes(old, changes)
        if new == old:
            return UpdateResult(old, changed=False, saved=True)
        self._settings = new
        saved = True
        if self._save is not None:
            try:
                self._save(new)
            except OSError:
                log.warning("설정을 저장하지 못했습니다.", exc_info=True)
                saved = False
        for listener in list(self._listeners):
            try:
                listener(new, old)
            except Exception:  # 한 곳의 오류가 다른 곳의 반영을 막지 않게 한다
                log.exception("설정 변경을 반영하는 중 오류가 났습니다.")
        return UpdateResult(new, changed=True, saved=saved)
