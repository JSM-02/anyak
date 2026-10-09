"""화면을 바꿀 때 옆으로 미끄러지듯 넘어가는 QStackedWidget.

메뉴 순서대로 오른쪽 메뉴를 고르면 새 화면이 오른쪽에서, 왼쪽 메뉴를 고르면 왼쪽에서 들어온다.
창이 보이지 않거나 Windows의 '애니메이션 효과'가 꺼져 있으면 움직임 없이 바로 바꾼다.
`currentWidget()`/`currentIndex()`는 미끄러지는 동안에도 항상 가려는 화면을 가리킨다.
"""

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation
from PySide6.QtWidgets import QStackedWidget, QWidget

from eyeexercise.platform.win_motion import animations_enabled

SLIDE_MS = 260


class SlideStack(QStackedWidget):
    def __init__(self, animations: Callable[[], bool] = animations_enabled, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._animations = animations
        self._group: QParallelAnimationGroup | None = None
        self._leaving: QWidget | None = None
        self._target = -1

    @property
    def sliding(self) -> bool:
        return self._group is not None

    def currentIndex(self) -> int:
        return self._target if self._group is not None else super().currentIndex()

    def currentWidget(self) -> QWidget:
        return self.widget(self.currentIndex())

    def setCurrentIndex(self, index: int) -> None:
        self._finish()  # 아직 미끄러지는 중이면 먼저 끝낸다
        current = super().currentIndex()
        if index == current or not 0 <= index < self.count():
            return
        if not self.isVisible() or not self._animations():
            super().setCurrentIndex(index)
            return
        self._slide(current, index)

    def _slide(self, old_index: int, new_index: int) -> None:
        old, new = self.widget(old_index), self.widget(new_index)
        width, height = self.width(), self.height()
        direction = 1 if new_index > old_index else -1
        new.setGeometry(0, 0, width, height)
        new.move(direction * width, 0)
        new.show()
        new.raise_()
        group = QParallelAnimationGroup(self)
        for widget, start, end in ((old, 0, -direction * width), (new, direction * width, 0)):
            anim = QPropertyAnimation(widget, b"pos", group)
            anim.setDuration(SLIDE_MS)
            anim.setStartValue(QPoint(start, 0))
            anim.setEndValue(QPoint(end, 0))
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(anim)
        self._group, self._leaving, self._target = group, old, new_index
        group.finished.connect(self._finish)
        group.start()

    def _finish(self) -> None:
        group, leaving, target = self._group, self._leaving, self._target
        if group is None:
            return
        self._group = self._leaving = None
        self._target = -1
        group.stop()
        group.deleteLater()
        super().setCurrentIndex(target)  # 떠나는 화면은 여기서 숨겨진다
        for widget in (leaving, self.widget(target)):
            if widget is not None:
                widget.setGeometry(0, 0, self.width(), self.height())
